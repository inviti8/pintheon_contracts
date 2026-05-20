"""Canonical signing-payload builders.

Mirrors `hvym-cert-registry/src/lib.rs::build_*_payload`. Any drift
between this module and the contract's reconstruction causes
`register_app_ca` to panic with "auth_payload does not match params", so
the two implementations are coupled and must stay in lockstep.

Encoding rules (locked, see HVYM_CERT_REGISTRY.md):

  - Sorted-keys compact JSON (`separators=(",",":")`, `sort_keys=True`).
  - UTF-8 bytes.
  - App address `a` is the Stellar strkey (G..., 56 chars) — what
    `Address::to_string()` returns on chain. We pass it through unchanged.
  - Member pubkey `m` and fingerprint `fp` are lowercase hex of the raw
    32-byte values.
  - All integers are written as JSON numbers (no quotes).
"""

from __future__ import annotations

import json


def _canonical_dump(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def register_payload(
    *,
    app_address: str,
    member_pubkey: bytes,
    app_kind: str,
    fingerprint: bytes,
    expires_at: int,
    nonce: int,
) -> bytes:
    """Bytes the member key signs for `register_app_ca`."""
    if app_kind not in {"Inkternity", "Andromica", "Pintheon", "Other"}:
        raise ValueError(f"unknown app_kind: {app_kind!r}")
    if len(member_pubkey) != 32:
        raise ValueError("member_pubkey must be 32 bytes")
    if len(fingerprint) != 32:
        raise ValueError("fingerprint must be 32 bytes")

    return _canonical_dump(
        {
            "a": app_address,
            "alg": "ed25519",
            "exp": expires_at,
            "fp": fingerprint.hex(),
            "i": "register-app-ca",
            "k": app_kind,
            "m": member_pubkey.hex(),
            "n": nonce,
        }
    )


def rotate_payload(
    *,
    app_address: str,
    new_fingerprint: bytes,
    new_expires_at: int,
    nonce: int,
) -> bytes:
    """Bytes the member key signs for `rotate_app_ca`."""
    if len(new_fingerprint) != 32:
        raise ValueError("new_fingerprint must be 32 bytes")
    return _canonical_dump(
        {
            "a": app_address,
            "exp": new_expires_at,
            "fp": new_fingerprint.hex(),
            "i": "rotate-app-ca",
            "n": nonce,
        }
    )


def revoke_payload(*, app_address: str, nonce: int) -> bytes:
    """Bytes the member key signs for `revoke_by_member`."""
    return _canonical_dump(
        {
            "a": app_address,
            "i": "revoke-app-ca",
            "n": nonce,
        }
    )
