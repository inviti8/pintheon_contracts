#!/usr/bin/env python3
"""
Deployment script that works around XDR processing errors by checking transaction success via API.
Supports both local and cloud deployment modes.
"""

import subprocess
import json
import time
import re
import requests
import sys
import os
import argparse
import toml
from pathlib import Path
from typing import Optional, Dict, Any

# Cloud deployment configuration
CLOUD_IDENTITY_DIR = os.path.expanduser("~/.stellar/identity")
CLOUD_CONFIG_DIR = os.path.expanduser("~/.stellar")
DEFAULT_IDENTITY_NAME = "DEPLOYER"

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
    """Deploy contract using the XDR workaround.
    
    Args:
        contract_name (str): Name of the contract being deployed
        wasm_path (str): Path to the WASM file
        constructor_args (str): Constructor arguments as a string
        network (str): Network to deploy to (testnet/public/futurenet)
        source_account (str): Source account to use for deployment
        
    Returns:
        dict: Deployment details or None if failed
    """
    print(f"\n🚀 Deploying {contract_name} with XDR workaround...")
    print(f"   Network: {network}")
    print(f"   Source: {source_account}")
    
    try:
        # Validate WASM file exists
        if not os.path.exists(wasm_path):
            print(f"❌ WASM file not found: {wasm_path}")
            return None
            
        # Step 1: Upload WASM
        print("📤 Uploading WASM...")
        upload_cmd = f"stellar contract upload --wasm {wasm_path} --network {network} --source-account {source_account}"
        upload_result = run_stellar_command_with_xdr_workaround(upload_cmd)
        
        if not upload_result['success']:
            print(f"❌ Failed to upload WASM for {contract_name}")
            if 'error' in upload_result:
                print(f"   Error: {upload_result['error']}")
            return None
            
        wasm_hash = extract_wasm_hash_from_output(upload_result['output'])
        if not wasm_hash:
            print(f"⚠️ Could not extract WASM hash from upload output")
            wasm_hash = "UNKNOWN"
        else:
            print(f"✅ WASM uploaded successfully: {wasm_hash}")
        
        # Step 2: Deploy contract
        print("🚀 Deploying contract...")
        deploy_cmd = f"stellar contract deploy"
        deploy_cmd += f" --wasm-hash {wasm_hash}"
        deploy_cmd += f" --network {network}"
        deploy_cmd += f" --source-account {source_account}"
        
        # Add constructor args after --
        if constructor_args:
            deploy_cmd += f" -- {constructor_args}"
        
        print(f"Running: {deploy_cmd}")
        deploy_result = run_stellar_command_with_xdr_workaround(deploy_cmd)
        
        if not deploy_result['success']:
            print(f"❌ Failed to deploy {contract_name}")
            if 'error' in deploy_result:
                print(f"   Error: {deploy_result['error']}")
            return None
        
        # Extract contract address from transaction
        contract_address = None
        if deploy_result.get('tx_hash'):
            contract_address = extract_contract_address_from_stellar_expert(
                deploy_result['tx_hash'],
                network=network
            )
        
        # Prepare result
        result = {
            'name': contract_name,
            'wasm_hash': wasm_hash,
            'tx_hash': deploy_result.get('tx_hash'),
            'address': contract_address if contract_address else 'UNKNOWN',
            'network': network,
            'source_account': source_account
        }
        
        # Print success message
        print(f"✅ Successfully deployed {contract_name}")
        print(f"   Contract Address: {result['address']}")
        print(f"   Transaction: {result['tx_hash'] or 'Unknown'}")
        
        return result
        
    except Exception as e:
        print(f"❌ Unexpected error deploying {contract_name}: {str(e)}")
        return None

def setup_cloud_identity(secret_key: str, identity_name: str = DEFAULT_IDENTITY_NAME) -> bool:
    """Set up Stellar CLI identity for cloud deployment."""
    try:
        from stellar_sdk import Keypair
        
        # Create identity directory if it doesn't exist
        os.makedirs(CLOUD_IDENTITY_DIR, exist_ok=True)
        
        # Generate a new mnemonic phrase
        mnemonic_phrase = Keypair.generate_mnemonic_phrase()
        
        # Create identity file
        identity_file = os.path.join(CLOUD_IDENTITY_DIR, f"{identity_name}.toml")
        with open(identity_file, 'w') as f:
            toml.dump({'seed_phrase': mnemonic_phrase}, f)
        
        # Verify the identity
        keypair = Keypair.from_mnemonic_phrase(mnemonic_phrase)
        print(f"✅ Created Stellar identity: {identity_name}")
        print(f"   Public key: {keypair.public_key}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to set up cloud identity: {str(e)}")
        return False

