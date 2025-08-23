#!/usr/bin/env python3
"""
Deployment script that works around XDR processing errors by checking transaction success via API.
"""

import subprocess
import json
import time
import re
import requests
import sys
import os
from pathlib import Path

def extract_transaction_hash(output):
    """Extract transaction hash from CLI output."""
    # Look for transaction hash patterns
    hash_patterns = [
        r'Transaction hash is ([a-f0-9]{64})',
        r'Signing transaction: ([a-f0-9]{64})',
        r'tx/([a-f0-9]{64})'
    ]
    
    for pattern in hash_patterns:
        match = re.search(pattern, output)
        if match:
            return match.group(1)
    return None

def check_transaction_success(tx_hash, network="testnet", max_retries=30):
    """Check if transaction succeeded using Stellar API."""
    if network == "testnet":
        base_url = "https://horizon-testnet.stellar.org"
    else:
        base_url = "https://horizon.stellar.org"
    
    url = f"{base_url}/transactions/{tx_hash}"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                tx_data = response.json()
                if tx_data.get('successful', False):
                    print(f"✅ Transaction {tx_hash} confirmed as successful")
                    return True, tx_data
                else:
                    print(f"❌ Transaction {tx_hash} failed: {tx_data.get('result_xdr', 'Unknown error')}")
                    return False, tx_data
            elif response.status_code == 404:
                print(f"⏳ Transaction {tx_hash} not found yet, waiting... ({attempt+1}/{max_retries})")
                time.sleep(2)
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
        import base64
        
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
            # Contract addresses are typically in the last part of successful deployment results
            if len(hex_data) >= 64:
                # Try to extract the contract address from the result
                # Look for the pattern that represents the contract address
                potential_addresses = []
                
                # Method 1: Look for 32-byte sequences that could be contract addresses
                for i in range(0, len(hex_data) - 63, 2):
                    candidate = hex_data[i:i+64]
                    # Skip if it's all zeros or has obvious non-address patterns
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

def run_stellar_command_with_xdr_workaround(cmd, cwd=None):
    """Run stellar CLI command and handle XDR errors by checking transaction success."""
    print(f"🚀 Running: {cmd}")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        output = result.stdout + result.stderr
        print(f"📋 Command output:\n{output}")
        
        # Check if we got an XDR error
        if "xdr processing error" in output.lower():
            print("⚠️ XDR processing error detected, checking transaction status...")
            
            # Extract transaction hash
            tx_hash = extract_transaction_hash(output)
            if tx_hash:
                print(f"🔍 Found transaction hash: {tx_hash}")
                
                # Check if transaction actually succeeded
                success, tx_data = check_transaction_success(tx_hash)
                if success:
                    print("✅ Transaction succeeded despite XDR error!")
                    
                    # Try to extract contract address if this was a deployment
                    if "deploy" in cmd.lower():
                        contract_address = extract_contract_address_from_stellar_expert(tx_hash)
                        if contract_address:
                            print(f"📍 Contract deployed at: {contract_address}")
                            return {
                                'success': True,
                                'tx_hash': tx_hash,
                                'contract_address': contract_address,
                                'output': output
                            }
                    
                    return {
                        'success': True,
                        'tx_hash': tx_hash,
                        'output': output
                    }
                else:
                    print("❌ Transaction actually failed")
                    return {
                        'success': False,
                        'tx_hash': tx_hash,
                        'output': output
                    }
            else:
                print("❌ Could not extract transaction hash from output")
                return {
                    'success': False,
                    'output': output
                }
        
        # No XDR error, check normal success
        elif result.returncode == 0:
            print("✅ Command succeeded normally")
            return {
                'success': True,
                'output': output
            }
        else:
            print(f"❌ Command failed with return code {result.returncode}")
            return {
                'success': False,
                'output': output
            }
            
    except subprocess.TimeoutExpired:
        print("❌ Command timed out")
        return {
            'success': False,
            'output': 'Command timed out'
        }
    except Exception as e:
        print(f"❌ Command execution error: {e}")
        return {
            'success': False,
            'output': str(e)
        }

def upload_wasm_with_workaround(contract_name, wasm_path, network="testnet", source_account="test-deployer"):
    """Upload WASM file with XDR workaround (for dependency contracts)."""
    print(f"\n📤 Uploading {contract_name} WASM...")
    
    # Upload WASM
    upload_cmd = f"stellar contract upload --wasm {wasm_path} --network {network} --source-account {source_account}"
    upload_result = run_stellar_command_with_xdr_workaround(upload_cmd)
    
    if upload_result['success']:
        # Extract WASM hash from output or transaction
        wasm_hash = extract_wasm_hash_from_output(upload_result['output'])
        if wasm_hash:
            print(f"✅ {contract_name} WASM uploaded successfully: {wasm_hash}")
            return {
                'name': contract_name,
                'wasm_hash': wasm_hash,
                'tx_hash': upload_result.get('tx_hash')
            }
        else:
            print(f"⚠️ {contract_name} uploaded but could not extract WASM hash")
            return {
                'name': contract_name,
                'tx_hash': upload_result.get('tx_hash')
            }
    else:
        print(f"❌ Failed to upload {contract_name} WASM")
        return None

