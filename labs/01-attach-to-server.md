# Lab 01: Attach to a server you run yourself

**For:** containerized CI, or anyone who does not want the driver to boot the embedded server
(and therefore wants no .NET on the machine). You run RavenDB yourself (Docker, testcontainers,
a shared CI service) and point the driver at its URL. The driver still creates a fresh, isolated
database per test and cleans it up afterwards.

## Point the driver at a server

Two equivalent ways:

```python
from ravendb_test_driver import RavenTestDriver

# 1. Explicit, before the first get_document_store():
RavenTestDriver.configure_external_server("http://localhost:8080")

# 2. Or set an environment variable (nice for CI):
#    RAVENDB_TEST_SERVER_URL=http://localhost:8080
```

For a secured (https) server, pass the client certificate: `configure_external_server(url,
certificate_pem_path=...)` (or set `RAVENDB_TEST_SERVER_CERT`); attaching to https without one
fails fast with a clear message.

Then use the driver exactly as with the embedded server:

```python
with RavenTestDriver() as driver:
    with driver.get_document_store() as store:  # isolated database on the attached server
        ...
```

The complete runnable example is [`01_attach_to_server.py`](01_attach_to_server.py).

## Run a server with Docker

```bash
docker run -d -p 8080:8080 \
  -e RAVEN_Setup_Mode=None -e RAVEN_License_Eula_Accepted=true \
  -e RAVEN_Security_UnsecuredAccessAllowed=PublicNetwork -e RAVEN_ServerUrl=http://0.0.0.0:8080 \
  ravendb/ravendb:7.2-ubuntu-latest

RAVENDB_TEST_SERVER_URL=http://localhost:8080 python labs/01_attach_to_server.py
```

## Run a server with testcontainers-python

There is no dedicated RavenDB module yet, so use the generic container:

```python
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

raven = (
    DockerContainer("ravendb/ravendb:7.2-ubuntu-latest")
    .with_env("RAVEN_Setup_Mode", "None")
    .with_env("RAVEN_License_Eula_Accepted", "true")
    .with_env("RAVEN_Security_UnsecuredAccessAllowed", "PublicNetwork")
    .with_env("RAVEN_ServerUrl", "http://0.0.0.0:8080")
    .with_exposed_ports(8080)
)
raven.start()
wait_for_logs(raven, "Server available on")
url = f"http://{raven.get_container_host_ip()}:{raven.get_exposed_port(8080)}"

from ravendb_test_driver import RavenTestDriver
RavenTestDriver.configure_external_server(url)
```

## In CI

This repo's own CI uses a GitHub Actions service container (see `.github/workflows/tests.yml`,
the `attach` job): it runs `ravendb/ravendb:7.2-ubuntu-latest`, waits for it, then runs the
attach test with `RAVENDB_TEST_SERVER_URL` set and no .NET installed.

## Cleanup on a shared server

Each test's database is deleted when its store closes, so dispose the driver (use it as a
context manager). If a run is hard-killed before that, per-test `test_*` databases can be left
behind on a shared server and a rerun may collide with them; prefer a fresh or per-run server,
and prune leftover `test_*` databases between runs.

## Takeaway

No embedded server and no .NET, at the cost of running RavenDB yourself. If you would rather
have the driver run the server for you (with or without .NET), see the embedded options in the
`ravendb-python-embedded` repository.
