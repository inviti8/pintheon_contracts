#!/usr/bin/env python3
import os
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Network configurations
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
        "rpc_url": "https://horizon.stellar.org"
    },
    "standalone": {
        "passphrase": "Standalone Network ; February 2017",
        "rpc_url": "http://localhost:8000"
    }
}

# Default to testnet
NETWORK = "testnet"

# Get network from environment variable if set
if os.environ.get("STELLAR_NETWORK"):
    NETWORK = os.environ["STELLAR_NETWORK"]

# Validate network
if NETWORK not in NETWORK_CONFIGS:
    print(f"❌ Error: Unsupported network '{NETWORK}'. Supported networks: {', '.join(NETWORK_CONFIGS.keys())}")
    sys.exit(1)

# Set network-specific constants
NETWORK_PASSPHRASE = NETWORK_CONFIGS[NETWORK]["passphrase"]
RPC_URL = NETWORK_CONFIGS[NETWORK]["rpc_url"]

# Contract list
CONTRACTS = [
    "pintheon_ipfs_token",
    "pintheon_node_token",
    "opus_token",
    "hvym_collective"
]

print(f"ℹ️  Using network: {NETWORK}")
print(f"   RPC URL: {RPC_URL}")

# Global variable to store the project root directory
PROJECT_ROOT = Path(__file__).parent.resolve()

# Initialize paths
DEPLOYMENTS_FILE = PROJECT_ROOT / "deployments.json"
DEPLOYMENTS_MD = PROJECT_ROOT / "deployments.md"
WASM_DIR = PROJECT_ROOT / "wasm"

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

# These are now defined at the top of the file using pathlib

def upload_contract(contract_name: str, deployer_acct: str):
    """Upload a contract and return the wasm hash."""
    wasm_file = WASM_DIR / f"{contract_name}.optimized.wasm"
    if not wasm_file.exists():
        print(f"❌ Error: {wasm_file} not found. Build the contract first.")
        sys.exit(1)

    print(f"\n📤 Uploading {contract_name}...")
    cmd = [
        "stellar", "contract", "deploy",
        "--wasm", str(wasm_file),
        "--source", deployer_acct,
        "--network", NETWORK,
        "--rpc-url", RPC_URL,
        "--network-passphrase", NETWORK_PASSPHRASE
    ]
    result = run_command(cmd)
    wasm_hash = result.strip()
    print(f"✅ Uploaded {contract_name} with hash: {wasm_hash}")
    return wasm_hash

