#!/usr/bin/env python3
import os
import subprocess
import sys

# Define test order (same as build order)
TEST_ORDER = [
    "pintheon-node-deployer/pintheon-node-token",
    "pintheon-ipfs-deployer/pintheon-ipfs-token",
    "opus_token",
    "hvym-collective"
]

def run_tests(contract_dir):
    print(f"\n=== Running tests in {contract_dir} ===")
    try:
        subprocess.run(["python", "test_contract.py", contract_dir], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running tests in {contract_dir}: {e}")
        return False

def main():
    all_success = True
    for contract in TEST_ORDER:
        if not run_tests(contract):
            all_success = False
            print(f"Tests failed for {contract}")
    
    if not all_success:
        print("\nSome tests failed!")
        sys.exit(1)
    else:
        print("\nAll tests passed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
