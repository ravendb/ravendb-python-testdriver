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

#### Where test data lives

Embedded test servers run in memory, so the create-and-delete-a-database cycle behind every
`get_document_store()` call never lands on disk. Only the server log is written, to a scratch
directory the driver removes when the interpreter exits.

Two consequences worth knowing:

- A large fixture seeded in `setup_database` is held in RAM rather than spilled to disk.
- Nothing survives a server restart, and there are no files to inspect after a failing run.

To go back to disk-backed storage, either set the argument yourself, which the driver never
overrides:

```python
options = TestServerOptions()
options.command_line_args.append("--RunInMemory=false")
options.data_directory = "/path/you/choose"
RavenTestDriver.configure_server(options)
```

or switch it off for a whole test class:

```python
class MyDriver(RavenTestDriver):
    run_in_memory = False
```

The driver also redirects the data directory when you leave it at the `ravendb-embedded` default,
which otherwise points inside the installed package. Set `data_directory` explicitly and the
driver leaves your path alone.

Nothing closes the shared test server before interpreter exit. Call
`RavenTestDriver.stop_test_server()` from a session-scoped fixture teardown when you want that
cost inside your test run rather than after the runner prints its summary; the server starts
again on the next `get_document_store()`.

#### Secured embedded server

Pass a server certificate together with the client PEM the tests authenticate with, and the driver
wires that client material into every store it hands out:

```python
options = TestServerOptions()
options.secured("server.pfx", "client.pem", ca_certificate_path="ca.crt")
RavenTestDriver.configure_server(options)
```

The client PEM is required here: a secured server the test client cannot authenticate to is
rejected before the server starts.

Runnable walkthrough: [Lab 05 — secured embedded server](labs/05-secured-embedded.md).

### On-demand self-contained server

Let the driver download, cache, and manage the self-contained build for the current platform:

```python
from ravendb_test_driver import RavenTestDriver, TestServerOptions

options = TestServerOptions()
options.with_auto_downloaded_server()
RavenTestDriver.configure_server(options)

with RavenTestDriver() as driver:
    with driver.get_document_store() as store:
        ...
```

`TestServerOptions` is a `ravendb_embedded.ServerOptions` that names the intent. `configure_server`
still accepts a plain `ServerOptions`, and the driver applies the same test defaults either way.

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

Explicit configuration wins over the environment. If a test calls `configure_server()` and
`RAVENDB_TEST_SERVER_URL` is also set, the environment variable is ignored and a warning is
emitted, because the driver creates and hard-deletes databases on whichever server it uses. To let
the environment pick the server, do not call `configure_server()`.

Runnable walkthrough: [Lab 01 — Docker, Testcontainers, and shared servers](labs/01-attach-to-server.md).

## Test lifecycle

Create a `RavenTestDriver` for the test or fixture. Closing the driver closes any store you left
open and deletes its database, so nothing leaks if a test throws halfway. Context managers make
both steps explicit:

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
tests independent even when they share one RavenDB server process. Database names are generated
(`test_1`, `test_2`, ...) from a process-wide counter; treat them as opaque and read
`store.database` rather than assuming a name, or pass `database="..."` to pick the stem yourself.

If closing the driver hits errors, it raises `DriverCloseError`, a `RuntimeError` subclass whose
`exceptions` attribute holds every original exception rather than a joined string.

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

Override `pre_configure_database(self, database_record)` to change the database itself before it is
created, for settings, revisions, expiration, encryption or topology:

```python
class PeopleTestDriver(RavenTestDriver):
    def pre_configure_database(self, database_record):
        database_record.settings["Indexing.MapTimeoutInSec"] = "30"
```

Use `GetDocumentStoreOptions.wait_for_indexing_timeout` when a store should not be returned until
indexing settles, or call `wait_for_indexing(store)` directly. It waits until every applicable
index is non-stale and any side-by-side replacement has been swapped in.

## Pausing for manual inspection

`wait_for_user_to_continue_the_test(store)` prints the Studio URL for that database, opens a
browser, and blocks until a document with the id `Debug/Done` shows up in the database. Store one
from Studio to continue; the driver deletes the marker so a later wait on the same store still
blocks.

The wait is bounded by a five-minute timeout and then raises `TimeoutException`, so a call left in
committed code fails a CI job instead of hanging it. Pass `timeout=None` to wait indefinitely,
which is also what happens automatically when a debugger is attached, or set
`RAVENDB_TEST_DRIVER_WAIT_FOR_USER=0` to skip the wait entirely.

Runnable walkthrough: [Lab 03 — seeding and indexes](labs/03-seeding-indexes.md).

## Opt-in switches

Defaults are chosen so an existing suite keeps working. These are the knobs worth knowing:

| Switch | Default | What it does |
|--------|---------|--------------|
| `RavenTestDriver.run_in_memory` | `True` | Runs embedded test servers in memory. Set `False` on a driver subclass to go back to disk |
| `RavenTestDriver.use_caller_name_for_database` | `False` | Names databases after the calling test (`test_stores_a_person_3`) instead of `test_3` |
| `RAVENDB_TEST_UNIQUE_DB_NAMES` | off | Adds the process id to database names, so parallel runners sharing one attached server stop colliding |
| `RAVENDB_TEST_STRICT_LICENSE` | off | Test servers refuse to start without a valid licence, matching the .NET test driver |
| `RAVENDB_TEST_DRIVER_WAIT_FOR_USER` | on | Set to `0` to skip `wait_for_user_to_continue_the_test` entirely |

Caller-name databases are sanitized to `[A-Za-z0-9_.-]` and truncated, and fall back to `test` when
the caller has no usable name, such as a lambda or a module-level call.

## Inspecting HTTP traffic

The client sends its requests through `requests`, which honors `HTTP_PROXY`, so any interception
proxy works without driver support:

```bash
HTTP_PROXY=http://127.0.0.1:8080 python -m unittest
```

On Windows, proxy bypass rules skip loopback addresses, so traffic to `127.0.0.1` never reaches the
proxy. Bind the test server to the machine name instead, which also needs unsecured access to be
allowed on the private network:

```python
import socket

from ravendb_test_driver import RavenTestDriver, TestServerOptions

options = TestServerOptions()
options.server_url = f"http://{socket.gethostname()}:0"
options.command_line_args.append("--Security.UnsecuredAccessAllowed=PrivateNetwork")
RavenTestDriver.configure_server(options)
```

That pair is what `TestServerOptions.UseFiddler()` does in the .NET test driver.

## Labs

| Lab | Scenario | Needs system .NET? |
|-----|----------|--------------------|
| [01](labs/01-attach-to-server.md) | Attach to Docker, Testcontainers, or a shared server | No |
| [02](labs/02-embedded-per-test.md) | Default embedded server and isolated databases | Yes |
| [03](labs/03-seeding-indexes.md) | Seed data and wait for real indexing | Yes |
| [04](labs/04-embedded-no-dotnet.md) | On-demand self-contained server | No |
| [05](labs/05-secured-embedded.md) | Secured embedded server with client certificates | Yes |

The runnable scripts live in this repository rather than `site-packages`. Clone or download the
repository, install the package, and run them from the repository root. See the
[complete labs guide](labs/README.md).

For lower-level server configuration, see
[`ravendb-embedded`](https://github.com/ravendb/ravendb-python-embedded).

## Links

- [PyPI](https://pypi.org/project/ravendb-test-driver/)
- [Source](https://github.com/ravendb/ravendb-python-testdriver)
- [RavenDB Python client documentation](https://ravendb.net/docs/article-page/latest/python)
