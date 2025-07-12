#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import glob
import json

CONTRACTS = {
    "pintheon-ipfs-token": "pintheon-ipfs-deployer/pintheon-ipfs-token",
    "pintheon-node-token": "pintheon-node-deployer/pintheon-node-token",
    "opus_token": "opus_token",
    "hvym-collective": "hvym-collective",
}
CONTRACT_ORDER = list(CONTRACTS.keys())

# Official release contracts mapping (using wasm_release folder)
OFFICIAL_CONTRACTS = {
    "pintheon-ipfs-token": "wasm_release/pintheon-ipfs-token",
    "pintheon-node-token": "wasm_release/pintheon-node-token",
    "opus_token": "wasm_release/opus-token",
    "hvym-collective": "wasm_release/hvym-collective",
}

DEPLOYMENTS_FILE = "deployments.json"
DEPLOYMENTS_MD = "deployments.md"

UPLOAD_ONLY_CONTRACTS = [
    "pintheon-ipfs-token",
    "pintheon-node-token"
]
DEPLOY_ONLY_CONTRACTS = [
    "opus_token",
    "hvym-collective"
]

def find_optimized_wasm(contract_dir, official_release=False):
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

def save_deployments(data):
    with open(DEPLOYMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    save_deployments_md(data)

def save_deployments_md(data):
    lines = [
        "# Soroban Contract Deployments\n",
        "| Contract Name | Contract Directory | Wasm Hash | Contract ID |",
        "|--------------|-------------------|--------------------------------------------------------------|----------------------------------------------------------|"
    ]
    for contract, info in data.items():
        lines.append(f"| `{contract}` | `{info.get('contract_dir', '')}` | `{info.get('wasm_hash', '')}` | `{info.get('contract_id', '')}` |")
    with open(DEPLOYMENTS_MD, "w") as f:
        f.write("\n".join(lines) + "\n")

def upload_and_deploy(contract_key, contract_dir, deployer_acct, network, deployments, constructor_args=None, official_release=False):
    mode = "OFFICIAL RELEASE" if official_release else "DEVELOPMENT"
    print(f"\n=== Uploading and deploying {contract_key} ({contract_dir}) [{mode}] ===")
    wasm_file = find_optimized_wasm(contract_dir, official_release)
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
    # Refined: Use the last line if it's a 64-char hex string
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
    # Deploy
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
    # Update deployments.json
    deployments[contract_key] = {
        "contract_dir": contract_dir,
        "wasm_hash": wasm_hash,
        "contract_id": contract_id
    }
    save_deployments(deployments)
    print(f"Updated {DEPLOYMENTS_FILE} with {contract_key}")

def upload_only(contract_key, contract_dir, deployer_acct, network, deployments, official_release=False):
    mode = "OFFICIAL RELEASE" if official_release else "DEVELOPMENT"
    print(f"\n=== Uploading {contract_key} ({contract_dir}) (upload only, no deploy) [{mode}] ===")
    wasm_file = find_optimized_wasm(contract_dir, official_release)
    if not wasm_file:
        if official_release:
            print(f"No WASM file found in {contract_dir}")
            print(f"Expected file pattern: {contract_dir}/*.wasm")
        else:
            print(f"No optimized .wasm file found in {contract_dir}")
            print(f"Expected file pattern: {contract_dir}/target/wasm32-unknown-unknown/release/*.optimized.wasm")
        sys.exit(1)
    wasm_file_rel = os.path.relpath(wasm_file, contract_dir)
    print(f"Uploading {wasm_file_rel} ...")
    upload_cmd = [
        "stellar", "contract", "upload",
        "--source-account", deployer_acct,
        "--wasm", wasm_file_rel,
        "--network", network
    ]
    upload_out = run_cmd(upload_cmd, cwd=contract_dir)
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
    deployments[contract_key] = {
        "contract_dir": contract_dir,
        "wasm_hash": wasm_hash,
        "contract_id": None
    }
    save_deployments(deployments)
    print(f"Updated {DEPLOYMENTS_FILE} with {contract_key}")

def load_args_from_json(contract_key):
    import json
    # Handle naming mismatch for opus_token
    if contract_key == "opus_token":
        json_file = "opus-token_args.json"
    else:
        json_file = f"{contract_key}_args.json"
    
    if not os.path.isfile(json_file):
        print(f"Warning: No argument file found for {contract_key} (expected {json_file}), no constructor args will be used.")
        return []
    with open(json_file, "r") as f:
        data = json.load(f)
    args = []
    # For hvym-collective, convert join_fee, mint_fee, reward to stroops
    if contract_key == "hvym-collective":
        for key in ["join_fee", "mint_fee", "reward"]:
            if key in data:
                # Allow both int and float (for decimal XLM values)
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
    parser = argparse.ArgumentParser(description="Upload and deploy Soroban contracts using Stellar CLI.\nIf --constructor-args is not provided, the script will look for a JSON file named <contract>_args.json and use its fields as constructor arguments.")
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
        help="Target a specific contract by short name (see list below)",
    )
    parser.add_argument(
        "--constructor-args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to the contract constructor (everything after this flag is passed to the deploy command after --). If not provided, arguments will be loaded from <contract>_args.json.",
    )
    parser.add_argument(
        "--official-release",
        action="store_true",
        help="Use official release WASM files from the 'wasm_release' directory.",
    )
    args = parser.parse_args()
    
    # Validate official release mode
    if args.official_release:
        if not os.path.exists("wasm_release"):
            print("Error: --official-release specified but 'wasm_release' directory not found.")
            print("Please run download_wasm_releases.py first to download the official release files.")
            sys.exit(1)
        print("Using official release WASM files from 'wasm_release' directory")
    
    deployments = load_deployments()
    if args.constructor_args is not None:
        constructor_args = args.constructor_args
        if '--admin' not in constructor_args:
            constructor_args = constructor_args + ['--admin', args.deployer_acct]
    else:
        if args.contract:
            constructor_args = load_args_from_json(args.contract)
            if '--admin' not in constructor_args:
                constructor_args = constructor_args + ['--admin', args.deployer_acct]
        else:
            constructor_args = None
    if args.contract:
        if args.contract not in CONTRACTS:
            print(f"Contract '{args.contract}' not in deploy list. Valid options:")
            for c in CONTRACT_ORDER:
                print(f"  {c}")
            sys.exit(1)
        contract_dir = CONTRACTS[args.contract]
        if args.official_release:
            contract_dir = OFFICIAL_CONTRACTS[args.contract]
        if args.contract in UPLOAD_ONLY_CONTRACTS:
            upload_only(args.contract, contract_dir, args.deployer_acct, args.network, deployments, args.official_release)
        elif args.contract in DEPLOY_ONLY_CONTRACTS:
            upload_and_deploy(args.contract, contract_dir, args.deployer_acct, args.network, deployments, constructor_args, args.official_release)
        else:
            print(f"Contract '{args.contract}' is not configured for upload or deploy.")
            sys.exit(1)
    else:
        for contract_key in CONTRACT_ORDER:
            contract_dir = CONTRACTS[contract_key]
            if args.official_release:
                contract_dir = OFFICIAL_CONTRACTS[contract_key]
            if contract_key in UPLOAD_ONLY_CONTRACTS:
                upload_only(contract_key, contract_dir, args.deployer_acct, args.network, deployments, args.official_release)
            elif contract_key in DEPLOY_ONLY_CONTRACTS:
                per_contract_args = constructor_args if constructor_args is not None else load_args_from_json(contract_key)
                if '--admin' not in per_contract_args:
                    per_contract_args = per_contract_args + ['--admin', args.deployer_acct]
                upload_and_deploy(contract_key, contract_dir, args.deployer_acct, args.network, deployments, per_contract_args, args.official_release)

if __name__ == "__main__":
    main() 