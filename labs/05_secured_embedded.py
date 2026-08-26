"""Lab 05: Secured embedded server, with client-certificate authentication.

For: tests that must run against HTTPS and a client certificate, without standing up a server
yourself. Point ServerOptions.secured() at a server certificate and the client certificate the
tests authenticate with; the driver passes that client material to every store it hands out, so
sessions work with no extra setup. Boots the embedded server and therefore needs a matching .NET.

Run:  python labs/05_secured_embedded.py
"""

import datetime
import ipaddress
import tempfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from ravendb_test_driver import RavenTestDriver, TestServerOptions


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        # In a real suite these are your own files; here they are generated so the lab is runnable.
        server_pfx, client_pem, ca_certificate = self_signed_material(directory)

        options = TestServerOptions()
        options.secured(server_pfx, client_pem, ca_certificate_path=ca_certificate)
        RavenTestDriver.configure_server(options)

        with RavenTestDriver() as driver:
            with driver.get_document_store() as store:
                assert store.urls[0].startswith("https://"), store.urls
                # The driver handed the server's client certificate to the store for you.
                assert store.certificate_pem_path == client_pem

                with store.open_session() as session:
                    session.store({"name": "John"}, "people/1")
                    session.save_changes()

                with store.open_session() as session:
                    assert session.load("people/1", dict)["name"] == "John"

        RavenTestDriver.stop_test_server()

    print("Lab 05 OK: secured embedded server, authenticated session, isolated database.")


def self_signed_material(directory: str):
    """Write a self-signed server certificate, a client PEM, and the CA to `directory`."""
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
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(
            # RavenDB refuses a server certificate without DigitalSignature and KeyEncipherment.
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
        pkcs12.serialize_key_and_certificates(b"localhost", key, certificate, None, serialization.NoEncryption())
    )
    client_pem.write_bytes(key_pem + certificate_pem)
    ca_certificate.write_bytes(certificate_pem)
    return str(server_pfx), str(client_pem), str(ca_certificate)


if __name__ == "__main__":
    main()
