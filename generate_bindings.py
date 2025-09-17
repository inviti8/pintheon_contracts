#!/usr/bin/env python3
"""
Script to generate Python bindings for Soroban contracts.

This script will:
1. Upload all optimized WASM files from the wasm/ directory
2. Deploy instances of each contract with their respective arguments
3. Generate Python bindings for each deployed contract
"""

import os
import sys
import json
import time
import subprocess
import argparse
from pathlib import Path
from typing import Dict, Optional, List

# Configuration
DEPLOYMENTS_FILE = "bindings_deployments.json"
BINDINGS_DIR = "bindings"
WASM_DIR = "wasm"

# Network configurations (aligned with deploy_contracts.py)
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
        "rpc_url": "https://mainnet.sorobanrpc.com"
    },
    "standalone": {
        "passphrase": "Standalone Network ; February 2017",
        "rpc_url": "http://localhost:8000"
    }
}

# Default to testnet
NETWORK = "testnet"
NETWORK_PASSPHRASE = NETWORK_CONFIGS[NETWORK]["passphrase"]
RPC_URL = NETWORK_CONFIGS[NETWORK]["rpc_url"]

def load_account() -> Optional[str]:
    """Load deployment account from account.json."""
    account_file = Path("account.json")
    if not account_file.exists():
        print(f"❌ Error: {account_file} not found. Please create this file with your deployment account.")
        return None
    
    try:
        with open(account_file) as f:
            account_data = json.load(f)
            account = account_data.get('secret')  # Changed from 'secret_key' to 'secret'
            if not account:
                print("❌ Error: 'secret' not found in account.json")
                return None
            print("✅ Loaded deployment account")
            return account
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing {account_file}: {e}")
        return None

def load_contract_args(contract_name: str) -> dict:
    """Load constructor arguments from {contract_name}_args.json if it exists."""
    args_file = Path(f"{contract_name}_args.json")
    if not args_file.exists():
        print(f"⚠️  No arguments file found for {contract_name}, using empty arguments")
        return {}
    
    try:
        with open(args_file) as f:
            args = json.load(f)
            # Convert float values to stroops (1 XLM = 10,000,000 stroops)
            for key, value in args.items():
                if isinstance(value, float):
                    args[key] = int(value * 10_000_000)
            print(f"✅ Loaded arguments for {contract_name}: {args}")
            return args
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing {args_file}: {e}")
        return {}

