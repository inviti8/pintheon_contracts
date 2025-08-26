#!/usr/bin/env python3
"""
Cloud build script for Soroban contracts.
Extends build_contracts.py with cloud-specific build configurations.
"""

import os
import sys
import shutil
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

def copy_to_wasm_dir(wasm_path: str, contract_name: str) -> str:
    """Copy WASM file to standard location."""
    os.makedirs("wasm", exist_ok=True)
    # Convert contract name to the format used in wasm filenames
    wasm_name = contract_name.replace("-", "_") + ".optimized.wasm"
    dest = os.path.join("wasm", wasm_name)
    shutil.copy2(wasm_path, dest)
    print(f"Copied {wasm_path} to {dest}")
    return dest

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
            
        # Optimize the WASM file if requested
        if optimize:
            wasm_file_rel = os.path.relpath(wasm_file, contract_dir)
            print(f"Optimizing {wasm_file_rel}...")
            subprocess.run(
                ["stellar", "contract", "optimize", "--wasm", wasm_file_rel], 
                cwd=contract_dir, 
                check=True
            )
            print(f"Optimization complete for {contract_dir}")
            
            # Copy the optimized WASM to the standard location
            optimized_wasm = wasm_file.replace(".wasm", ".optimized.wasm")
            if os.path.exists(optimized_wasm):
                contract_name = os.path.basename(contract_dir)
                copy_to_wasm_dir(optimized_wasm, contract_name)
        
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
        contract_path = os.path.join(os.getcwd(), args.contract)
        success = build_contract_cloud(contract_path)
        return 0 if success else 1
    else:
        all_success = True
        for contract_dir in CONTRACTS:
            contract_path = os.path.join(os.getcwd(), contract_dir)
            if not build_contract_cloud(contract_path):
                all_success = False
        return 0 if all_success else 1

if __name__ == "__main__":
    sys.exit(main())
