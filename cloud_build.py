#!/usr/bin/env python3
"""
Cloud build script for Soroban contracts.
Extends build_contracts.py with cloud-specific build configurations.
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path

# Add parent directory to path to import build_contracts
sys.path.insert(0, str(Path(__file__).parent.parent))
from build_contracts import (
    CONTRACTS,
    clean_targets,
    find_wasm_file
)

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
    """Copy WASM file to standard location.
    
    Args:
        wasm_path: Path to the source WASM file
        contract_name: Name of the contract (e.g., 'pintheon-node-token')
        
    Returns:
        Path to the destination WASM file
    """
    # Create wasm directory if it doesn't exist
    wasm_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "wasm"))
    os.makedirs(wasm_dir, exist_ok=True)
    
    # Convert contract name to the format used in wasm filenames
    # Handle both 'pintheon-node-token' and 'pintheon_node_token' formats
    base_name = os.path.basename(contract_name).replace("-", "_")
    wasm_name = f"{base_name}.optimized.wasm"
    
    # Destination path in the wasm directory
    dest = os.path.join(wasm_dir, wasm_name)
    
    # If the source is already an optimized wasm, just copy it
    if wasm_path.endswith('.optimized.wasm'):
        shutil.copy2(wasm_path, dest)
    else:
        # Otherwise, optimize it first
        print(f"Optimizing {wasm_path}...")
        subprocess.run(
            ["stellar", "contract", "optimize", "--wasm", wasm_path],
            check=True
        )
        optimized_path = wasm_path.replace(".wasm", ".optimized.wasm")
        if os.path.exists(optimized_path):
            shutil.copy2(optimized_path, dest)
        else:
            # If optimization didn't create a new file, just copy the original
            shutil.copy2(wasm_path, dest)
    
    print(f"Copied {wasm_path} to {dest}")
    print(f"WASM file size: {os.path.getsize(dest) // 1024} KB")
    return dest

def ensure_wasm_files_for_collective():
    """Ensure required WASM files are in place for hvym-collective."""
    wasm_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "wasm"))
    os.makedirs(wasm_dir, exist_ok=True)
    
    required_files = [
        "pintheon_node_token.optimized.wasm",
        "pintheon_ipfs_token.optimized.wasm"
    ]
    
    missing_files = []
    for wasm_file in required_files:
        src_path = os.path.join(wasm_dir, wasm_file)
        if not os.path.exists(src_path):
            print(f"Warning: Required WASM file not found: {src_path}")
            missing_files.append(wasm_file)
    
    return len(missing_files) == 0

def build_contract_cloud(contract_dir, optimize=True, source_repo=None):
    """Build a contract in the cloud environment.
    
    Args:
        contract_dir: Directory containing the contract to build
        optimize: Whether to optimize the WASM output
        source_repo: Source repository in format "github:owner/repo"
    """
    print(f"\n=== Building {contract_dir} in cloud ===")
    print(f"Current working directory: {os.getcwd()}")
    
    # Get the contract name from the directory
    contract_name = os.path.basename(contract_dir)
    
    # Create wasm directory in the project root
    wasm_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "wasm"))
    os.makedirs(wasm_dir, exist_ok=True)
    
    # Log the wasm directory and its contents before building
    print(f"WASM directory: {wasm_dir}")
    if os.path.exists(wasm_dir):
        print("Current contents of wasm directory:")
        for f in sorted(os.listdir(wasm_dir)):
            if f.endswith('.wasm'):
                print(f"  - {f}: {os.path.getsize(os.path.join(wasm_dir, f)) // 1024} KB")
    
    # If building hvym-collective, ensure dependencies are in place
    if contract_name == 'hvym-collective':
        print("\nVerifying required WASM files for hvym-collective...")
        if not ensure_wasm_files_for_collective():
            print("Error: Missing required WASM files for hvym-collective")
            print("Current wasm directory contents:")
            for f in sorted(os.listdir(wasm_dir)):
                if f.endswith('.wasm'):
                    print(f"  - {f}")
            return False
    
    # Clean build targets before building
    print(f"\nCleaning build targets for {contract_name}...")
    clean_targets(contract_dir)
    
    try:
        # Build the contract using stellar cli
        print(f"\nBuilding {contract_name}...")
        cmd = ["stellar", "contract", "build"]
        if source_repo:
            cmd.extend(["--meta", f"source_repo={source_repo}"])
        
        subprocess.run(
            cmd,
            cwd=contract_dir,
            check=True,
            capture_output=True,
            text=True
        )
        
        # Find the built WASM file
        wasm_file = find_wasm_file(contract_dir)
        if not wasm_file:
            print(f"Error: No .wasm file found in {contract_dir}")
            return False
            
        print(f"Found built WASM: {wasm_file}")
        print(f"File size: {os.path.getsize(wasm_file) // 1024} KB")
        
        # If not optimizing, we're done
        if not optimize:
            return True
            
        # Optimize the WASM file
        wasm_file_rel = os.path.relpath(wasm_file, contract_dir)
        optimized_wasm = wasm_file.replace(".wasm", ".optimized.wasm")
        
        print(f"Optimizing {wasm_file_rel}...")
        result = subprocess.run(
            ["stellar", "contract", "optimize", "--wasm", wasm_file_rel], 
            cwd=contract_dir, 
            check=True,
            capture_output=True,
            text=True
        )
        
        # Verify the optimized file was created
        if not os.path.exists(optimized_wasm):
            print(f"Error: Optimized file not found at {optimized_wasm}")
            print(f"Current directory: {os.getcwd()}")
            print(f"Directory contents: {os.listdir(os.path.dirname(optimized_wasm))}")
            return False
            
        print(f"Optimized WASM size: {os.path.getsize(optimized_wasm) // 1024} KB")
        
        # Copy the optimized wasm to the project's wasm directory
        wasm_dest = copy_to_wasm_dir(optimized_wasm, contract_name)
        print(f"Successfully built and optimized: {wasm_dest}")
        
        # Special handling for dependencies needed by hvym-collective
        if contract_name in ['pintheon-node-token', 'pintheon-ipfs-token']:
            # Ensure the file has the expected name in the wasm directory
            expected_name = f"{contract_name.replace('-', '_')}.optimized.wasm"
            expected_path = os.path.join(wasm_dir, expected_name)
            
            if wasm_dest != expected_path and not os.path.exists(expected_path):
                shutil.copy2(wasm_dest, expected_path)
                print(f"Copied to {expected_path} for hvym-collective")
        
        return True
            
    except subprocess.CalledProcessError as e:
        print(f"Error building {contract_name}:")
        if hasattr(e, 'stdout') and e.stdout:
            print(f"stdout: {e.stdout}")
        if hasattr(e, 'stderr') and e.stderr:
            print(f"stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"Unexpected error building {contract_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Build Soroban contracts with metadata')
    parser.add_argument('--contract', help='Specific contract to build')
    parser.add_argument('--source-repo', 
                      default='github:inviti8/philos_contracts',
                      help='Source repository in format "github:owner/repo"')
    return parser.parse_args()

def main():
    """Main entry point for cloud builds."""
    args = parse_args()
    setup_cloud_environment()
    
    # Create wasm directory if it doesn't exist
    os.makedirs("wasm", exist_ok=True)
    
    # Define build order to ensure dependencies are built first
    build_order = [
        "pintheon-node-deployer/pintheon-node-token",
        "pintheon-ipfs-deployer/pintheon-ipfs-token",
        "opus_token",
        "hvym-collective",
        "hvym-roster"
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
                if not build_contract_cloud(contract_path, source_repo=args.source_repo):
                    return 1
        
        contract_path = os.path.join(os.getcwd(), args.contract)
        success = build_contract_cloud(contract_path, source_repo=args.source_repo)
        return 0 if success else 1
    else:
        # Build all contracts in the specified order
        all_success = True
        for contract_dir in build_order:
            if contract_dir in CONTRACTS:
                contract_path = os.path.join(os.getcwd(), contract_dir)
                if not build_contract_cloud(contract_path, source_repo=args.source_repo):
                    all_success = False
                    # Don't continue if a dependency fails
                    if contract_dir != build_order[-1]:  # If not the last contract
                        break
        return 0 if all_success else 1

if __name__ == "__main__":
    sys.exit(main())
