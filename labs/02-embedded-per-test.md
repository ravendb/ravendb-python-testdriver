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

You do not have to close every store yourself. Closing the driver closes the ones you left open and
deletes their databases, so a test that throws halfway still cleans up:

```python
driver = RavenTestDriver()
store = driver.get_document_store()
driver.close()          # store closed, database deleted
```

The embedded server is shared by every driver in the process and runs in memory. Nothing closes it
before the interpreter exits, so call `RavenTestDriver.stop_test_server()` from your runner's
teardown when you want that cost inside the run:

```python
def pytest_sessionfinish(session, exitstatus):
    RavenTestDriver.stop_test_server()
```

## Takeaway

No server to manage in your tests: the driver runs one and gives each test its own database. To
run without .NET, attach to a server you start yourself (Lab 01), or let the driver automatically
download, cache, and manage a self-contained embedded server (Lab 04).
