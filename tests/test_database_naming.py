"""Database-name generation: the caller-name opt-in, per-process uniqueness, and the counter."""

import os
from unittest import TestCase

from ravendb_test_driver import RavenTestDriver


class _CallerNameDriver(RavenTestDriver):
    use_caller_name_for_database = True

    def name_for_test(self):
        # Stands in for get_document_store, so _caller_name sees the same call depth.
        return self._next_database_name(None)


class TestCallerNameOptIn(TestCase):
    def test_is_off_by_default(self):
        self.assertFalse(RavenTestDriver.use_caller_name_for_database)
        self.assertTrue(RavenTestDriver()._next_database_name(None).startswith("test_"))

    def test_uses_the_calling_test_name_when_switched_on(self):
        name = _CallerNameDriver().name_for_test()

        self.assertTrue(name.startswith("test_uses_the_calling_test_name_when_switched_on_"), name)

    def test_an_explicit_database_still_wins(self):
        name = _CallerNameDriver()._next_database_name("chosen")

        self.assertTrue(name.startswith("chosen_"), name)

    def test_synthetic_frame_names_fall_back_to_test(self):
        driver = _CallerNameDriver()
        name = (lambda: driver._next_database_name(None))()

        # co_name is <lambda> here, which is not a usable database name.
        self.assertTrue(name.startswith("test_"), name)

    def test_illegal_characters_are_replaced(self):
        def _name():
            return RavenTestDriver._caller_name(depth=1)

        _name.__code__ = _name.__code__.replace(co_name="weird name/with:chars")

        self.assertEqual("weird_name_with_chars", _name())

    def test_caller_name_is_truncated(self):
        def _name():
            return RavenTestDriver._caller_name(depth=1)

        _name.__code__ = _name.__code__.replace(co_name="x" * 300)

        self.assertEqual(100, len(_name()))


class TestPerProcessUniqueness(TestCase):
    def setUp(self):
        previous = os.environ.get("RAVENDB_TEST_UNIQUE_DB_NAMES")
        if previous is None:
            self.addCleanup(os.environ.pop, "RAVENDB_TEST_UNIQUE_DB_NAMES", None)
        else:
            self.addCleanup(os.environ.__setitem__, "RAVENDB_TEST_UNIQUE_DB_NAMES", previous)

    def test_is_off_by_default(self):
        os.environ.pop("RAVENDB_TEST_UNIQUE_DB_NAMES", None)

        name = RavenTestDriver()._next_database_name("stem")

        self.assertNotIn(str(os.getpid()), name)

    def test_adds_the_process_id_when_switched_on(self):
        os.environ["RAVENDB_TEST_UNIQUE_DB_NAMES"] = "1"

        name = RavenTestDriver()._next_database_name("stem")

        self.assertTrue(name.startswith(f"stem_{os.getpid()}_"), name)

    def test_falsy_values_leave_it_off(self):
        for value in ("0", "false", "no", "off", ""):
            with self.subTest(value=value):
                os.environ["RAVENDB_TEST_UNIQUE_DB_NAMES"] = value

                self.assertNotIn(str(os.getpid()), RavenTestDriver()._next_database_name("stem"))


class TestDatabaseNameCounter(TestCase):
    def test_counter_is_process_wide_and_monotonic(self):
        first = RavenTestDriver()._next_database_name("stem")
        second = RavenTestDriver()._next_database_name("stem")

        self.assertNotEqual(first, second)
        self.assertLess(int(first.rsplit("_", 1)[1]), int(second.rsplit("_", 1)[1]))
