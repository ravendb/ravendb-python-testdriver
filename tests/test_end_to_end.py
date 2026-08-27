"""End-to-end checks against a real embedded server.

The unit tests elsewhere pin behavior with fakes; these boot an actual RavenDB server and assert
on what the server, the filesystem and the process left behind. Everything here is skipped when
the suite is pointed at a server the driver does not own.
"""

import glob
import os
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import TestCase, skipIf

from ravendb import GetDatabaseNamesOperation
from ravendb.documents.indexes.abstract_index_creation_tasks import AbstractIndexCreationTask

from ravendb_test_driver import GetDocumentStoreOptions, RavenTestDriver, TestServerOptions
from tests.support import attach_mode_is_active, certificates, isolate_environment, reset_driver

skip_without_own_server = skipIf(attach_mode_is_active(), "attach mode: the driver does not own the server")


def _database_names():
    store = RavenTestDriver._TEST_SERVER_STORE.value
    return store.maintenance.server.send(GetDatabaseNamesOperation(0, 1000))


class Person:
    def __init__(self, Id=None, name=None):
        self.Id = Id
        self.name = name


@skip_without_own_server
class TestDatabaseLifecycle(TestCase):
    def test_closing_a_store_deletes_its_database_on_the_server(self):
        driver = RavenTestDriver()
        store = driver.get_document_store()
        database = store.database

        self.assertIn(database, _database_names())

        store.close()

        self.assertNotIn(database, _database_names())
        driver.close()

    def test_closing_the_driver_deletes_databases_of_stores_left_open(self):
        # The contract the README advertises: whatever you forget to close, the driver cleans up.
        driver = RavenTestDriver()
        first = driver.get_document_store().database
        second = driver.get_document_store().database

        self.assertIn(first, _database_names())
        self.assertIn(second, _database_names())

        driver.close()

        names = _database_names()
        self.assertNotIn(first, names)
        self.assertNotIn(second, names)


@skip_without_own_server
class TestDatabaseNamingAgainstServer(TestCase):
    def setUp(self):
        self.addCleanup(setattr, RavenTestDriver, "use_caller_name_for_database", False)
        isolate_environment(self)

    def test_caller_name_and_process_id_reach_the_created_database(self):
        RavenTestDriver.use_caller_name_for_database = True
        os.environ["RAVENDB_TEST_UNIQUE_DB_NAMES"] = "1"

        with RavenTestDriver() as driver:
            with driver.get_document_store() as store:
                self.assertTrue(
                    store.database.startswith(
                        f"test_caller_name_and_process_id_reach_the_created_database_{os.getpid()}_"
                    ),
                    store.database,
                )
                # The server really has a database under that generated name.
                self.assertIn(store.database, _database_names())


@skip_without_own_server
class TestInMemoryStorage(TestCase):
    def test_no_database_files_are_written_to_disk(self):
        reset_driver()
        self.addCleanup(reset_driver)

        with tempfile.TemporaryDirectory() as directory:
            options = TestServerOptions()
            options.data_directory = directory
            RavenTestDriver.configure_server(options)

            with RavenTestDriver() as driver:
                with driver.get_document_store() as store:
                    with store.open_session() as session:
                        for i in range(100):
                            session.store(Person(name=f"person-{i}"), f"people/{i}")
                        session.save_changes()

                written = [str(path.relative_to(directory)) for path in Path(directory).rglob("*") if path.is_file()]

            # Only the server log survives; the storage engine never touched this directory.
            self.assertTrue(written, "expected at least the server log")
            self.assertEqual(
                [], [name for name in written if name.endswith((".voron", ".journal", ".buffers"))], written
            )
            self.assertEqual([], [name for name in written if not name.startswith("Logs")], written)


@skip_without_own_server
class TestSecuredEmbeddedServer(TestCase):
    def test_driver_authenticates_to_a_secured_embedded_server(self):
        # Regression: the driver used to build its stores without the client certificate the
        # embedded server was started with, so a secured embedded server was unusable.
        reset_driver()
        self.addCleanup(reset_driver)

        with tempfile.TemporaryDirectory() as directory:
            server_pfx, client_pem, ca_certificate = certificates(directory)
            options = TestServerOptions()
            options.secured(server_pfx, client_pem, ca_certificate_path=ca_certificate)
            RavenTestDriver.configure_server(options)

            with RavenTestDriver() as driver:
                with driver.get_document_store() as store:
                    self.assertTrue(store.urls[0].startswith("https://"), store.urls)
                    self.assertEqual(client_pem, store.certificate_pem_path)

                    with store.open_session() as session:
                        session.store(Person(name="secured"), "people/1")
                        session.save_changes()

                    with store.open_session() as session:
                        self.assertEqual("secured", session.load("people/1", Person).name)


@skip_without_own_server
class TestWaitForIndexingOption(TestCase):
    def test_a_zero_wait_for_indexing_timeout_still_waits(self):
        # `if options.wait_for_indexing_timeout:` skipped the wait entirely for timedelta(0).
        recorded = []

        class _RecordingDriver(RavenTestDriver):
            @staticmethod
            def wait_for_indexing(store, database=None, timeout=None):
                recorded.append(timeout)

        with _RecordingDriver() as driver:
            with driver.get_document_store(GetDocumentStoreOptions.with_timeout(timedelta(0))):
                pass

        self.assertEqual([timedelta(0)], recorded)


class People_ByName(AbstractIndexCreationTask):
    def __init__(self):
        super().__init__()
        self.map = "from p in docs.People select new { p.name }"


class _SeedingDriver(RavenTestDriver):
    def setup_database(self, store) -> None:
        store.execute_index(People_ByName())
        with store.open_session() as session:
            session.store(Person(name="Seeded"), "people/1")
            session.save_changes()


@skip_without_own_server
class TestSeedingAndIndexing(TestCase):
    def test_seeded_data_is_queryable_through_a_real_index(self):
        # wait_for_indexing is unit-tested against canned statistics; this proves it against a
        # real indexer, on an in-memory server, through setup_database.
        with _SeedingDriver() as driver:
            with driver.get_document_store() as store:
                driver.wait_for_indexing(store)

                with store.open_session() as session:
                    hits = list(session.query_index_type(People_ByName, Person).where_equals("name", "Seeded"))

                self.assertEqual(1, len(hits))
                self.assertEqual("Seeded", hits[0].name)


@skip_without_own_server
class TestProcessExitCleanup(TestCase):
    def test_a_finished_test_run_leaves_no_temporary_files(self):
        # atexit can only be observed from the outside, so this runs a real child interpreter.
        temporary = tempfile.gettempdir()
        data_before = set(glob.glob(os.path.join(temporary, "ravendb-test-driver-*")))
        settings_before = set(glob.glob(os.path.join(temporary, "settings-*.json")))

        child = subprocess.run(
            [
                sys.executable,
                "-c",
                "from ravendb_test_driver import RavenTestDriver\n"
                "with RavenTestDriver() as driver:\n"
                "    with driver.get_document_store() as store:\n"
                "        with store.open_session() as session:\n"
                "            session.store({'name': 'child'}, 'people/1')\n"
                "            session.save_changes()\n",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(Path(__file__).resolve().parent.parent),
        )

        self.assertEqual(0, child.returncode, child.stderr)
        self.assertEqual(set(), set(glob.glob(os.path.join(temporary, "ravendb-test-driver-*"))) - data_before)
        self.assertEqual(set(), set(glob.glob(os.path.join(temporary, "settings-*.json"))) - settings_before)
