#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import json

CONTRACTS = {
    "pintheon-ipfs-token": "pintheon-ipfs-deployer/pintheon-ipfs-token",
    "pintheon-node-token": "pintheon-node-deployer/pintheon-node-token",
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

def deploy_contract(contract_key, contract_dir, deployer_acct, network, deployments):
    print(f"\n=== Deploying {contract_key} ({contract_dir}) ===")
    
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
    parser = argparse.ArgumentParser(description="Deploy pintheon-ipfs-token and pintheon-node-token contracts using their hashes from deployments.json")
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
        help="Target a specific contract (default: deploy both)",
    )
    
    args = parser.parse_args()
    
    # Load deployments
    deployments = load_deployments()
    if not deployments:
        print(f"Error: {DEPLOYMENTS_FILE} not found or empty")
        sys.exit(1)
    
    # Determine which contracts to deploy
    contracts_to_deploy = []
    if args.contract:
        contracts_to_deploy = [args.contract]
    else:
        contracts_to_deploy = list(CONTRACTS.keys())
    
    print(f"Deploying contracts: {', '.join(contracts_to_deploy)}")
    
    # Deploy each contract
    for contract_key in contracts_to_deploy:
        contract_dir = CONTRACTS[contract_key]
        contract_id = deploy_contract(contract_key, contract_dir, args.deployer_acct, args.network, deployments)
        print(f"Successfully deployed {contract_key} with contract ID: {contract_id}")

if __name__ == "__main__":
    main() 