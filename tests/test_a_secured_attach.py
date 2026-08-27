import os
import tempfile
from pathlib import Path
from unittest import TestCase

from ravendb.exceptions.raven_exceptions import RavenException
from ravendb_embedded import EmbeddedServer, ServerOptions

from ravendb_test_driver import RavenTestDriver
from tests.support import certificates, isolate_environment, reset_driver


class TestSecuredAttach(TestCase):
    def setUp(self):
        isolate_environment(self)
        reset_driver()
        self.addCleanup(reset_driver)

    def _write_and_read(self, database):
        with RavenTestDriver() as driver:
            with driver.get_document_store(database=database) as store:
                with store.open_session() as session:
                    session.store({"name": database}, "people/1")
                    session.save_changes()
                with store.open_session() as session:
                    self.assertEqual(database, session.load("people/1", dict)["name"])

    def test_api_and_environment_credentials_reach_database_store(self):
        with tempfile.TemporaryDirectory() as directory:
            server_pfx, client_pem, ca_certificate = certificates(directory)
            options = ServerOptions()
            options.secured(
                server_pfx,
                client_pem,
                ca_certificate_path=ca_certificate,
            )
            options.data_directory = str(Path(directory, "data"))
            options.logs_path = str(Path(directory, "logs"))

            with EmbeddedServer() as server:
                server.start_server(options)

                RavenTestDriver.configure_external_server(
                    server.get_server_uri(),
                    certificate_pem_path=client_pem,
                    trust_store_path=ca_certificate,
                )
                self._write_and_read("configured")

                reset_driver()

                os.environ["RAVENDB_TEST_SERVER_URL"] = server.get_server_uri()
                os.environ["RAVENDB_TEST_SERVER_CERT"] = client_pem
                os.environ["RAVENDB_TEST_SERVER_CA"] = ca_certificate
                self._write_and_read("environment")

    def test_https_attach_requires_a_client_certificate(self):
        RavenTestDriver.configure_external_server("https://127.0.0.1:1")

        with self.assertRaisesRegex(RavenException, "needs a client certificate"):
            RavenTestDriver._run_server()
