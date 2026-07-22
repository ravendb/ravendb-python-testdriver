import os
import unittest
from unittest import TestCase

from ravendb_test_driver import RavenTestDriver

# Path C: attach to a server you run yourself (Docker, testcontainers, shared CI) instead of
# booting the embedded one, so no .NET is needed. Point RAVENDB_TEST_SERVER_URL at a running
# server to run this. It must run in its own process (the driver's server is a process-wide
# singleton), which is exactly how CI invokes it. CI also sets RAVENDB_TEST_REQUIRE_ATTACH=1 so
# a missing URL fails loudly there instead of skipping silently.
SERVER_URL = os.environ.get("RAVENDB_TEST_SERVER_URL")
_REQUIRE = os.environ.get("RAVENDB_TEST_REQUIRE_ATTACH") == "1"


class TestAttachToExternalServer(TestCase):
    def setUp(self):
        if not SERVER_URL:
            message = "set RAVENDB_TEST_SERVER_URL to a running server to run the attach test"
            if _REQUIRE:
                self.fail(message)
            self.skipTest(message)

    def test_attach_gives_isolated_database(self):
        driver = RavenTestDriver()
        with driver.get_document_store() as store:
            self.assertIn(SERVER_URL.rstrip("/"), store.urls[0])
            with store.open_session() as session:
                session.store({"name": "attached"}, "people/1")
                session.save_changes()
            with store.open_session() as session:
                self.assertEqual("attached", session.load("people/1", dict)["name"])
