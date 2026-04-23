#!/usr/bin/env python3
"""
Verify a local deployments.{network}.json file against the on-chain
hvym_registry contract, and optionally verify that the WASM currently on
ledger at each contract ID matches the repo's local wasm/ artifact.

This gives a three-way verification path:
  1. Registry contract IDs match the IDs recorded in the local file
  2. Local wasm/ bytes match the wasm_hash recorded in the local file
     (same check as verify_deployment_hashes.py — included for symmetry)
  3. ON-LEDGER wasm bytes at each contract_id match the local wasm/ bytes
     (only runs with --verify-wasm; requires the stellar CLI)

Exit codes:
  0  local file agrees with the registry (and wasm matches if --verify-wasm)
  1  at least one discrepancy found
  2  could not reach the registry / fatal error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Make the generated bindings importable regardless of where this script runs
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "bindings"))

from hvym_registry.bindings import (  # noqa: E402
    Client as RegistryClient,
    Network,
    NetworkKind,
)


# ── Network configuration ───────────────────────────────────────────────────
NETWORKS = {
    "testnet": {
        "rpc_url": "https://soroban-testnet.stellar.org",
        "passphrase": "Test SDF Network ; September 2015",
        "registry_kind": NetworkKind.Testnet,
        "default_deployments_file": "deployments.testnet.json",
        "expected_deployer_markers": ("TESTNET_DEPLOYER", "testnet"),
    },
    "public": {
        "rpc_url": "https://stellar-soroban-public.nodies.app",
        "passphrase": "Public Global Stellar Network ; September 2015",
        "registry_kind": NetworkKind.Mainnet,
        "default_deployments_file": "deployments.public.json",
        "expected_deployer_markers": ("lepus-luminary-1", "public"),
    },
}

# Contracts that are upload-only (no on-chain contract_id). They won't appear
# in the registry — don't flag them as missing.
UPLOAD_ONLY = {"pintheon_ipfs_token", "pintheon_node_token"}


def _decode_name(name) -> str:
    """ContractEntry.name comes back as bytes from the bindings; decode."""
    if isinstance(name, bytes):
        return name.decode("utf-8")
    return str(name)


def _address_str(addr) -> str:
    """Normalise a bindings Address/str into a bare G/C-string."""
    if isinstance(addr, str):
        return addr
    if hasattr(addr, "address"):
        return addr.address
    return str(addr)


def fetch_registry(
    contract_id: str, rpc_url: str, passphrase: str, network_kind: NetworkKind
) -> dict[str, str]:
    """Return {contract_name: contract_id} from the on-chain registry."""
    client = RegistryClient(
        contract_id=contract_id,
        rpc_url=rpc_url,
        network_passphrase=passphrase,
    )
    tx = client.get_all_contracts(network=Network(network_kind))
    tx.simulate()
    entries = tx.result()
    out: dict[str, str] = {}
    for entry in entries:
        out[_decode_name(entry.name)] = _address_str(entry.contract_id)
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_ledger_wasm(
    contract_id: str | None,
    wasm_hash: str | None,
    rpc_url: str,
    passphrase: str,
) -> bytes:
    """Download WASM bytes currently on ledger via `stellar contract fetch`.

    Exactly one of contract_id / wasm_hash must be provided. Uses a temp file
    for the CLI output to avoid any stdout-encoding issues on Windows.
    """
    if (contract_id is None) == (wasm_hash is None):
        raise ValueError("fetch_ledger_wasm: pass exactly one of contract_id/wasm_hash")

    cmd = [
        "stellar", "contract", "fetch",
        "--rpc-url", rpc_url,
        "--network-passphrase", passphrase,
    ]
    if contract_id:
        cmd += ["--id", contract_id]
    else:
        cmd += ["--wasm-hash", wasm_hash]

    with tempfile.NamedTemporaryFile(suffix=".wasm", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    cmd += ["-o", str(tmp_path)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(
                f"stellar contract fetch failed (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return tmp_path.read_bytes()
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def load_local(path: Path) -> dict:
    if not path.is_file():
        print(f"ERROR: deployments file not found: {path}", file=sys.stderr)
        sys.exit(2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compare(
    local: dict,
    registry: dict[str, str],
    network_key: str,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (mismatches, missing_locally, missing_from_registry, suspicious_meta)."""
    cfg = NETWORKS[network_key]
    expected_deployer, expected_network_marker = cfg["expected_deployer_markers"]

    # Extract contract_id rows from local file
    local_contracts: dict[str, dict] = {}
    for k, v in local.items():
        if isinstance(v, dict) and ("wasm_hash" in v or "contract_id" in v):
            local_contracts[k] = v

    mismatches: list[str] = []
    missing_locally: list[str] = []
    missing_from_registry: list[str] = []
    suspicious_meta: list[str] = []

    # 1. Suspicious metadata in local rows (wrong 'network' / 'deployer' for this file)
    for name, row in local_contracts.items():
        row_network = row.get("network", "")
        row_deployer = row.get("deployer", "")
        issues: list[str] = []
        if row_network and row_network != expected_network_marker:
            issues.append(f'network="{row_network}" (expected "{expected_network_marker}")')
        if row_deployer and row_deployer != expected_deployer:
            # Skip the flagging for upload-only rows if they were cloned from testnet
            # data; they are still suspicious but worth surfacing distinctly.
            issues.append(f'deployer="{row_deployer}" (expected "{expected_deployer}")')
        if issues:
            suspicious_meta.append(f"  {name}: " + "; ".join(issues))

    # 2. Compare contract IDs row-by-row
    for name, row in local_contracts.items():
        local_id = (row.get("contract_id") or "").strip()
        reg_id = registry.get(name)

        if name in UPLOAD_ONLY:
            # Upload-only contracts: expect no contract_id locally, and not in registry
            if local_id and local_id != "Upload only":
                mismatches.append(
                    f"  {name}: upload-only contract but local has contract_id={local_id!r}"
                )
            continue

        if local_id and reg_id is None:
            missing_from_registry.append(f"  {name}: local={local_id}, registry=<not registered>")
            continue

        if not local_id and reg_id is not None:
            missing_locally.append(f"  {name}: registry={reg_id}, local=<empty>")
            continue

        if local_id and reg_id and local_id != reg_id:
            mismatches.append(f"  {name}:\n      local    = {local_id}\n      registry = {reg_id}")

    # 3. Contracts in registry that local file does not mention at all
    for name, reg_id in registry.items():
        if name not in local_contracts:
            missing_locally.append(f"  {name}: registry={reg_id} (no entry in local file)")

    return mismatches, missing_locally, missing_from_registry, suspicious_meta


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a local deployments file against the on-chain hvym_registry.",
    )
    parser.add_argument(
        "--network",
        required=True,
        choices=sorted(NETWORKS.keys()),
        help="Network to verify against (public = mainnet).",
    )
    parser.add_argument(
        "--registry-id",
        required=True,
        help="Contract ID of the deployed hvym_registry instance on the chosen network.",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Local deployments file to verify. Default: deployments.{network}.json.",
    )
    parser.add_argument(
        "--rpc-url",
        default=None,
        help="Override the RPC URL (also honours STELLAR_RPC_URL env var).",
    )
    parser.add_argument(
        "--verify-wasm",
        action="store_true",
        help="Also fetch the WASM currently on ledger for each registered "
             "contract and compare its sha256 to the local wasm/ file. "
             "Requires the stellar CLI in PATH.",
    )
    parser.add_argument(
        "--wasm-dir",
        default="wasm",
        help="Directory containing optimized .wasm files for on-ledger "
             "verification. Default: ./wasm.",
    )
    args = parser.parse_args()

    cfg = NETWORKS[args.network]
    rpc_url = args.rpc_url or os.environ.get("STELLAR_RPC_URL") or cfg["rpc_url"]
    local_path = Path(args.file) if args.file else REPO_ROOT / cfg["default_deployments_file"]

    print(f"Network         : {args.network} ({cfg['passphrase']})")
    print(f"RPC URL         : {rpc_url}")
    print(f"Registry        : {args.registry_id}")
    print(f"Local file      : {local_path}")
    print()

    try:
        registry = fetch_registry(
            args.registry_id, rpc_url, cfg["passphrase"], cfg["registry_kind"]
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not fetch from registry: {exc}", file=sys.stderr)
        return 2

    print(f"Registry reports {len(registry)} contract(s):")
    for name in sorted(registry):
        print(f"  {name:<30} {registry[name]}")
    print()

    local = load_local(local_path)
    mismatches, missing_locally, missing_from_registry, suspicious_meta = compare(
        local, registry, args.network
    )

    any_issues = False

    if suspicious_meta:
        any_issues = True
        print("Suspicious metadata (wrong network/deployer in local file):")
        for line in suspicious_meta:
            print(line)
        print()

    if mismatches:
        any_issues = True
        print("MISMATCHED contract IDs:")
        for line in mismatches:
            print(line)
        print()

    if missing_from_registry:
        any_issues = True
        print("In local file but NOT registered on-chain:")
        for line in missing_from_registry:
            print(line)
        print()

    if missing_locally:
        any_issues = True
        print("On-chain but missing / empty in local file:")
        for line in missing_locally:
            print(line)
        print()

    if args.verify_wasm:
        wasm_issues = verify_wasm_on_ledger(
            registry=registry,
            local=local,
            wasm_dir=REPO_ROOT / args.wasm_dir,
            rpc_url=rpc_url,
            passphrase=cfg["passphrase"],
        )
        if wasm_issues:
            any_issues = True

    if any_issues:
        print("RESULT: discrepancies found.")
        return 1

    print("RESULT: local file agrees with on-chain registry.")
    if args.verify_wasm:
        print("        on-ledger WASM matches local wasm/ artifacts.")
    return 0


def verify_wasm_on_ledger(
    registry: dict[str, str],
    local: dict,
    wasm_dir: Path,
    rpc_url: str,
    passphrase: str,
) -> bool:
    """Fetch on-ledger WASM for each registry entry and compare to local wasm/.

    Also verifies upload-only contracts (pintheon_*_token) by fetching the
    wasm_hash recorded in the local file directly from ledger. Returns True
    if any discrepancy was found.
    """
    print("=" * 70)
    print("On-ledger WASM verification")
    print("=" * 70)

    issues = False

    # 1. Contracts with an on-chain contract_id: fetch by ID
    for name, contract_id in sorted(registry.items()):
        local_wasm_path = wasm_dir / f"{name}.optimized.wasm"

        if not local_wasm_path.is_file():
            print(f"  {name}: local WASM missing at {local_wasm_path} — skipped")
            issues = True
            continue

        local_hash = _sha256_file(local_wasm_path)

        try:
            ledger_bytes = fetch_ledger_wasm(
                contract_id=contract_id,
                wasm_hash=None,
                rpc_url=rpc_url,
                passphrase=passphrase,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  {name} ({contract_id}): FETCH FAILED — {exc}")
            issues = True
            continue

        ledger_hash = _sha256_bytes(ledger_bytes)

        if ledger_hash == local_hash:
            print(f"  {name:<28} OK  ({local_hash})")
        else:
            issues = True
            print(f"  {name:<28} MISMATCH")
            print(f"      local  wasm/{name}.optimized.wasm sha256 = {local_hash}")
            print(f"      ledger {contract_id}                      = {ledger_hash}")

    # 2. Upload-only contracts: verify the recorded wasm_hash is present on ledger
    for name in sorted(UPLOAD_ONLY):
        row = local.get(name)
        if not isinstance(row, dict):
            continue
        recorded_hash = (row.get("wasm_hash") or "").strip()
        if not recorded_hash:
            continue
        local_wasm_path = wasm_dir / f"{name}.optimized.wasm"
        local_hash = _sha256_file(local_wasm_path) if local_wasm_path.is_file() else None

        try:
            ledger_bytes = fetch_ledger_wasm(
                contract_id=None,
                wasm_hash=recorded_hash,
                rpc_url=rpc_url,
                passphrase=passphrase,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:<28} upload-only: not found on ledger ({exc})")
            issues = True
            continue

        ledger_hash = _sha256_bytes(ledger_bytes)
        tag = "OK"
        detail = f"ledger={ledger_hash}"
        if local_hash and local_hash != ledger_hash:
            tag = "MISMATCH (local wasm differs)"
            detail = f"local={local_hash}, ledger={ledger_hash}"
            issues = True
        elif local_hash is None:
            tag = "OK (local wasm missing, cannot compare)"
        print(f"  {name:<28} {tag}  {detail}")

    print()
    return issues


if __name__ == "__main__":
    sys.exit(main())
