"""Error paths: message wording, swallowed teardown failures, and browser launch failures.

All hermetic: no server is started.
"""

import io
import webbrowser
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from ravendb import Lazy
from ravendb.exceptions.cluster import NoLoaderException
from ravendb.exceptions.exceptions import DatabaseDoesNotExistException
from ravendb.exceptions.raven_exceptions import RavenException
from ravendb_embedded import ServerOptions

from ravendb_test_driver import RavenTestDriver


class _StoreThatRaises:
    def __init__(self, error):
        self.sent = []

        def send(operation):
            self.sent.append(operation)
            if error is not None:
                raise error

        self.maintenance = SimpleNamespace(server=SimpleNamespace(send=send))


class TestDeleteTestDatabase(TestCase):
    def test_deletes_the_database_it_was_given(self):
        store = _StoreThatRaises(None)

        RavenTestDriver._delete_test_database(store, "test_1")

        self.assertEqual(1, len(store.sent))

    def test_a_database_that_is_already_gone_is_not_an_error(self):
        RavenTestDriver._delete_test_database(_StoreThatRaises(DatabaseDoesNotExistException("gone")), "test_1")

    def test_a_typed_no_leader_failure_is_ignored(self):
        RavenTestDriver._delete_test_database(_StoreThatRaises(NoLoaderException("no leader")), "test_1")

    def test_an_untyped_no_leader_failure_is_ignored(self):
        # The client maps the server's NoLeaderException under a misspelled key, so today a real
        # no-leader failure arrives as a plain RavenException carrying the name in its message.
        error = RavenException("Raven.Client.Exceptions.Cluster.NoLeaderException: no leader elected")

        RavenTestDriver._delete_test_database(_StoreThatRaises(error), "test_1")

    def test_any_other_failure_still_propagates(self):
        with self.assertRaises(RavenException):
            RavenTestDriver._delete_test_database(_StoreThatRaises(RavenException("disk on fire")), "test_1")


class TestConfigurationMessages(TestCase):
    def setUp(self):
        started = Lazy(lambda: object())
        started.value  # force creation, so the driver believes the server is already up
        self.addCleanup(setattr, RavenTestDriver, "_TEST_SERVER_STORE", RavenTestDriver._TEST_SERVER_STORE)
        RavenTestDriver._TEST_SERVER_STORE = started

    def test_configure_server_names_the_python_api(self):
        # The message used to carry the Java driver's camelCase names.
        with self.assertRaises(RuntimeError) as caught:
            RavenTestDriver.configure_server(ServerOptions())

        message = str(caught.exception)
        self.assertIn("configure_server", message)
        self.assertIn("get_document_store", message)
        self.assertNotIn("configureServer", message)
        self.assertNotIn("getDocumentStore", message)

    def test_configure_external_server_names_the_python_api(self):
        with self.assertRaises(RuntimeError) as caught:
            RavenTestDriver.configure_external_server("http://localhost:8080")

        message = str(caught.exception)
        self.assertIn("configure_external_server", message)
        self.assertIn("get_document_store", message)


class TestOpenBrowser(TestCase):
    def test_a_launch_failure_names_the_url_and_keeps_the_cause(self):
        cause = OSError("no display")

        with patch.object(webbrowser, "open", side_effect=cause):
            with self.assertRaises(RuntimeError) as caught:
                with redirect_stdout(io.StringIO()):
                    RavenTestDriver().open_browser("http://127.0.0.1:8080/studio")

        self.assertIn("http://127.0.0.1:8080/studio", str(caught.exception))
        self.assertIs(cause, caught.exception.__cause__)

    def test_a_headless_machine_is_reported_rather_than_ignored(self):
        # webbrowser.open returns False instead of raising when there is no browser.
        output = io.StringIO()

        with patch.object(webbrowser, "open", return_value=False):
            with redirect_stdout(output):
                RavenTestDriver().open_browser("http://127.0.0.1:8080/studio")

        self.assertIn("No browser could be opened", output.getvalue())

    def test_open_browser_can_be_overridden(self):
        # It is the driver's override hook, the analogue of C#'s protected virtual OpenBrowser.
        opened = []

        class _Driver(RavenTestDriver):
            @staticmethod
            def open_browser(url):
                opened.append(url)

        _Driver().open_browser("http://127.0.0.1:8080/studio")

        self.assertEqual(["http://127.0.0.1:8080/studio"], opened)
