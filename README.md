# RavenDB Test Driver

`ravendb-test-driver` runs integration tests against a real RavenDB server instead of a mock. It
creates an isolated database for each test and deletes that database when its `DocumentStore` is
closed. Your tests use the standard `ravendb` client API.

## Install

```bash
pip install ravendb-test-driver
```

Python 3.10+ is required.

## Quick start

With the default configuration, the driver starts an embedded RavenDB server and gives every
store its own database:

```python
from ravendb_test_driver import RavenTestDriver

with RavenTestDriver() as driver:
    with driver.get_document_store() as store:
        with store.open_session() as session:
            session.store({"name": "John"}, "people/1")
            session.save_changes()

        with store.open_session() as session:
            assert session.load("people/1", dict)["name"] == "John"
```

The default mode requires a matching system .NET runtime. The two alternatives below do not
require .NET on the machine running the Python tests.

## Choose where RavenDB runs

| Mode | .NET on the test machine? | Who manages the server? | Best for |
|------|---------------------------|-------------------------|----------|
| [Embedded default](#embedded-server-default) | Yes | Test driver | The simplest local setup |
| [On-demand self-contained](#on-demand-self-contained-server) | No | Test driver | Portable developer machines and CI runners |
| [Attach to your server](#attach-to-a-server-you-run) | No | You | Docker, Testcontainers, or a shared service |

Configure the selected mode before the first call to `get_document_store()`.

### Embedded server (default)

No configuration is needed. The driver starts the framework-dependent server bundled with
`ravendb-embedded`.

| `ravendb-test-driver` version | Required runtime |
|-------------------------------|------------------|
| 7.2.x                         | .NET 10          |
| 7.1.x                         | .NET 8           |

Run `dotnet --list-runtimes` and look for `Microsoft.NETCore.App`. Re-check the requirement when
upgrading to a new RavenDB minor version.

Runnable walkthrough: [Lab 02 — isolated embedded databases](labs/02-embedded-per-test.md).

### On-demand self-contained server

Let the driver download, cache, and manage the self-contained build for the current platform:

```python
from ravendb_embedded import ServerOptions
from ravendb_test_driver import RavenTestDriver

options = ServerOptions()
options.with_auto_downloaded_server()
RavenTestDriver.configure_server(options)

with RavenTestDriver() as driver:
    with driver.get_document_store() as store:
        ...
```

The same test configuration works across supported Windows, Linux, and macOS machines because the
operating system and architecture are detected at runtime. The first run downloads 100 MB+;
later runs reuse `~/.cache/ravendb-embedded`. Pass `cache_root` to
`with_auto_downloaded_server()` when your build system restores a different cache directory.

Supported targets are Windows x64/x86, Linux x64/ARM64, and macOS x64/ARM64. Self-contained mode
removes the system .NET requirement, but normal RavenDB operating-system dependencies still
apply. Minimal Linux images may need their distribution's ICU package. The Python wheel stays
platform-independent because it downloads only the self-contained build needed by the current
machine rather than bundling every platform.

Runnable walkthrough: [Lab 04 — portable embedded tests without .NET](labs/04-embedded-no-dotnet.md).

### Attach to a server you run

Start RavenDB yourself—locally, in Docker or Testcontainers, or as a shared service—and configure
its URL:

```python
from ravendb_test_driver import RavenTestDriver

RavenTestDriver.configure_external_server("http://localhost:8080")
```

Alternatively, configure the URL through the environment:

```bash
RAVENDB_TEST_SERVER_URL=http://localhost:8080 python -m unittest
```

This path does not use `EmbeddedServer`: the driver neither starts nor stops the server, but it
still creates and deletes an isolated database for each test. No .NET installation is needed on
the test machine; the server environment supplies its own runtime.

For HTTPS with client-certificate authentication:

```python
RavenTestDriver.configure_external_server(
    "https://my-ravendb",
    certificate_pem_path="client.pem",
    trust_store_path="ca.crt",
)
```

The equivalent environment variables are:

- `RAVENDB_TEST_SERVER_URL`
- `RAVENDB_TEST_SERVER_CERT`
- `RAVENDB_TEST_SERVER_CA`

`trust_store_path` or `RAVENDB_TEST_SERVER_CA` is needed when the server's CA is not already
trusted by the test machine.

Runnable walkthrough: [Lab 01 — Docker, Testcontainers, and shared servers](labs/01-attach-to-server.md).

## Test lifecycle

Create a `RavenTestDriver` for the test or fixture, then close every returned store. A context
manager handles both steps:

```python
from unittest import TestCase
from ravendb_test_driver import RavenTestDriver


class TestPeople(TestCase):
    def test_stores_a_person(self):
        with RavenTestDriver() as driver:
            with driver.get_document_store() as store:
                with store.open_session() as session:
                    session.store({"name": "John"}, "people/1")
                    session.save_changes()
```

Each `get_document_store()` call creates a new database. Closing the store deletes it, which keeps
tests independent even when they share one RavenDB server process.

## Seed data and wait for indexing

Override `setup_database(self, store)` to create indexes or seed reference data whenever the
driver creates a database:

```python
class PeopleTestDriver(RavenTestDriver):
    def setup_database(self, store):
        with store.open_session() as session:
            session.store({"name": "Seeded"}, "people/seed")
            session.save_changes()
```

Use `GetDocumentStoreOptions.wait_for_indexing_timeout` when a store should not be returned until
indexing settles, or call `wait_for_indexing(store)` directly.

`wait_for_user_to_continue_the_test(store)` opens RavenDB Studio and pauses the test for manual
inspection.

Runnable walkthrough: [Lab 03 — seeding and indexes](labs/03-seeding-indexes.md).

## Labs

| Lab | Scenario | Needs system .NET? |
|-----|----------|--------------------|
| [01](labs/01-attach-to-server.md) | Attach to Docker, Testcontainers, or a shared server | No |
| [02](labs/02-embedded-per-test.md) | Default embedded server and isolated databases | Yes |
| [03](labs/03-seeding-indexes.md) | Seed data and wait for real indexing | Yes |
| [04](labs/04-embedded-no-dotnet.md) | On-demand self-contained server | No |

The runnable scripts live in this repository rather than `site-packages`. Clone or download the
repository, install the package, and run them from the repository root. See the
[complete labs guide](labs/README.md).

For lower-level server configuration, see
[`ravendb-embedded`](https://github.com/ravendb/ravendb-python-embedded).

## Links

- [PyPI](https://pypi.org/project/ravendb-test-driver/)
- [Source](https://github.com/ravendb/ravendb-python-testdriver)
- [RavenDB Python client documentation](https://ravendb.net/docs/article-page/latest/python)
