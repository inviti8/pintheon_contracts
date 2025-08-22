import argparse
import os
import subprocess
import glob
import json
import re

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
                f.write("\n")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if debug:
            with open("debug_output.json", "a") as f:
                json.dump({"command": command, "stdout": e.stdout, "stderr": e.stderr}, f)
                f.write("\n")
        print(f"Error running command: {command}")
        print(f"Error: {e.stderr}")
        raise

def deploy_contract(wasm_file, deployer_acct, network, rpc_url, debug=False):
    """Upload a WASM file to the Stellar network."""
    contract_name = re.sub(r"_v\d+\.\d+\.\d+\.wasm$", "", os.path.basename(wasm_file))
    print(f"=== Uploading {contract_name} (upload only, no deploy) ===")
    print(f"Uploading {os.path.basename(wasm_file)} ...")
    
    # Calculate WASM hash for verification
    wasm_hash = subprocess.check_output(f"sha256sum {wasm_file} | cut -d ' ' -f1", shell=True, text=True).strip()
    print(f"WASM Hash: {wasm_hash}")
    
    # Define network passphrase
    network_passphrase = {
        "testnet": "Test SDF Network ; September 2015",
        "mainnet": "Public Global Stellar Network ; September 2015",
        "futurenet": "Test SDF Future Network ; October 2022"
    }.get(network, "Test SDF Network ; September 2015")
    
    # Check CLI version to determine command
    cli_version = subprocess.check_output("soroban --version || stellar --version", shell=True, text=True).strip()
    if "soroban-cli" in cli_version:
        upload_command = (
            f"soroban contract deploy --wasm {wasm_file} "
            f"--source-account {deployer_acct} --network {network} "
            f"--rpc-url {rpc_url} "
            f"--network-passphrase \"{network_passphrase}\" "
            f"--fee 100000"
        )
    else:
        upload_command = (
            f"stellar contract upload --source-account {deployer_acct} "
            f"--wasm {wasm_file} --network {network} "
            f"--network-passphrase \"{network_passphrase}\" "
            f"--rpc-url {rpc_url} "
            f"--fee 100000"
        )
    
    try:
        output = run_command(upload_command, debug)
        print(f"Uploaded {contract_name}: {output}")
        with open("deployments.md", "a") as f:
            f.write(f"\n- {contract_name}: {output} (WASM Hash: {wasm_hash})")
        return output
    except subprocess.CalledProcessError as e:
        print(f"Failed to upload {contract_name}")
        if debug and "Signing transaction" in e.stderr:
            tx_id = e.stderr.split("Signing transaction: ")[1].split("\n")[0]
            tx_command = (
                f"soroban transaction read --id {tx_id} "
                f"--network {network} --rpc-url {rpc_url}"
            ) if "soroban-cli" in cli_version else (
                f"stellar transaction read --id {tx_id} "
                f"--network {network} --rpc-url {rpc_url}"
            )
            try:
                tx_output = run_command(tx_command, debug)
                print(f"Transaction details for {tx_id}: {tx_output}")
            except subprocess.CalledProcessError:
                print(f"Failed to fetch transaction details for {tx_id}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Deploy Soroban contracts from release WASM files")
    parser.add_argument("--deployer-acct", required=True, help="Deployer account secret key")
    parser.add_argument("--network", required=True, choices=["testnet", "mainnet", "futurenet"], help="Network to deploy to")
    parser.add_argument("--release-dir", required=True, help="Directory containing WASM files")
    parser.add_argument("--rpc-url", default="https://soroban-testnet.stellar.org", help="RPC URL for the network")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    if not args.deployer_acct:
        print("Error: DEPLOYER_ACCT is empty")
        exit(1)

    wasm_files = sorted(glob.glob(os.path.join(args.release_dir, "*_v*.wasm")))
    if not wasm_files:
        print(f"No WASM files found in {args.release_dir}")
        exit(1)

    deployments = []
    for wasm_file in wasm_files:
        try:
            deploy_contract(wasm_file, args.deployer_acct, args.network, args.rpc_url, args.debug)
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