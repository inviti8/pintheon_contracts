#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys

def run_cargo_test(target_dir):
    cargo_toml = os.path.join(target_dir, "Cargo.toml")
    if not os.path.isfile(cargo_toml):
        print(f"Error: No Cargo.toml found in {target_dir}. Not a Rust crate.")
        sys.exit(1)
    print(f"\n=== Running tests in {target_dir} ===")
    try:
        subprocess.run(["cargo", "test"], cwd=target_dir, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running tests in {target_dir}: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Run cargo test in a specified contract/crate directory.")
    parser.add_argument(
        "target_dir",
        type=str,
        help="Relative path to the contract/crate directory (must contain Cargo.toml)",
    )
    args = parser.parse_args()
    run_cargo_test(args.target_dir)

if __name__ == "__main__":
    main() 