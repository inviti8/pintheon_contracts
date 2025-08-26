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
    print(f"Current working directory: {os.getcwd()}")
    clean_targets(contract_dir)
    
    # Create the wasm directory in the project root if it doesn't exist
    wasm_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "wasm"))
    os.makedirs(wasm_dir, exist_ok=True)
    
    # Log the wasm directory and its contents
    print(f"WASM directory: {wasm_dir}")
    if os.path.exists(wasm_dir):
        print("Contents of wasm directory:")
        try:
            for f in os.listdir(wasm_dir):
                print(f"  - {f}")
        except Exception as e:
            print(f"  Error listing wasm directory: {e}")
    
    try:
        # Build the contract using stellar cli
        print(f"Building {contract_dir}...")
        subprocess.run(["stellar", "contract", "build"], cwd=contract_dir, check=True)
        
        # Find and optimize the wasm file
        wasm_file = find_wasm_file(contract_dir)
        if not wasm_file:
            print(f"No .wasm file found in {contract_dir}")
            
            # Check all possible target directories
            possible_targets = [
                os.path.join(contract_dir, "target", "wasm32-unknown-unknown", "release"),
                os.path.join(contract_dir, "target", "wasm32v1-none", "release"),
                os.path.join(contract_dir, "target")
            ]
            
            print("Searching in the following directories:")
            for target_dir in possible_targets:
                print(f"- {target_dir}")
                if os.path.exists(target_dir):
                    print("  Contents:")
                    try:
                        for root, dirs, files in os.walk(target_dir):
                            for f in files:
                                if f.endswith('.wasm'):
                                    print(f"    - {os.path.join(root, f)}")
                    except Exception as e:
                        print(f"  Error walking directory: {e}")
            return False
            
        print(f"Found WASM file: {wasm_file}")
        print(f"File exists: {os.path.exists(wasm_file)}")
        print(f"File size: {os.path.getsize(wasm_file) if os.path.exists(wasm_file) else 0} bytes")
            
        # Optimize the WASM file if requested
        if optimize:
            wasm_file_rel = os.path.relpath(wasm_file, contract_dir)
            optimized_wasm = wasm_file.replace(".wasm", ".optimized.wasm")
            
            print(f"Optimizing {wasm_file_rel}...")
            try:
                result = subprocess.run(
                    ["stellar", "contract", "optimize", "--wasm", wasm_file_rel], 
                    cwd=contract_dir, 
                    check=True,
                    capture_output=True,
                    text=True
                )
                print(f"Optimization complete for {contract_dir}")
                if result.stderr:
                    print(f"Optimization stderr: {result.stderr}")
                
                # Verify the optimized file was created
                if not os.path.exists(optimized_wasm):
                    print(f"Error: Optimized file not found at {optimized_wasm}")
                    print(f"Current directory: {os.getcwd()}")
                    print(f"Directory contents: {os.listdir(os.path.dirname(optimized_wasm))}")
                    return False
                    
                print(f"Optimized WASM size: {os.path.getsize(optimized_wasm) // 1024} KB")
                
            except subprocess.CalledProcessError as e:
                print(f"Error optimizing WASM: {e}")
                print(f"stderr: {e.stderr}")
                print(f"stdout: {e.stdout}")
                return False
                
                # Copy to both the project root wasm/ and the contract's wasm/ directory
                contract_name = os.path.basename(contract_dir)
                wasm_dest = copy_to_wasm_dir(optimized_wasm, contract_name)
                
                # Also copy to the contract's wasm/ directory if it exists
                contract_wasm_dir = os.path.join(contract_dir, "wasm")
                if not os.path.exists(contract_wasm_dir):
                    os.makedirs(contract_wasm_dir, exist_ok=True)
                contract_wasm_dest = os.path.join(contract_wasm_dir, os.path.basename(wasm_dest))
                shutil.copy2(optimized_wasm, contract_wasm_dest)
                print(f"Copied {optimized_wasm} to {contract_wasm_dest}")
                
                # For hvym-collective, ensure the wasm files are in the expected location
                if contract_name == "hvym-collective":
                    # The hvym-collective contract expects these specific files
                    required_wasm_files = {
                        "pintheon_node_token.optimized.wasm": "pintheon-node-token",
                        "pintheon_ipfs_token.optimized.wasm": "pintheon-ipfs-token"
                    }
                    
                    for wasm_file, contract_dir_name in required_wasm_files.items():
                        src_path = os.path.join("wasm", wasm_file)
                        if os.path.exists(src_path):
                            # Copy to the hvym-collective's expected location
                            dest_dir = os.path.join(contract_dir, "..", "..", "wasm")
                            os.makedirs(dest_dir, exist_ok=True)
                            dest_path = os.path.join(dest_dir, wasm_file)
                            shutil.copy2(src_path, dest_path)
                            print(f"Copied {src_path} to {dest_path} for hvym-collective")
                        else:
                            print(f"Warning: Required WASM file not found: {src_path}")
                            
                    # Also ensure the wasm files are in the project root wasm/ directory
                    for wasm_file in required_wasm_files.keys():
                        src_path = os.path.join("wasm", wasm_file)
                        if os.path.exists(src_path):
                            dest_path = os.path.join(wasm_dir, wasm_file)
                            if not os.path.exists(dest_path):
                                shutil.copy2(src_path, dest_path)
                                print(f"Copied {src_path} to {dest_path}")
                    # Copy node and ipfs token wasm files to the project root wasm/ directory
                    src_wasm_dir = os.path.dirname(wasm_dest)
                    for token in ["pintheon_node_token", "pintheon_ipfs_token"]:
                        src = os.path.join(wasm_dir, f"{token}.optimized.wasm")
                        if os.path.exists(src):
                            dest = os.path.join(os.path.dirname(os.path.dirname(contract_dir)), "wasm", f"{token}.optimized.wasm")
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            shutil.copy2(src, dest)
                            print(f"Copied {src} to {dest} for hvym-collective")
        
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
    
    # Create wasm directory if it doesn't exist
    os.makedirs("wasm", exist_ok=True)
    
    # Define build order to ensure dependencies are built first
    build_order = [
        "pintheon-node-deployer/pintheon-node-token",
        "pintheon-ipfs-deployer/pintheon-ipfs-token",
        "opus_token",
        "hvym-collective"
    ]
    
    # Build specified contract or all contracts in order
    if args.contract:
        if args.contract not in CONTRACTS:
            print(f"Contract {args.contract} not in build list. Valid options:")
            for c in CONTRACTS:
                print(f"  {c}")
            return 1
        
        # If building hvym-collective, ensure its dependencies are built first
        if args.contract == "hvym-collective":
            for dep in build_order[:-1]:  # All except hvym-collective itself
                contract_path = os.path.join(os.getcwd(), dep)
                if not build_contract_cloud(contract_path):
                    return 1
        
        contract_path = os.path.join(os.getcwd(), args.contract)
        success = build_contract_cloud(contract_path)
        return 0 if success else 1
    else:
        # Build all contracts in the specified order
        all_success = True
        for contract_dir in build_order:
            if contract_dir in CONTRACTS:
                contract_path = os.path.join(os.getcwd(), contract_dir)
                if not build_contract_cloud(contract_path):
                    all_success = False
                    # Don't continue if a dependency fails
                    if contract_dir != build_order[-1]:  # If not the last contract
                        break
        return 0 if all_success else 1

if __name__ == "__main__":
    sys.exit(main())
