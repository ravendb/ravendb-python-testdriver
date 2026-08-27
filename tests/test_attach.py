"""Attach path: the driver talks to a server it does not own and does not boot.

Where the server comes from, in order:
  1. RAVENDB_TEST_SERVER_URL, which is how CI runs this with no .NET installed at all.
  2. A second embedded server this module starts itself, so the attach path is covered on a
     developer machine without Docker. That fallback needs .NET, which the attach mode itself
     does not; only the URL is borrowed from it.
Skipped when neither is available, unless RAVENDB_TEST_REQUIRE_ATTACH=1 (CI) makes it fail loudly.
"""

import os
from unittest import TestCase

from ravendb_embedded import EmbeddedServer

from ravendb_test_driver import RavenTestDriver, TestServerOptions
from tests.support import isolate_environment, reset_driver

_REQUIRE = os.environ.get("RAVENDB_TEST_REQUIRE_ATTACH") == "1"


class TestAttachToExternalServer(TestCase):
    server_url = None
    _owned_server = None

    @classmethod
    def setUpClass(cls):
        cls.server_url = os.environ.get("RAVENDB_TEST_SERVER_URL")
        if cls.server_url:
            return

        if _REQUIRE:
            raise AssertionError("set RAVENDB_TEST_SERVER_URL to a running server to run the attach test")

        reset_driver()
        try:
            cls._owned_server = EmbeddedServer()
            cls._owned_server.start_server(RavenTestDriver._normalize_test_server_options(TestServerOptions()))
            cls.server_url = cls._owned_server.get_server_uri()
        except Exception as e:  # no .NET runtime, or the server refused to start
            cls._owned_server = None
            raise TestCase.skipTest(cls, f"no server to attach to: {e}") from e

    @classmethod
    def tearDownClass(cls):
        if cls._owned_server is not None:
            cls._owned_server.close()
            cls._owned_server = None

    def setUp(self):
        isolate_environment(self)
        reset_driver()
        self.addCleanup(reset_driver)
        os.environ["RAVENDB_TEST_SERVER_URL"] = self.server_url

    def test_attach_gives_isolated_database(self):
        driver = RavenTestDriver()
        with driver.get_document_store() as store:
            self.assertIn(self.server_url.rstrip("/"), store.urls[0])
            with store.open_session() as session:
                session.store({"name": "attached"}, "people/1")
                session.save_changes()
            with store.open_session() as session:
                self.assertEqual("attached", session.load("people/1", dict)["name"])

    def test_the_attached_server_keeps_running_when_the_driver_closes(self):
        # The driver owns the databases it creates, never the server somebody else runs.
        first = RavenTestDriver()
        with first.get_document_store() as store:
            database = store.database

        RavenTestDriver.stop_test_server()

        second = RavenTestDriver()
        with second.get_document_store() as store:
            self.assertNotEqual(database, store.database)
            self.assertIn(self.server_url.rstrip("/"), store.urls[0])
