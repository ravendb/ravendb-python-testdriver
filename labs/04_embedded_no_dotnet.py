"""Lab 04: Self-contained embedded server without system .NET.

For: test suites that want the driver to manage RavenDB without installing .NET or running a
separate server. The first run downloads and caches a self-contained RavenDB build.

Run:  python labs/04_embedded_no_dotnet.py
"""

import atexit
import shutil
import tempfile
from pathlib import Path

from ravendb_embedded import ServerOptions
from ravendb_test_driver import RavenTestDriver


def main() -> None:
    work = tempfile.mkdtemp()
    atexit.register(lambda: shutil.rmtree(work, ignore_errors=True))

    options = ServerOptions()
    options.dot_net_path = "__no_dotnet__"
    options.with_auto_downloaded_server()
    options.data_directory = str(Path(work, "data"))
    options.logs_path = str(Path(work, "logs"))
    RavenTestDriver.configure_server(options)

    with RavenTestDriver() as driver:
        with driver.get_document_store() as store:
            with store.open_session() as session:
                session.store({"name": "no-dotnet"}, "people/1")
                session.save_changes()
            with store.open_session() as session:
                assert session.load("people/1", dict)["name"] == "no-dotnet"

    print("Lab 04 OK: self-contained embedded server ran without system .NET.")


if __name__ == "__main__":
    main()
