import argparse
import os
import subprocess
import glob
import json
import re
import requests
import time
import base64

def extract_transaction_hash(output):
    """Extract transaction hash from CLI output."""
    import re
    # Look for transaction hash patterns
    hash_patterns = [
        r'Transaction hash is ([a-f0-9]{64})',
        r'Signing transaction: ([a-f0-9]{64})',
        r'hash ([a-f0-9]{64})'
    ]
    
    for pattern in hash_patterns:
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    return None

def check_transaction_success(tx_hash, network="testnet", max_retries=10):
    """Check if transaction succeeded using Stellar Expert API."""
    url = f"https://api.stellar.expert/explorer/{network}/tx/{tx_hash}"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                tx_data = response.json()
                return tx_data.get('successful', False), tx_data
            else:
                print(f"⚠️ API error {response.status_code}, retrying...")
                time.sleep(2)
        except Exception as e:
            print(f"⚠️ Error checking transaction: {e}, retrying...")
            time.sleep(2)
    
    print(f"❌ Transaction {tx_hash} not confirmed after {max_retries} attempts")
    return False, None

def extract_contract_address_from_stellar_expert(tx_hash, network="testnet"):
    """Extract contract address from Stellar Expert API transaction data."""
    try:
        from stellar_sdk import StrKey
        
        # Get transaction data from Stellar Expert API
        url = f"https://api.stellar.expert/explorer/{network}/tx/{tx_hash}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"⚠️ Failed to fetch transaction from Stellar Expert: {response.status_code}")
            return None
            
        tx_data = response.json()
        
        # Extract contract address from result XDR
        result_xdr = tx_data.get('result')
        if not result_xdr:
            print("⚠️ No result XDR found in transaction")
            return None
            
        try:
            # Decode the XDR result
            decoded_result = base64.b64decode(result_xdr)
            hex_data = decoded_result.hex()
            
            # Look for contract address pattern in the result
            if len(hex_data) >= 64:
                potential_addresses = []
                
                # Look for 32-byte sequences that could be contract addresses
                for i in range(0, len(hex_data) - 63, 2):
                    candidate = hex_data[i:i+64]
                    if candidate != '0' * 64 and not candidate.startswith('0000000000000000'):
                        potential_addresses.append(candidate)
                
                # Try the most likely candidates (usually near the end)
                for candidate in reversed(potential_addresses[-3:]):
                    try:
                        contract_bytes = bytes.fromhex(candidate)
                        contract_address = StrKey.encode_contract(contract_bytes)
                        if contract_address.startswith('C') and len(contract_address) == 56:
                            return contract_address
                    except:
                        continue
                        
        except Exception as e:
            print(f"⚠️ Error decoding transaction result: {e}")
            
        return None
        
    except Exception as e:
        print(f"⚠️ Error extracting contract address from Stellar Expert: {e}")
        return None

