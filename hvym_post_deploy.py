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
    parser = argparse.ArgumentParser(description="Fund hvym-collective and launch opus token via CLI, updating deployments.json.")
    parser.add_argument("--deployer-acct", required=True, help="Stellar CLI account name or secret to use as source")
    parser.add_argument("--network", default="testnet", help="Network name (default: testnet)")
    parser.add_argument("--fund-amount", required=True, type=float, help="Amount to fund hvym-collective contract (whole number, e.g. 30 XLM)")
    parser.add_argument("--initial-opus-alloc", required=True, type=float, help="Initial opus token allocation to mint to admin (whole number, e.g. 10 XLM)")
    args = parser.parse_args()

    # Convert to stroops (1 XLM = 10^7 stroops)
    fund_amount_stroops = str(int(args.fund_amount * 10**7))
    initial_opus_alloc_stroops = str(int(args.initial_opus_alloc * 10**7))

    deployments = load_deployments()
    hvym = deployments.get("hvym-collective", {})
    contract_id = hvym.get("contract_id")
    if not contract_id:
        print("hvym-collective contract_id not found in deployments.json")
        sys.exit(1)

    # Fund contract
    print(f"\n=== Funding hvym-collective contract {contract_id} ===")
    fund_cmd = [
        "stellar", "contract", "invoke",
        "--id", contract_id,
        "--source", args.deployer_acct,
        "--network", args.network,
        "--", "fund-contract",
        "--caller", args.deployer_acct,
        "--fund-amount", fund_amount_stroops
    ]
    fund_out = run_cmd(fund_cmd)
    print(fund_out)

    # Launch opus
    print(f"\n=== Launching opus token from hvym-collective {contract_id} ===")
    launch_cmd = [
        "stellar", "contract", "invoke",
        "--id", contract_id,
        "--source", args.deployer_acct,
        "--network", args.network,
        "--", "launch-opus",
        "--caller", args.deployer_acct,
        "--initial-alloc", initial_opus_alloc_stroops
    ]
    launch_out = run_cmd(launch_cmd)
    print(launch_out)
    opus_id = extract_last_nonempty_line(launch_out)
    if opus_id and len(opus_id) >= 56:
        deployments.setdefault("opus_token", {})["contract_id"] = opus_id
        save_deployments(deployments)
        print(f"Updated deployments.json with opus_token contract_id: {opus_id}")
    else:
        print("Could not extract opus_token contract ID from output.")

if __name__ == "__main__":
    main() 