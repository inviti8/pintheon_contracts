#!/usr/bin/env python3
"""
stellar_accounts.py - Manage Stellar CLI identities for this repo.

Wraps the `stellar keys` CLI and adds helpers the deployment workflow needs
without adding a parallel keystore (we delegate to the CLI for storage).

Subcommands:
  create     Generate a new keypair via `stellar keys generate`.
  address    Print the G-address of a named identity.
  list       Print every CLI identity with its balance on the chosen network.
  fund       Show a QR code + SEP-0007 URI for external-wallet funding.
             On testnet, also tries Friendbot.
  balance    Print balances for a named identity.
  estimate   Estimate the XLM needed to upload+deploy a built contract.

Conventions match deploy_contracts.py:
  - --network testnet|public (default: public via STELLAR_NETWORK env or fallback)
  - delegated storage in the stellar CLI keystore (~/.config/stellar/identity)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional


# ── Network config (mirrors deploy_contracts.py) ───────────────────────────

NETWORK_CONFIGS = {
    "testnet": {
        "passphrase": "Test SDF Network ; September 2015",
        "rpc_url": "https://soroban-testnet.stellar.org",
        "horizon_url": "https://horizon-testnet.stellar.org",
        "friendbot_url": "https://friendbot.stellar.org",
        "explorer": "https://stellar.expert/explorer/testnet/account/",
    },
    "public": {
        "passphrase": "Public Global Stellar Network ; September 2015",
        "rpc_url": "https://stellar-soroban-public.nodies.app",
        "horizon_url": "https://horizon.stellar.org",
        "friendbot_url": None,
        "explorer": "https://stellar.expert/explorer/public/account/",
    },
}

REPO_ROOT = Path(__file__).parent.resolve()
WASM_DIR = REPO_ROOT / "wasm"


def resolve_network(cli_value: Optional[str]) -> str:
    """CLI flag > STELLAR_NETWORK env > 'public' (mainnet)."""
    network = cli_value or os.environ.get("STELLAR_NETWORK") or "public"
    if network not in NETWORK_CONFIGS:
        sys.exit(
            f"Unsupported network '{network}'. "
            f"Supported: {', '.join(NETWORK_CONFIGS)}"
        )
    return network


# ── Stellar CLI wrappers ───────────────────────────────────────────────────


def cli_keys_ls() -> list[str]:
    result = subprocess.run(
        ["stellar", "keys", "ls"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def cli_keys_address(name: str) -> str:
    result = subprocess.run(
        ["stellar", "keys", "address", name],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def cli_keys_generate(name: str, overwrite: bool = False) -> None:
    cmd = ["stellar", "keys", "generate", name]
    if overwrite:
        cmd.append("--overwrite")
    subprocess.run(cmd, check=True)


def cli_keys_fund_testnet(name: str) -> bool:
    """Friendbot-fund via the CLI's built-in helper. Testnet only."""
    try:
        subprocess.run(
            ["stellar", "keys", "fund", name, "--network", "testnet"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        # Already funded is success in our book.
        msg = (e.stderr or "") + (e.stdout or "")
        if "already exists" in msg.lower() or "createaccountalreadyexist" in msg.lower():
            return True
        print(f"  friendbot error: {msg.strip()}", file=sys.stderr)
        return False


# ── Horizon balance queries ────────────────────────────────────────────────


def fetch_account(public_key: str, horizon_url: str) -> Optional[dict]:
    url = f"{horizon_url}/accounts/{public_key}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def native_balance(account: dict) -> float:
    for b in account.get("balances", []):
        if b.get("asset_type") == "native":
            return float(b["balance"])
    return 0.0


# ── QR code rendering ──────────────────────────────────────────────────────


def _import_qrcode():
    try:
        import qrcode  # noqa: F401
    except ImportError:
        sys.exit(
            "qrcode package not installed. Run: pip install -r requirements.txt"
        )
    return __import__("qrcode")


def render_qr_ascii(data: str) -> None:
    qrcode = _import_qrcode()
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.make(fit=True)
    # invert=True gives dark modules on light terminal background, which scans
    # reliably with phone cameras against both light and dark terminal themes.
    qr.print_ascii(invert=True)


def render_qr_popup(data: str) -> Optional[str]:
    """Save the QR as a PNG and open it in the OS default image viewer.

    Returns the path to the saved file (so the user can re-open / share it),
    or None if popup failed and we fell back to ASCII.
    """
    qrcode = _import_qrcode()
    try:
        img = qrcode.make(data)  # PilImage when qrcode[pil] (Pillow) is installed
    except Exception as e:  # noqa: BLE001
        print(f"  (PIL unavailable: {e}; falling back to ASCII)\n", file=sys.stderr)
        render_qr_ascii(data)
        return None

    tmp = tempfile.NamedTemporaryFile(
        suffix=".png", prefix="stellar_qr_", delete=False
    )
    tmp.close()
    try:
        img.save(tmp.name)
    except Exception as e:  # noqa: BLE001
        print(f"  (could not save PNG: {e}; falling back to ASCII)\n", file=sys.stderr)
        render_qr_ascii(data)
        return None

    opened = False
    try:
        if sys.platform.startswith("win"):
            os.startfile(tmp.name)  # noqa: SIM115
            opened = True
        elif sys.platform == "darwin":
            subprocess.run(["open", tmp.name], check=False)
            opened = True
        else:
            # Most Linux desktop envs honor xdg-open.
            subprocess.run(["xdg-open", tmp.name], check=False)
            opened = True
    except Exception as e:  # noqa: BLE001
        print(f"  (could not launch image viewer: {e})", file=sys.stderr)

    if not opened:
        print(
            f"  (auto-open not available on this platform; "
            f"please open the file manually: {tmp.name})",
            file=sys.stderr,
        )

    return tmp.name


def build_sep0007_uri(
    destination: str,
    network_passphrase: str,
    amount: Optional[str] = None,
    memo: Optional[str] = None,
) -> str:
    """SEP-0007 web+stellar:pay URI. Supported by Lobstr, Freighter,
    Albedo, and most modern Stellar wallets."""
    params = {"destination": destination}
    if amount is not None:
        params["amount"] = amount
    if memo is not None:
        params["memo"] = memo
        params["memo_type"] = "MEMO_TEXT"
    params["network_passphrase"] = network_passphrase
    return "web+stellar:pay?" + urllib.parse.urlencode(params)


# ── Funding poll ───────────────────────────────────────────────────────────


def poll_for_funding(
    public_key: str,
    horizon_url: str,
    initial_balance: float,
    expected_amount: Optional[float] = None,
    timeout_s: int = 600,
    interval_s: int = 4,
) -> bool:
    """Poll Horizon until the account is funded or the balance increases.

    Returns True if funding was observed before the timeout, False otherwise.
    Ctrl+C exits cleanly and returns False.
    """
    start = time.monotonic()
    current = initial_balance
    print(
        f"Waiting for funding on {public_key[:8]}...{public_key[-6:]} "
        f"(timeout {timeout_s}s; Ctrl+C to skip)."
    )
    if expected_amount is not None:
        print(f"  Expecting at least {expected_amount:.4f} XLM delta.")

    try:
        while time.monotonic() - start < timeout_s:
            elapsed = int(time.monotonic() - start)
            try:
                acct = fetch_account(public_key, horizon_url)
            except Exception as e:  # noqa: BLE001
                # Transient Horizon errors are non-fatal; just keep polling.
                print(f"\r  [{elapsed:4d}s] horizon error: {e!s:.60}", end="", flush=True)
                time.sleep(interval_s)
                continue

            current = native_balance(acct) if acct else 0.0
            delta = current - initial_balance

            funded = False
            if initial_balance == 0.0 and current > 0.0:
                # Unprovisioned -> provisioned.
                funded = True
            elif expected_amount is not None:
                # Specific amount expected — accept once that delta arrives
                # (allow 1% tolerance for human-imprecise sends).
                if delta >= expected_amount * 0.99:
                    funded = True
            elif delta > 0:
                # Any positive delta counts when no expected amount given.
                funded = True

            if funded:
                # Clear status line, then summary.
                print("\r" + " " * 70, end="\r")
                print(f"  Funded. Balance: {current:.7f} XLM (delta {delta:+.7f}).")
                return True

            print(
                f"\r  [{elapsed:4d}s] balance: {current:.7f} XLM "
                f"(delta {delta:+.7f})  waiting...",
                end="",
                flush=True,
            )
            time.sleep(interval_s)
    except KeyboardInterrupt:
        print("\n  Polling cancelled by user.")
        return False

    print(
        f"\n  Timed out after {timeout_s}s. Current balance: {current:.7f} XLM."
    )
    return False


# ── Cost estimation ────────────────────────────────────────────────────────


def estimate_upload_fee_xlm(
    contract_name: str, network: str
) -> tuple[Optional[float], int, Optional[str]]:
    """Return (upload_fee_xlm, wasm_size_bytes, error_message).

    Builds an upload tx, simulates against the chosen Soroban RPC,
    and reads `min_resource_fee` from the simulation result.
    Does not submit anything.
    """
    wasm_path = WASM_DIR / f"{contract_name}.optimized.wasm"
    if not wasm_path.exists():
        return None, 0, (
            f"WASM not found: {wasm_path}\n"
            f"Build first: python build_contracts.py --contract <dir>"
        )
    wasm_bytes = wasm_path.read_bytes()
    wasm_size = len(wasm_bytes)

    cfg = NETWORK_CONFIGS[network]
    try:
        from stellar_sdk import (
            Account,
            Keypair,
            SorobanServer,
            TransactionBuilder,
        )
    except ImportError:
        return None, wasm_size, (
            "stellar-sdk not installed. "
            "Run: pip install stellar-sdk"
        )

    # Simulation doesn't actually validate source-account existence, so we
    # can use a deterministic ephemeral keypair (no funds needed).
    ephemeral = Keypair.random()
    source = Account(account=ephemeral.public_key, sequence=0)

    tx = (
        TransactionBuilder(
            source_account=source,
            network_passphrase=cfg["passphrase"],
            base_fee=100,
        )
        .append_upload_contract_wasm_op(contract=wasm_bytes)
        .set_timeout(30)
        .build()
    )

    server = SorobanServer(cfg["rpc_url"])
    try:
        sim = server.simulate_transaction(tx)
    except Exception as e:  # noqa: BLE001
        return None, wasm_size, f"simulate_transaction error: {e}"

    if getattr(sim, "error", None):
        return None, wasm_size, f"simulation failed: {sim.error}"

    # min_resource_fee is the Soroban-side fee in stroops (1 XLM = 10^7 stroops).
    fee_stroops = int(getattr(sim, "min_resource_fee", 0) or 0)
    return fee_stroops / 10_000_000.0, wasm_size, None


def load_registry_contract_id(network: str) -> Optional[str]:
    """Read hvym_registry's deployed contract_id from deployments.{network}.json."""
    path = REPO_ROOT / f"deployments.{network}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None
    entry = data.get("hvym_registry") or {}
    cid = entry.get("contract_id")
    return cid if isinstance(cid, str) and cid.startswith("C") else None


def load_contract_id(network: str, contract_name: str) -> Optional[str]:
    """Read any contract's deployed contract_id from deployments.{network}.json."""
    path = REPO_ROOT / f"deployments.{network}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None
    entry = data.get(contract_name) or {}
    cid = entry.get("contract_id")
    return cid if isinstance(cid, str) and cid.startswith("C") else None


def fetch_first_admin(registry_id: str, network: str) -> Optional[str]:
    """Query hvym_registry.get_admin_list and return the first admin G-address.

    Returns None on any failure.
    """
    cfg = NETWORK_CONFIGS[network]
    try:
        from stellar_sdk import (
            Account,
            Keypair,
            SorobanServer,
            TransactionBuilder,
            scval,
            xdr as stellar_xdr,
        )
    except ImportError:
        return None

    server = SorobanServer(cfg["rpc_url"])
    ephemeral = Keypair.random()
    source = Account(ephemeral.public_key, 0)
    tx = (
        TransactionBuilder(source, cfg["passphrase"], 100)
        .append_invoke_contract_function_op(
            contract_id=registry_id,
            function_name="get_admin_list",
            parameters=[],
        )
        .set_timeout(30)
        .build()
    )
    try:
        sim = server.simulate_transaction(tx)
    except Exception:  # noqa: BLE001
        return None
    if getattr(sim, "error", None) or not sim.results:
        return None
    raw_xdr = sim.results[0].xdr
    if not raw_xdr:
        return None
    try:
        sc_val = stellar_xdr.SCVal.from_xdr(raw_xdr)
        admins = scval.to_native(sc_val)
    except Exception:  # noqa: BLE001
        return None
    if not admins:
        return None
    first = admins[0]
    # to_native returns stellar_sdk Address objects; coerce to G-string.
    return getattr(first, "address", str(first))


def estimate_registry_set_fee_xlm(
    registry_id: str,
    admin_pub: str,
    contract_name: str,
    contract_id_to_register: str,
    network: str,
) -> tuple[Optional[float], Optional[str]]:
    """Simulate hvym_registry.set_contract_id and return (fee_xlm, error)."""
    cfg = NETWORK_CONFIGS[network]
    try:
        from stellar_sdk import (
            Account,
            SorobanServer,
            TransactionBuilder,
            scval,
        )
    except ImportError as e:
        return None, f"stellar-sdk not installed: {e}"

    network_variant = "Testnet" if network == "testnet" else "Mainnet"
    server = SorobanServer(cfg["rpc_url"])
    source = Account(admin_pub, 0)

    params = [
        scval.to_address(admin_pub),
        scval.to_string(contract_name),
        scval.to_enum(network_variant, None),
        scval.to_address(contract_id_to_register),
    ]
    tx = (
        TransactionBuilder(source, cfg["passphrase"], 100)
        .append_invoke_contract_function_op(
            contract_id=registry_id,
            function_name="set_contract_id",
            parameters=params,
        )
        .set_timeout(30)
        .build()
    )
    try:
        sim = server.simulate_transaction(tx)
    except Exception as e:  # noqa: BLE001
        return None, f"simulate_transaction error: {e}"
    if getattr(sim, "error", None):
        return None, f"simulation failed: {sim.error}"
    fee_stroops = int(getattr(sim, "min_resource_fee", 0) or 0)
    return fee_stroops / 10_000_000.0, None


# ── Subcommand handlers ────────────────────────────────────────────────────


def cmd_create(args: argparse.Namespace) -> int:
    network = resolve_network(args.network)
    cfg = NETWORK_CONFIGS[network]

    existing = cli_keys_ls()
    if args.name in existing and not args.overwrite:
        print(
            f"Identity '{args.name}' already exists. "
            f"Address: {cli_keys_address(args.name)}\n"
            "Pass --overwrite to replace it."
        )
        return 1

    cli_keys_generate(args.name, overwrite=args.overwrite)
    pub = cli_keys_address(args.name)
    print(f"Created '{args.name}'")
    print(f"  public key : {pub}")
    print(f"  network    : {network}")
    print(f"  explorer   : {cfg['explorer']}{pub}")
    print()
    print("Next:")
    print(
        f"  Fund:    python stellar_accounts.py fund --name {args.name} --network {network}"
    )
    print(
        f"  Balance: python stellar_accounts.py balance --name {args.name} --network {network}"
    )
    return 0


def cmd_address(args: argparse.Namespace) -> int:
    print(cli_keys_address(args.name))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    network = resolve_network(args.network)
    cfg = NETWORK_CONFIGS[network]
    identities = cli_keys_ls()
    if not identities:
        print("No identities in the stellar CLI keystore.")
        return 0

    print(f"Network: {network}  ({cfg['horizon_url']})")
    print()
    print(f"  {'NAME':<22} {'ADDRESS':<58} {'BALANCE':>15}")
    print(f"  {'-' * 22} {'-' * 58} {'-' * 15}")
    for name in identities:
        try:
            pub = cli_keys_address(name)
        except subprocess.CalledProcessError:
            print(f"  {name:<22} <unable to read>")
            continue
        acct = fetch_account(pub, cfg["horizon_url"])
        if acct is None:
            balance_str = "unfunded"
        else:
            balance_str = f"{native_balance(acct):.4f} XLM"
        print(f"  {name:<22} {pub:<58} {balance_str:>15}")
    return 0


def cmd_balance(args: argparse.Namespace) -> int:
    network = resolve_network(args.network)
    cfg = NETWORK_CONFIGS[network]
    pub = cli_keys_address(args.name)

    acct = fetch_account(pub, cfg["horizon_url"])
    if acct is None:
        print(f"{args.name} ({pub}) is not provisioned on {network}.")
        print(f"  Fund: python stellar_accounts.py fund --name {args.name} --network {network}")
        return 1

    print(f"{args.name} on {network}")
    print(f"  address : {pub}")
    for b in acct.get("balances", []):
        if b.get("asset_type") == "native":
            print(f"  XLM     : {float(b['balance']):.7f}")
        else:
            code = b.get("asset_code", "?")
            issuer = b.get("asset_issuer", "?")
            print(f"  {code:<8}: {float(b['balance']):.7f}  (issuer {issuer})")
    print(f"  explorer: {cfg['explorer']}{pub}")
    return 0


def cmd_fund(args: argparse.Namespace) -> int:
    network = resolve_network(args.network)
    cfg = NETWORK_CONFIGS[network]
    pub = cli_keys_address(args.name)

    # Snapshot the balance before funding, for the poll's delta calculation.
    initial_account = fetch_account(pub, cfg["horizon_url"])
    initial_balance = native_balance(initial_account) if initial_account else 0.0

    # Testnet: try friendbot first (free + automatic). If the caller passed
    # --no-friendbot, fall through to the QR path.
    if network == "testnet" and not args.no_friendbot:
        print(f"Friendbot funding {pub} on testnet...")
        if cli_keys_fund_testnet(args.name):
            acct = fetch_account(pub, cfg["horizon_url"])
            bal = native_balance(acct) if acct else 0.0
            print(f"  OK. Balance: {bal:.7f} XLM")
            return 0
        print("  Friendbot failed; falling back to QR.")

    # Otherwise (mainnet, or testnet --no-friendbot): show the QR.
    #
    # Default to a plain G-address QR — universally supported by every
    # Stellar wallet (the wallet just asks the user to type amount/memo).
    # SEP-0007 web+stellar:pay URIs are only honored by Lobstr in
    # practice; other wallets (Freighter, etc.) paste the raw URI string
    # into their address field, which is broken. Opt in via --sep0007.
    if args.sep0007:
        uri = build_sep0007_uri(
            destination=pub,
            network_passphrase=cfg["passphrase"],
            amount=args.amount,
            memo=args.memo,
        )
        qr_format_label = "SEP-0007 (web+stellar:pay) - Lobstr only"
    else:
        uri = pub
        qr_format_label = "plain G-address - works with any wallet"

    print(f"Funding identity : {args.name}")
    print(f"Network          : {network}")
    print(f"Destination      : {pub}")
    print(f"Current balance  : {initial_balance:.7f} XLM")
    print(f"QR encoding      : {qr_format_label}")
    if args.amount:
        print(f"Amount to send   : {args.amount} XLM")
    if args.memo:
        print(f"Memo to attach   : {args.memo}")
    print()
    if args.sep0007:
        print(
            "Scan with Lobstr (other wallets paste the URI text into the "
            "address field and break):"
        )
    else:
        print(
            "Scan with any Stellar wallet (Lobstr, Freighter, Albedo, "
            "Solar, ...). The wallet will prompt you for the amount and "
            "memo above."
        )
    print()

    if args.ascii:
        render_qr_ascii(uri)
        saved_path = None
    else:
        saved_path = render_qr_popup(uri)

    print()
    print(f"URI: {uri}")
    if saved_path:
        print(f"QR PNG: {saved_path}")
    print()

    if args.no_wait:
        print("Polling skipped (--no-wait). After funding, verify with:")
        print(
            f"  python stellar_accounts.py balance --name {args.name} --network {network}"
        )
        return 0

    expected = float(args.amount) if args.amount else None
    ok = poll_for_funding(
        public_key=pub,
        horizon_url=cfg["horizon_url"],
        initial_balance=initial_balance,
        expected_amount=expected,
        timeout_s=args.wait_timeout,
    )
    if not ok:
        print()
        print("Re-check later with:")
        print(
            f"  python stellar_accounts.py balance --name {args.name} --network {network}"
        )
        return 1
    print(f"  Explorer: {cfg['explorer']}{pub}")
    return 0


def cmd_estimate(args: argparse.Namespace) -> int:
    network = resolve_network(args.network)
    upload_xlm, wasm_size, err = estimate_upload_fee_xlm(args.contract, network)
    if err:
        print(err, file=sys.stderr)
        return 2

    # Soroban deploy itself is small relative to upload; the storage rent
    # on the persistent WASM blob is the dominant cost and is already
    # reflected in upload_xlm via min_resource_fee.
    deploy_buffer = 0.5      # XLM for the deploy op itself
    account_reserve = 1.0    # base XLM reserve to provision the account
    op_buffer = 1.5          # operational headroom for post-deploy admin calls

    register_xlm: Optional[float] = None
    register_note: Optional[str] = None
    if args.include_register:
        register_xlm, register_note = _estimate_register_into_hvym_registry(
            contract_name=args.contract,
            network=network,
        )

    total = (upload_xlm or 0.0) + deploy_buffer + account_reserve + op_buffer
    if register_xlm is not None:
        total += register_xlm

    print(f"Contract : {args.contract}")
    print(f"WASM     : {wasm_size} bytes ({wasm_size / 1024:.2f} KB)")
    print(f"Network  : {network}")
    print()
    print(f"  Upload fee (simulated)         : {upload_xlm:>10.4f} XLM")
    print(f"  Deploy op (estimate)           : {deploy_buffer:>10.4f} XLM")
    print(f"  Account base reserve           : {account_reserve:>10.4f} XLM")
    print(f"  Operational buffer             : {op_buffer:>10.4f} XLM")
    if register_xlm is not None:
        print(f"  hvym_registry set_contract_id  : {register_xlm:>10.4f} XLM")
    elif args.include_register and register_note:
        print(f"  hvym_registry set_contract_id  :  (skipped — {register_note})")
    print(f"  {'-' * 48}")
    print(f"  Recommended funding            : {total:>10.4f} XLM")
    print()
    print(
        "Notes: 'upload' / 'hvym_registry set_contract_id' fees come from "
        "live Soroban simulations; 'deploy op' / 'buffer' are flat estimates "
        "that have been empirically sufficient for the contracts in this "
        "repo. Round up generously for mainnet."
    )
    if args.include_register and register_xlm is None:
        print()
        print(
            "  hvym_registry register cost could not be simulated — see "
            "the skip reason above. The actual cost is typically <1 XLM on "
            "testnet and <5 XLM on mainnet for a single set_contract_id call."
        )
    return 0


def _estimate_register_into_hvym_registry(
    *,
    contract_name: str,
    network: str,
) -> tuple[Optional[float], Optional[str]]:
    """Wrapper that resolves registry_id + admin_pub + contract_id_to_register
    from local + on-chain state, then simulates the set_contract_id call.

    Returns (fee_xlm, skip_reason). Either fee_xlm or skip_reason is set.
    """
    registry_id = load_registry_contract_id(network)
    if not registry_id:
        return None, f"hvym_registry not in deployments.{network}.json"

    admin_pub = fetch_first_admin(registry_id, network)
    if not admin_pub:
        return None, "could not read admin list from on-chain hvym_registry"

    # The contract_id we'd register. If the target contract isn't deployed
    # yet, the registry-set fee is essentially independent of the bytes
    # being stored (all Stellar addresses are 32 bytes), so we use the
    # registry's own contract_id as a syntactically-valid placeholder.
    contract_id_to_register = (
        load_contract_id(network, contract_name) or registry_id
    )

    fee, err = estimate_registry_set_fee_xlm(
        registry_id=registry_id,
        admin_pub=admin_pub,
        contract_name=contract_name,
        contract_id_to_register=contract_id_to_register,
        network=network,
    )
    if err:
        return None, err
    return fee, None


# ── argparse plumbing ──────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage Stellar CLI identities for the hvym_contracts repo.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Generate a new keypair via the stellar CLI.")
    p_create.add_argument("--name", required=True, help="Identity name.")
    p_create.add_argument("--network", default=None, help="testnet|public (informational; affects suggested next-steps).")
    p_create.add_argument("--overwrite", action="store_true", help="Replace an existing identity of the same name.")
    p_create.set_defaults(func=cmd_create)

    p_addr = sub.add_parser("address", help="Print the G-address of a named identity.")
    p_addr.add_argument("--name", required=True)
    p_addr.set_defaults(func=cmd_address)

    p_list = sub.add_parser("list", help="List CLI identities with their balance on the chosen network.")
    p_list.add_argument("--network", default=None)
    p_list.set_defaults(func=cmd_list)

    p_bal = sub.add_parser("balance", help="Print balances for a named identity.")
    p_bal.add_argument("--name", required=True)
    p_bal.add_argument("--network", default=None)
    p_bal.set_defaults(func=cmd_balance)

    p_fund = sub.add_parser("fund", help="Friendbot (testnet) or QR-prompt (mainnet) funding.")
    p_fund.add_argument("--name", required=True)
    p_fund.add_argument("--network", default=None)
    p_fund.add_argument("--amount", default=None,
                        help="Expected XLM amount. Embeds in SEP-0007 URI and tightens the funding-detection threshold during polling.")
    p_fund.add_argument("--memo", default=None, help="Optional MEMO_TEXT for the SEP-0007 URI.")
    p_fund.add_argument("--sep0007", action="store_true",
                        help="Encode the QR as a SEP-0007 web+stellar:pay URI "
                             "(amount/memo pre-filled). Only Lobstr honors this "
                             "format reliably; other wallets paste the URI text "
                             "into the address field and break. Default QR is the "
                             "plain G-address, which every wallet accepts.")
    p_fund.add_argument("--no-friendbot", action="store_true",
                        help="On testnet, skip friendbot and show QR instead.")
    p_fund.add_argument("--ascii", action="store_true",
                        help="Render QR as ASCII in the terminal (default: open PNG in OS image viewer).")
    p_fund.add_argument("--no-wait", action="store_true",
                        help="Skip the post-QR funding poll and exit immediately.")
    p_fund.add_argument("--wait-timeout", type=int, default=600,
                        help="Seconds to wait for funding before giving up (default 600).")
    p_fund.set_defaults(func=cmd_fund)

    p_est = sub.add_parser("estimate", help="Estimate XLM needed to upload+deploy a contract.")
    p_est.add_argument("--contract", required=True, help="Contract name (matches wasm/<name>.optimized.wasm).")
    p_est.add_argument("--network", default=None)
    p_est.add_argument(
        "--include-register",
        action="store_true",
        help="Also simulate the hvym_registry.set_contract_id admin call "
             "that registers the deployed contract ID, and add its fee to "
             "the total. Reads hvym_registry's contract_id from "
             "deployments.{network}.json and the first admin from chain.",
    )
    p_est.set_defaults(func=cmd_estimate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
