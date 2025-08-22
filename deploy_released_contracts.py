#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import glob
import json
import requests
import re

CONTRACTS = {
    "pintheon-ipfs-token": "pintheon-ipfs-token",
    "pintheon-node-token": "pintheon-node-token",
    "opus-token": "opus-token",
    "hvym-collective": "hvym-collective",
}
CONTRACT_ORDER = list(CONTRACTS.keys())

DEPLOYMENTS_FILE = "deployments.json"
DEPLOYMENTS_MD = "deployments.md"

UPLOAD_ONLY_CONTRACTS = [
    "pintheon-ipfs-token",
    "pintheon-node-token"
]
DEPLOY_ONLY_CONTRACTS = [
    "opus-token",
    "hvym-collective"
]

def find_wasm_file(contract_key, release_dir):
    """Find the WASM file for the given contract in the release directory."""
    wasm_pattern = os.path.join(release_dir, f"{contract_key}_v*.wasm")
    wasm_files = glob.glob(wasm_pattern)
    if not wasm_files:
        print(f"No WASM file found for {contract_key} in {release_dir}")
        print(f"Expected file pattern: {wasm_pattern}")
        sys.exit(1)
    return wasm_files[0]

def run_cmd(cmd, cwd=None, capture_output=True):
    """Run a shell command and return its output."""
    try:
        result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=capture_output, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {' '.join(cmd)}")
        print(e.stdout)
        print(e.stderr)
        sys.exit(1)

def load_deployments():
    """Load existing deployments from deployments.json."""
    if os.path.isfile(DEPLOYMENTS_FILE):
        with open(DEPLOYMENTS_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}

