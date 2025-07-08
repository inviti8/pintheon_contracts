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

def build_contract(contract_dir):
    print(f"\n=== Building {contract_dir} ===")
    clean_targets(contract_dir)
    try:
        subprocess.run(["stellar", "contract", "build"], cwd=contract_dir, check=True)
        wasm_file = find_wasm_file(contract_dir)
        if not wasm_file:
            print(f"No .wasm file found to optimize in {contract_dir}")
            sys.exit(1)
        # Make the path relative to contract_dir
        wasm_file_rel = os.path.relpath(wasm_file, contract_dir)
        print(f"Optimizing {wasm_file_rel}")
        subprocess.run(["stellar", "contract", "optimize", "--wasm", wasm_file_rel], cwd=contract_dir, check=True)
        print(f"Build and optimization complete for {contract_dir}")
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
    args = parser.parse_args()

    if args.contract:
        if args.contract not in CONTRACTS:
            print(f"Contract {args.contract} not in build list. Valid options:")
            for c in CONTRACTS:
                print(f"  {c}")
            sys.exit(1)
        build_contract(args.contract)
    else:
        for contract in CONTRACTS:
            build_contract(contract)

if __name__ == "__main__":
    main() 