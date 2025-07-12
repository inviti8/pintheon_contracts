#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import json
import glob

CONTRACTS = {
    "pintheon-ipfs-token": "pintheon-ipfs-deployer/pintheon-ipfs-token",
    "pintheon-node-token": "pintheon-node-deployer/pintheon-node-token",
}

# Official release contracts mapping (using wasm_release folder)
OFFICIAL_CONTRACTS = {
    "pintheon-ipfs-token": "wasm_release/pintheon-ipfs-token",
    "pintheon-node-token": "wasm_release/pintheon-node-token",
}

DEPLOYMENTS_FILE = "deployments.json"

def run_cmd(cmd, cwd=None, capture_output=True):
    try:
        result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=capture_output, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {' '.join(cmd)}")
        print(e.stdout)
        print(e.stderr)
        sys.exit(1)

def load_deployments():
    if os.path.isfile(DEPLOYMENTS_FILE):
        with open(DEPLOYMENTS_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}

def load_args_from_json(contract_key):
    json_file = f"{contract_key}_args.json"
    if not os.path.isfile(json_file):
        print(f"Error: No argument file found for {contract_key} (expected {json_file})")
        sys.exit(1)
    with open(json_file, "r") as f:
        data = json.load(f)
    args = []
    for k, v in data.items():
        args.append(f"--{k.replace('_', '-')}")
        args.append(str(v))
    return args

def find_wasm_file(contract_dir, official_release=False):
    """Find WASM file in the contract directory"""
    if official_release:
        # For official releases, look for WASM files in the wasm_release directory
        if not os.path.isdir(contract_dir):
            return None
        wasm_files = glob.glob(os.path.join(contract_dir, "*.wasm"))
        if not wasm_files:
            return None
        # Return the first WASM file found (should be the only one)
        return wasm_files[0]
    else:
        # For development, look in the target directory
        wasm_dir = os.path.join(contract_dir, "target", "wasm32-unknown-unknown", "release")
        if not os.path.isdir(wasm_dir):
            return None
        wasm_files = glob.glob(os.path.join(wasm_dir, "*.optimized.wasm"))
        if not wasm_files:
            return None
        # Prefer the one matching the contract dir name if possible
        base = os.path.basename(contract_dir).replace("-", "_")
        for f in wasm_files:
            if base in os.path.basename(f):
                return f
        return wasm_files[0]

def upload_and_deploy_contract(contract_key, contract_dir, deployer_acct, network, official_release=False):
    """Upload and deploy a contract using its WASM file"""
    mode = "OFFICIAL RELEASE" if official_release else "DEVELOPMENT"
    print(f"\n=== Uploading and deploying {contract_key} ({contract_dir}) [{mode}] ===")
    
    # Find WASM file
    wasm_file = find_wasm_file(contract_dir, official_release)
    if not wasm_file:
        if official_release:
            print(f"No WASM file found in {contract_dir}")
            print(f"Expected file pattern: {contract_dir}/*.wasm")
        else:
            print(f"No optimized .wasm file found in {contract_dir}")
            print(f"Expected file pattern: {contract_dir}/target/wasm32-unknown-unknown/release/*.optimized.wasm")
        sys.exit(1)
    
    wasm_file_rel = os.path.relpath(wasm_file, contract_dir)
    
    # Upload
    print(f"Uploading {wasm_file_rel} ...")
    upload_cmd = [
        "stellar", "contract", "upload",
        "--source-account", deployer_acct,
        "--wasm", wasm_file_rel,
        "--network", network
    ]
    upload_out = run_cmd(upload_cmd, cwd=contract_dir)
    
    # Extract wasm hash from upload output
    lines = [line.strip() for line in upload_out.splitlines() if line.strip()]
    wasm_hash = None
    if lines:
        last_line = lines[-1]
        if len(last_line) == 64 and all(c in '0123456789abcdefABCDEF' for c in last_line):
            wasm_hash = last_line
    if not wasm_hash:
        print(f"Could not extract wasm hash from upload output (expected last line to be hash):\n{upload_out}")
        sys.exit(1)
    print(f"Wasm hash: {wasm_hash}")
    
    # Load constructor arguments from JSON file
    constructor_args = load_args_from_json(contract_key)
    print(f"Constructor arguments: {' '.join(constructor_args)}")
    
    # Deploy contract
    print(f"Deploying contract with hash {wasm_hash} ...")
    deploy_cmd = [
        "stellar", "contract", "deploy",
        "--wasm-hash", wasm_hash,
        "--source-account", deployer_acct,
        "--network", network
    ]
    if constructor_args:
        deploy_cmd.append("--")
        deploy_cmd.extend(constructor_args)
    
    deploy_out = run_cmd(deploy_cmd, cwd=contract_dir)
    print(f"Deploy output:\n{deploy_out}")
    
    # Extract contract ID from last line
    deploy_lines = [line.strip() for line in deploy_out.splitlines() if line.strip()]
    contract_id = None
    if deploy_lines:
        last_line = deploy_lines[-1]
        if len(last_line) == 56 and last_line.isalnum() and last_line.isupper():
            contract_id = last_line
    
    if not contract_id:
        print(f"Could not extract contract ID from deploy output (expected last line to be contract ID):\n{deploy_out}")
        sys.exit(1)
    
    print(f"Contract ID: {contract_id}")
    return contract_id

