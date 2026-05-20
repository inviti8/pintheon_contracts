"""Mock of the Portal's `mint_app_ca_registration_token`.

The real Portal will (per INKTERNITY.md §3):
  1. Authenticate the member's session.
  2. Decrypt the member's Stellar secret via Banker + Guardian.
  3. Sign a canonical payload with that secret.
  4. Discard the plaintext secret in `try/finally`.
  5. Return base64url(sig) + "." + base64url(payload).

This mock just holds the member's Stellar Keypair in memory and signs.
No Banker, no Guardian, no session — but the produced bytes are exactly
what `register_app_ca` expects to verify.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from stellar_sdk import Keypair

from mock_c2pa import canonical


@dataclass
class RegistrationToken:
    """The wire-format token the Portal returns to the app."""

    payload: bytes      # the canonical JSON bytes that were signed
    signature: bytes    # 64-byte Ed25519 signature
    wire: str           # base64url(sig) "." base64url(payload), no padding

    @property
    def member_pubkey(self) -> bytes:
        """For convenience — the 32 raw ed25519 pubkey bytes. Pulled from
        the payload's "m" field (hex)."""
        import json

        return bytes.fromhex(json.loads(self.payload)["m"])


def _b64url_nopad(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def mint_register_token(
    *,
    member_keypair: Keypair,
    app_address: str,
    app_kind: str,
    fingerprint: bytes,
    expires_at: int,
    nonce: int,
) -> RegistrationToken:
    """Mint a `register-app-ca` authorization token.

    Args:
        member_keypair: the member's funded Stellar keypair. In the real
            Portal this is decrypted in-process and discarded after; here
            we hold it as a parameter.
        app_address: the Stellar G-address of the app instance to register.
        app_kind: "Inkternity" | "Andromica" | "Pintheon" | "Other".
        fingerprint: 32-byte SHA-256 of the app's DER-encoded CA cert.
        expires_at: Unix seconds (UTC) — matches the CA cert's notAfter.
        nonce: uniqueness tag. Use current ledger timestamp or a random u64.
    """
    payload = canonical.register_payload(
        app_address=app_address,
        member_pubkey=member_keypair.raw_public_key(),
        app_kind=app_kind,
        fingerprint=fingerprint,
        expires_at=expires_at,
        nonce=nonce,
    )
    signature = member_keypair.sign(payload)
    wire = f"{_b64url_nopad(signature)}.{_b64url_nopad(payload)}"
    return RegistrationToken(payload=payload, signature=signature, wire=wire)


def mint_rotate_token(
    *,
    member_keypair: Keypair,
    app_address: str,
    new_fingerprint: bytes,
    new_expires_at: int,
    nonce: int,
) -> RegistrationToken:
    payload = canonical.rotate_payload(
        app_address=app_address,
        new_fingerprint=new_fingerprint,
        new_expires_at=new_expires_at,
        nonce=nonce,
    )
    signature = member_keypair.sign(payload)
    wire = f"{_b64url_nopad(signature)}.{_b64url_nopad(payload)}"
    return RegistrationToken(payload=payload, signature=signature, wire=wire)


def mint_revoke_token(
    *,
    member_keypair: Keypair,
    app_address: str,
    nonce: int,
) -> RegistrationToken:
    payload = canonical.revoke_payload(app_address=app_address, nonce=nonce)
    signature = member_keypair.sign(payload)
    wire = f"{_b64url_nopad(signature)}.{_b64url_nopad(payload)}"
    return RegistrationToken(payload=payload, signature=signature, wire=wire)
