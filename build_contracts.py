#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import glob

# Define build order to ensure dependencies are built first
BUILD_ORDER = [
    "pintheon-node-deployer/pintheon-node-token",
    "pintheon-ipfs-deployer/pintheon-ipfs-token",
    "opus_token",
    "hvym-collective",
    "hvym-roster"
]

# For backward compatibility
CONTRACTS = BUILD_ORDER

def clean_targets(contract_dir):
    target_dir = os.path.join(contract_dir, "target")
    for sub in ["debug", "release"]:
        subdir = os.path.join(target_dir, sub)
        if os.path.isdir(subdir):
            print(f"Removing {subdir}")
            shutil.rmtree(subdir)

def find_wasm_file(contract_dir):
    """Find the compiled WASM file in the contract directory.
    
    Args:
        contract_dir: Directory containing the contract to build
        
    Returns:
        Path to the compiled WASM file, or None if not found
    """
    # Get the contract name from the directory
    contract_name = os.path.basename(contract_dir).replace("-", "_")
    
    # Possible locations where the WASM file might be
    possible_paths = [
        # Standard output directories with contract name
        os.path.join(contract_dir, "target", "wasm32-unknown-unknown", "release", f"{contract_name}.wasm"),
        os.path.join(contract_dir, "target", "wasm32v1-none", "release", f"{contract_name}.wasm"),
        
        # Standard output directories with any .wasm file
        os.path.join(contract_dir, "target", "wasm32-unknown-unknown", "release", "*.wasm"),
        os.path.join(contract_dir, "target", "wasm32v1-none", "release", "*.wasm"),
        
        # Check any .wasm file in target directory
        os.path.join(contract_dir, "target", "**", "*.wasm"),
        
        # Check directly in the contract directory (as a last resort)
        os.path.join(contract_dir, "*.wasm")
    ]
    
    # First check for exact matches
    for path in possible_paths:
        if '*' not in path:  # Exact path check
            if os.path.exists(path) and os.path.isfile(path):
                print(f"Found WASM file at exact path: {path}")
                return path
    
    # Then check for glob patterns
    for pattern in possible_paths:
        if '*' in pattern:  # Pattern match
            matches = [f for f in glob.glob(pattern, recursive=True) 
                      if not f.endswith('.optimized.wasm')]
            
            if matches:
                # Prefer exact name matches first
                exact_matches = [m for m in matches if m.endswith(f"{contract_name}.wasm")]
                if exact_matches:
                    print(f"Found exact match: {exact_matches[0]}")
                    return exact_matches[0]
                
                # Then prefer files that contain the contract name
                name_matches = [m for m in matches if contract_name in m]
                if name_matches:
                    print(f"Found name match: {name_matches[0]}")
                    return name_matches[0]
                
                # Otherwise return the first match
                print(f"Found first match: {matches[0]}")
                return matches[0]
    
    print(f"No WASM file found for {contract_name} in {contract_dir}")
    print("Searched in:")
    for path in possible_paths:
        print(f"- {path}")
    
    return None

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

    # Create wasm directory if it doesn't exist
    os.makedirs("wasm", exist_ok=True)
    
    if args.contract:
        if args.contract not in CONTRACTS:
            print(f"Contract {args.contract} not in build list. Valid options:")
            for c in CONTRACTS:
                print(f"  {c}")
            sys.exit(1)
            
        # If building hvym-collective, ensure its dependencies are built first
        if args.contract == "hvym-collective":
            for dep in BUILD_ORDER[:-1]:  # All except hvym-collective itself
                if dep != args.contract:  # Skip if it's the same as the target
                    print(f"Building dependency: {dep}")
                    build_contract(dep, optimize=optimize)
        
        build_contract(args.contract, optimize=optimize)
    else:
        # Build all contracts in the specified order
        for contract in BUILD_ORDER:
            build_contract(contract, optimize=optimize)

if __name__ == "__main__":
    main() 