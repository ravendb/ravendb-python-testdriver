# Lab 02: Embedded server, one isolated database per test (the default)

**For:** the normal way to write tests with the driver. Subclass `RavenTestDriver` (or hold an
instance); each `get_document_store()` returns a store backed by a fresh, isolated database that
is cleaned up afterwards, so tests never see each other's data. This path boots the embedded
server and needs a matching .NET (see the README).

## Run it

```bash
pip install ravendb-test-driver
python labs/02_embedded_per_test.py
```

The complete example is [`02_embedded_per_test.py`](02_embedded_per_test.py). In a real test:

```python
from unittest import TestCase
from ravendb_test_driver import RavenTestDriver

class TestThings(TestCase):
    def setUp(self):
        self.driver = RavenTestDriver()

    def test_it(self):
        with self.driver.get_document_store() as store:   # fresh isolated database
            with store.open_session() as session:
                session.store({"name": "John"}, "people/1")
                session.save_changes()
```

Two `get_document_store()` calls give two different databases, so data written to one is invisible
to the other. That isolation is what keeps tests independent.

## Takeaway

No server to manage in your tests: the driver runs one and gives each test its own database. To
run without .NET, attach to a server you start yourself (Lab 01).
