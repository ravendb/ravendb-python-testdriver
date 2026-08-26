"""Test-server option normalization, server selection precedence, and shared-server teardown.

Everything except the last class is hermetic: no server is started, so these run anywhere.
"""

import os
import tempfile
import warnings
from datetime import timedelta
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from ravendb.exceptions.exceptions import TimeoutException
from ravendb.exceptions.raven_exceptions import RavenException
from ravendb_embedded import ServerOptions

from ravendb_test_driver import DriverCloseError, RavenTestDriver, TestServerOptions


def _run_in_memory_args(options):
    return [arg for arg in options.command_line_args if arg.startswith("--RunInMemory")]


class TestOptionNormalization(TestCase):
    def test_applies_test_defaults_to_a_plain_server_options(self):
        options = RavenTestDriver._normalize_test_server_options(ServerOptions())

        self.assertEqual(["--RunInMemory=true"], _run_in_memory_args(options))
        self.assertEqual("-c", options.command_line_args[0])
        self.assertTrue(options.command_line_args[1].endswith(".json"))

    def test_is_idempotent(self):
        options = TestServerOptions()
        RavenTestDriver._normalize_test_server_options(options)
        first_pass = list(options.command_line_args)
        data_directory = options.data_directory

        RavenTestDriver._normalize_test_server_options(options)

        self.assertEqual(first_pass, options.command_line_args)
        self.assertEqual(data_directory, options.data_directory)

    def test_keeps_a_caller_supplied_run_in_memory_value(self):
        options = ServerOptions()
        options.command_line_args.append("--RunInMemory=false")

        RavenTestDriver._normalize_test_server_options(options)

        self.assertEqual(["--RunInMemory=false"], _run_in_memory_args(options))

    def test_run_in_memory_can_be_switched_off_on_the_driver(self):
        class _OnDiskDriver(RavenTestDriver):
            run_in_memory = False

        options = _OnDiskDriver._normalize_test_server_options(ServerOptions())

        self.assertEqual([], _run_in_memory_args(options))

    def test_does_not_mutate_the_callers_argument_list(self):
        options = ServerOptions()
        caller_list = options.command_line_args

        RavenTestDriver._normalize_test_server_options(options)

        self.assertEqual([], caller_list)
        self.assertIsNot(caller_list, options.command_line_args)

    def test_redirects_the_packaged_default_data_directory(self):
        options = ServerOptions()
        packaged_default = options.data_directory

        RavenTestDriver._normalize_test_server_options(options)

        self.assertNotEqual(packaged_default, options.data_directory)
        # Logs follow the data directory, so one temp root covers both.
        self.assertTrue(options.logs_path.startswith(options.data_directory))

    def test_leaves_an_explicit_data_directory_alone(self):
        options = ServerOptions()
        options.data_directory = os.path.join(os.getcwd(), "chosen-by-the-user")

        RavenTestDriver._normalize_test_server_options(options)

        self.assertTrue(options.data_directory.endswith("chosen-by-the-user"))

    def test_rejects_a_secured_server_the_client_cannot_authenticate_to(self):
        options = ServerOptions()
        options.secured("server.pfx")

        with self.assertRaisesRegex(RavenException, "client certificate"):
            RavenTestDriver._normalize_test_server_options(options)