def extract_wasm_hash_from_output(output):
    """Extract WASM hash from CLI output."""
    # Look for 64-character hex strings in the output
    import re
    hash_matches = re.findall(r'\b[a-f0-9]{64}\b', output)
    if hash_matches:
        return hash_matches[-1]  # Return the last one found
    return None

def load_hvym_collective_args(opus_token_address, admin_account):
    """Load HVYM Collective constructor arguments."""
    args_file = "hvym-collective_args.json"
    
    # Default arguments
    default_args = {
        "admin": admin_account,
        "join_fee": 1000000,  # 0.1 XLM in stroops
        "mint_fee": 500000,   # 0.05 XLM in stroops  
        "token": opus_token_address,
        "reward": 100000     # 0.01 XLM in stroops
    }
    
    # Try to load from JSON file
    if os.path.exists(args_file):
        try:
            with open(args_file, 'r') as f:
                file_args = json.load(f)
            
            # Convert XLM values to stroops if needed
            for key in ["join_fee", "mint_fee", "reward"]:
                if key in file_args:
                    try:
                        file_args[key] = int(float(file_args[key]) * 10_000_000)
                    except:
                        pass
            
            # Merge with defaults
            default_args.update(file_args)
            print(f"📄 Loaded constructor args from {args_file}")
        except Exception as e:
            print(f"⚠️ Error loading {args_file}: {e}, using defaults")
    else:
        print(f"📄 Using default constructor args (no {args_file} found)")
    
    # Override with current values
    default_args["admin"] = admin_account
    default_args["token"] = opus_token_address
    
    # Convert to CLI argument format
    cli_args = []
    for key, value in default_args.items():
        cli_args.extend([f"--{key.replace('_', '-')}", str(value)])
    
    return " ".join(cli_args)

def deploy_contract_with_workaround(contract_name, wasm_path, constructor_args="", network="testnet", source_account="test-deployer"):
    """Deploy contract using the XDR workaround."""
    print(f"\n🚀 Deploying {contract_name} with XDR workaround...")
    
    # Step 1: Upload WASM
    print("📤 Uploading WASM...")
    upload_cmd = f"stellar contract upload --wasm {wasm_path} --network {network} --source-account {source_account}"
    upload_result = run_stellar_command_with_xdr_workaround(upload_cmd)
    
    if not upload_result['success']:
        print(f"❌ Failed to upload WASM for {contract_name}")
        return None
    
    # Extract WASM hash from output
    wasm_hash = None
    hash_match = re.search(r'([a-f0-9]{64})', upload_result['output'])
    if hash_match:
        wasm_hash = hash_match.group(1)
        print(f"📦 WASM hash: {wasm_hash}")
    else:
        print("❌ Could not extract WASM hash")
        return None
    
    # Step 2: Deploy contract
    print("🚀 Deploying contract...")
    deploy_cmd = f"stellar contract deploy --wasm-hash {wasm_hash} --network {network} --source-account {source_account}"
    if constructor_args:
        deploy_cmd += f" -- {constructor_args}"
    
    deploy_result = run_stellar_command_with_xdr_workaround(deploy_cmd)
    
    if deploy_result['success']:
        contract_address = deploy_result.get('contract_address')
        if not contract_address:
            # Try to extract from output
            addr_match = re.search(r'(C[A-Z0-9]{55})', deploy_result['output'])
            if addr_match:
                contract_address = addr_match.group(1)
        
        if contract_address:
            print(f"✅ {contract_name} deployed successfully!")
            return {
                'name': contract_name,
                'address': contract_address,
                'wasm_hash': wasm_hash,
                'tx_hash': deploy_result.get('tx_hash')
            }
        else:
            print(f"⚠️ {contract_name} deployed but could not extract address")
            return {
                'name': contract_name,
                'wasm_hash': wasm_hash,
                'tx_hash': deploy_result.get('tx_hash'),
                'address': 'UNKNOWN'
            }
    else:
        print(f"❌ Failed to deploy {contract_name}")
        return None

