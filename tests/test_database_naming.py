"""Database-name generation: the caller-name opt-in, per-process uniqueness, and the counter."""

import os
from unittest import TestCase

from ravendb_test_driver import RavenTestDriver
from tests.support import isolate_environment


class _CallerNameDriver(RavenTestDriver):
    use_caller_name_for_database = True


class TestCallerNameOptIn(TestCase):
    def test_is_off_by_default(self):
        self.assertFalse(RavenTestDriver.use_caller_name_for_database)
        self.assertTrue(RavenTestDriver()._next_database_name(None).startswith("test_"))

    def test_uses_the_calling_test_name_when_switched_on(self):
        name = _CallerNameDriver()._next_database_name(None)

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
        self.assertEqual("weird_name_with_chars", RavenTestDriver._database_stem("weird name/with:chars"))

    def test_synthetic_names_have_no_stem(self):
        self.assertIsNone(RavenTestDriver._database_stem("<lambda>"))


class TestPerProcessUniqueness(TestCase):
    def setUp(self):
        isolate_environment(self)

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
