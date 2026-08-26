import atexit
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import warnings
import webbrowser
from datetime import timedelta
from typing import Optional, Dict, Any, Callable
from urllib.parse import quote

from ravendb import (
    DocumentStore,
    Lazy,
    CreateDatabaseOperation,
    GetStatisticsOperation,
    GetIndexErrorsOperation,
)
from ravendb.documents.indexes.definitions import IndexState
from ravendb.exceptions.cluster import NoLoaderException
from ravendb.exceptions.exceptions import (
    DatabaseDoesNotExistException,
    TimeoutException,
)
from ravendb.exceptions.raven_exceptions import RavenException
from ravendb.primitives.constants import Documents
from ravendb.serverwide.database_record import DatabaseRecord
from ravendb.serverwide.operations.common import DeleteDatabaseOperation
from ravendb_embedded import EmbeddedServer, ServerOptions

from ravendb_test_driver.errors import DriverCloseError
from ravendb_test_driver.options import GetDocumentStoreOptions, TestServerOptions

_LOGGER = logging.getLogger(__name__)

_WAIT_FOR_USER_ENVIRONMENT_VARIABLE = "RAVENDB_TEST_DRIVER_WAIT_FOR_USER"
_UNIQUE_DATABASE_NAMES_ENVIRONMENT_VARIABLE = "RAVENDB_TEST_UNIQUE_DB_NAMES"
_STRICT_LICENSE_ENVIRONMENT_VARIABLE = "RAVENDB_TEST_STRICT_LICENSE"
_FALSY_ENVIRONMENT_VALUES = frozenset({"0", "false", "no", "off"})

_SYNTHETIC_FRAME_NAMES = frozenset({"<module>", "<lambda>", "<listcomp>", "<dictcomp>", "<setcomp>", "<genexpr>"})
_DATABASE_NAME_STEM_MAX_LENGTH = 100


