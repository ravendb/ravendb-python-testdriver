"""Lab 01: Attach to a server you run yourself (Docker / testcontainers / shared CI).

For: containerized CI, or any setup where you do NOT want the driver to boot the embedded
server (so you need no .NET). You run RavenDB yourself and point the driver at its URL; the
driver still gives every test its own isolated database.

Start a server, for example with Docker:
  docker run -d -p 8080:8080 \
    -e RAVEN_Setup_Mode=None -e RAVEN_License_Eula_Accepted=true \
    -e RAVEN_Security_UnsecuredAccessAllowed=PublicNetwork -e RAVEN_ServerUrl=http://0.0.0.0:8080 \
    ravendb/ravendb:7.2-ubuntu-latest

Then run:
  RAVENDB_TEST_SERVER_URL=http://localhost:8080 python labs/01_attach_to_server.py
"""

import os
import sys

from ravendb_test_driver import RavenTestDriver

URL = os.environ.get("RAVENDB_TEST_SERVER_URL") or (sys.argv[1] if len(sys.argv) > 1 else None)
if not URL:
    sys.exit("Set RAVENDB_TEST_SERVER_URL (or pass a URL) to a running RavenDB server. See the header.")


def main() -> None:
    # Attach explicitly (equivalent to setting RAVENDB_TEST_SERVER_URL); call before the
    # first get_document_store.
    RavenTestDriver.configure_external_server(URL)

    with RavenTestDriver() as driver:
        with driver.get_document_store() as store:  # a fresh, isolated database on the attached server
            with store.open_session() as session:
                session.store({"name": "Ayende"}, "people/1")
                session.save_changes()
            with store.open_session() as session:
                assert session.load("people/1", dict)["name"] == "Ayende"

    print("Lab 01 OK: attached to an external server, no embedded boot and no .NET.")


if __name__ == "__main__":
    main()
