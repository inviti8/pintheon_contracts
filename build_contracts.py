#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import glob

# Ordered list of contract directories
CONTRACTS = [
    "pintheon-ipfs-deployer/pintheon-ipfs-token",
    "pintheon-node-deployer/pintheon-node-token",
    "opus_token",
    "hvym-collective",
]

def clean_targets(contract_dir):
    target_dir = os.path.join(contract_dir, "target")
    for sub in ["debug", "release"]:
        subdir = os.path.join(target_dir, sub)
        if os.path.isdir(subdir):
            print(f"Removing {subdir}")
            shutil.rmtree(subdir)

def find_wasm_file(contract_dir):
    wasm_dir = os.path.join(contract_dir, "target", "wasm32-unknown-unknown", "release")
    if not os.path.isdir(wasm_dir):
        return None
    # Find .wasm files that are not already optimized
    wasm_files = [f for f in glob.glob(os.path.join(wasm_dir, "*.wasm")) if not f.endswith(".optimized.wasm")]
    if not wasm_files:
        return None
    # Prefer the one matching the contract dir name if possible
    base = os.path.basename(contract_dir).replace("-", "_")
    for f in wasm_files:
        if base in os.path.basename(f):
            return f
    # Otherwise, just return the first
    return wasm_files[0]

def copy_to_wasm_dir(wasm_path: str, contract_name: str) -> str:
    """Copy WASM file to standard location."""
    os.makedirs("wasm", exist_ok=True)
    # Convert contract name to the format used in wasm filenames
    wasm_name = contract_name.replace("-", "_") + ".optimized.wasm"
    dest = os.path.join("wasm", wasm_name)
    shutil.copy2(wasm_path, dest)
    print(f"Copied {wasm_path} to {dest}")
    return dest

def build_contract(contract_dir, optimize=True):
    print(f"\n=== Building {contract_dir} ===")
    clean_targets(contract_dir)
    try:
        # Build the contract
        print(f"Building {contract_dir}...")
        subprocess.run(["stellar", "contract", "build"], cwd=contract_dir, check=True)
        
        # Find the generated WASM file
        wasm_file = find_wasm_file(contract_dir)
        if not wasm_file:
            print(f"No .wasm file found in {contract_dir}")
            sys.exit(1)
            
        # Make the path relative to contract_dir
        wasm_file_rel = os.path.relpath(wasm_file, contract_dir)
        
        # Optimize the WASM file if requested
        if optimize:
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
        else:
            print(f"Skipping optimization for {contract_dir} (--no-optimize)")
            
        print(f"Build complete for {contract_dir}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error building {contract_dir}: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Build Soroban contracts in order.")
    parser.add_argument(
        "--contract",
        type=str,
        help="Build only the specified contract directory (relative path)",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Optimize the built WASM files (default: True)",
    )
    args = parser.parse_args()

    # Default to optimizing if --optimize is not specified
    optimize = args.optimize if hasattr(args, 'optimize') else True

    if args.contract:
        if args.contract not in CONTRACTS:
            print(f"Contract {args.contract} not in build list. Valid options:")
            for c in CONTRACTS:
                print(f"  {c}")
            sys.exit(1)
        build_contract(args.contract, optimize=optimize)
    else:
        for contract in CONTRACTS:
            build_contract(contract, optimize=optimize)

if __name__ == "__main__":
    main() 