def main():
    """Main deployment function."""
    print("🔧 Stellar Contract Deployment with XDR Workaround")
    
    # Ensure we have a funded test account
    print("💰 Checking test account...")
    # Try to fund existing account first
    fund_result = run_stellar_command_with_xdr_workaround(
        "stellar keys fund test-deployer --network testnet"
    )
    
    if not fund_result['success']:
        print("⚠️ Account funding failed, trying to create new account...")
        setup_result = run_stellar_command_with_xdr_workaround(
            "stellar keys generate --global --network testnet test-deployer-new --fund"
        )
        if setup_result['success']:
            source_account = "test-deployer-new"
        else:
            print("❌ Failed to setup test account")
            sys.exit(1)
    else:
        source_account = "test-deployer"
        print("✅ Using existing test-deployer account")
    
    # Build all contracts first
    print("\n🔨 Building contracts...")
    contracts_to_build = ["opus_token", "hvym-collective", "hvym-collective-factory"]
    
    for contract in contracts_to_build:
        if os.path.exists(contract):
            print(f"Building {contract}...")
            build_result = run_stellar_command_with_xdr_workaround(
                "stellar contract build",
                cwd=contract
            )
            if not build_result['success']:
                print(f"❌ Failed to build {contract}")
    
    # Deploy contracts in dependency order
    deployments = []
    
    # Step 1: Deploy dependency contracts (upload only - these are imported by hvym-collective)
    # Order matches GitHub Actions build order: node-token first, then ipfs-token
    dependency_contracts = [
        {
            "name": "pintheon-node-token", 
            "wasm": "pintheon-node-deployer/pintheon-node-token/target/wasm32-unknown-unknown/release/pintheon_node_token.wasm",
            "upload_only": True
        },
        {
            "name": "pintheon-ipfs-token",
            "wasm": "pintheon-ipfs-deployer/pintheon-ipfs-token/target/wasm32-unknown-unknown/release/pintheon_ipfs_token.wasm",
            "upload_only": True
        }
    ]
    
    dependency_hashes = {}
    for dep in dependency_contracts:
        if os.path.exists(dep["wasm"]):
            print(f"\n📤 Uploading dependency: {dep['name']}")
            upload_result = upload_wasm_with_workaround(dep["name"], dep["wasm"], source_account=source_account)
            if upload_result:
                dependency_hashes[dep["name"]] = upload_result["wasm_hash"]
                deployments.append({
                    "name": dep["name"],
                    "wasm_hash": upload_result["wasm_hash"],
                    "upload_only": True,
                    "tx_hash": upload_result.get("tx_hash")
                })
        else:
            print(f"⚠️ Dependency WASM not found: {dep['wasm']}")
    
    # Step 2: Deploy Opus Token
    opus_result = None
    opus_wasm = "opus_token/target/wasm32-unknown-unknown/release/opus_token.wasm"
    if os.path.exists(opus_wasm):
        opus_result = deploy_contract_with_workaround(
            "opus_token",
            opus_wasm,
            f"--admin {source_account}",
            source_account=source_account
        )
        if opus_result:
            deployments.append(opus_result)
    
    # Step 3: Deploy HVYM Collective (final contract with all dependencies)
    # Note: hvym-collective-factory is not built by GitHub Actions, so skipping it
    collective_wasm = "hvym-collective/target/wasm32-unknown-unknown/release/hvym_collective.wasm"
    if os.path.exists(collective_wasm) and opus_result:
        # Load constructor arguments from JSON file if available
        constructor_args = load_hvym_collective_args(opus_result['address'], source_account)
        
        collective_result = deploy_contract_with_workaround(
            "hvym-collective",
            collective_wasm,
            constructor_args,
            source_account=source_account
        )
        if collective_result:
            deployments.append(collective_result)
    else:
        if not os.path.exists(collective_wasm):
            print(f"⚠️ HVYM Collective WASM not found: {collective_wasm}")
        if not opus_result:
            print("⚠️ Cannot deploy HVYM Collective: Opus Token deployment failed")
    
    # Save results
    if deployments:
        deployment_data = {
            "network": "testnet",
            "timestamp": int(time.time()),
            "cli_version": "22.8.2",
            "note": "Deployed with XDR workaround - transactions succeeded despite CLI errors",
            "contracts": deployments
        }
        
        with open("xdr_workaround_deployments.json", "w") as f:
            json.dump(deployment_data, f, indent=2)
        
        print(f"\n🎉 Deployment completed! {len(deployments)} contracts deployed")
        print("📄 Results saved to xdr_workaround_deployments.json")
        
        for deployment in deployments:
            if 'upload_only' in deployment and deployment['upload_only']:
                print(f"  • {deployment['name']}: WASM uploaded (upload only)")
            else:
                print(f"  • {deployment['name']}: {deployment.get('address', 'Deployment failed')}")
    else:
        print("\n❌ No contracts were successfully deployed")
        sys.exit(1)

if __name__ == "__main__":
    main()