class TestStrictLicenseOptIn(TestCase):
    def setUp(self):
        previous = os.environ.get("RAVENDB_TEST_STRICT_LICENSE")
        if previous is None:
            self.addCleanup(os.environ.pop, "RAVENDB_TEST_STRICT_LICENSE", None)
        else:
            self.addCleanup(os.environ.__setitem__, "RAVENDB_TEST_STRICT_LICENSE", previous)

    def test_is_off_by_default(self):
        os.environ.pop("RAVENDB_TEST_STRICT_LICENSE", None)

        options = RavenTestDriver._normalize_test_server_options(TestServerOptions())

        self.assertFalse(options.licensing.throw_on_invalid_or_missing_license)

    def test_switched_on_by_the_environment(self):
        os.environ["RAVENDB_TEST_STRICT_LICENSE"] = "1"

        options = RavenTestDriver._normalize_test_server_options(TestServerOptions())

        self.assertTrue(options.licensing.throw_on_invalid_or_missing_license)

    def test_a_caller_who_set_it_keeps_it(self):
        os.environ.pop("RAVENDB_TEST_STRICT_LICENSE", None)
        options = TestServerOptions()
        options.licensing.throw_on_invalid_or_missing_license = True

        RavenTestDriver._normalize_test_server_options(options)

        self.assertTrue(options.licensing.throw_on_invalid_or_missing_license)


class TestServerSelectionPrecedence(TestCase):
    def setUp(self):
        self.addCleanup(setattr, RavenTestDriver, "_GLOBAL_SERVER_OPTIONS", RavenTestDriver._GLOBAL_SERVER_OPTIONS)
        self.addCleanup(setattr, RavenTestDriver, "_EXTERNAL_SERVER_URL", RavenTestDriver._EXTERNAL_SERVER_URL)
        previous_url = os.environ.get("RAVENDB_TEST_SERVER_URL")
        if previous_url is None:
            self.addCleanup(os.environ.pop, "RAVENDB_TEST_SERVER_URL", None)
        else:
            self.addCleanup(os.environ.__setitem__, "RAVENDB_TEST_SERVER_URL", previous_url)

    def test_configure_external_server_wins_over_the_environment(self):
        RavenTestDriver._GLOBAL_SERVER_OPTIONS = None
        RavenTestDriver._EXTERNAL_SERVER_URL = "http://from-the-api:8080"
        os.environ["RAVENDB_TEST_SERVER_URL"] = "http://from-the-environment:8080"

        self.assertEqual("http://from-the-api:8080", RavenTestDriver._resolve_external_server_url())

    def test_environment_is_used_when_nothing_was_configured(self):
        RavenTestDriver._GLOBAL_SERVER_OPTIONS = None
        RavenTestDriver._EXTERNAL_SERVER_URL = None
        os.environ["RAVENDB_TEST_SERVER_URL"] = "http://from-the-environment:8080"

        self.assertEqual("http://from-the-environment:8080", RavenTestDriver._resolve_external_server_url())

    def test_configure_server_wins_over_the_environment_and_warns(self):
        # The environment used to silently redirect a suite pinned to the embedded server onto
        # someone else's, where the driver then creates and hard-deletes databases.
        RavenTestDriver._EXTERNAL_SERVER_URL = None
        RavenTestDriver._GLOBAL_SERVER_OPTIONS = TestServerOptions()
        os.environ["RAVENDB_TEST_SERVER_URL"] = "http://from-the-environment:8080"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            resolved = RavenTestDriver._resolve_external_server_url()

        self.assertIsNone(resolved)
        self.assertEqual(1, len(caught))
        self.assertIn("configure_server", str(caught[0].message))


class _FakeSession:
    def __init__(self, exists):
        self.advanced = SimpleNamespace(exists=lambda key: exists)
        self.deleted = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def delete(self, key):
        self.deleted.append(key)

    def save_changes(self):
        pass


class _FakeStore:
    def __init__(self, exists=False):
        self.database = "test_1"
        self.urls = ["http://127.0.0.1:8080"]
        self.sessions = []
        self._exists = exists

    def open_session(self):
        session = _FakeSession(self._exists)
        self.sessions.append(session)
        return session


class _SilentDriver(RavenTestDriver):
    opened = []

    @staticmethod
    def open_browser(url: str) -> None:
        _SilentDriver.opened.append(url)


