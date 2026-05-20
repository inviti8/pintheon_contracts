"""End-to-end mock of the C2PA app-CA registration flow.

Two modes:

  --mode dry-run    Generates the CA + leaf, builds the registration bundle,
                    has the Portal mock sign an authorization token, locally
                    verifies the signature round-trips, and prints the
                    SCVal-encoded arguments that WOULD be sent to
                    `register_app_ca`. No network, no contract.

  --mode testnet    Friendbot-funds the mock keypairs if needed, reads
                    hvym_cert_registry's contract_id from
                    deployments.testnet.json, submits `register_app_ca`,
                    and reads back via `get_app_ca` + `is_trusted`.

Run from repo root:

    python -m mock_c2pa.run_mock_flow --mode dry-run
    python -m mock_c2pa.run_mock_flow --mode testnet --app-kind Andromica
"""

from __future__ import annotations

import argparse
import datetime
import json
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from mock_c2pa import canonical
from mock_c2pa.andromica import bundle as bundle_mod
from mock_c2pa.andromica import ca_generation
from mock_c2pa.keystore import friendbot_fund, load_or_create
from mock_c2pa.portal_mock import mint_token


REPO_ROOT = Path(__file__).parent.parent
DEPLOYMENTS_TESTNET = REPO_ROOT / "deployments.testnet.json"


def _print_header(s: str) -> None:
    print()
    print("=" * 72)
    print(s)
    print("=" * 72)


