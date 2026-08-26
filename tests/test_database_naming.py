"""Database-name generation: the caller-name opt-in and the process-wide counter."""

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


class TestDatabaseNameCounter(TestCase):
    def test_counter_is_process_wide_and_monotonic(self):
        first = RavenTestDriver()._next_database_name("stem")
        second = RavenTestDriver()._next_database_name("stem")

        self.assertNotEqual(first, second)
        self.assertLess(int(first.rsplit("_", 1)[1]), int(second.rsplit("_", 1)[1]))
