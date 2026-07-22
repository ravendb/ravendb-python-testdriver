## RavenDB Test Driver

`ravendb-test-driver` is a package for writing integration tests against RavenDB server.

### Setup

Install from PyPi:

`pip install ravendb-test-driver`


### Requirements

Python 3.10+ is required.

By default the driver boots an **embedded** RavenDB server, which is a .NET application, so a matching .NET runtime must be installed:

- `ravendb-test-driver` 7.2.x requires **.NET 10**
- `ravendb-test-driver` 7.1.x requires **.NET 8**

If you would rather not manage .NET, attach the driver to a server you run yourself (Docker, testcontainers, a shared CI service), with no runtime on the machine:

```python
from ravendb_test_driver import RavenTestDriver

RavenTestDriver.configure_external_server("http://localhost:8080")
# or set the RAVENDB_TEST_SERVER_URL environment variable
```

Each test still gets its own database. See [`labs/03-attach-to-server.md`](labs/03-attach-to-server.md) for a runnable Docker / testcontainers guide (and the `ravendb-python-embedded` repo for the embedded and self-contained options).


### Usage

Inherit `RavenTestDriver` to your test class or create an instance within your class.

Unittest example:

```python
from ravendb_test_driver import RavenTestDriver
from unittest import TestCase

class TestBasic(TestCase):
    def setUp(self):
        super().setUp()
        self.test_driver = RavenTestDriver()

    def test_1(self):
        with self.test_driver.get_document_store() as store:
            with store.open_session() as session:
                person = {"Name": "John"}
                session.store(person, "people1")
                session.save_changes()
```
### PyPi
https://pypi.org/project/ravendb-test-driver/

### Github
https://github.com/ravendb/ravendb-python-testdriver
