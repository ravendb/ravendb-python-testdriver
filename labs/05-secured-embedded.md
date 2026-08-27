# Lab 05: Secured embedded server, with client-certificate authentication

**For:** tests that must run against HTTPS and a client certificate, without standing up a server
yourself. Point `ServerOptions.secured()` at a server certificate and the client certificate your
tests authenticate with; the driver passes that client material to every store it hands out. This
path boots the embedded server and needs a matching .NET (see the README).

## Run it

```bash
pip install ravendb-test-driver
python labs/05_secured_embedded.py
```

The complete example is [`05_secured_embedded.py`](05_secured_embedded.py). The part that matters
is three lines of configuration:

```python
from ravendb_test_driver import RavenTestDriver, TestServerOptions

options = TestServerOptions()
options.secured("server.pfx", "client.pem", ca_certificate_path="ca.crt")
RavenTestDriver.configure_server(options)

with RavenTestDriver() as driver:
    with driver.get_document_store() as store:      # https, already authenticated
        with store.open_session() as session:
            session.store({"name": "John"}, "people/1")
            session.save_changes()
```

- `server.pfx` is what the server presents. RavenDB requires it to carry the `DigitalSignature`
  and `KeyEncipherment` key usages, and a matching subject alternative name.
- `client.pem` is what the tests authenticate with. It is required: a secured server the test
  client cannot authenticate to is reported before the server starts.
- `ca_certificate_path` becomes the store's trust store, which a self-signed certificate needs.

The lab generates all three into a temporary directory so it can run anywhere. A real suite points
at its own files instead.

## Takeaway

Securing the test server is a configuration change, not a code change: the stores the driver hands
you already carry the client certificate and the trust store. To attach to a secured server you run
yourself, see Lab 01 and `configure_external_server(url, certificate_pem_path=..., trust_store_path=...)`.
