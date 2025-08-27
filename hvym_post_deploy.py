#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys

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

def extract_last_nonempty_line(output):
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else None

def main():
    parser = argparse.ArgumentParser(description="Fund hvym-collective and set opus token via CLI, updating deployments.json.")
    parser.add_argument("--deployer-acct", required=True, help="Stellar CLI account name or secret to use as source")
    parser.add_argument("--deployer-pubkey", required=True, help="Public key of the deployer account (starts with 'G')")
    parser.add_argument("--network", default="testnet", help="Network name (default: testnet)")
    parser.add_argument("--fund-amount", required=True, type=float, help="Amount to fund hvym-collective contract (whole number, e.g. 30 XLM)")
    parser.add_argument("--initial-opus-alloc", required=True, type=float, help="Initial opus token allocation to mint to admin (whole number, e.g. 10 XLM)")
    args = parser.parse_args()

    # Convert to stroops (1 XLM = 10^7 stroops)
    fund_amount_stroops = str(int(args.fund_amount * 10**7))
    initial_opus_alloc_stroops = str(int(args.initial_opus_alloc * 10**7))

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
        "--source", args.deployer_acct,  # Uses identity name or secret key
        "--network", args.network,
        "--", "fund-contract",
        "--caller", args.deployer_pubkey,  # Uses the provided public key
        "--fund-amount", fund_amount_stroops
    ]
    fund_out = run_cmd(fund_cmd)
    print(fund_out)

    # Set opus token
    print(f"\n=== Setting opus token in hvym-collective {contract_id} ===")
    print(f"Using opus contract ID: {opus_contract_id}")
    set_opus_cmd = [
        "stellar", "contract", "invoke",
        "--id", contract_id,
        "--source", args.deployer_acct,  # Uses identity name or secret key
        "--network", args.network,
        "--", "set-opus-token",
        "--caller", args.deployer_pubkey,  # Uses the provided public key
        "--opus-contract-id", opus_contract_id,
        "--initial-alloc", initial_opus_alloc_stroops
    ]
    set_opus_out = run_cmd(set_opus_cmd)
    print(set_opus_out)
    
    print(f"Successfully set opus token in hvym-collective")

if __name__ == "__main__":
    main() 