## RavenDB Test Driver

`ravendb-test-driver` is a package for writing integration tests against RavenDB server.

### Setup

Install from PyPi:

`pip install ravendb-test-driver`


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
