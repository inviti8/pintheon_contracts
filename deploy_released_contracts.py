import argparse
import os
import subprocess
import glob
import json
import requests

def run_command(command, debug=False):
    """Run a shell command and return the output, optionally saving debug info."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        if debug:
            with open("debug_output.json", "a") as f:
                json.dump({"command": command, "stdout": result.stdout, "stderr": result.stderr}, f)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if debug:
            with open("debug_output.json", "a") as f:
                json.dump({"command": command, "stdout": e.stdout, "stderr": e.stderr}, f)
        print(f"Error running command: {command}")
        print(f"Error: {e.stderr}")
        raise

def deploy_contract(wasm_file, deployer_acct, network, debug=False):
    """Upload a WASM file to the Stellar network."""
    contract_name = os.path.basename(wasm_file).replace("_v0.0.6.wasm", "").replace("_v0.0.1.wasm", "")
    print(f"=== Uploading {contract_name} (upload only, no deploy) ===")
    print(f"Uploading {os.path.basename(wasm_file)} ...")
    
    # Define network passphrase
    network_passphrase = {
        "testnet": "Test SDF Network ; September 2015",
        "mainnet": "Public Global Stellar Network ; September 2015",
        "futurenet": "Test SDF Future Network ; October 2022"
    }.get(network, "Test SDF Network ; September 2015")
    
    # Perform upload with explicit fee and RPC URL
    upload_command = (
        f"stellar contract upload --source-account {deployer_acct} "
        f"--wasm {wasm_file} --network {network} "
        f"--network-passphrase \"{network_passphrase}\" "
        f"--rpc-url https://soroban-testnet.stellar.org "
        f"--fee 10000"
    )
    try:
        output = run_command(upload_command, debug)
        print(f"Uploaded {contract_name}: {output}")
        # Save contract hash for debugging
        with open("deployments.md", "a") as f:
            f.write(f"\n- {contract_name}: {output}")
    except subprocess.CalledProcessError:
        print(f"Failed to upload {contract_name}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Deploy Soroban contracts from release WASM files")
    parser.add_argument("--deployer-acct", required=True, help="Deployer account secret key")
    parser.add_argument("--network", required=True, choices=["testnet", "mainnet", "futurenet"], help="Network to deploy to")
    parser.add_argument("--release-dir", required=True, help="Directory containing WASM files")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    if not args.deployer_acct:
        print("Error: DEPLOYER_ACCT is empty")
        exit(1)

    wasm_files = glob.glob(os.path.join(args.release_dir, "*_v*.wasm"))
    if not wasm_files:
        print(f"No WASM files found in {args.release_dir}")
        exit(1)

    deployments = []
    for wasm_file in wasm_files:
        try:
            deploy_contract(wasm_file, args.deployer_acct, args.network, args.debug)
            deployments.append(f"Successfully uploaded {os.path.basename(wasm_file)}")
        except subprocess.CalledProcessError:
            deployments.append(f"Failed to upload {os.path.basename(wasm_file)}")
            if args.debug:
                print("Check debug_output.json for details")
            continue

    with open("deployments.md", "w") as f:
        f.write("# Deployment Results\n\n")
        f.write("\n".join(deployments))

if __name__ == "__main__":
    main()