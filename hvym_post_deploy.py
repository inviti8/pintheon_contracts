#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from decimal import Decimal, ROUND_DOWN
from typing import Optional

# Network configurations (shared with deploy_contracts.py)
NETWORK_CONFIGS = {
    "testnet": {
        "passphrase": "Test SDF Network ; September 2015",
        "rpc_url": "https://soroban-testnet.stellar.org"
    },
    "futurenet": {
        "passphrase": "Test SDF Future Network ; October 2022",
        "rpc_url": "https://rpc-futurenet.stellar.org"
    },
    "public": {
        "passphrase": "Public Global Stellar Network ; September 2015",
        "rpc_url": "https://stellar-soroban-public.nodies.app"
    },
    "standalone": {
        "passphrase": "Standalone Network ; February 2017",
        "rpc_url": "http://localhost:8000"
    }
}

NETWORK = None
NETWORK_PASSPHRASE = None
RPC_URL = None

def resolve_network(cli_network: Optional[str] = None) -> str:
    """Resolve which network to use: CLI flag > env var > public (mainnet)."""
    global NETWORK, NETWORK_PASSPHRASE, RPC_URL

    if cli_network:
        network = cli_network
    elif os.environ.get("STELLAR_NETWORK"):
        network = os.environ["STELLAR_NETWORK"]
    else:
        network = "public"

    if network not in NETWORK_CONFIGS:
        print(f"Error: Unsupported network '{network}'. Supported: {', '.join(NETWORK_CONFIGS.keys())}")
        sys.exit(1)

    NETWORK = network
    NETWORK_PASSPHRASE = NETWORK_CONFIGS[network]["passphrase"]
    RPC_URL = os.environ.get("STELLAR_RPC_URL", NETWORK_CONFIGS[network]["rpc_url"])

    print(f"Using network: {NETWORK}")
    print(f"  RPC URL:    {RPC_URL}")
    print(f"  Passphrase: {NETWORK_PASSPHRASE}")
    return network

def load_deployments():
    if not os.path.isfile("deployments.json"):
        print("deployments.json not found. Run deployment first.")
        sys.exit(1)
    with open("deployments.json", "r") as f:
        return json.load(f)

def save_deployments(data):
    with open("deployments.json", "w") as f:
        json.dump(data, f, indent=2)

def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {' '.join(cmd)}\n{e.stdout}\n{e.stderr}")
        sys.exit(1)

def get_public_key(identity_name):
    """Get public key from Stellar CLI identity."""
    try:
        result = subprocess.run(
            ["stellar", "keys", "public-key", identity_name],
            capture_output=True,
            text=True,
            check=True
        )
        public_key = result.stdout.strip().splitlines()[-1]
        if not public_key.startswith('G'):
            raise ValueError(f"Invalid public key format: {public_key}")
        return public_key
    except subprocess.CalledProcessError as e:
        print(f"Failed to get public key for identity {identity_name}")
        print(f"Error: {e.stderr}")
        sys.exit(1)

# Maximum XLM that can be safely converted to u32 (4,294,967,295 stroops)
MAX_XLM_U32 = Decimal('429.4967295')

def xlm_to_stroops(xlm_amount):
    """Convert XLM to stroops with validation against u32 max."""
    try:
        amount = Decimal(str(xlm_amount))
        if amount > MAX_XLM_U32:
            print(f"Warning: Amount {xlm_amount} XLM exceeds maximum for u32. Capping at {MAX_XLM_U32} XLM")
            amount = MAX_XLM_U32

        stroops = (amount * Decimal('10000000')).quantize(Decimal('1.'), rounding=ROUND_DOWN)
        return str(int(stroops))
    except (ValueError, TypeError) as e:
        print(f"Error converting amount {xlm_amount} to stroops: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Fund hvym-collective and set opus token via CLI, updating deployments.json.")
    parser.add_argument("--deployer-acct", required=True, help="Stellar CLI account name or secret to use as source")
    parser.add_argument("--network", default=None, help="Network name (testnet, futurenet, public, standalone)")
    parser.add_argument("--fund-amount", required=True, type=float, help=f"Amount to fund hvym-collective contract (e.g. 30 XLM, max {MAX_XLM_U32} XLM)")
    parser.add_argument("--initial-opus-alloc", required=True, type=float, help=f"Initial opus token allocation (e.g. 10 XLM, max {MAX_XLM_U32} XLM)")
    args = parser.parse_args()

    # Resolve network from: CLI flag > STELLAR_NETWORK env var > public (mainnet)
    resolve_network(args.network)

    # Convert to stroops with validation
    fund_amount_stroops = xlm_to_stroops(args.fund_amount)
    initial_opus_alloc_stroops = xlm_to_stroops(args.initial_opus_alloc)

    print(f"Using fund amount: {args.fund_amount} XLM ({fund_amount_stroops} stroops)")
    print(f"Using initial opus allocation: {args.initial_opus_alloc} XLM ({initial_opus_alloc_stroops} stroops)")

    deployments = load_deployments()

    # Get hvym_collective contract ID
    hvym = deployments.get("hvym_collective", {})
    contract_id = hvym.get("contract_id")
    if not contract_id:
        print("hvym_collective contract_id not found in deployments.json")
        print("Available contracts:", ", ".join(deployments.keys()))
        sys.exit(1)

    # Get opus_token contract ID from deployments.json
    opus = deployments.get("opus_token", {})
    opus_contract_id = opus.get("contract_id")
    if not opus_contract_id:
        print("opus_token contract_id not found in deployments.json")
        print("Please run deploy_contracts.py first to deploy opus_token")
        sys.exit(1)

    # Fund contract
    print(f"\n=== Funding hvym_collective contract {contract_id} ===")
    fund_cmd = [
        "stellar", "contract", "invoke",
        "--id", contract_id,
        "--source", args.deployer_acct,
        "--rpc-url", RPC_URL,
        "--network-passphrase", NETWORK_PASSPHRASE,
        "--", "fund-contract",
        "--caller", get_public_key(args.deployer_acct),
        "--fund-amount", fund_amount_stroops
    ]
    fund_out = run_cmd(fund_cmd)
    print(fund_out)

    # Now set the opus token in the collective contract
    print(f"\n=== Setting opus token in hvym-collective {contract_id} ===")
    print(f"Using opus contract ID: {opus_contract_id}")
    set_opus_cmd = [
        "stellar", "contract", "invoke",
        "--id", contract_id,
        "--source", args.deployer_acct,
        "--rpc-url", RPC_URL,
        "--network-passphrase", NETWORK_PASSPHRASE,
        "--", "set-opus-token",
        "--caller", get_public_key(args.deployer_acct),
        "--opus-contract-id", opus_contract_id,
        "--initial-alloc", initial_opus_alloc_stroops
    ]
    set_opus_out = run_cmd(set_opus_cmd)
    print(set_opus_out)

    print(f"Successfully set opus token in hvym-collective")

if __name__ == "__main__":
    main()
