import datetime
import ipaddress
import tempfile
from pathlib import Path
from unittest import TestCase

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from ravendb import Lazy
from ravendb_embedded import EmbeddedServer, ServerOptions

from ravendb_test_driver import RavenTestDriver


def _certificates(directory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )

    server_pfx = Path(directory, "server.pfx")
    client_pem = Path(directory, "client.pem")
    ca_certificate = Path(directory, "ca.crt")
    server_pfx.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"localhost",
            key,
            certificate,
            None,
            serialization.NoEncryption(),
        )
    )
    client_pem.write_bytes(key_pem + certificate_pem)
    ca_certificate.write_bytes(certificate_pem)
    return str(server_pfx), str(client_pem), str(ca_certificate)


class TestSecuredAttach(TestCase):
    def test_client_certificate_and_trust_store_reach_database_store(self):
        with tempfile.TemporaryDirectory() as directory:
            server_pfx, client_pem, ca_certificate = _certificates(directory)
            options = ServerOptions()
            options.secured(
                server_pfx,
                client_pem,
                ca_certificate_path=ca_certificate,
            )
            options.data_directory = str(Path(directory, "data"))
            options.logs_path = str(Path(directory, "logs"))

            try:
                with EmbeddedServer() as server:
                    server.start_server(options)
                    RavenTestDriver.configure_external_server(
                        server.get_server_uri(),
                        certificate_pem_path=client_pem,
                        trust_store_path=ca_certificate,
                    )

                    with RavenTestDriver() as driver:
                        with driver.get_document_store() as store:
                            with store.open_session() as session:
                                session.store({"name": "secured"}, "people/1")
                                session.save_changes()
                            with store.open_session() as session:
                                self.assertEqual(
                                    "secured",
                                    session.load("people/1", dict)["name"],
                                )
            finally:
                lazy = RavenTestDriver._TEST_SERVER_STORE
                if lazy.is_value_created:
                    lazy.value.close()
                RavenTestDriver._EXTERNAL_SERVER_URL = None
                RavenTestDriver._EXTERNAL_SERVER_CERT = None
                RavenTestDriver._EXTERNAL_SERVER_TRUST_STORE = None
                RavenTestDriver._TEST_SERVER_STORE = Lazy(lambda: RavenTestDriver.run_server())
                RavenTestDriver._INDEX = 0
