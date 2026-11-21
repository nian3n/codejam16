# Owner: Teammate 1 (Game, scenes, widgets)
"""Self-signed HTTPS for LAN play.

Browsers allow getUserMedia (the camera) only on https:// or http://localhost. A
second laptop opens http://<your-ip>:8000, which is neither, so its camera is blocked.
`uv run escape-pod --host 0.0.0.0 --https` serves the game over HTTPS with a
certificate made here. Each browser shows a warning once ("Advanced" -> "Proceed").
"""
from __future__ import annotations

import datetime
import ipaddress
import socket

from escape_pod import config


def lan_ips() -> list[str]:
    """This laptop's IPv4 addresses that other devices on the Wi-Fi can reach."""
    ips = set()
    try:  # the address the OS would use to reach the internet (no packet is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def ensure_cert():
    """Return (cert_path, key_path), creating them once in etc/tls/."""
    cert_path, key_path = config.TLS_DIR / "cert.pem", config.TLS_DIR / "key.pem"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Escape Pod (local)")])
    alt = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    alt += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in lan_ips()]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .sign(key, hashes.SHA256())
    )
    config.TLS_DIR.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Made a self-signed certificate in {config.TLS_DIR} (valid for 1 year).", flush=True)
    return cert_path, key_path