def upload_wasm(wasm_path: Path, source_key: str) -> Optional[str]:
    """Upload a WASM file and return its hash."""
    print(f"\nUploading WASM: {wasm_path.name}")
    
    try:
        # Set environment variables
        env = os.environ.copy()
        env['STELLAR_NETWORK_PASSPHRASE'] = NETWORK_PASSPHRASE
        
        # Upload the WASM
        upload_cmd = [
            "stellar", "contract", "upload",
            "--wasm", str(wasm_path),
            "--source-account", source_key,
            f"--network={NETWORK}",
            f"--rpc-url={RPC_URL}",
            "--fee=1000000"
        ]
        
        result = subprocess.run(
            upload_cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        wasm_hash = result.stdout.strip()
        print(f"✅ Uploaded with hash: {wasm_hash}")
        return wasm_hash
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to upload WASM: {e.stderr}")
        return None

def deploy_contract_instance(contract_name: str, wasm_hash: str, source_key: str) -> Optional[str]:
    """Deploy a contract instance and return its ID."""
    print(f"Deploying {contract_name} instance...")
    
    # Load contract arguments
    contract_args = load_contract_args(contract_name)
    
    try:
        # Set environment variables
        env = os.environ.copy()
        env['STELLAR_NETWORK_PASSPHRASE'] = NETWORK_PASSPHRASE
        
        # If we don't have a hash, upload the WASM first
        if not wasm_hash:
            wasm_path = Path(WASM_DIR) / f"{contract_name}.optimized.wasm"
            if not wasm_path.exists():
                print(f"❌ WASM file not found: {wasm_path}")
                return None
                
            wasm_hash = upload_wasm(wasm_path, source_key)
            if not wasm_hash:
                return None
        
        # Build deployment command
        cmd = [
            "stellar", "contract", "deploy",
            f"--wasm-hash={wasm_hash}",
            f"--source-account={source_key}",
            f"--network={NETWORK}",
            f"--rpc-url={RPC_URL}",
            "--fee=1000000",
            "--"  # End of options, start of constructor args
        ]
        
        # Add constructor arguments if any
        if contract_args:
            for key, value in contract_args.items():
                cmd.append(f"--{key.replace('_', '-')}")
                cmd.append(str(value))
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        
        contract_id = result.stdout.strip()
        print(f"✅ Deployed with ID: {contract_id}")
        return contract_id
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to deploy contract: {e.stderr}")
        return None

def generate_bindings(contract_name: str, contract_id: str) -> bool:
    """Generate Python bindings for a contract using stellar-contract-bindings."""
    output_dir = Path(BINDINGS_DIR) / contract_name
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\nGenerating bindings for {contract_name}...")
    print(f"Contract ID: {contract_id}")
    print(f"Output: {output_dir}")
    
    try:
        # Generate bindings using stellar-contract-bindings
        # The contract spec will be fetched automatically by the bindings tool
        bindings_cmd = [
            "stellar-contract-bindings", "python",
            f"--contract-id={contract_id}",
            f"--output={output_dir}",
            f"--rpc-url={RPC_URL}",
            "--client-type=both"
        ]
        
        print("Running command:", " ".join(bindings_cmd))
        
        result = subprocess.run(
            bindings_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if result.stderr:
            print(f"   Info: {result.stderr.strip()}")
            
        print(f"✅ Successfully generated bindings for {contract_name}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate bindings for {contract_name}")
        if e.stderr:
            print(f"   Error: {e.stderr.strip()}")
        if e.stdout:
            print(f"   Output: {e.stdout.strip()}")
        return False

def load_deployments() -> dict:
    """Load existing deployments from bindings_deployments.json."""
    if not os.path.exists(DEPLOYMENTS_FILE):
        return {}
    
    try:
        with open(DEPLOYMENTS_FILE) as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("⚠️  Error parsing bindings_deployments.json, starting fresh")
        return {}

def save_deployments(deployments: dict) -> None:
    """Save deployments to bindings_deployments.json."""
    with open(DEPLOYMENTS_FILE, 'w') as f:
        json.dump(deployments, f, indent=2)
    print(f"💾 Saved deployments to {DEPLOYMENTS_FILE}")

def main():
    global NETWORK, NETWORK_PASSPHRASE, RPC_URL
    
    parser = argparse.ArgumentParser(description="Generate Python bindings for Soroban contracts")
    parser.add_argument("--network", default=NETWORK, help="Network to use")
    parser.add_argument("--skip-existing", action="store_true", 
                       help="Skip contracts that already have bindings")
    args = parser.parse_args()
    
    # Load deployment account
    source_key = load_account()
    if not source_key:
        sys.exit(1)
    
    # Update network settings if specified
    if args.network != NETWORK and args.network in NETWORK_CONFIGS:
        NETWORK = args.network
        NETWORK_PASSPHRASE = NETWORK_CONFIGS[NETWORK]["passphrase"]
        RPC_URL = NETWORK_CONFIGS[NETWORK]["rpc_url"]
    
    print(f"Generating bindings for network: {NETWORK}")
    print(f"RPC URL: {RPC_URL}\n")
    
    # Ensure wasm directory exists
    wasm_dir = Path(WASM_DIR)
    if not wasm_dir.exists():
        print(f"❌ Error: {wasm_dir} directory not found")
        sys.exit(1)
    
    # Process each optimized WASM file
    wasm_files = list(wasm_dir.glob("*.optimized.wasm"))
    if not wasm_files:
        print("❌ No optimized WASM files found in the wasm directory")
        sys.exit(1)
    
    # Load existing deployments
    deployments = load_deployments()
    
    for wasm_file in wasm_files:
        contract_name = wasm_file.stem.replace('.optimized', '')
        print(f"\n=== Processing {contract_name} ===")
        
        # Check if we should skip existing
        if args.skip_existing and contract_name in deployments:
            print(f"✓ Using existing deployment for {contract_name}")
            contract_id = deployments[contract_name].get('contract_id')
            if not contract_id:
                print(f"⚠️  No contract ID found for {contract_name} in deployments")
                continue
        else:
            # 1. Upload WASM
            wasm_hash = upload_wasm(wasm_file, source_key)
            if not wasm_hash:
                continue
            
            # 2. Deploy contract instance
            contract_id = deploy_contract_instance(contract_name, wasm_hash, source_key)
            if not contract_id:
                continue
            
            # Update deployments
            deployments[contract_name] = {
                'contract_id': contract_id,
                'wasm_hash': wasm_hash,
                'network': NETWORK,
                'timestamp': int(time.time())
            }
            save_deployments(deployments)
        
        # 3. Generate bindings
        if not generate_bindings(contract_name, contract_id):
            print(f"⚠️  Failed to generate bindings for {contract_name}")
            continue
    
    print("\n✅ Bindings generation complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