class RavenTestDriver:
    run_in_memory: bool = True

    use_caller_name_for_database: bool = False

    _TEST_SERVER: EmbeddedServer = EmbeddedServer()
    _TEST_SERVER_STORE: Lazy[DocumentStore] = Lazy(lambda: RavenTestDriver._run_server())
    _INDEX = 0
    _INDEX_LOCK = threading.Lock()
    _GLOBAL_SERVER_OPTIONS: Optional[ServerOptions] = None
    _EMPTY_SETTINGS_FILE_NAME: Optional[str] = None
    _EXTERNAL_SERVER_URL: Optional[str] = None
    _EXTERNAL_SERVER_CERT: Optional[str] = None
    _EXTERNAL_SERVER_TRUST_STORE: Optional[str] = None

    def __init__(self) -> None:
        self.disposed = False
        self._document_stores: Dict[DocumentStore, bool] = {}
        self.on_driver_closed: Optional[Callable[[RavenTestDriver], None]] = None

    def __enter__(self) -> "RavenTestDriver":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    @staticmethod
    def _next_index() -> int:
        # Qualified, not cls: 'cls._INDEX += 1' would shadow the counter per subclass.
        with RavenTestDriver._INDEX_LOCK:
            RavenTestDriver._INDEX += 1
            return RavenTestDriver._INDEX

    @staticmethod
    def _remove_empty_settings_file(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass  # already gone, or held by something else

    @staticmethod
    def _get_empty_settings_file() -> str:
        if not RavenTestDriver._EMPTY_SETTINGS_FILE_NAME:
            temp_file = tempfile.NamedTemporaryFile(delete=False, prefix="settings-", suffix=".json")
            temp_file.write(b"{}")
            temp_file.close()
            RavenTestDriver._EMPTY_SETTINGS_FILE_NAME = temp_file.name
            # Registered before the server's own atexit hook, so it runs after it (LIFO).
            atexit.register(RavenTestDriver._remove_empty_settings_file, temp_file.name)
        return RavenTestDriver._EMPTY_SETTINGS_FILE_NAME

    @staticmethod
    def configure_server(options: ServerOptions) -> None:
        if RavenTestDriver._TEST_SERVER_STORE.is_value_created:
            raise RuntimeError(
                "Cannot configure the server after it was started. "
                "Call 'configure_server' before any 'get_document_store'."
            )
        RavenTestDriver._GLOBAL_SERVER_OPTIONS = options

    @staticmethod
    def configure_external_server(
        url: str,
        certificate_pem_path: str = None,
        trust_store_path: str = None,
    ) -> None:
        """Attach to a server you run yourself (no embedded boot, no .NET); still one database per test.

        For HTTPS, pass the client certificate and, when needed, the CA trust store. The equivalent
        environment variables are RAVENDB_TEST_SERVER_URL, RAVENDB_TEST_SERVER_CERT, and
        RAVENDB_TEST_SERVER_CA. Call before the first get_document_store.
        """
        if RavenTestDriver._TEST_SERVER_STORE.is_value_created:
            raise RuntimeError(
                "Cannot configure the server after it was started. "
                "Call 'configure_external_server' before any 'get_document_store'."
            )
        RavenTestDriver._EXTERNAL_SERVER_URL = url
        RavenTestDriver._EXTERNAL_SERVER_CERT = certificate_pem_path
        RavenTestDriver._EXTERNAL_SERVER_TRUST_STORE = trust_store_path

    def get_document_store(
        self,
        options: Optional[GetDocumentStoreOptions] = None,
        database: Optional[str] = None,
    ) -> DocumentStore:
        options = options or GetDocumentStoreOptions()
        name = self._next_database_name(database)
        document_store = self._TEST_SERVER_STORE.value

        database_record = DatabaseRecord(name)
        self.pre_configure_database(database_record)

        create_database_operation = CreateDatabaseOperation(database_record)
        document_store.maintenance.server.send(create_database_operation)

        store = DocumentStore(document_store.urls, name)
        if document_store.certificate_pem_path:
            store.certificate_pem_path = document_store.certificate_pem_path
        if document_store.trust_store_path:
            store.trust_store_path = document_store.trust_store_path

        self.pre_initialize(store)
        store.initialize()

        def __close_event_callback():
            try:
                self._document_stores.pop(store)
            except KeyError:
                return

            # The record's name, not store.database: pre_configure_database may rename it.
            self._delete_test_database(store, database_record.database_name)

        store.add_after_close(__close_event_callback)

        self.setup_database(store)

        if options.wait_for_indexing_timeout is not None:
            self.wait_for_indexing(store, name, options.wait_for_indexing_timeout)

        self._document_stores[store] = True

        return store

    @staticmethod
    def _delete_test_database(store: DocumentStore, database_name: str) -> None:
        """Hard-delete a test database, ignoring the failures that are not the test's problem."""
        try:
            store.maintenance.server.send(DeleteDatabaseOperation(database_name, True))
        except (DatabaseDoesNotExistException, NoLoaderException):
            pass  # already gone, or the cluster has no leader right now
        except RavenException as e:
            # The client maps NoLeaderException under a misspelled key, so it arrives untyped.
            if "NoLeaderException" not in str(e):
                raise

    @classmethod
    def _caller_name(cls, depth: int = 3) -> Optional[str]:
        """The calling test's name, C#'s [CallerMemberName] equivalent.

        sys._getframe, not inspect.stack(): the latter costs milliseconds per call.
        """
        try:
            frame_name = sys._getframe(depth).f_code.co_name
        except ValueError:  # stack is not that deep
            return None

        if frame_name in _SYNTHETIC_FRAME_NAMES:
            return None

        sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", frame_name)[:_DATABASE_NAME_STEM_MAX_LENGTH]
        return sanitized or None

    @staticmethod
    def _environment_flag(name: str) -> bool:
        value = os.environ.get(name)
        if value is None:
            return False
        value = value.strip().lower()
        return bool(value) and value not in _FALSY_ENVIRONMENT_VALUES

    @classmethod
    def _next_database_name(cls, database: Optional[str] = None) -> str:
        stem = database
        if stem is None and cls.use_caller_name_for_database:
            stem = cls._caller_name()

        parts = [stem or "test"]
        if cls._environment_flag(_UNIQUE_DATABASE_NAMES_ENVIRONMENT_VARIABLE):
            # The counter restarts per process, so runners sharing a server would collide.
            parts.append(str(os.getpid()))
        parts.append(str(cls._next_index()))

        return "_".join(parts)

    def pre_initialize(self, document_store: DocumentStore) -> None:
        pass  # empty by design

    def pre_configure_database(self, database_record: DatabaseRecord) -> None:
        pass  # empty by design

    def setup_database(self, document_store: DocumentStore) -> None:
        pass  # empty by design

    @staticmethod
    def wait_for_indexing(
        store: DocumentStore,
        database: Optional[str] = None,
        timeout: Optional[timedelta] = None,
    ) -> None:
        timeout = timeout if timeout is not None else timedelta(seconds=60)  # Default timeout
        admin = store.maintenance.for_database(database)
        start_time = time.monotonic()

        while time.monotonic() - start_time < timeout.total_seconds():
            database_statistics = admin.send(GetStatisticsOperation())

            # A replacement index holds the wait: until the swap lands, queries hit the old one.
            pending = [
                x
                for x in database_statistics.indexes
                if x.state != IndexState.DISABLED
                and (x.stale or x.name.startswith(Documents.Indexing.SIDE_BY_SIDE_INDEX_NAME_PREFIX))
            ]

            if not pending:
                return

            if any(index.state == IndexState.ERROR for index in database_statistics.indexes):
                break

            time.sleep(0.1)

        errors = admin.send(GetIndexErrorsOperation())
        all_index_errors_text = (
            "\n".join(
                f"Index {index_errors.name} ({len(index_errors.errors)} errors):\n"
                + "".join(f"-{error}\n" for error in index_errors.errors)
                for index_errors in errors
            )
            if errors
            else ""
        )

        raise TimeoutException(f"The indexes stayed stale for more than {timeout}. {all_index_errors_text}")

    @staticmethod
    def _is_debugger_attached() -> bool:
        """Used only to make the wait unbounded, never to skip it.

        sys.gettrace() is not consulted: coverage.py would make every run look debugged.
        """
        debugpy = sys.modules.get("debugpy")
        if debugpy is not None:
            try:
                if debugpy.is_client_connected():
                    return True
            except Exception:  # pragma: no cover - debugpy internals
                pass

        pydevd = sys.modules.get("pydevd")
        if pydevd is not None:
            try:
                return pydevd.get_global_debugger() is not None
            except Exception:  # pragma: no cover - pydevd internals
                pass

        return False

    def wait_for_user_to_continue_the_test(
        self,
        store: DocumentStore,
        timeout: Optional[timedelta] = timedelta(minutes=5),
    ) -> None:
        """Open Studio and block until a 'Debug/Done' document shows up in this database.

        Bounded by `timeout` so a call left in committed code fails a CI job fast instead of
        hanging it; pass timeout=None to wait forever. Set RAVENDB_TEST_DRIVER_WAIT_FOR_USER to
        0/false/no/off to skip the wait entirely.
        """
        environment_value = os.environ.get(_WAIT_FOR_USER_ENVIRONMENT_VARIABLE)
        if environment_value is not None and environment_value.strip().lower() in _FALSY_ENVIRONMENT_VALUES:
            return

        if self._is_debugger_attached():
            timeout = None

        database_name_encoded = quote(store.database, safe="")
        documents_page = (
            f"{store.urls[0]}/studio/index.html#databases/documents?&database={database_name_encoded}&withStop=true"
        )

        self.open_browser(documents_page)

        start_time = time.monotonic()
        while True:
            if timeout is not None and time.monotonic() - start_time >= timeout.total_seconds():
                raise TimeoutException(
                    f"No 'Debug/Done' document showed up in '{store.database}' within {timeout}. "
                    "Store a document with that id to continue the test, pass timeout=None to wait "
                    f"forever, or set {_WAIT_FOR_USER_ENVIRONMENT_VARIABLE}=0 to skip this wait."
                )

            time.sleep(0.5)
            with store.open_session() as session:
                # Deleted after the wait, so a later one cannot return on a stale marker.
                if session.advanced.exists("Debug/Done"):
                    session.delete("Debug/Done")
                    session.save_changes()
                    break

    @staticmethod
    def open_browser(url: str) -> None:
        print(url)
        try:
            opened = webbrowser.open(url)
        except Exception as e:
            raise RuntimeError(f"Failed to open a browser at {url}") from e

        if not opened:
            # Headless machines return False rather than raising; the wait still works.
            print("No browser could be opened here; use the URL above.")

    def close(self) -> None:
        if getattr(self, "disposed", False):
            return

        exceptions = []

        try:
            # Snapshot: each store's after-close callback pops itself out of this dict.
            for document_store in list(self._document_stores):
                try:
                    document_store.close()
                except Exception as e:
                    exceptions.append(e)
        finally:
            self.disposed = True

        if self.on_driver_closed:
            # Collected, so a raising callback cannot discard the store-close errors.
            try:
                self.on_driver_closed(self)
            except Exception as e:
                exceptions.append(e)

        if exceptions:
            raise DriverCloseError(exceptions)

    @staticmethod
    def _cleanup_temp_dirs(*dirs: str) -> None:
        for _ in range(30):
            any_failure = False
            for dir_ in dirs:
                if not os.path.exists(dir_):
                    continue
                # rmtree returns None; the directory still being there is the only signal.
                shutil.rmtree(dir_, ignore_errors=True)
                if os.path.exists(dir_):
                    any_failure = True
            if not any_failure:
                return
            time.sleep(0.2)

    @staticmethod
    def _default_server_options() -> ServerOptions:
        return RavenTestDriver._normalize_test_server_options(TestServerOptions())

    @classmethod
    def _normalize_test_server_options(cls, options: ServerOptions) -> ServerOptions:
        """Give any ServerOptions the defaults a test server needs.

        Idempotent, and it never overrides a value the caller set explicitly.
        """
        security = getattr(options, "security", None)
        if security is not None and not security.client_pem_certificate_path:
            raise RavenException(
                "A secured test server needs a client certificate the test client can "
                "authenticate with. Pass client_pem_certificate_path to ServerOptions.secured()."
            )

        if cls._environment_flag(_STRICT_LICENSE_ENVIRONMENT_VARIABLE):
            # C# sets this unconditionally, which makes a licence mandatory to run any suite.
            # Opt-in until that is a product decision; a caller who set it keeps it.
            options.licensing.throw_on_invalid_or_missing_license = True

        # A local copy: the caller's list is theirs, and there is more than one writer now.
        command_line_args = list(options.command_line_args)

        settings_file = cls._get_empty_settings_file()
        if settings_file not in command_line_args:
            command_line_args[:0] = ["-c", settings_file]

        if cls.run_in_memory and not any(arg.startswith("--RunInMemory") for arg in command_line_args):
            command_line_args.append("--RunInMemory=true")

        options.command_line_args = command_line_args

        # The embedded default sits inside the installed package. Logs follow the data directory.
        default_data_directory = getattr(ServerOptions, "_DEFAULT_DATA_DIRECTORY", None)
        if default_data_directory is not None and options.data_directory == default_data_directory:
            data_directory = tempfile.mkdtemp(prefix="ravendb-test-driver-")
            options.data_directory = data_directory
            atexit.register(cls._cleanup_temp_dirs, data_directory)
            _LOGGER.info("Test server data and logs redirected to %s", data_directory)

        return options

    @classmethod
    def _resolve_external_server_url(cls) -> Optional[str]:
        """Explicit configuration beats the environment, which could otherwise redirect a suite
        onto a server where the driver creates and hard-deletes databases.
        """
        if cls._EXTERNAL_SERVER_URL:
            return cls._EXTERNAL_SERVER_URL

        environment_url = os.environ.get("RAVENDB_TEST_SERVER_URL")
        if environment_url and cls._GLOBAL_SERVER_OPTIONS is not None:
            warnings.warn(
                f"Ignoring RAVENDB_TEST_SERVER_URL={environment_url!r} because configure_server() "
                "was called explicitly. Drop that call to attach to the server from the "
                "environment; the driver creates and hard-deletes databases on whichever server "
                "it ends up using.",
                stacklevel=2,
            )
            return None

        return environment_url

    @classmethod
    def _run_server(cls) -> DocumentStore:
        external_url = cls._resolve_external_server_url()
        if external_url:
            # Attach to an existing server; do not boot the embedded one (no .NET needed).
            certificate = cls._EXTERNAL_SERVER_CERT or os.environ.get("RAVENDB_TEST_SERVER_CERT")
            trust_store = cls._EXTERNAL_SERVER_TRUST_STORE or os.environ.get("RAVENDB_TEST_SERVER_CA")
            if external_url.lower().startswith("https") and not certificate:
                raise RavenException(
                    f"Attaching to a secured server ({external_url}) needs a client certificate; pass "
                    "configure_external_server(url, certificate_pem_path=...) or set RAVENDB_TEST_SERVER_CERT."
                )
            store = DocumentStore(external_url, None)
            if certificate:
                store.certificate_pem_path = certificate
            if trust_store:
                store.trust_store_path = trust_store
            store.initialize()
            return store

        try:
            options = cls._GLOBAL_SERVER_OPTIONS or TestServerOptions()
            cls._normalize_test_server_options(options)
        except Exception as e:
            # Only option preparation is wrapped; start_server raises the embedded layer's error.
            raise RavenException(f"Unable to prepare the test server options: {e}", e) from e

        cls._TEST_SERVER.start_server(options)

        url = cls._TEST_SERVER.get_server_uri()

        store = DocumentStore(url, None)

        # Without this the test client cannot authenticate to the secured server it just booted.
        if cls._TEST_SERVER.client_pem_certificate_path:
            store.certificate_pem_path = cls._TEST_SERVER.client_pem_certificate_path
        if cls._TEST_SERVER.trust_store_path:
            store.trust_store_path = cls._TEST_SERVER.trust_store_path

        store.initialize()

        return store

    @classmethod
    def stop_test_server(cls) -> None:
        """Close the shared test server and its server-level store.

        Nothing else closes them, so without this the cost lands at interpreter exit.
        Idempotent, and the server can be started again afterwards.
        """
        lazy = cls._TEST_SERVER_STORE
        if lazy.is_value_created:
            try:
                lazy.value.close()
            finally:
                cls._TEST_SERVER_STORE = Lazy(lambda: RavenTestDriver._run_server())

        cls._TEST_SERVER.close()

    @classmethod
    def reset_server_configuration(cls) -> None:
        """Forget configure_server / configure_external_server, without touching the server."""
        cls._GLOBAL_SERVER_OPTIONS = None
        cls._EXTERNAL_SERVER_URL = None
        cls._EXTERNAL_SERVER_CERT = None
        cls._EXTERNAL_SERVER_TRUST_STORE = None

    # Never meant to be public (private in the JVM driver, absent in C#). Kept for one release.

    @staticmethod
    def _deprecated_alias(old: str, new: str) -> None:
        warnings.warn(
            f"RavenTestDriver.{old}() is internal and will be removed in a future release; "
            f"use {new}() if you really need it.",
            DeprecationWarning,
            stacklevel=3,
        )

    @classmethod
    def run_server(cls) -> DocumentStore:
        cls._deprecated_alias("run_server", "_run_server")
        return cls._run_server()

    @staticmethod
    def default_server_options() -> ServerOptions:
        RavenTestDriver._deprecated_alias("default_server_options", "_default_server_options")
        return RavenTestDriver._default_server_options()

    @staticmethod
    def cleanup_temp_dirs(*dirs: str) -> None:
        RavenTestDriver._deprecated_alias("cleanup_temp_dirs", "_cleanup_temp_dirs")
        RavenTestDriver._cleanup_temp_dirs(*dirs)
