# Lab 04: Self-contained embedded server without system .NET

**For:** test suites that want the driver to manage RavenDB without installing .NET and without
running a separate server. `ravendb-embedded` downloads and caches a self-contained RavenDB build,
then the test driver uses it while keeping each test database isolated.

The embedded package detects the host operating system and architecture at runtime. This keeps the
same test suite portable across supported Windows, Linux, and macOS machines without per-platform
server paths or a matching system .NET installation.

## Run it

Run from a checkout of this repository:

```bash
pip install ravendb-test-driver
python labs/04_embedded_no_dotnet.py
```

The complete example is [`04_embedded_no_dotnet.py`](04_embedded_no_dotnet.py). The core is:

```python
from ravendb_embedded import ServerOptions
from ravendb_test_driver import RavenTestDriver

options = ServerOptions()
options.with_auto_downloaded_server()
RavenTestDriver.configure_server(options)

with RavenTestDriver() as driver:
    with driver.get_document_store() as store:
        ...  # isolated database on a self-contained server
```

The first run downloads a self-contained build (100 MB+) to
`~/.cache/ravendb-embedded`; later runs reuse that cache. Pass `cache_root` to
`with_auto_downloaded_server()` when your build system restores a different cache directory.
Normal RavenDB operating-system dependencies still apply; minimal Linux images may need their
distribution's ICU package.

## Takeaway

This mode keeps the zero-server-management experience of embedded tests while making the same test
configuration portable across supported platforms without requiring a system .NET runtime.
