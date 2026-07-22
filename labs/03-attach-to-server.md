# Lab 03: Attach to a server you run yourself

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

Then use the driver exactly as with the embedded server:

```python
with RavenTestDriver() as driver:
    with driver.get_document_store() as store:  # isolated database on the attached server
        ...
```

The complete runnable example is [`03_attach_to_server.py`](03_attach_to_server.py).

## Run a server with Docker

```bash
docker run -d -p 8080:8080 \
  -e RAVEN_Setup_Mode=None -e RAVEN_License_Eula_Accepted=true \
  -e RAVEN_Security_UnsecuredAccessAllowed=PublicNetwork -e RAVEN_ServerUrl=http://0.0.0.0:8080 \
  ravendb/ravendb:7.2-ubuntu-latest

RAVENDB_TEST_SERVER_URL=http://localhost:8080 python labs/03_attach_to_server.py
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

## Takeaway

No embedded server and no .NET, at the cost of running RavenDB yourself. For the embedded
options (with or without .NET), see the labs in the `ravendb-python-embedded` repository
(Lab 01 and Lab 02).
