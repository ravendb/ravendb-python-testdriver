"""Shared test helpers: self-signed certificate material and global driver state reset."""

import datetime
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from ravendb_test_driver import RavenTestDriver

ENVIRONMENT_NAMES = ("RAVENDB_TEST_SERVER_URL", "RAVENDB_TEST_SERVER_CERT", "RAVENDB_TEST_SERVER_CA")


def attach_mode_is_active() -> bool:
    """True when the suite is pointed at a server it does not own, so embedded tests must skip."""
    return bool(RavenTestDriver._EXTERNAL_SERVER_URL or os.environ.get("RAVENDB_TEST_SERVER_URL"))


def reset_driver() -> None:
    """Put the shared server and its configuration back to a pristine state."""
    RavenTestDriver.stop_test_server()
    RavenTestDriver.reset_server_configuration()
    for name in ENVIRONMENT_NAMES:
        os.environ.pop(name, None)


def certificates(directory):
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
