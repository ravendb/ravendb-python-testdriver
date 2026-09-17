"""Seeding every test database from a .ravendbdump, the way the .NET driver does."""

import io
import tempfile
from pathlib import Path
from unittest import TestCase, skipIf

from ravendb import DatabaseSmugglerExportOptions

from ravendb_test_driver import RavenTestDriver
from tests.support import attach_mode_is_active

skip_without_own_server = skipIf(attach_mode_is_active(), "attach mode: the driver does not own the server")


class Person:
    def __init__(self, Id=None, name=None):
        self.Id = Id
        self.name = name


def _dump_of_two_people(directory: str) -> str:
    """Build a real dump by seeding a database and exporting it."""
    dump = str(Path(directory, "people.ravendbdump"))

    with RavenTestDriver() as driver:
        with driver.get_document_store() as store:
            with store.open_session() as session:
                session.store(Person(name="Ayende"), "people/1")
                session.store(Person(name="Oren"), "people/2")
                session.save_changes()

            store.smuggler.for_database(store.database).export(DatabaseSmugglerExportOptions(), dump)

    return dump


class _FilePathDriver(RavenTestDriver):
    dump_path = None

    def database_dump_file_path(self):
        return self.dump_path


class _StreamDriver(RavenTestDriver):
    def __init__(self, dump_path):
        super().__init__()
        self._path = dump_path
        self.opened = 0

    def database_dump_file_stream(self):
        self.opened += 1
        return open(self._path, "rb")


@skip_without_own_server
class TestDumpSeeding(TestCase):
    def test_a_dump_path_seeds_every_database(self):
        with tempfile.TemporaryDirectory() as directory:
            _FilePathDriver.dump_path = _dump_of_two_people(directory)
            self.addCleanup(setattr, _FilePathDriver, "dump_path", None)

            with _FilePathDriver() as driver:
                for _ in range(2):
                    with driver.get_document_store() as store:
                        with store.open_session() as session:
                            self.assertEqual("Ayende", session.load("people/1", Person).name)
                            self.assertEqual("Oren", session.load("people/2", Person).name)

    def test_a_dump_stream_is_read_once_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            dump = _dump_of_two_people(directory)

            driver = _StreamDriver(dump)
            with driver.get_document_store() as first, driver.get_document_store() as second:
                for store in (first, second):
                    with store.open_session() as session:
                        self.assertEqual("Ayende", session.load("people/1", Person).name)

            # The hook is asked once; the stream is rewound for the second database.
            self.assertEqual(1, driver.opened)

            driver.close()
            self.assertTrue(driver._dump_stream.closed)

    def test_no_dump_means_an_empty_database(self):
        with RavenTestDriver() as driver:
            with driver.get_document_store() as store:
                with store.open_session() as session:
                    self.assertIsNone(session.load("people/1", Person))


class TestDumpHooksAreEmptyByDefault(TestCase):
    def test_both_hooks_return_none(self):
        driver = RavenTestDriver()

        self.assertIsNone(driver.database_dump_file_path())
        self.assertIsNone(driver.database_dump_file_stream())

    def test_closing_without_a_dump_stream_is_fine(self):
        driver = RavenTestDriver()
        driver.close()

        self.assertIsNone(driver._dump_stream)

    def test_a_stream_the_driver_never_used_is_left_alone(self):
        driver = RavenTestDriver()
        driver._dump_stream = io.BytesIO(b"")
        driver.close()

        self.assertTrue(driver._dump_stream.closed)
