"""App-instance CA + member-leaf X.509 generation per C2PA.md §4.2 / §4.3.

This module is the load-bearing piece Andromica (and Inkternity) need at
first run. It runs locally on the user's machine, generates an Ed25519
keypair, and self-signs an X.509 cert with the three C2PA-mandatory
properties:

  1. CA:TRUE basic constraint (so it can issue leaves)
  2. critical KeyUsage with keyCertSign + digitalSignature
  3. critical ExtendedKeyUsage with the C2PA claim-signing OID
     (1.3.6.1.4.1.42038.1.5.0)

And one Heavymeta-specific property:

  4. SubjectAlternativeName URI binding the app's Stellar address
     (stellar:G...) so the cert can be linked back to the on-chain
     `hvym-cert-registry` record.

The DER-encoded cert is what gets fingerprinted (SHA-256) and stored in
the registry; the private key stays on the user's machine in their local
keystore alongside the app's Stellar private key.
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.x509.oid import NameOID

# C2PA claim-signing Extended Key Usage OID (RFC 9476 / C2PA spec).
C2PA_CLAIM_SIGNING_OID = x509.ObjectIdentifier("1.3.6.1.4.1.42038.1.5.0")


@dataclass
class AppCa:
    """The result of `generate_app_ca`. The private key never leaves this
    process unless the caller chooses to persist it."""

    private_key: Ed25519PrivateKey
    cert: x509.Certificate

    @property
    def der_bytes(self) -> bytes:
        return self.cert.public_bytes(serialization.Encoding.DER)

    @property
    def pem_bytes(self) -> bytes:
        return self.cert.public_bytes(serialization.Encoding.PEM)

    @property
    def fingerprint_sha256(self) -> bytes:
        """The 32-byte SHA-256 of the DER-encoded cert. This is the
        `fingerprint` field stored in `AppCaRecord` on chain."""
        return hashlib.sha256(self.der_bytes).digest()

    @property
    def expires_at_unix(self) -> int:
        """The cert's `notAfter` as a Unix timestamp (UTC seconds)."""
        return int(
            self.cert.not_valid_after_utc.replace(
                tzinfo=datetime.timezone.utc
            ).timestamp()
        )

    @property
    def public_key_raw(self) -> bytes:
        """The raw 32-byte Ed25519 public key of the CA."""
        return self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )


def generate_app_ca(
    *,
    app_name: str,
    app_stellar_address: str,
    valid_days: int = 3650,
    not_before: Optional[datetime.datetime] = None,
) -> AppCa:
    """Generate a self-signed Ed25519 CA cert for one app instance.

    Args:
        app_name: e.g. "Andromica" or "Inkternity". Goes into the CN and
            the heavymeta:app/<name> SAN URI.
        app_stellar_address: the app instance's Stellar G-address. Goes
            into the SAN as `stellar:G...` and is what the on-chain
            registry uses as the lookup key.
        valid_days: cert lifetime. Default 10 years, matching the
            spec's "long-lived" CA recommendation.
        not_before: if you need a fixed start time (e.g. for tests).
            Defaults to "now" in UTC.

    Returns:
        AppCa with the keypair + self-signed cert. The caller is
        responsible for persisting the private key to the local
        keystore alongside the app's Stellar key.
    """
    if not app_stellar_address.startswith("G") or len(app_stellar_address) != 56:
        raise ValueError(
            "app_stellar_address must be a Stellar account strkey "
            f"(G..., 56 chars); got {app_stellar_address!r}"
        )

    if not_before is None:
        not_before = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0
        )
    not_after = not_before + datetime.timedelta(days=valid_days)

    sk = Ed25519PrivateKey.generate()

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, f"{app_name} Instance"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Heavymeta Cooperative"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "App Instances"),
        ]
    )

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(sk.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        # CA:TRUE, pathlen:0 — this cert can issue leaves but no further CAs.
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )
        # keyCertSign + digitalSignature — required for issuing leaves.
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        # C2PA claim-signing EKU. Marked critical so non-C2PA verifiers
        # correctly reject the cert.
        .add_extension(
            x509.ExtendedKeyUsage([C2PA_CLAIM_SIGNING_OID]),
            critical=True,
        )
        # SANs: the Stellar URI is the load-bearing one (the registry key).
        # The heavymeta: URI is human-readable provenance metadata.
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.UniformResourceIdentifier(f"stellar:{app_stellar_address}"),
                    x509.UniformResourceIdentifier(f"heavymeta:app/{app_name}"),
                ]
            ),
            critical=False,
        )
    )

    # Ed25519 is sign-without-prehash: the algorithm arg is None.
    cert = builder.sign(private_key=sk, algorithm=None)
    return AppCa(private_key=sk, cert=cert)


