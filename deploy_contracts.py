#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Constants
NETWORK = "testnet"  # or take from env/args
NETWORK_PASSPHRASE = "Test SDF Network ; September 2015"  # Testnet passphrase
WASM_DIR = "wasm"
CONTRACTS = [
    "pintheon_ipfs_token",
    "pintheon_node_token",
    "opus_token",
    "hvym_collective"
]

# Global variable to store the project root directory
PROJECT_ROOT = Path(__file__).parent.resolve()

def ensure_project_root():
    """Ensure the script is being run from the project root directory."""
    # Check for key project files/directories
    required_paths = [
        PROJECT_ROOT / 'deploy_contracts.py',
        PROJECT_ROOT / '.github',
        PROJECT_ROOT / 'wasm'
    ]
    
    for path in required_paths:
        if not path.exists():
            print(f"Error: Could not find required path: {path}")
            print("Please run this script from the project root directory.")
            sys.exit(1)

def load_contract_args(contract_name: str) -> dict:
    """Load constructor arguments from JSON file."""
    args_file = f"{contract_name}_args.json"
    try:
        with open(args_file) as f:
            args = json.load(f)
            
        # Convert XLM to stroops for hvym_collective
        if contract_name == "hvym_collective":
            for key in ['join_fee', 'mint_fee', 'reward']:
                if key in args:
                    args[key] = int(float(args[key]) * 10_000_000)
        
        return args
    except FileNotFoundError:
        print(f"No argument file found for {contract_name}")
        return {}

def run_command(cmd: list, cwd: str = ".") -> str:
    """Run a shell command and return its output."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
        
    return result.stdout.strip()

DEPLOYMENTS_FILE = "deployments.json"
DEPLOYMENTS_MD = "deployments.md"

def upload_contract(contract_name: str, deployer_acct: str) -> str:
    """Upload a contract and return the wasm hash."""
    wasm_file = f"{WASM_DIR}/{contract_name}.optimized.wasm"
    cmd = [
        "stellar", "contract", "upload",
        f"--source-account={deployer_acct}",
        f"--wasm={wasm_file}",
        f"--network={NETWORK}",
        f"--network-passphrase={NETWORK_PASSPHRASE}",
        "--fee=1000000"
    ]
    return run_command(cmd)

def deploy_contract(contract_name: str, wasm_hash: str, deployer_acct: str, args: Optional[dict] = None) -> str:
    """Deploy a contract with the given wasm hash and arguments."""
    cmd = [
        "stellar", "contract", "deploy",
        f"--wasm-hash={wasm_hash}",
        f"--source-account={deployer_acct}",
        f"--network={NETWORK}",
        f"--network-passphrase={NETWORK_PASSPHRASE}",
        "--fee=1000000",
        "--"
    ]
    
    # Add constructor arguments
    if args:
        for key, value in args.items():
            cmd.append(f"--{key.replace('_', '-')}")
            cmd.append(str(value))
    
    return run_command(cmd)

def load_deployments() -> dict:
    """Load existing deployments from deployments.json."""
    try:
        with open(DEPLOYMENTS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_deployments(deployments: dict) -> None:
    """Save deployments to deployments.json."""
    with open(DEPLOYMENTS_FILE, 'w') as f:
        json.dump(deployments, f, indent=2)

# Contract categories
UPLOAD_ONLY_CONTRACTS = [
    "pintheon_ipfs_token",
    "pintheon_node_token"
]

DEPLOY_ONLY_CONTRACTS = [
    "opus_token",
    "hvym_collective"
]

def generate_deployments_md(deployments: dict) -> None:
    """Generate a markdown file with deployment details."""
    md = "# Contract Deployments\n\n"
    md += "| Contract | Network | Contract ID | Wasm Hash |\n"
    md += "|----------|---------|-------------|-----------|\n"
    
    # Skip these top-level keys that aren't contract deployments
    skip_keys = {'network', 'timestamp', 'cli_version', 'note', 'contracts'}
    
    for contract, info in deployments.items():
        # Skip non-dictionary items and metadata keys
        if not isinstance(info, dict) or contract in skip_keys:
            continue
            
        network = info.get('network', 'testnet')  # Default to testnet if not specified
        contract_id = info.get('contract_id', info.get('address', 'Not deployed'))
        wasm_hash = info.get('wasm_hash', 'N/A')
        
        # Ensure contract_id is a string
        if isinstance(contract_id, dict):
            contract_id = contract_id.get('address', 'Not deployed')
            
        md += f"| {contract} | {network} | `{contract_id}` | `{wasm_hash}` |\n"
    
    # Add a note if no deployments were found
    if md.count('\n') <= 4:  # Only headers in the markdown
        md += "| No deployments found | | | |\n"
    
    with open(DEPLOYMENTS_MD, 'w') as f:
        f.write(md)

def main():
    """Main deployment function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Deploy Soroban contracts')
    parser.add_argument('--deployer-acct', required=True, help='Deployer account')
    parser.add_argument('--network', default=NETWORK, help='Network to deploy to')
    parser.add_argument('--wasm-dir', default=WASM_DIR, help='Directory containing WASM files')
    args = parser.parse_args()
    
    print(f"Starting deployment with deployer: {args.deployer_acct}")
    
    # Load existing deployments
    deployments = load_deployments()
    
    try:
        # Process each contract in order
        for contract in CONTRACTS:
            print(f"\n=== Processing {contract} ===")
            
            # Upload the contract
            print(f"Uploading {contract}...")
            wasm_hash = upload_contract(contract, args.deployer_acct)
            print(f"Uploaded with hash: {wasm_hash}")
            
            # Update deployments
            if contract not in deployments:
                deployments[contract] = {}
                
            deployments[contract].update({
                'wasm_hash': wasm_hash,
                'network': args.network,
                'deployer': args.deployer_acct
            })
            
            # Deploy if needed
            if contract in DEPLOY_ONLY_CONTRACTS:
                print(f"Deploying {contract}...")
                contract_args = load_contract_args(contract)
                contract_id = deploy_contract(contract, wasm_hash, args.deployer_acct, contract_args)
                print(f"Deployed with ID: {contract_id}")
                deployments[contract]['contract_id'] = contract_id
            
            # Save progress after each contract
            save_deployments(deployments)
        
        # Generate markdown report
        generate_deployments_md(deployments)
        print("\n✅ All contracts processed successfully!")
        
    except Exception as e:
        print(f"\n❌ Deployment failed: {str(e)}")
        raise

if __name__ == "__main__":
    ensure_project_root()
    main()
