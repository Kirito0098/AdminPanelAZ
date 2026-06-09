"""Generate and store mTLS materials for panel ↔ node agent (CA, panel client, per-node agent)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.config import get_settings

_CA_CN = "AdminPanelAZ-CA"
_PANEL_CN = "adminpanelaz-panel"
_CERT_DAYS = 3650
_DIR_MODE = 0o700
_KEY_MODE = 0o600
_CERT_MODE = 0o644


@dataclass(frozen=True)
class PanelMtlsPaths:
    ca_cert: Path
    ca_key: Path
    panel_cert: Path
    panel_key: Path


@dataclass(frozen=True)
class AgentCertPaths:
    node_id: int
    agent_cert: Path
    agent_key: Path


@dataclass(frozen=True)
class MtlsProvisionBundle:
    ca_pem: str
    agent_cert_pem: str
    agent_key_pem: str


def _mtls_root() -> Path:
    return Path(get_settings().node_agent_mtls_dir)


def _panel_paths(root: Path) -> PanelMtlsPaths:
    return PanelMtlsPaths(
        ca_cert=root / "ca.crt",
        ca_key=root / "ca.key",
        panel_cert=root / "panel.crt",
        panel_key=root / "panel.key",
    )


def _agent_dir(node_id: int, root: Path | None = None) -> Path:
    base = root if root is not None else _mtls_root()
    return base / "nodes" / str(node_id)


def _agent_paths(node_id: int, root: Path | None = None) -> AgentCertPaths:
    node_dir = _agent_dir(node_id, root)
    return AgentCertPaths(
        node_id=node_id,
        agent_cert=node_dir / "agent.crt",
        agent_key=node_dir / "agent.key",
    )


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, _DIR_MODE)


def _write_private_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(path, _KEY_MODE)


def _write_certificate(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.chmod(path, _CERT_MODE)


def _generate_ca_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=4096)


def _generate_client_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _build_name(cn: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AdminPanelAZ"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ]
    )


def _sign_certificate(
    *,
    subject_cn: str,
    issuer_name: x509.Name,
    public_key,
    issuer_key: rsa.RSAPrivateKey,
    extended_key_usage: x509.ObjectIdentifier | None = None,
) -> x509.Certificate:
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(_build_name(subject_cn))
        .issuer_name(issuer_name)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=_CERT_DAYS))
    )
    if extended_key_usage is not None:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([extended_key_usage]),
            critical=False,
        )
    return builder.sign(issuer_key, hashes.SHA256())


def _create_ca(root: Path) -> PanelMtlsPaths:
    paths = _panel_paths(root)
    _ensure_dir(root)

    ca_key = _generate_ca_key()
    ca_name = _build_name(_CA_CN)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=_CERT_DAYS))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    _write_private_key(paths.ca_key, ca_key)
    _write_certificate(paths.ca_cert, ca_cert)

    panel_key = _generate_client_key()
    panel_cert = _sign_certificate(
        subject_cn=_PANEL_CN,
        issuer_name=ca_name,
        public_key=panel_key.public_key(),
        issuer_key=ca_key,
        extended_key_usage=ExtendedKeyUsageOID.CLIENT_AUTH,
    )
    _write_private_key(paths.panel_key, panel_key)
    _write_certificate(paths.panel_cert, panel_cert)

    return paths


def _load_ca_material(root: Path) -> tuple[x509.Certificate, rsa.RSAPrivateKey, x509.Name]:
    paths = _panel_paths(root)
    ca_cert = x509.load_pem_x509_certificate(paths.ca_cert.read_bytes())
    ca_key = serialization.load_pem_private_key(paths.ca_key.read_bytes(), password=None)
    if not isinstance(ca_key, rsa.RSAPrivateKey):
        raise ValueError("CA private key must be RSA")
    return ca_cert, ca_key, ca_cert.subject


def panel_mtls_ready() -> bool:
    """True when CA and panel client certificate files exist."""
    paths = _panel_paths(_mtls_root())
    return all(p.is_file() for p in (paths.ca_cert, paths.panel_cert, paths.panel_key))


def panel_mtls_dir_writable() -> bool:
    """True when the panel process can create or update files under ``node_agent_mtls_dir``."""
    root = _mtls_root()
    try:
        if root.exists():
            return os.access(root, os.W_OK)
        parent = root.parent
        return parent.exists() and os.access(parent, os.W_OK)
    except OSError:
        return False


def count_provisioned_agent_certs(root: Path | None = None) -> int:
    """Number of per-node agent certificate pairs under ``nodes/{id}/``."""
    nodes_dir = (root if root is not None else _mtls_root()) / "nodes"
    if not nodes_dir.is_dir():
        return 0
    count = 0
    for child in nodes_dir.iterdir():
        if child.is_dir() and (child / "agent.crt").is_file() and (child / "agent.key").is_file():
            count += 1
    return count


def get_panel_mtls_status() -> dict[str, str | int | bool]:
    """Panel CA readiness and storage paths (no PEM contents)."""
    root = _mtls_root()
    paths = _panel_paths(root)
    return {
        "ready": panel_mtls_ready(),
        "writable": panel_mtls_dir_writable(),
        "mtls_dir": str(root),
        "ca_cert": str(paths.ca_cert),
        "panel_cert": str(paths.panel_cert),
        "panel_key": str(paths.panel_key),
        "agent_certs_count": count_provisioned_agent_certs(root),
    }


def ensure_panel_mtls_materials(*, force: bool = False) -> PanelMtlsPaths:
    """Create CA and panel client certificate once under ``node_agent_mtls_dir``."""
    root = _mtls_root()
    paths = _panel_paths(root)

    if panel_mtls_ready() and not force:
        return paths

    if any(p.exists() for p in (paths.ca_cert, paths.ca_key, paths.panel_cert, paths.panel_key)):
        if not force:
            return paths

    return _create_ca(root)


def _agent_common_name(node_id: int, node_name: str) -> str:
    name = (node_name or "").strip()
    if name:
        return name
    return f"adminpanelaz-node-{node_id}"


def generate_agent_cert_for_node(
    node_id: int,
    node_name: str,
    *,
    force: bool = False,
) -> AgentCertPaths:
    """Issue a server certificate for one node agent under ``nodes/{node_id}/``."""
    if not panel_mtls_ready():
        raise RuntimeError("Panel mTLS materials are missing; call ensure_panel_mtls_materials() first")

    root = _mtls_root()
    paths = _agent_paths(node_id, root)
    if paths.agent_cert.is_file() and paths.agent_key.is_file() and not force:
        return paths

    if paths.agent_cert.exists() or paths.agent_key.exists():
        if not force:
            return paths

    _ensure_dir(_agent_dir(node_id, root))
    _, ca_key, ca_name = _load_ca_material(root)

    agent_key = _generate_client_key()
    agent_cert = _sign_certificate(
        subject_cn=_agent_common_name(node_id, node_name),
        issuer_name=ca_name,
        public_key=agent_key.public_key(),
        issuer_key=ca_key,
        extended_key_usage=ExtendedKeyUsageOID.SERVER_AUTH,
    )
    _write_private_key(paths.agent_key, agent_key)
    _write_certificate(paths.agent_cert, agent_cert)
    return paths


def read_agent_bundle_for_node(node_id: int) -> MtlsProvisionBundle:
    """Read PEM bundle to send to a node agent for provision-mtls."""
    root = _mtls_root()
    panel = _panel_paths(root)
    agent = _agent_paths(node_id, root)

    for path in (panel.ca_cert, agent.agent_cert, agent.agent_key):
        if not path.is_file():
            raise FileNotFoundError(f"mTLS material missing: {path}")

    return MtlsProvisionBundle(
        ca_pem=panel.ca_cert.read_text(encoding="utf-8"),
        agent_cert_pem=agent.agent_cert.read_text(encoding="utf-8"),
        agent_key_pem=agent.agent_key.read_text(encoding="utf-8"),
    )