def deploy_contract(contract_name: str, wasm_hash: str, deployer_acct: str, args: Optional[dict] = None) -> str:
    """Deploy a contract with the given wasm hash and arguments."""
    cmd = [
        "stellar", "contract", "deploy",
        f"--wasm-hash={wasm_hash}",
        f"--source-account={deployer_acct}",
        f"--network={NETWORK}",
        f"--rpc-url={RPC_URL}",
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

def migrate_deployments(deployments: dict) -> dict:
    """Migrate old deployment format to new format with only underscores."""
    # Create a copy to avoid modifying during iteration
    old_deployments = deployments.copy()
    
    # Process contracts from the old 'contracts' array
    if 'contracts' in old_deployments and isinstance(old_deployments['contracts'], list):
        for contract_info in old_deployments['contracts']:
            if not isinstance(contract_info, dict):
                continue
                
            # Convert contract name to underscore format
            contract_name = contract_info.get('name', '').replace('-', '_')
            if not contract_name:
                continue
                
            # Initialize contract entry if it doesn't exist
            if contract_name not in deployments:
                deployments[contract_name] = {}
                
            # Update with contract info, preserving existing values
            for key, value in contract_info.items():
                if key != 'name':  # Skip the name field
                    deployments[contract_name][key] = value
    
    # Remove old hyphenated entries
    for key in list(deployments.keys()):
        if '-' in key and key.replace('-', '_') in deployments:
            print(f"Removing duplicate hyphenated entry: {key}")
            del deployments[key]
    
    # Remove the old contracts array
    if 'contracts' in deployments:
        del deployments['contracts']
    
    return deployments

def load_deployments() -> dict:
    """Load existing deployments from deployments.json and migrate if needed."""
    if DEPLOYMENTS_FILE.exists():
        with open(DEPLOYMENTS_FILE, 'r') as f:
            try:
                deployments = json.load(f)
                
                # Check if migration is needed
                if any('-' in key or 'contracts' in deployments for key in deployments):
                    print("Migrating deployments to new format...")
                    deployments = migrate_deployments(deployments)
                    # Save the migrated version
                    with open(DEPLOYMENTS_FILE, 'w') as f_out:
                        json.dump(deployments, f_out, indent=2)
                
                return deployments
            except json.JSONDecodeError as e:
                print(f"Error parsing {DEPLOYMENTS_FILE}: {e}")
                return {}
    return {}

def save_deployments(deployments: dict) -> None:
    """Save deployments to deployments.json."""
    # Ensure the directory exists
    DEPLOYMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DEPLOYMENTS_FILE, 'w') as f:
        json.dump(deployments, f, indent=2)
    print(f"Saved deployments to {DEPLOYMENTS_FILE}")

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
    
    # Track processed contracts to avoid duplicates
    processed_contracts = set()
    
    # First, process contracts from the 'contracts' array (old format)
    if 'contracts' in deployments and isinstance(deployments['contracts'], list):
        for contract_info in deployments['contracts']:
            if not isinstance(contract_info, dict):
                continue
                
            # Convert contract name to underscore format
            contract_name = contract_info.get('name', '').replace('-', '_')
            if not contract_name or contract_name in processed_contracts:
                continue
                
            processed_contracts.add(contract_name)
            
            # Skip if we have a direct entry for this contract (prefer direct entries)
            if contract_name in deployments and isinstance(deployments[contract_name], dict):
                continue
                
            # Add to markdown
            network = contract_info.get('network', 'testnet')
            contract_id = contract_info.get('contract_id', contract_info.get('address', 'Not deployed'))
            wasm_hash = contract_info.get('wasm_hash', 'N/A')
            
            if isinstance(contract_id, dict):
                contract_id = contract_id.get('address', 'Not deployed')
                
            md += f"| {contract_name} | {network} | `[{contract_id}](https://stellar.expert/explorer/testnet/contract/{contract_id})` | `{wasm_hash}` |\n"
    
    # Process direct contract entries (new format)
    for contract, info in deployments.items():
        # Skip non-dictionary items, metadata keys, and hyphenated names
        if (not isinstance(info, dict) or 
            contract in skip_keys or 
            '-' in contract):
            continue
            
        # Skip if we've already processed this contract
        if contract in processed_contracts:
            continue
            
        processed_contracts.add(contract)
        
        network = info.get('network', 'testnet')
        contract_id = info.get('contract_id', info.get('address', 'Not deployed'))
        wasm_hash = info.get('wasm_hash', 'N/A')
        
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
    
    # Load existing deployments and clean up old format
    deployments = load_deployments()
    
    # Remove old hyphenated entries if they exist
    for contract in CONTRACTS:
        hyphenated = contract.replace('_', '-')
        if hyphenated in deployments:
            print(f"Removing old hyphenated entry: {hyphenated}")
            del deployments[hyphenated]
    
    # Clean up old contracts array if it exists
    if 'contracts' in deployments:
        print("Removing old contracts array from deployments")
        del deployments['contracts']
    
    try:
        # Process each contract in order
        for contract in CONTRACTS:
            print(f"\n=== Processing {contract} ===")
            
            # Upload the contract
            print(f"Uploading {contract}...")
            wasm_hash = upload_contract(contract, args.deployer_acct)
            print(f"Uploaded with hash: {wasm_hash}")
            
            # Initialize contract entry if it doesn't exist
            if contract not in deployments:
                deployments[contract] = {}
            
            # Update contract info
            contract_info = {
                'wasm_hash': wasm_hash,
                'network': args.network,
                'deployer': args.deployer_acct,
                'timestamp': int(time.time())
            }
            
            # Deploy if needed
            if contract in DEPLOY_ONLY_CONTRACTS:
                print(f"Deploying {contract}...")
                contract_args = load_contract_args(contract)
                contract_id = deploy_contract(contract, wasm_hash, args.deployer_acct, contract_args)
                print(f"Deployed with ID: {contract_id}")
                contract_info['contract_id'] = contract_id
            
            # Update deployments with the new info
            deployments[contract].update(contract_info)
            
            # Save progress after each contract
            save_deployments(deployments)
        
        # Add metadata
        deployments.update({
            'network': args.network,
            'timestamp': int(time.time()),
            'cli_version': '23.0.1',
            'note': 'Deployed with standardized underscore format'
        })
        
        # Save final state
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
