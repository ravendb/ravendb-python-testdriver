# RavenDB Test Driver

`ravendb-test-driver` runs your integration tests against a **real** RavenDB server instead of a
mock. Each test gets its own isolated database, created on demand and torn down afterwards, so
tests do not leak state into one another. You write ordinary `ravendb` client code; the driver
handles the server and the per-test database lifecycle.

## Install

```bash
pip install ravendb-test-driver
```

Python 3.10+ is required.

## Providing a server: pick one

The driver needs a RavenDB server to talk to. There are two ways to give it one; choose based on
whether you want .NET on the test machine.

### 1. Embedded server (default, needs .NET)

Out of the box the driver boots an **embedded** RavenDB server (via `ravendb-embedded`). Nothing
to configure, but the embedded server is a .NET application, so a matching runtime must be
installed:

| `ravendb-test-driver` version | Required runtime |
|-------------------------------|------------------|
| 7.2.x                         | .NET 10          |
| 7.1.x                         | .NET 8           |

Check with `dotnet --list-runtimes`. The requirement tracks the embedded server and can change on
a minor upgrade, so re-check it when you bump versions.

### 2. Attach to a server you run yourself (no .NET)

If you would rather not put .NET on the test machine (containerized CI, locked-down hosts), run
RavenDB yourself (Docker, testcontainers, a shared CI service) and point the driver at its URL.
The driver skips the embedded boot entirely and still creates an isolated database per test.

```python
from ravendb_test_driver import RavenTestDriver

RavenTestDriver.configure_external_server("http://localhost:8080")
# or set RAVENDB_TEST_SERVER_URL in the environment (handy for CI)
```

Call it once, before the first `get_document_store()`. A runnable Docker / testcontainers guide
is in [`labs/01-attach-to-server.md`](labs/01-attach-to-server.md). For the embedded and
self-contained server options, see the
[`ravendb-python-embedded`](https://github.com/ravendb/ravendb-python-embedded) repository.

## Usage

Subclass `RavenTestDriver` (or hold an instance) and call `get_document_store()` in each test to
get a store backed by a fresh database:

```python
from unittest import TestCase
from ravendb_test_driver import RavenTestDriver


class TestBasic(TestCase):
    def setUp(self):
        self.test_driver = RavenTestDriver()

    def test_stores_a_document(self):
        with self.test_driver.get_document_store() as store:   # isolated database
            with store.open_session() as session:
                session.store({"Name": "John"}, "people/1")
                session.save_changes()
```

Runnable example: [`labs/02-embedded-per-test.md`](labs/02-embedded-per-test.md).

### Seeding data and waiting for indexes

- Override `setup_database(self, store)` to seed or configure every database the driver hands
  out (indexes, reference data, and so on).
- `get_document_store(options)` accepts `GetDocumentStoreOptions`; set a
  `wait_for_indexing_timeout` to block until indexing settles, or call
  `wait_for_indexing(store)` yourself.
- `wait_for_user_to_continue_the_test(store)` opens RavenDB Studio so you can inspect the data
  mid-test.

Runnable example: [`labs/03-seeding-indexes.md`](labs/03-seeding-indexes.md).

## Links

- PyPI: https://pypi.org/project/ravendb-test-driver/
- GitHub: https://github.com/ravendb/ravendb-python-testdriver
- Server and self-contained options: https://github.com/ravendb/ravendb-python-embedded
