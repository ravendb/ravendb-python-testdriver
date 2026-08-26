"""Regressions around driver lifecycle, database-name allocation, indexing waits and cleanup.

None of these paths had coverage before, which is why the defects survived: every other test
and lab closes its store in a nested `with` block and never closes the driver itself.
"""

import os
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from ravendb import GetIndexErrorsOperation, GetDatabaseRecordOperation
from ravendb.documents.indexes.definitions import IndexState
from ravendb.documents.operations.statistics import IndexInformation
from ravendb.exceptions.exceptions import TimeoutException

from ravendb_test_driver import DriverCloseError, RavenTestDriver


class TestDriverClose(TestCase):
    def test_closing_the_driver_closes_a_store_left_open(self):
        # close() used to iterate _document_stores while each store's after-close callback
        # popped itself out of that same dict, so the for statement raised
        # RuntimeError: dictionary changed size during iteration - outside the try/except,
        # leaving disposed unset and on_driver_closed unfired.
        driver = RavenTestDriver()
        store = driver.get_document_store()
        with store.open_session() as session:
            session.store({"name": "John"}, "people/1")
            session.save_changes()

        closed = []
        driver.on_driver_closed = closed.append

        driver.close()

        self.assertTrue(driver.disposed)
        self.assertEqual([driver], closed)
        self.assertEqual(0, len(driver._document_stores))

    def test_closing_the_driver_twice_is_a_no_op(self):
        driver = RavenTestDriver()
        with driver.get_document_store():
            pass

        driver.close()
        driver.close()

        self.assertTrue(driver.disposed)


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


class TestDatabaseNameAllocation(TestCase):
    def test_two_drivers_get_distinct_database_names(self):
        # self._INDEX += 1 read the class attribute and wrote an instance one, so every
        # driver restarted numbering at 1 and two live drivers both asked for test_1.
        with RavenTestDriver() as first, RavenTestDriver() as second:
            with first.get_document_store() as first_store:
                with second.get_document_store() as second_store:
                    self.assertNotEqual(first_store.database, second_store.database)

    def test_index_stays_a_class_attribute(self):
        driver = RavenTestDriver()
        before = RavenTestDriver._INDEX
        with driver.get_document_store():
            pass

        self.assertEqual(before + 1, RavenTestDriver._INDEX)
        self.assertNotIn("_INDEX", driver.__dict__)
        driver.close()


class _PreConfiguringDriver(RavenTestDriver):
    def __init__(self):
        super().__init__()
        self.records = []

    def pre_configure_database(self, database_record) -> None:
        self.records.append(database_record)
        database_record.settings["Indexing.MapTimeoutInSec"] = "17"


class TestPreConfigureDatabase(TestCase):
    def test_hook_can_change_the_record_before_the_database_is_created(self):
        driver = _PreConfiguringDriver()
        with driver.get_document_store() as store:
            self.assertEqual(1, len(driver.records))
            self.assertEqual(store.database, driver.records[0].database_name)

            created = store.maintenance.server.send(GetDatabaseRecordOperation(store.database))
            self.assertEqual("17", created.settings["Indexing.MapTimeoutInSec"])

        driver.close()


def _index(name, stale=False, state=IndexState.NORMAL):
    return IndexInformation(stale=stale, index_state=state, name=name)


class _FakeAdmin:
    """Serves canned GetStatisticsOperation results, one per poll, then repeats the last."""

    def __init__(self, *statistics):
        self._statistics = list(statistics)
        self.polls = 0

    def send(self, operation):
        if isinstance(operation, GetIndexErrorsOperation):
            return []
        self.polls += 1
        return self._statistics.pop(0) if len(self._statistics) > 1 else self._statistics[0]


class _FakeStore:
    def __init__(self, admin):
        self.maintenance = SimpleNamespace(for_database=lambda database=None: admin)


class TestWaitForIndexing(TestCase):
    def test_returns_once_nothing_is_stale(self):
        admin = _FakeAdmin(SimpleNamespace(indexes=[_index("Orders/ByCompany")]))

        RavenTestDriver.wait_for_indexing(_FakeStore(admin), "db", timedelta(seconds=5))

        self.assertEqual(1, admin.polls)

    def test_keeps_polling_while_something_is_stale(self):
        admin = _FakeAdmin(
            SimpleNamespace(indexes=[_index("Orders/ByCompany", stale=True)]),
            SimpleNamespace(indexes=[_index("Orders/ByCompany")]),
        )

        RavenTestDriver.wait_for_indexing(_FakeStore(admin), "db", timedelta(seconds=5))

        self.assertEqual(2, admin.polls)

    def test_waits_for_a_side_by_side_replacement_to_be_swapped_in(self):
        # A replacement index blocks the return even when it is not stale, matching C#:
        # until the server swaps it in, querying the original returns pre-swap results.
        # The old predicate excluded ReplacementOf/ indexes and returned immediately.
        admin = _FakeAdmin(
            SimpleNamespace(
                indexes=[
                    _index("Orders/ByCompany"),
                    _index("ReplacementOf/Orders/ByCompany"),
                ]
            )
        )

        with self.assertRaises(TimeoutException):
            RavenTestDriver.wait_for_indexing(_FakeStore(admin), "db", timedelta(milliseconds=200))

        self.assertGreater(admin.polls, 0)

    def test_a_zero_timeout_is_honored_instead_of_becoming_sixty_seconds(self):
        # `timeout or timedelta(seconds=60)` silently turned an explicit zero into a minute.
        admin = _FakeAdmin(SimpleNamespace(indexes=[_index("Orders/ByCompany", stale=True)]))

        started = time.monotonic()
        with self.assertRaises(TimeoutException):
            RavenTestDriver.wait_for_indexing(_FakeStore(admin), "db", timedelta(0))

        self.assertLess(time.monotonic() - started, 1)

    def test_disabled_indexes_are_ignored(self):
        admin = _FakeAdmin(SimpleNamespace(indexes=[_index("Orders/Disabled", stale=True, state=IndexState.DISABLED)]))

        RavenTestDriver.wait_for_indexing(_FakeStore(admin), "db", timedelta(seconds=5))

        self.assertEqual(1, admin.polls)


class TestCleanupTempDirs(TestCase):
    def test_cleanup_returns_as_soon_as_the_directory_is_gone(self):
        # The retry loop read shutil.rmtree's None return as a failure flag, so a successful
        # delete still cost one 0.2s sleep and a second pass.
        directory = tempfile.mkdtemp()
        Path(directory, "file.txt").write_text("x", encoding="utf-8")

        started = time.monotonic()
        RavenTestDriver._cleanup_temp_dirs(directory)
        elapsed = time.monotonic() - started

        self.assertFalse(os.path.exists(directory))
        self.assertLess(elapsed, 0.15)
