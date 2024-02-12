from unittest import TestCase

from ravendb_test_driver import RavenTestDriver


class TestBasic(TestCase):
    def setUp(self):
        super().setUp()
        self.test_driver = RavenTestDriver()

    def test_1(self):
        with self.test_driver.get_document_store() as store:
            with store.open_session() as session:
                person = {"Name": "John"}
                session.store(person, "people1")
                session.save_changes()

    def test_2(self):
        with self.test_driver.get_document_store() as store:
            with store.open_session() as session:
                person = Person(name="Grisha")
                session.store(person, "people/1")
                session.save_changes()

            with store.open_session() as session:
                grisha = session.load("people/1", Person)
                self.assertEqual("Grisha", grisha.name)
                self.assertEqual("people/1", grisha.Id)

    def test_another(self):
        with self.test_driver.get_document_store() as store:
            with store.open_session() as session:
                person = session.load("people/1", Person)
                self.assertIsNone(person)


class Person:
    def __init__(self, Id: str = None, name: str = None):
        self.Id = Id
        self.name = name
