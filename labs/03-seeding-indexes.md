# Lab 03: Seed data and query an index in tests

**For:** tests that need pre-seeded data and a defined index, and must wait for indexing to settle
before asserting. Override `setup_database()` to seed and create the index for every database the
driver hands out; call `wait_for_indexing()` before querying so the assertion is not racing the
indexer.

## Run it

```bash
pip install ravendb-test-driver
python labs/03_seeding_indexes.py
```

The complete example is [`03_seeding_indexes.py`](03_seeding_indexes.py). The core is:

```python
from ravendb.documents.indexes.abstract_index_creation_tasks import AbstractIndexCreationTask
from ravendb_test_driver import RavenTestDriver

class People_ByName(AbstractIndexCreationTask):
    def __init__(self):
        super().__init__()
        self.map = "from p in docs.People select new { p.name }"

class SeedingDriver(RavenTestDriver):
    def setup_database(self, store):        # runs for every database the driver creates
        store.execute_index(People_ByName())
        with store.open_session() as session:
            session.store(Person(name="Seeded"), "people/1")
            session.save_changes()

with SeedingDriver() as driver:
    with driver.get_document_store() as store:
        driver.wait_for_indexing(store)     # block until no index is stale
        with store.open_session() as session:
            hits = list(session.query_index_type(People_ByName, Person).where_equals("name", "Seeded"))
```

## Why `wait_for_indexing`

RavenDB indexes are updated asynchronously, so right after you write, an index query can return
stale (empty) results. `wait_for_indexing()` blocks until no index is stale, making index-backed
assertions deterministic instead of flaky.

## Takeaway

`setup_database()` is the single place to seed data and register indexes for every test database;
`wait_for_indexing()` removes the race between writing and querying an index.
