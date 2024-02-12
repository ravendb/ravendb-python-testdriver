import atexit
import os
import shutil
import tempfile
import time
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
from ravendb.exceptions.exceptions import (
    DatabaseDoesNotExistException,
    TimeoutException,
)
from ravendb.exceptions.raven_exceptions import RavenException
from ravendb.primitives.constants import Documents
from ravendb.serverwide.database_record import DatabaseRecord
from ravendb.serverwide.operations.common import DeleteDatabaseOperation
from ravendb_embedded import EmbeddedServer, ServerOptions
from ravendb_embedded.raven_server_runner import CommandLineArgumentEscaper

from ravendb_test_driver.options import GetDocumentStoreOptions


class RavenTestDriver:
    _TEST_SERVER: EmbeddedServer = EmbeddedServer()
    _TEST_SERVER_STORE: Lazy[DocumentStore] = Lazy(lambda: RavenTestDriver.run_server())
    _INDEX = 0
    _GLOBAL_SERVER_OPTIONS: Optional[ServerOptions] = None
    _EMPTY_SETTINGS_FILE_NAME: Optional[str] = None

    def __init__(self) -> None:
        self.disposed = False
        self._document_stores: Dict[DocumentStore, bool] = {}
        self.on_driver_closed: Optional[Callable[[RavenTestDriver], None]] = None

    def __enter__(self) -> "RavenTestDriver":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    @staticmethod
    def _get_empty_settings_file() -> str:
        if not RavenTestDriver._EMPTY_SETTINGS_FILE_NAME:
            temp_file = tempfile.NamedTemporaryFile(delete=False, prefix="settings-", suffix=".json")
            temp_file.write(b"{}")
            temp_file.close()
            RavenTestDriver._EMPTY_SETTINGS_FILE_NAME = temp_file.name
        return RavenTestDriver._EMPTY_SETTINGS_FILE_NAME

    @staticmethod
    def configure_server(options: ServerOptions) -> None:
        if RavenTestDriver._TEST_SERVER_STORE.is_value_created:
            raise RuntimeError(
                "Cannot configure server after it was started. "
                "Please call 'configureServer' method before any 'getDocumentStore' is called."
            )
        RavenTestDriver._GLOBAL_SERVER_OPTIONS = options

    def get_document_store(
        self,
        options: Optional[GetDocumentStoreOptions] = None,
        database: Optional[str] = None,
    ) -> DocumentStore:
        database = database or "test"
        options = options or GetDocumentStoreOptions()
        self._INDEX += 1
        name = f"{database}_{self._INDEX}"
        document_store = self._TEST_SERVER_STORE.value

        create_database_operation = CreateDatabaseOperation(DatabaseRecord(name))
        document_store.maintenance.server.send(create_database_operation)

        store = DocumentStore(document_store.urls, name)

        self.pre_initialize(store)
        store.initialize()

        def __close_event_callback():
            try:
                self._document_stores.pop(store)
            except KeyError:
                return

            try:
                store.maintenance.server.send(DeleteDatabaseOperation(store.database, True))
            except DatabaseDoesNotExistException:
                pass  # ignore

        store.add_after_close(__close_event_callback)

        self.setup_database(store)

        if options.wait_for_indexing_timeout:
            self.wait_for_indexing(store, name, options.wait_for_indexing_timeout)

        self._document_stores[store] = True

        return store

    def pre_initialize(self, document_store: DocumentStore) -> None:
        pass  # empty by design

    def setup_database(self, document_store: DocumentStore) -> None:
        pass  # empty by design

    @staticmethod
    def wait_for_indexing(
        store: DocumentStore,
        database: Optional[str] = None,
        timeout: Optional[timedelta] = None,
    ) -> None:
        database = database or None
        timeout = timeout or timedelta(seconds=60)  # Default timeout
        admin = store.maintenance.for_database(database)
        start_time = time.monotonic()

        while time.monotonic() - start_time < timeout.total_seconds():
            database_statistics = admin.send(GetStatisticsOperation())

            indexes = [
                x
                for x in database_statistics.indexes
                if x.state != IndexState.DISABLED
                and not x.stale
                and not x.name.startswith(Documents.Indexing.SIDE_BY_SIDE_INDEX_NAME_PREFIX)
            ]

            if all(indexes):
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

        raise TimeoutException(f"The indexes stayed stale for more than {timeout} seconds. {all_index_errors_text}")

    def wait_for_user_to_continue_the_test(self, store: DocumentStore) -> None:
        database_name_encoded = quote(store.database, safe="")
        documents_page = (
            f"{store.urls[0]}/studio/index.html#databases/documents?&database={database_name_encoded}&withStop=true"
        )

        self.open_browser(documents_page)

        while True:
            time.sleep(0.5)
            with store.open_session() as session:
                if session.load("Debug/Done", dict):
                    break

    @staticmethod
    def open_browser(url: str) -> None:
        print(url)
        try:
            webbrowser.open(url)
        except Exception as e:
            raise RuntimeError() from e

    def close(self) -> None:
        if getattr(self, "disposed", False):
            return

        exceptions = []

        for document_store in self._document_stores:
            try:
                document_store.close()
            except Exception as e:
                exceptions.append(e)

        self.disposed = True

        if self.on_driver_closed:
            self.on_driver_closed(self)

        if exceptions:
            raise RuntimeError(", ".join(map(str, exceptions)))

    @staticmethod
    def cleanup_temp_dirs(*dirs: str) -> None:
        try:
            for i in range(30):
                any_failure = False
                for dir_ in dirs:
                    if os.path.exists(dir_):
                        if not shutil.rmtree(dir_, ignore_errors=True):
                            any_failure = True
                if not any_failure:
                    return
                time.sleep(0.2)
        except Exception:
            pass

    @staticmethod
    def default_server_options() -> ServerOptions:
        options = ServerOptions()

        data_dir = tempfile.mkdtemp()
        logs_dir = tempfile.mkdtemp()

        options.data_directory = data_dir
        options.logs_path = logs_dir

        def cleanup_temp_dirs() -> None:
            RavenTestDriver.cleanup_temp_dirs(data_dir, logs_dir)

        atexit.register(cleanup_temp_dirs)

        return options

    @classmethod
    def run_server(cls) -> DocumentStore:
        try:
            options = RavenTestDriver._GLOBAL_SERVER_OPTIONS or RavenTestDriver.default_server_options()

            command_line_args = options.command_line_args

            command_line_args.insert(0, "-c")
            command_line_args.insert(
                1,
                CommandLineArgumentEscaper.escape_single_arg(RavenTestDriver._get_empty_settings_file()),
            )
        except Exception as e:
            raise RavenException(f"Unable to start server: {e}")

        cls._TEST_SERVER.start_server(options)

        url = cls._TEST_SERVER.get_server_uri()

        store = DocumentStore(url, None)

        store.initialize()

        return store
