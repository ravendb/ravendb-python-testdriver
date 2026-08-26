# What's new

## 7.2.5.post3

Embedded test servers now run in memory and stop writing into the installed package directory.
Secured embedded servers work end to end, because the driver finally hands its client certificate
to the stores it creates. Databases can be shaped before they are created through a new
`pre_configure_database` hook, named after the calling test, and made unique per process for
parallel runs. Closing a driver that still holds open stores no longer crashes.

Docs: [RavenDB Python client](https://ravendb.net/docs/article-page/latest/python) ·
[labs](labs/README.md) · PyPI: https://pypi.org/project/ravendb-test-driver/7.2.5.post3/

### New features

#### In-memory test servers

Embedded test servers run with `--RunInMemory=true`, so the create-and-delete-a-database cycle
behind every `get_document_store()` call never touches disk. Only the server log is written, into
a scratch directory removed at interpreter exit. Data and log directories left at the
`ravendb-embedded` default are redirected out of `site-packages`, where test data used to land.

```python
from ravendb_test_driver import RavenTestDriver, TestServerOptions

# Back to disk-backed storage, either per driver...
class OnDiskDriver(RavenTestDriver):
    run_in_memory = False


# ...or by saying so on the command line, which the driver never overrides.
options = TestServerOptions()
options.command_line_args.append("--RunInMemory=false")
options.data_directory = "/path/you/choose"
RavenTestDriver.configure_server(options)
```

New class attribute: `RavenTestDriver.run_in_memory`

#### Secured embedded servers

A secured embedded server now hands its client certificate and trust store to every store the
driver creates, so the test client can authenticate to the server it just booted. A secured server
configured without a client certificate is rejected before it starts, instead of failing later on
the first request.

```python
from ravendb_test_driver import RavenTestDriver, TestServerOptions

options = TestServerOptions()
options.secured("server.pfx", "client.pem", ca_certificate_path="ca.crt")
RavenTestDriver.configure_server(options)

with RavenTestDriver() as driver:
    with driver.get_document_store() as store:
        with store.open_session() as session:
            session.store({"name": "John"}, "people/1")
            session.save_changes()
```

#### Shape a database before it is created

`pre_configure_database` runs on the `DatabaseRecord` before `CreateDatabaseOperation` is sent, so
subclasses can set database settings, revisions, expiration, encryption or topology. It matches
`PreConfigureDatabase` in the .NET test driver.

```python
from ravendb_test_driver import RavenTestDriver


class PeopleTestDriver(RavenTestDriver):
    def pre_configure_database(self, database_record):
        database_record.settings["Indexing.MapTimeoutInSec"] = "30"
```

New hook: `RavenTestDriver.pre_configure_database`

#### Database names that say which test they came from

Two opt-ins, both off by default because they change every generated database name. The class
attribute names databases after the calling test; the environment variable adds the process id so
parallel runners sharing one attached server stop colliding.

```python
from ravendb_test_driver import RavenTestDriver


class PeopleTestDriver(RavenTestDriver):
    use_caller_name_for_database = True  # test_stores_a_person_3 instead of test_3
```

```bash
RAVENDB_TEST_UNIQUE_DB_NAMES=1 pytest -n auto
```

New class attribute: `RavenTestDriver.use_caller_name_for_database`
New environment variable: `RAVENDB_TEST_UNIQUE_DB_NAMES`

#### Shared test server teardown

Nothing used to close the shared test server before interpreter exit, so its shutdown cost landed
after the test runner printed its summary. `stop_test_server()` closes the server and its
server-level store, is idempotent, and the server starts again on the next `get_document_store()`.
Configuration is cleared separately, so freeing resources cannot silently drop a `configure_server`
call.

```python
from ravendb_test_driver import RavenTestDriver


def pytest_sessionfinish(session, exitstatus):
    RavenTestDriver.stop_test_server()
```

New methods: `RavenTestDriver.stop_test_server`, `RavenTestDriver.reset_server_configuration`

#### Opt-in strict licence checking

`RAVENDB_TEST_STRICT_LICENSE=1` makes a test server refuse to start without a valid licence, which
is what the .NET test driver does by default. Off by default here, so existing suites are
unaffected.

New environment variable: `RAVENDB_TEST_STRICT_LICENSE`

### API changes and improvements

- New `TestServerOptions`, a `ravendb_embedded.ServerOptions` that names the intent. Test defaults
  are applied to whatever options object the driver is given, so `configure_server` keeps accepting
  a plain `ServerOptions` and no call site has to change.
- New `DriverCloseError`, raised by `close()` when teardown hits errors. It subclasses
  `RuntimeError`, so existing handlers keep working, and its `exceptions` attribute holds the
  original exceptions instead of a joined string. An exception raised by an `on_driver_closed`
  callback is collected there too rather than discarding the store-close errors.
- `wait_for_user_to_continue_the_test` takes a `timeout` and defaults to five minutes, then raises
  `TimeoutException`, so a call left in committed code fails a CI job instead of hanging it. Pass
  `timeout=None` to wait indefinitely, which also happens automatically when a debugger is
  attached, or set `RAVENDB_TEST_DRIVER_WAIT_FOR_USER=0` to skip the wait.
- **Behavior change:** explicit configuration now beats the environment. When `configure_server()`
  was called and `RAVENDB_TEST_SERVER_URL` is also set, the variable is ignored and a warning is
  emitted; the driver creates and hard-deletes databases on whichever server it uses, so a silent
  redirect was dangerous. To let the environment pick the server, do not call `configure_server()`.
- **Behavior change:** `wait_for_indexing` keeps waiting while a side-by-side replacement index
  exists, matching the .NET driver's index-swap semantics. It used to return early, letting the
  next query hit the pre-swap index.
- **Behavior change:** database numbering is process-wide again. Every driver instance used to
  restart at `1`, so two live drivers both asked for `test_1`. Read `store.database` rather than
  assuming a generated name.
- `open_browser` is an instance method and can be overridden, matching the .NET driver's
  `protected virtual OpenBrowser`.
- `run_server`, `default_server_options` and `cleanup_temp_dirs` are now `_run_server`,
  `_default_server_options` and `_cleanup_temp_dirs`. The old names still work for one release and
  emit a `DeprecationWarning`.

### Other fixes

- `close()` no longer raises `RuntimeError: dictionary changed size during iteration` when a store
  is still open. It iterates a snapshot, so remaining stores are closed, their databases deleted,
  `disposed` set and `on_driver_closed` fired.
- Database-name allocation is thread-safe and no longer shadows the class counter with an instance
  attribute.
- `wait_for_user_to_continue_the_test` checks for `Debug/Done` with an existence check instead of
  loading and tracking the document, and deletes the marker afterwards so a later wait cannot
  return immediately on a stale one.
- A no-leader failure while deleting a test database is ignored, as in the .NET driver.
- `timedelta(0)` is honored instead of being treated as "not set", both for
  `GetDocumentStoreOptions.wait_for_indexing_timeout` and for `wait_for_indexing(timeout=...)`.
- The temporary settings file the driver generates is removed at exit.
- `cleanup_temp_dirs` stops treating `shutil.rmtree`'s `None` return as a failure, which cost a
  pointless retry pass on every successful cleanup.
- Server option preparation no longer mutates the caller's `command_line_args` list.
- Error messages name the actual Python API (`configure_server`, `get_document_store`) instead of
  Java-style names, wrapped exceptions keep their `__cause__`, and a failed `open_browser` reports
  the URL it could not open rather than raising an empty `RuntimeError`. A browser that cannot open
  on a headless machine is reported instead of ignored.