@dataclass
class MemberLeaf:
    """An ephemeral per-publish leaf cert. Never persist any of this."""

    private_key: Ed25519PrivateKey
    cert: x509.Certificate

    @property
    def der_bytes(self) -> bytes:
        return self.cert.public_bytes(serialization.Encoding.DER)

    @property
    def pem_bytes(self) -> bytes:
        return self.cert.public_bytes(serialization.Encoding.PEM)


def issue_member_leaf(
    *,
    app_ca: AppCa,
    member_name: str,
    member_stellar_address: str,
    member_canon_url: Optional[str] = None,
    valid_hours: int = 24,
    not_before: Optional[datetime.datetime] = None,
) -> MemberLeaf:
    """Issue a short-lived leaf cert for a single publish event.

    The leaf's private key is ephemeral — it should be regenerated on every
    publish and discarded immediately after signing. Nothing about it is
    worth persisting. The leaf SAN's stellar URI is **informational**; the
    authoritative member identity for verification is the `member_pubkey`
    field on the on-chain `AppCaRecord` (per C2PA.md §4.3).
    """
    if not member_stellar_address.startswith("G") or len(member_stellar_address) != 56:
        raise ValueError("member_stellar_address must be a Stellar G-address")

    if not_before is None:
        not_before = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0
        )
    not_after = not_before + datetime.timedelta(hours=valid_hours)

    leaf_sk = Ed25519PrivateKey.generate()

    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, member_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Heavymeta Cooperative"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Members"),
        ]
    )
    sans = [x509.UniformResourceIdentifier(f"stellar:{member_stellar_address}")]
    if member_canon_url:
        sans.append(x509.UniformResourceIdentifier(member_canon_url))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(app_ca.cert.subject)
        .public_key(leaf_sk.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
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
            x509.ExtendedKeyUsage([C2PA_CLAIM_SIGNING_OID]),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName(sans),
            critical=False,
        )
        .sign(private_key=app_ca.private_key, algorithm=None)
    )

    return MemberLeaf(private_key=leaf_sk, cert=cert)


def verify_chain(leaf_der: bytes, ca_der: bytes) -> tuple[bool, Optional[str]]:
    """Verify a leaf -> CA chain cryptographically (signatures + validity
    windows + chain integrity). Does NOT consult the on-chain registry —
    that's a separate step (see `mock_c2pa.register.is_trusted`).

    Returns (ok, reason_if_not_ok).
    """
    try:
        leaf = x509.load_der_x509_certificate(leaf_der)
        ca = x509.load_der_x509_certificate(ca_der)
    except Exception as e:  # noqa: BLE001
        return (False, f"could not parse cert: {e}")

    now = datetime.datetime.now(datetime.timezone.utc)

    if not (ca.not_valid_before_utc <= now <= ca.not_valid_after_utc):
        return (False, "CA cert is outside its validity window")
    if not (leaf.not_valid_before_utc <= now <= leaf.not_valid_after_utc):
        return (False, "leaf cert is outside its validity window")

    if leaf.issuer != ca.subject:
        return (False, "leaf issuer DN does not match CA subject DN")

    try:
        # CA verifies its own self-signature.
        ca_pubkey: Ed25519PublicKey = ca.public_key()  # type: ignore[assignment]
        ca_pubkey.verify(ca.signature, ca.tbs_certificate_bytes)
    except Exception:  # noqa: BLE001
        return (False, "CA self-signature invalid")

    try:
        # CA verifies the leaf's signature.
        ca_pubkey.verify(leaf.signature, leaf.tbs_certificate_bytes)
    except Exception:  # noqa: BLE001
        return (False, "leaf signature does not verify against CA")

    return (True, None)