class TestWaitForUserToContinueTheTest(TestCase):
    def setUp(self):
        _SilentDriver.opened = []
        previous = os.environ.get("RAVENDB_TEST_DRIVER_WAIT_FOR_USER")
        if previous is None:
            self.addCleanup(os.environ.pop, "RAVENDB_TEST_DRIVER_WAIT_FOR_USER", None)
        else:
            self.addCleanup(os.environ.__setitem__, "RAVENDB_TEST_DRIVER_WAIT_FOR_USER", previous)

    def test_environment_kill_switch_skips_the_wait_entirely(self):
        os.environ["RAVENDB_TEST_DRIVER_WAIT_FOR_USER"] = "0"
        store = _FakeStore()

        _SilentDriver().wait_for_user_to_continue_the_test(store)

        self.assertEqual([], _SilentDriver.opened)
        self.assertEqual([], store.sessions)

    def test_times_out_instead_of_hanging_a_ci_job(self):
        store = _FakeStore(exists=False)

        with self.assertRaisesRegex(TimeoutException, "Debug/Done"):
            _SilentDriver().wait_for_user_to_continue_the_test(store, timeout=timedelta(milliseconds=1))

        self.assertEqual(1, len(_SilentDriver.opened))

    def test_deletes_the_marker_and_returns(self):
        store = _FakeStore(exists=True)

        _SilentDriver().wait_for_user_to_continue_the_test(store, timeout=timedelta(seconds=5))

        self.assertEqual(["Debug/Done"], store.sessions[-1].deleted)


class TestDriverCloseError(TestCase):
    def test_a_raising_callback_is_collected_not_swallowed(self):
        driver = RavenTestDriver()

        def explode(_):
            raise ValueError("callback blew up")

        driver.on_driver_closed = explode

        with self.assertRaises(DriverCloseError) as caught:
            driver.close()

        self.assertEqual(1, len(caught.exception.exceptions))
        self.assertIsInstance(caught.exception.exceptions[0], ValueError)
        # Subclasses RuntimeError, so existing handlers keep working.
        self.assertIsInstance(caught.exception, RuntimeError)


class TestDeprecatedHelperAliases(TestCase):
    def test_default_server_options_alias_still_works(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            options = RavenTestDriver.default_server_options()

        self.assertEqual(["--RunInMemory=true"], _run_in_memory_args(options))
        self.assertEqual(1, len(caught))
        self.assertIs(DeprecationWarning, caught[0].category)
        self.assertIn("_default_server_options", str(caught[0].message))

    def test_run_server_alias_still_works(self):
        with patch.object(RavenTestDriver, "_run_server", return_value="store") as run_server:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = RavenTestDriver.run_server()

        self.assertEqual("store", result)
        self.assertEqual(1, run_server.call_count)
        self.assertIs(DeprecationWarning, caught[0].category)
        self.assertIn("_run_server", str(caught[0].message))

    def test_cleanup_temp_dirs_alias_still_works(self):
        directory = tempfile.mkdtemp()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            RavenTestDriver.cleanup_temp_dirs(directory)

        self.assertFalse(os.path.exists(directory))
        self.assertIs(DeprecationWarning, caught[0].category)


class TestSharedServerTeardown(TestCase):
    """Runs last on purpose: it stops the server the rest of the suite shares."""

    def test_stop_test_server_is_idempotent_and_the_server_comes_back(self):
        if RavenTestDriver._EXTERNAL_SERVER_URL or os.environ.get("RAVENDB_TEST_SERVER_URL"):
            self.skipTest("attach mode: the driver does not own the server")

        with RavenTestDriver() as driver:
            with driver.get_document_store():
                pass

        RavenTestDriver.stop_test_server()
        RavenTestDriver.stop_test_server()

        self.assertFalse(RavenTestDriver._TEST_SERVER_STORE.is_value_created)

        with RavenTestDriver() as driver:
            with driver.get_document_store() as store:
                with store.open_session() as session:
                    session.store({"name": "after restart"}, "people/1")
                    session.save_changes()

        RavenTestDriver.stop_test_server()