def deploy_contract_from_deployments(contract_key, contract_dir, deployer_acct, network, deployments):
    """Deploy a contract using its hash from deployments.json"""
    print(f"\n=== Deploying {contract_key} ({contract_dir}) from deployments.json ===")
    
    # Get wasm hash from deployments.json
    if contract_key not in deployments:
        print(f"Error: {contract_key} not found in {DEPLOYMENTS_FILE}")
        sys.exit(1)
    
    wasm_hash = deployments[contract_key].get("wasm_hash")
    if not wasm_hash:
        print(f"Error: No wasm hash found for {contract_key} in {DEPLOYMENTS_FILE}")
        sys.exit(1)
    
    print(f"Using wasm hash: {wasm_hash}")
    
    # Load constructor arguments from JSON file
    constructor_args = load_args_from_json(contract_key)
    print(f"Constructor arguments: {' '.join(constructor_args)}")
    
    # Deploy contract
    print(f"Deploying contract with hash {wasm_hash} ...")
    deploy_cmd = [
        "stellar", "contract", "deploy",
        "--wasm-hash", wasm_hash,
        "--source-account", deployer_acct,
        "--network", network
    ]
    if constructor_args:
        deploy_cmd.append("--")
        deploy_cmd.extend(constructor_args)
    
    deploy_out = run_cmd(deploy_cmd, cwd=contract_dir)
    print(f"Deploy output:\n{deploy_out}")
    
    # Extract contract ID from last line
    deploy_lines = [line.strip() for line in deploy_out.splitlines() if line.strip()]
    contract_id = None
    if deploy_lines:
        last_line = deploy_lines[-1]
        if len(last_line) == 56 and last_line.isalnum() and last_line.isupper():
            contract_id = last_line
    
    if not contract_id:
        print(f"Could not extract contract ID from deploy output (expected last line to be contract ID):\n{deploy_out}")
        sys.exit(1)
    
    print(f"Contract ID: {contract_id}")
    return contract_id

def main():
    parser = argparse.ArgumentParser(description="Deploy pintheon-ipfs-token and pintheon-node-token contracts")
    parser.add_argument(
        "--deployer-acct",
        required=True,
        help="Stellar CLI account name or secret to use as deployer (--source-account value)",
    )
    parser.add_argument(
        "--network",
        default="testnet",
        help="Network name for deployment (default: testnet)",
    )
    parser.add_argument(
        "--contract",
        type=str,
        choices=list(CONTRACTS.keys()),
        help="Target a specific contract (default: deploy all)",
    )
    parser.add_argument(
        "--official-release",
        action="store_true",
        help="Use official release WASM files from the 'wasm_release' directory instead of deployments.json",
    )
    
    args = parser.parse_args()
    
    # Validate official release mode
    if args.official_release:
        if not os.path.exists("wasm_release"):
            print("Error: --official-release specified but 'wasm_release' directory not found.")
            print("Please run download_wasm_releases.py first to download the official release files.")
            sys.exit(1)
        print("Using official release WASM files from 'wasm_release' directory")
    
    # Determine which contracts to deploy
    contracts_to_deploy = []
    if args.contract:
        contracts_to_deploy = [args.contract]
    else:
        contracts_to_deploy = list(CONTRACTS.keys())
    
    print(f"Deploying contracts: {', '.join(contracts_to_deploy)}")
    
    if args.official_release:
        # Deploy using official release WASM files
        for contract_key in contracts_to_deploy:
            contract_dir = OFFICIAL_CONTRACTS[contract_key]
            contract_id = upload_and_deploy_contract(contract_key, contract_dir, args.deployer_acct, args.network, args.official_release)
            print(f"Successfully deployed {contract_key} with contract ID: {contract_id}")
    else:
        # Deploy using hashes from deployments.json
        deployments = load_deployments()
        if not deployments:
            print(f"Error: {DEPLOYMENTS_FILE} not found or empty")
            print("Please run deploy_contracts.py first to upload contracts and generate deployment records.")
            sys.exit(1)
        
        for contract_key in contracts_to_deploy:
            contract_dir = CONTRACTS[contract_key]
            contract_id = deploy_contract_from_deployments(contract_key, contract_dir, args.deployer_acct, args.network, deployments)
            print(f"Successfully deployed {contract_key} with contract ID: {contract_id}")

if __name__ == "__main__":
    main() 