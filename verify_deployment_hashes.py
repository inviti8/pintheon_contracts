#!/usr/bin/env python3
"""
Verify that deployed WASM hashes match the actual WASM files.
This helps catch issues where:
1. Deployed WASM hash doesn't match current WASM file
2. WASM file is missing but deployment shows it exists
3. Network mismatch (testnet vs mainnet deployments)
"""

import json
import os
import hashlib
from pathlib import Path

def get_file_hash(filepath):
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def verify_deployments():
    """Verify deployments against actual WASM files."""
    print("🔍 Verifying deployment hashes...")
    
    # Load deployments
    with open('deployments.json', 'r') as f:
        deployments = json.load(f)
    
    # Check each deployment
    issues_found = False
    
    for contract_name, deployment in deployments.items():
        print(f"\n📋 Checking {contract_name}...")
        
        # Skip non-contract entries
        if not isinstance(deployment, dict) or 'wasm_hash' not in deployment:
            continue
            
        wasm_hash = deployment.get('wasm_hash', '')
        network = deployment.get('network', '')
        contract_id = deployment.get('contract_id', '')
        
        print(f"  📄 Network: {network}")
        print(f"  📝 WASM Hash: {wasm_hash}")
        print(f"  🆔 Contract ID: {contract_id}")
        
        # Check if WASM file exists
        wasm_filename = f"{contract_name}.optimized.wasm"
        wasm_path = Path("wasm") / wasm_filename
        
        if not wasm_path.exists():
            print(f"  ❌ WASM file missing: {wasm_path}")
            issues_found = True
            continue
        
        # Calculate actual WASM hash
        actual_hash = get_file_hash(wasm_path)
        print(f"  🔢 Actual WASM Hash: {actual_hash}")
        
        # Compare hashes
        if wasm_hash and actual_hash:
            if wasm_hash == actual_hash:
                print(f"  ✅ Hashes match - WASM file is current")
            else:
                print(f"  ⚠️  Hash mismatch - deployed hash differs from actual WASM file")
                print(f"      Expected: {wasm_hash}")
                print(f"      Actual:   {actual_hash}")
                issues_found = True
        else:
            print(f"  ❌ Missing WASM hash in deployment")
            issues_found = True
    
    print(f"\n{'🎉 VERIFICATION COMPLETE' if not issues_found else '⚠️  ISSUES FOUND'}")
    return not issues_found

if __name__ == "__main__":
    verify_deployments()