def save_deployments(data):
    """Save deployments to deployments.json and update deployments.md."""
    with open(DEPLOYMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    save_deployments_md(data)

def save_deployments_md(data):
    """Generate deployments.md with a markdown table of deployment details."""
    lines = [
        "# Soroban Contract Deployments\n",
        "| Contract Name | WASM File | WASM Hash | Contract ID |",
        "|--------------|-----------|--------------------------------------------------------------|----------------------------------------------------------|"
    ]
    for contract, info in data.items():
        lines.append(f"| `{contract}` | `{info.get('wasm_file', '')}` | `{info.get('wasm_hash', '')}` | `{info.get('contract_id', '') or 'N/A'}` |")
    with open(DEPLOYMENTS_MD, "w") as f:
        f.write("\n".join(lines) + "\n")

def upload_and_deploy(contract_key, release_dir, deployer_acct, network, deployments, constructor_args=None):
    """Upload and deploy a contract to the Stellar network."""
    print(f"\n=== Uploading and deploying {contract_key} ===")
    wasm_file = find_wasm_file(contract_key, release_dir)
    wasm_file_rel = os.path.basename(wasm_file)
    # Upload
    print(f"Uploading {wasm_file_rel} ...")
    upload_cmd = [
        "stellar", "contract", "upload",
        "--source", deployer_acct,
        "--wasm", wasm_file,
        "--network", network
    ]
    upload_out = run_cmd(upload_cmd)
    # Extract WASM hash
    lines = [line.strip() for line in upload_out.splitlines() if line.strip()]
    wasm_hash = None
    if lines:
        last_line = lines[-1]
        if len(last_line) == 64 and all(c in '0123456789abcdefABCDEF' for c in last_line):
            wasm_hash = last_line
    if not wasm_hash:
        print(f"Could not extract WASM hash from upload output:\n{upload_out}")
        sys.exit(1)
    print(f"WASM hash: {wasm_hash}")
    # Deploy
    print(f"Deploying contract with hash {wasm_hash} ...")
    deploy_cmd = [
        "stellar", "contract", "deploy",
        "--wasm-hash", wasm_hash,
        "--source", deployer_acct,
        "--network", network
    ]
    if constructor_args:
        deploy_cmd.append("--")
        deploy_cmd.extend(constructor_args)
    deploy_out = run_cmd(deploy_cmd)
    # Extract contract ID
    deploy_lines = [line.strip() for line in deploy_out.splitlines() if line.strip()]
    contract_id = None
    if deploy_lines:
        last_line = deploy_lines[-1]
        if len(last_line) == 56 and last_line.isalnum() and last_line.isupper():
            contract_id = last_line
    if not contract_id:
        print(f"Could not extract contract ID from deploy output:\n{deploy_out}")
        sys.exit(1)
    print(f"Contract ID: {contract_id}")
    # Update deployments
    deployments[contract_key] = {
        "wasm_file": wasm_file_rel,
        "wasm_hash": wasm_hash,
        "contract_id": contract_id
    }
    save_deployments(deployments)
    print(f"Updated {DEPLOYMENTS_FILE} with {contract_key}")

def upload_only(contract_key, release_dir, deployer_acct, network, deployments):
    """Upload a contract WASM file without deploying."""
    print(f"\n=== Uploading {contract_key} (upload only, no deploy) ===")
    wasm_file = find_wasm_file(contract_key, release_dir)
    wasm_file_rel = os.path.basename(wasm_file)
    print(f"Uploading {wasm_file_rel} ...")
    upload_cmd = [
        "stellar", "contract", "upload",
        "--source", deployer_acct,
        "--wasm", wasm_file,
        "--network", network
    ]
    upload_out = run_cmd(upload_cmd)
    lines = [line.strip() for line in upload_out.splitlines() if line.strip()]
    wasm_hash = None
    if lines:
        last_line = lines[-1]
        if len(last_line) == 64 and all(c in '0123456789abcdefABCDEF' for c in last_line):
            wasm_hash = last_line
    if not wasm_hash:
        print(f"Could not extract WASM hash from upload output:\n{upload_out}")
        sys.exit(1)
    print(f"WASM hash: {wasm_hash}")
    deployments[contract_key] = {
        "wasm_file": wasm_file_rel,
        "wasm_hash": wasm_hash,
        "contract_id": None
    }
    save_deployments(deployments)
    print(f"Updated {DEPLOYMENTS_FILE} with {contract_key}")

def load_args_from_json(contract_key):
    """Load constructor arguments from a JSON file."""
    json_file = f"{contract_key}_args.json"
    if not os.path.isfile(json_file):
        print(f"Warning: No argument file found for {contract_key} (expected {json_file}), no constructor args will be used.")
        return []
    with open(json_file, "r") as f:
        data = json.load(f)
    args = []
    if contract_key == "hvym-collective":
        for key in ["join_fee", "mint_fee", "reward"]:
            if key in data:
                try:
                    data[key] = int(float(data[key]) * 10_000_000)
                except Exception as e:
                    print(f"Error converting {key} to stroops: {e}")
                    sys.exit(1)
    for k, v in data.items():
        args.append(f"--{k.replace('_', '-')}")
        args.append(str(v))
    return args

def main():
    parser = argparse.ArgumentParser(description="Deploy Soroban contracts from GitHub release assets using Stellar CLI.")
    parser.add_argument(
        "--deployer-acct",
        required=True,
        help="Stellar CLI secret key for the deployer account",
    )
    parser.add_argument(
        "--network",
        required=True,
        help="Network name for deployment (e.g., testnet, mainnet)",
    )
    parser.add_argument(
        "--contract",
        type=str,
        help="Target a specific contract by short name",
    )
    parser.add_argument(
        "--release-dir",
        default="release-wasm",
        help="Directory containing released WASM files (default: release-wasm)",
    )
    args = parser.parse_args()

    # Validate network
    valid_networks = ["testnet", "mainnet", "futurenet"]
    if args.network not in valid_networks:
        print(f"Invalid network: {args.network}. Valid options: {', '.join(valid_networks)}")
        sys.exit(1)

    # Ensure release directory exists
    if not os.path.isdir(args.release_dir):
        print(f"Release directory {args.release_dir} does not exist.")
        sys.exit(1)

    deployments = load_deployments()
    constructor_args = None if args.contract else None
    if args.contract:
        if args.contract not in CONTRACTS:
            print(f"Contract '{args.contract}' not in deploy list. Valid options:")
            for c in CONTRACT_ORDER:
                print(f"  {c}")
            sys.exit(1)
        constructor_args = load_args_from_json(args.contract)
        if '--admin' not in constructor_args:
            constructor_args = constructor_args + ['--admin', args.deployer_acct]
        if args.contract in UPLOAD_ONLY_CONTRACTS:
            upload_only(args.contract, args.release_dir, args.deployer_acct, args.network, deployments)
        elif args.contract in DEPLOY_ONLY_CONTRACTS:
            upload_and_deploy(args.contract, args.release_dir, args.deployer_acct, args.network, deployments, constructor_args)
        else:
            print(f"Contract '{args.contract}' is not configured for upload or deploy.")
            sys.exit(1)
    else:
        for contract_key in CONTRACT_ORDER:
            per_contract_args = constructor_args if constructor_args is not None else load_args_from_json(contract_key)
            if '--admin' not in per_contract_args:
                per_contract_args = per_contract_args + ['--admin', args.deployer_acct]
            if contract_key in UPLOAD_ONLY_CONTRACTS:
                upload_only(contract_key, args.release_dir, args.deployer_acct, args.network, deployments)
            elif contract_key in DEPLOY_ONLY_CONTRACTS:
                upload_and_deploy(contract_key, args.release_dir, args.deployer_acct, args.network, deployments, per_contract_args)

if __name__ == "__main__":
    main()