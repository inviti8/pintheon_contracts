#!/usr/bin/env python3
"""
Cloud build script for Soroban contracts.
Extends build_contracts.py with cloud-specific build configurations.
"""

import os
import sys
import subprocess
from pathlib import Path

# Add parent directory to path to import build_contracts
sys.path.insert(0, str(Path(__file__).parent.parent))
from build_contracts import (
    CONTRACTS,
    clean_targets,
    find_wasm_file
)
import subprocess

def setup_cloud_environment():
    """Set up the cloud build environment."""
    print("Setting up cloud build environment...")
    
    # Install wasm32v1 target if not present
    try:
        subprocess.run(["rustup", "target", "add", "wasm32v1-none"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to add wasm32v1 target: {e}")
    
    # Set environment variables for cloud build
    os.environ["RUSTFLAGS"] = "--remap-path-prefix=/home/runner/.cargo/registry/src= "

def build_contract_cloud(contract_dir, optimize=True):
    """Build a contract in the cloud environment."""
    print(f"\n=== Building {contract_dir} in cloud ===")
    clean_targets(contract_dir)
    
    try:
        # Build with wasm32v1-none target
        cmd = [
            "cargo", "build", "--release",
            "--target", "wasm32v1-none"
        ]
        subprocess.run(cmd, cwd=contract_dir, check=True)
        
        # Find and optimize the wasm file
        wasm_file = find_wasm_file(contract_dir)
        if not wasm_file:
            print(f"No .wasm file found in {contract_dir}")
            return False
            
        print(f"Built: {wasm_file}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error building {contract_dir}: {e}")
        return False

def main():
    """Main entry point for cloud builds."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Build Soroban contracts in cloud environment.")
    parser.add_argument(
        "--contract",
        type=str,
        help="Build only the specified contract directory (relative path)",
    )
    args = parser.parse_args()
    
    # Set up cloud environment
    setup_cloud_environment()
    
    # Build specified contract or all contracts
    if args.contract:
        if args.contract not in CONTRACTS:
            print(f"Contract {args.contract} not in build list. Valid options:")
            for c in CONTRACTS:
                print(f"  {c}")
            return 1
        success = build_contract_cloud(CONTRACTS[args.contract])
        return 0 if success else 1
    else:
        all_success = True
        for contract_dir in CONTRACTS.values():
            if not build_contract_cloud(contract_dir):
                all_success = False
        return 0 if all_success else 1

if __name__ == "__main__":
    sys.exit(main())
