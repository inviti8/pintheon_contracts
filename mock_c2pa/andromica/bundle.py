"""Produce the human-pasteable registration bundle Andromica shows to the
user at first-run. The user copies this bundle into the Portal's
`/dashboard/provenance/register` page; the Portal returns an
authorization token signed by the member's Stellar key.

Format follows C2PA.md §4.2 step 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class RegistrationBundle:
    app_address: str
    app_kind: str       # "Andromica" | "Inkternity" | "Pintheon" | "Other"
    fingerprint_hex: str
    pubkey_alg: str     # always "ed25519" for v1
    expires_at_iso: str
    expires_at_unix: int

    def to_text(self) -> str:
        """Render the bundle as the multi-line text the user copies."""
        return (
            "HVYM-CA-REG-v1\n"
            f"app_address:    {self.app_address}\n"
            f"app_kind:       {self.app_kind}\n"
            f"fingerprint:    {self.fingerprint_hex}\n"
            f"pubkey_alg:     {self.pubkey_alg}\n"
            f"expires_at:     {self.expires_at_iso}\n"
        )


def build_bundle(
    *,
    app_address: str,
    app_kind: str,
    fingerprint_bytes: bytes,
    expires_at_unix: int,
    pubkey_alg: str = "ed25519",
) -> RegistrationBundle:
    if app_kind not in {"Inkternity", "Andromica", "Pintheon", "Other"}:
        raise ValueError(f"unknown app_kind: {app_kind!r}")
    if len(fingerprint_bytes) != 32:
        raise ValueError("fingerprint_bytes must be exactly 32 bytes (SHA-256)")

    iso = datetime.fromtimestamp(expires_at_unix, tz=timezone.utc).isoformat(
        timespec="seconds"
    )
    return RegistrationBundle(
        app_address=app_address,
        app_kind=app_kind,
        fingerprint_hex=fingerprint_bytes.hex(),
        pubkey_alg=pubkey_alg,
        expires_at_iso=iso,
        expires_at_unix=expires_at_unix,
    )
