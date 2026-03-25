#!/usr/bin/env python3
"""
Verify that deployed WASM hashes match the actual WASM files.
This helps catch issues where:
1. Deployed WASM hash doesn't match current WASM file
2. WASM file is missing but deployment shows it exists
"""

import argparse
import json
import hashlib
from pathlib import Path

def get_file_hash(filepath):
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def verify_deployments(dep_file: str):
    """Verify deployments against actual WASM files."""
    print(f"Verifying deployment hashes from {dep_file}...")

    with open(dep_file, 'r') as f:
        deployments = json.load(f)

    issues_found = False

    for contract_name, deployment in deployments.items():
        if not isinstance(deployment, dict) or 'wasm_hash' not in deployment:
            continue

        wasm_hash = deployment.get('wasm_hash', '')
        contract_id = deployment.get('contract_id', '')

        print(f"\n  {contract_name}:")
        print(f"    WASM Hash:   {wasm_hash}")
        print(f"    Contract ID: {contract_id or 'Upload only'}")

        wasm_path = Path("wasm") / f"{contract_name}.optimized.wasm"

        if not wasm_path.exists():
            print(f"    WASM file missing: {wasm_path}")
            issues_found = True
            continue

        actual_hash = get_file_hash(wasm_path)

        if wasm_hash == actual_hash:
            print(f"    Hashes match")
        else:
            print(f"    MISMATCH - local: {actual_hash}")
            issues_found = True

    print(f"\n{'VERIFICATION COMPLETE' if not issues_found else 'ISSUES FOUND'}")
    return not issues_found

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Verify deployed WASM hashes')
    parser.add_argument('file', nargs='?', default=None,
                        help='Deployments JSON file (e.g. deployments.testnet.json)')
    args = parser.parse_args()

    if args.file:
        verify_deployments(args.file)
    else:
        # Verify all network deployment files found
        found = list(Path('.').glob('deployments.*.json'))
        if not found:
            print("No deployments.*.json files found.")
        for f in sorted(found):
            verify_deployments(str(f))
            print()