def configure_network(network: str, rpc_url: Optional[str] = None) -> bool:
    """Configure Stellar network settings."""
    try:
        # Create config directory if it doesn't exist
        os.makedirs(CLOUD_CONFIG_DIR, exist_ok=True)
        
        config_file = os.path.join(CLOUD_CONFIG_DIR, 'config.toml')
        config = {}
        
        # Load existing config if it exists
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = toml.load(f)
        
        # Update network settings
        if 'network' not in config:
            config['network'] = {}
        
        config['network']['name'] = network
        if rpc_url:
            config['network']['rpc_url'] = rpc_url
        
        # Save config
        with open(config_file, 'w') as f:
            toml.dump(config, f)
        
        print(f"✅ Configured network: {network}")
        if rpc_url:
            print(f"   RPC URL: {rpc_url}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to configure network: {str(e)}")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Deploy Stellar contracts with XDR workaround')
    
    # Cloud deployment arguments
    cloud_group = parser.add_argument_group('Cloud Deployment')
    cloud_group.add_argument('--cloud', action='store_true', help='Enable cloud deployment mode')
    cloud_group.add_argument('--mode', choices=['local', 'cloud'], default='local',
                           help='Deployment mode (default: %(default)s)')
    cloud_group.add_argument('--secret-key', type=str, help='Secret key for cloud deployment')
    cloud_group.add_argument('--deployer-account', type=str, help='Deployer account address')
    cloud_group.add_argument('--wasm-dir', type=str, default='.',
                           help='Directory containing WASM files (default: current directory)')
    cloud_group.add_argument('--rpc-url', type=str, help='RPC URL for the network')
    cloud_group.add_argument('--network', type=str, choices=['testnet', 'public', 'futurenet'], default='testnet',
                           help='Network to deploy to (default: %(default)s)')
    cloud_group.add_argument('--contract', type=str, help='Specific contract to deploy')
    cloud_group.add_argument('--post-deploy-config', type=str,
                           help='Path to post-deployment configuration file')
    
    # Contract deployment arguments
    contract_group = parser.add_argument_group('Contract Deployment')
    contract_group.add_argument('--wasm-path', type=str,
                              help='Path to the WASM file to deploy (overrides --wasm-dir)')
    
    # Local deployment arguments
    local_group = parser.add_argument_group('Local Deployment')
    local_group.add_argument('--identity-name', type=str, default=DEFAULT_IDENTITY_NAME,
                           help='Name for the identity file (default: %(default)s)')
    
    return parser.parse_args()

def get_wasm_path(contract_name, wasm_dir, cloud_mode=False):
    """Get the correct WASM path based on deployment mode."""
    if cloud_mode:
        # In cloud mode, use the release-wasm directory with hyphenated names
        wasm_name = contract_name.replace('_', '-') + '.wasm'
        return os.path.join(wasm_dir, wasm_name)
    else:
        # In local mode, use the standard target directory structure
        return os.path.join(contract_name, 'target', 'wasm32-unknown-unknown', 'release', f"{contract_name.replace('-', '_')}.wasm")