def run_command_with_xdr_workaround(command, debug=False, network="testnet"):
    """Run a shell command with XDR error handling and contract address extraction."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )
        
        output = result.stdout + result.stderr
        
        if debug:
            with open("debug_output.json", "a") as f:
                json.dump({"command": command, "stdout": result.stdout, "stderr": result.stderr}, f)
                f.write("\n")
        
        # Check for XDR processing error
        if "xdr processing error" in output.lower():
            print("⚠️ XDR processing error detected, checking transaction status...")
            
            # Extract transaction hash
            tx_hash = extract_transaction_hash(output)
            if tx_hash:
                print(f"🔍 Found transaction hash: {tx_hash}")
                
                # Check if transaction actually succeeded
                success, tx_data = check_transaction_success(tx_hash, network)
                if success:
                    print("✅ Transaction succeeded despite XDR error!")
                    
                    # Try to extract contract address if this was a deployment
                    if "deploy" in command.lower():
                        contract_address = extract_contract_address_from_stellar_expert(tx_hash, network)
                        if contract_address:
                            print(f"📍 Contract deployed at: {contract_address}")
                            return {
                                'success': True,
                                'tx_hash': tx_hash,
                                'contract_address': contract_address,
                                'output': output
                            }
                    
                    # For upload operations, extract WASM hash from output
                    if "upload" in command.lower():
                        wasm_hash = extract_wasm_hash_from_output(output)
                        if wasm_hash:
                            return {
                                'success': True,
                                'tx_hash': tx_hash,
                                'wasm_hash': wasm_hash,
                                'output': output
                            }
                    
                    return {
                        'success': True,
                        'tx_hash': tx_hash,
                        'output': output
                    }
                else:
                    print("❌ Transaction failed")
                    raise subprocess.CalledProcessError(1, command, output)
            else:
                print("⚠️ Could not extract transaction hash from output")
                raise subprocess.CalledProcessError(1, command, output)
        
        # Normal success case
        if result.returncode == 0:
            return {
                'success': True,
                'output': result.stdout.strip()
            }
        else:
            raise subprocess.CalledProcessError(result.returncode, command, output)
            
    except subprocess.CalledProcessError as e:
        if debug:
            with open("debug_output.json", "a") as f:
                json.dump({"command": command, "stdout": getattr(e, 'stdout', ''), "stderr": getattr(e, 'stderr', '')}, f)
                f.write("\n")
        print(f"Error running command: {command}")
        print(f"Error: {e}")
        raise

def extract_wasm_hash_from_output(output):
    """Extract WASM hash from CLI output."""
    import re
    hash_matches = re.findall(r'\b[a-f0-9]{64}\b', output)
    if hash_matches:
        return hash_matches[-1]  # Return the last one found
    return None

def deploy_contract(wasm_file, deployer_acct, network, rpc_url, debug=False):
    """Upload a WASM file to the Stellar network with XDR workaround."""
    contract_name = os.path.splitext(os.path.basename(wasm_file))[0]
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
    
    # Use Stellar CLI upload command
    upload_command = (
        f"stellar contract upload --source-account {deployer_acct} "
        f"--wasm {wasm_file} --network {network} "
        f"--network-passphrase \"{network_passphrase}\" "
        f"--rpc-url {rpc_url} "
        f"--fee 100000"
    )
    
    try:
        result = run_command_with_xdr_workaround(upload_command, debug, network)
        
        if result['success']:
            # Extract WASM hash from result if available
            extracted_hash = result.get('wasm_hash')
            if extracted_hash:
                print(f"Uploaded {contract_name}: {extracted_hash}")
                with open("deployments.md", "a") as f:
                    f.write(f"\n- {contract_name}: {extracted_hash} (TX: {result.get('tx_hash', 'N/A')})")
                return extracted_hash
            else:
                # Fallback to CLI output parsing
                output = result['output']
                # Try to extract hash from output
                hash_match = re.search(r'\b[a-f0-9]{64}\b', output)
                if hash_match:
                    extracted_hash = hash_match.group(0)
                    print(f"Uploaded {contract_name}: {extracted_hash}")
                    with open("deployments.md", "a") as f:
                        f.write(f"\n- {contract_name}: {extracted_hash} (TX: {result.get('tx_hash', 'N/A')})")
                    return extracted_hash
                else:
                    print(f"Uploaded {contract_name}: {output}")
                    with open("deployments.md", "a") as f:
                        f.write(f"\n- {contract_name}: {output} (TX: {result.get('tx_hash', 'N/A')})")
                    return output
        else:
            raise subprocess.CalledProcessError(1, upload_command, result.get('output', ''))
            
    except subprocess.CalledProcessError as e:
        print(f"Failed to upload {contract_name}")
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

    wasm_files = sorted(glob.glob(os.path.join(args.release_dir, "*.wasm")))
    if not wasm_files:
        print(f"No WASM files found in {args.release_dir}")
        exit(1)

    deployments = []
    failed_count = 0
    
    for wasm_file in wasm_files:
        try:
            result = deploy_contract(wasm_file, args.deployer_acct, args.network, args.rpc_url, args.debug)
            deployments.append(f"✅ Successfully uploaded {os.path.basename(wasm_file)}: {result}")
        except Exception as e:
            failed_count += 1
            deployments.append(f"❌ Failed to upload {os.path.basename(wasm_file)}: {e}")
            if args.debug:
                print("Check debug_output.json for details")
            continue

    with open("deployments.md", "w") as f:
        f.write("# Deployment Results\n\n")
        f.write("\n".join(deployments))
        f.write(f"\n\n**Summary**: {len(wasm_files) - failed_count}/{len(wasm_files)} deployments successful")
    
    # Exit with error code if any deployments failed
    if failed_count > 0:
        print(f"\n❌ {failed_count}/{len(wasm_files)} deployments failed")
        exit(1)
    else:
        print(f"\n✅ All {len(wasm_files)} deployments successful")

if __name__ == "__main__":
    main()