def _load_testnet_contract_id() -> str:
    if not DEPLOYMENTS_TESTNET.exists():
        sys.exit(
            f"deployments.testnet.json not found at {DEPLOYMENTS_TESTNET}.\n"
            "Deploy hvym-cert-registry to testnet first."
        )
    data = json.loads(DEPLOYMENTS_TESTNET.read_text())
    entry = data.get("hvym_cert_registry")
    if not entry or not entry.get("contract_id"):
        sys.exit(
            "deployments.testnet.json does not contain a hvym_cert_registry.contract_id.\n"
            "Run: python deploy_contracts.py --contract hvym-cert-registry --network testnet"
        )
    return entry["contract_id"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mock the C2PA app-CA registration end-to-end."
    )
    parser.add_argument(
        "--mode",
        choices=["dry-run", "testnet"],
        default="dry-run",
        help="dry-run: no network. testnet: submit register_app_ca to testnet.",
    )
    parser.add_argument(
        "--app-kind",
        choices=["Inkternity", "Andromica", "Pintheon", "Other"],
        default="Andromica",
        help="AppKind enum value to register under.",
    )
    parser.add_argument(
        "--app-name",
        default=None,
        help="Cert CN prefix. Defaults to --app-kind.",
    )
    parser.add_argument(
        "--valid-days",
        type=int,
        default=3650,
        help="CA cert validity in days (default: 10 years).",
    )
    parser.add_argument(
        "--skip-friendbot",
        action="store_true",
        help="In testnet mode, do not call Friendbot; assume accounts are funded.",
    )
    args = parser.parse_args()
    app_name = args.app_name or args.app_kind

    # ── 1. Mock keypairs (gitignored persistence) ──────────────────────────
    _print_header("1. Mock keypairs")
    ks = load_or_create()
    print(f"  App Stellar address    : {ks.app_address}")
    print(f"  Member Stellar address : {ks.member_address}")
    print(f"  Member raw pubkey hex  : {ks.member.raw_public_key().hex()}")

    # ── 2. Generate the app CA ─────────────────────────────────────────────
    _print_header("2. Generate Ed25519 self-signed CA (per C2PA.md section4.2)")
    app_ca = ca_generation.generate_app_ca(
        app_name=app_name,
        app_stellar_address=ks.app_address,
        valid_days=args.valid_days,
    )
    fingerprint = app_ca.fingerprint_sha256
    expires_at = app_ca.expires_at_unix
    print(f"  CA cert subject CN     : {app_ca.cert.subject.rfc4514_string()}")
    print(f"  DER size               : {len(app_ca.der_bytes)} bytes")
    print(f"  SHA-256 fingerprint    : {fingerprint.hex()}")
    print(
        "  notAfter (UTC)         : "
        f"{app_ca.cert.not_valid_after_utc.isoformat()}  (unix {expires_at})"
    )
    print(f"  CA public key (raw)    : {app_ca.public_key_raw.hex()}")

    # ── 3. Build the registration bundle (what the user pastes) ────────────
    _print_header("3. Registration bundle (paste this into the Portal)")
    reg_bundle = bundle_mod.build_bundle(
        app_address=ks.app_address,
        app_kind=args.app_kind,
        fingerprint_bytes=fingerprint,
        expires_at_unix=expires_at,
    )
    print(reg_bundle.to_text())

    # ── 4. Portal mock signs the authorization payload ─────────────────────
    _print_header("4. Portal mints the authorization token")
    nonce = secrets.randbits(64)
    token = mint_token.mint_register_token(
        member_keypair=ks.member,
        app_address=ks.app_address,
        app_kind=args.app_kind,
        fingerprint=fingerprint,
        expires_at=expires_at,
        nonce=nonce,
    )
    print(f"  nonce                  : {nonce}")
    print(f"  payload bytes ({len(token.payload)}):")
    print(f"    {token.payload.decode()}")
    print(f"  signature (hex)        : {token.signature.hex()}")
    print(f"  wire format            : {token.wire[:80]}...")

    # ── 5. Round-trip verify: contract spec <=> Portal mock agree ────────────
    _print_header("5. Round-trip self-verification")
    expected = canonical.register_payload(
        app_address=ks.app_address,
        member_pubkey=ks.member.raw_public_key(),
        app_kind=args.app_kind,
        fingerprint=fingerprint,
        expires_at=expires_at,
        nonce=nonce,
    )
    if expected != token.payload:
        print("  FAIL: canonical payload mismatch between Portal mock and spec module")
        return 1
    print("  canonical bytes match : OK (Portal mock <=> canonical.py)")

    # Verify the signature locally before paying gas to submit.
    member_pub = Ed25519PublicKey.from_public_bytes(ks.member.raw_public_key())
    try:
        member_pub.verify(token.signature, token.payload)
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL: signature does not verify locally: {e}")
        return 1
    print("  signature verifies     : OK (ed25519 over canonical payload)")

    # Verify CA cert self-signature.
    chain_ok, reason = ca_generation.verify_chain(
        leaf_der=app_ca.der_bytes, ca_der=app_ca.der_bytes
    )
    # The CA verifies against itself (self-signed). For a real leaf+CA chain
    # check, see issue_member_leaf below.
    if not chain_ok:
        print(f"  WARN: CA self-signature check: {reason}")
    else:
        print("  CA self-signature      : OK")

    # ── 6. Issue an ephemeral member leaf (C2PA.md section4.3) ───────────────────
    _print_header("6. Issue ephemeral member leaf cert")
    leaf = ca_generation.issue_member_leaf(
        app_ca=app_ca,
        member_name="MockMember",
        member_stellar_address=ks.member_address,
        member_canon_url=f"https://heavymeta.art/profile/MockMember",
        valid_hours=24,
    )
    chain_ok, reason = ca_generation.verify_chain(
        leaf_der=leaf.der_bytes, ca_der=app_ca.der_bytes
    )
    if not chain_ok:
        print(f"  FAIL: leaf-CA chain does not verify: {reason}")
        return 1
    print(f"  leaf cert subject CN   : {leaf.cert.subject.rfc4514_string()}")
    print(f"  leaf DER size          : {len(leaf.der_bytes)} bytes")
    print("  leaf -> CA chain       : OK")

    # ── 7. Either submit to testnet, or dry-run print SCVal args ───────────
    if args.mode == "dry-run":
        _print_header("7. Dry-run: arguments that WOULD be sent to register_app_ca")
        print(f"  app_address     : {ks.app_address}")
        print(f"  member_pubkey   : {ks.member.raw_public_key().hex()}")
        print(f"  app_kind        : {args.app_kind}")
        print(f"  fingerprint     : {fingerprint.hex()}")
        print(f"  pubkey_alg      : ed25519")
        print(f"  expires_at      : {expires_at}")
        print(f"  nonce           : {nonce}")
        print(f"  auth_payload    : {token.payload.decode()}")
        print(f"  auth_signature  : {token.signature.hex()}")
        print()
        print("  All local checks passed. To submit on chain:")
        print("    python -m mock_c2pa.run_mock_flow --mode testnet "
              f"--app-kind {args.app_kind}")
        return 0

    # testnet mode
    _print_header("7. Testnet submission")
    if not args.skip_friendbot:
        print("  Friendbot-funding app keypair...")
        if not friendbot_fund(ks.app_address):
            print(f"    FAIL: could not fund {ks.app_address}")
            return 1
        print("    OK")
        print("  Friendbot-funding member keypair...")
        if not friendbot_fund(ks.member_address):
            print(f"    FAIL: could not fund {ks.member_address}")
            return 1
        print("    OK")

    contract_id = _load_testnet_contract_id()
    print(f"  hvym_cert_registry id  : {contract_id}")

    from mock_c2pa import register

    result = register.submit_register(
        rpc_url=register.TESTNET_RPC,
        network_passphrase=register.TESTNET_PASSPHRASE,
        contract_id=contract_id,
        app_keypair=ks.app,
        member_pubkey=ks.member.raw_public_key(),
        app_kind=args.app_kind,
        fingerprint=fingerprint,
        expires_at=expires_at,
        nonce=nonce,
        auth_payload=token.payload,
        auth_signature=token.signature,
    )
    print(f"  tx hash                : {result.hash}")
    print(f"  status                 : {result.status}")
    if not result.success:
        print(f"  FAIL: {result.error}")
        return 1
    print("  register_app_ca submitted successfully.")

    _print_header("8. Read-back verification")
    trusted = register.is_trusted(
        rpc_url=register.TESTNET_RPC,
        network_passphrase=register.TESTNET_PASSPHRASE,
        contract_id=contract_id,
        source_pub=ks.app_address,
        app_address=ks.app_address,
        fingerprint=fingerprint,
    )
    print(f"  is_trusted(app, fp)    : {trusted}")
    raw = register.get_app_ca_raw(
        rpc_url=register.TESTNET_RPC,
        network_passphrase=register.TESTNET_PASSPHRASE,
        contract_id=contract_id,
        source_pub=ks.app_address,
        app_address=ks.app_address,
    )
    print(f"  get_app_ca raw         : {raw}")

    return 0 if trusted else 1


if __name__ == "__main__":
    raise SystemExit(main())