def main():
    """Main deployment function."""
    print("🔧 Stellar Contract Deployment with XDR Workaround")
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Determine if we're in cloud mode (either --cloud flag or --mode=cloud)
    cloud_mode = args.cloud or args.mode == 'cloud'
    wasm_dir = args.wasm_dir or ('.' if not cloud_mode else 'release-wasm')
    
    # Handle cloud deployment setup
    if cloud_mode:
        if not args.secret_key and not args.deployer_account:
            print("❌ Error: Either --secret-key or --deployer-account is required for cloud deployment")
            sys.exit(1)
            
        print("☁️  Setting up cloud deployment...")
        
        # Set up identity if secret key is provided
        if args.secret_key:
            if not setup_cloud_identity(args.secret_key, args.identity_name):
                sys.exit(1)
            source_account = args.identity_name
        else:
            source_account = args.deployer_account
            
        # Configure network
        if not configure_network(args.network, args.rpc_url):
            sys.exit(1)
            
        print(f"✅ Cloud deployment setup complete")
        print(f"   Using account: {source_account}")
        print(f"   Network: {args.network}")
        
        # If specific contract deployment was requested
        if args.contract:
            wasm_path = args.wasm_path or os.path.join(args.wasm_dir, f"{args.contract}.wasm")
            if not os.path.exists(wasm_path):
                print(f"❌ Error: WASM file not found at {wasm_path}")
                sys.exit(1)
                
            result = deploy_contract_with_workaround(
                contract_name=args.contract,
                wasm_path=wasm_path,
                network=args.network,
                source_account=source_account
            )
            
            # Handle post-deployment configuration if specified
            if result and args.post_deploy_config and os.path.exists(args.post_deploy_config):
                print(f"📋 Applying post-deployment configuration from {args.post_deploy_config}")
                # Add post-deployment logic here if needed
                
            if not result:
                sys.exit(1)
            return
    else:
        # Local development mode with test account
        print("🏠 Running in local development mode")
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
    
    # Set up deployment mode message
    if cloud_mode:
        print("\n☁️  Cloud deployment mode: Using pre-built WASM files from", wasm_dir)
    else:
        print("\n💻 Local deployment mode: Using local build artifacts")
    
    # Deploy contracts in dependency order
    deployments = []
    
    # Step 1: Deploy dependency contracts (upload only - these are imported by hvym-collective)
    # Order matches GitHub Actions build order: node-token first, then ipfs-token
    dependency_contracts = [
        {
            "name": "pintheon-node-token", 
            "wasm": get_wasm_path("pintheon-node-token", wasm_dir, cloud_mode),
            "deploy": False  # These are dependencies, we just need to upload them
        },
        {
            "name": "pintheon-ipfs-token",
            "wasm": get_wasm_path("pintheon-ipfs-token", wasm_dir, cloud_mode),
            "deploy": False  # These are dependencies, we just need to upload them
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
    opus_wasm = get_wasm_path("opus-token", wasm_dir, cloud_mode)
    if os.path.exists(opus_wasm):
        opus_result = deploy_contract_with_workaround(
            "opus_token",
            opus_wasm,
            f"--admin {source_account}",
            source_account=source_account
        )
        if opus_result:
            deployments.append(opus_result)
    else:
        print(f"⚠️ Opus Token WASM not found: {opus_wasm}")
    
    # Step 3: Deploy HVYM Collective (final contract with all dependencies)
    collective_wasm = get_wasm_path("hvym-collective", wasm_dir, cloud_mode)
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
        
        # Save JSON data
        json_file = "deployments.json"
        with open(json_file, 'w') as f:
            json.dump(deployment_data, f, indent=2)
        
        # Generate markdown report
        md_file = "deployments.md"
        with open(md_file, 'w') as f:
            f.write("# Deployment Summary\n\n")
            f.write(f"- **Network**: {deployment_data['network'].capitalize()}\n")
            f.write(f"- **Deployment Time**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
            f.write(f"- **CLI Version**: {deployment_data['cli_version']}\n\n")
            
            f.write("## Contracts Deployed\n\n")
            f.write("| Contract | Address | Transaction |\n")
            f.write("|----------|---------|-------------|\n")
            
            for deployment in deployments:
                if 'upload_only' in deployment and deployment['upload_only']:
                    f.write(f"| {deployment['name']} (WASM only) | - | - |\n")
                else:
                    tx_hash = deployment.get('tx_hash', '')
                    tx_link = f"[View on Stellar Expert](https://stellar.expert/explorer/{deployment_data['network']}/tx/{tx_hash})" if tx_hash else "-"
                    f.write(f"| {deployment['name']} | `{deployment.get('address', 'Failed')}` | {tx_link} |\n")
        
        print(f"\n🎉 Deployment completed! {len(deployments)} contracts processed")
        print(f"📄 JSON results saved to {json_file}")
        print(f"📝 Markdown report saved to {md_file}")
        
        # Print summary to console
        print("\n📋 Deployment Summary:")
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
