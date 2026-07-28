"""Lab 03: Seed data and query an index in tests.

For: tests that need pre-seeded data and a defined index, and must wait for indexing to settle
before asserting. Override setup_database() to seed and create the index for every database the
driver hands out; call wait_for_indexing() before querying so the assertion is not racing the
indexer. Boots the embedded server (needs .NET).

Run:  python labs/03_seeding_indexes.py
"""

from ravendb.documents.indexes.abstract_index_creation_tasks import AbstractIndexCreationTask

from ravendb_test_driver import RavenTestDriver


class Person:
    def __init__(self, Id=None, name=None):
        self.Id = Id
        self.name = name


class People_ByName(AbstractIndexCreationTask):
    def __init__(self):
        super().__init__()
        self.map = "from p in docs.People select new { p.name }"


class SeedingDriver(RavenTestDriver):
    def setup_database(self, store) -> None:  # runs for every database the driver creates
        store.execute_index(People_ByName())
        with store.open_session() as session:
            session.store(Person(name="Seeded"), "people/1")
            session.save_changes()


def main() -> None:
    with SeedingDriver() as driver:
        with driver.get_document_store() as store:
            driver.wait_for_indexing(store)  # block until the index is no longer stale
            with store.open_session() as session:
                hits = list(session.query_index_type(People_ByName, Person).where_equals("name", "Seeded"))
                assert len(hits) == 1 and hits[0].name == "Seeded", hits

    print("Lab 03 OK: setup_database seeded data + index, wait_for_indexing settled, query returned it.")


if __name__ == "__main__":
    main()
