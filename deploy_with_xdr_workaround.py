#!/usr/bin/env python3
"""
Deployment script that works around XDR processing errors by checking transaction success via API.
Supports both local development and cloud deployment modes.
"""

import subprocess
import json
import time
import re
import requests
import sys
import os
import argparse
from pathlib import Path

# Stellar SDK imports
from stellar_sdk import Keypair, Network, Server
from stellar_sdk.transaction_builder import TransactionBuilder, TransactionEnvelope
from stellar_sdk.operation import InvokeHostFunction, Operation
from stellar_sdk.xdr import Xdr
from stellar_sdk.soroban import SorobanServer
from stellar_sdk.soroban.soroban_rpc import TransactionStatus
from stellar_sdk.exceptions import NotFoundError, BadRequestError

def get_soroban_server(network, rpc_url=None):
    """Get a Soroban server instance for the specified network."""
    if not rpc_url:
        rpc_url = {
            'testnet': 'https://soroban-testnet.stellar.org',
            'futurenet': 'https://rpc-futurenet.stellar.org',
            'mainnet': 'https://horizon.stellar.org',
        }.get(network, 'https://soroban-testnet.stellar.org')
    
    return SorobanServer(rpc_url)

def get_network_passphrase(network):
    """Get the network passphrase for the specified network."""
    return {
        'testnet': Network.TESTNET_NETWORK_PASSPHRASE,
        'futurenet': Network.FUTURENET_NETWORK_PASSPHRASE,
        'mainnet': Network.PUBLIC_NETWORK_PASSPHRASE,
    }.get(network, Network.TESTNET_NETWORK_PASSPHRASE)

def setup_account(secret_key, network, rpc_url=None):
    """Set up and fund an account using the provided secret key."""
    try:
        keypair = Keypair.from_secret(secret_key)
        soroban_server = get_soroban_server(network, rpc_url)
        
        # Check if account exists and is funded
        try:
            account = soroban_server.load_account(keypair.public_key)
            print(f"✅ Using existing account: {keypair.public_key}")
            return keypair
        except NotFoundError:
            print(f"Account {keypair.public_key} not found, attempting to fund...")
            if network == 'testnet':
                # Try to fund using friendbot
                response = requests.get(
                    f"https://friendbot.stellar.org?addr={keypair.public_key}"
                )
                if response.status_code == 200:
                    print(f"✅ Successfully funded account: {keypair.public_key}")
                    return keypair
                else:
                    raise Exception(f"Failed to fund account: {response.text}")
            else:
                raise Exception(f"Account {keypair.public_key} not found and automatic funding not supported for {network}")
                
    except Exception as e:
        print(f"❌ Error setting up account: {str(e)}")
        raise

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

def run_stellar_command_with_xdr_workaround(cmd, cwd=None, network="testnet", rpc_url=None):
    """Run stellar CLI command and handle XDR errors by checking transaction success."""
    print(f"⚡ Running: {cmd}")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False
        )
        
        output = result.stdout + "\n" + result.stderr
        
        # Check for XDR processing errors
        if "XDR processing error" in output or "tx_bad_seq" in output:
            print("⚠️ Detected XDR processing error, attempting workaround...")
            tx_hash = extract_transaction_hash(output)
            if tx_hash:
                print(f"🔍 Found transaction hash: {tx_hash}")
                success, tx_data = check_transaction_success(tx_hash, network=network, rpc_url=rpc_url)
                if success:
                    print("✅ Transaction confirmed successful via API")
                    # Try to extract contract address from transaction data
                    contract_address = extract_contract_address_from_stellar_expert(tx_hash, network=network)
                    return {
                        'success': True,
                        'output': output,
                        'tx_hash': tx_hash,
                        'contract_address': contract_address
                    }
                else:
                    print("❌ Transaction failed according to API")
                    return {'success': False, 'output': output, 'error': 'Transaction failed'}
            else:
                print("❌ Could not extract transaction hash from output")
                return {'success': False, 'output': output, 'error': 'No transaction hash found'}
        
        # If we got here, either the command succeeded or failed without XDR issues
        return {
            'success': result.returncode == 0,
            'output': output,
            'returncode': result.returncode
        }
        
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return {'success': False, 'error': str(e)}

def upload_wasm_with_workaround(contract_name, wasm_path, network="testnet", source_account="test-deployer", rpc_url=None):
    """Upload WASM file with XDR workaround (for dependency contracts)."""
    print(f"📤 Uploading {contract_name} WASM...")
    
    # Build the upload command
    cmd = [
        "stellar", "contract", "install",
        "--wasm", wasm_path,
        "--source", source_account,
        "--network", network,
        "--force"
    ]
    
    # Add RPC URL if provided
    if rpc_url:
        cmd.extend(["--rpc-url", rpc_url])
    
    # Run the command with XDR workaround
    result = run_stellar_command_with_xdr_workaround(" ".join(cmd), network=network, rpc_url=rpc_url)
    
    if result['success']:
        wasm_hash = extract_wasm_hash_from_output(result['output'])
        if wasm_hash:
            print(f"✅ Uploaded {contract_name} (WASM hash: {wasm_hash})")
            return {
                'name': contract_name,
                'wasm_hash': wasm_hash,
                'tx_hash': result.get('tx_hash')
            }
    
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

def load_hvym_collective_args(opus_token_address, admin_account, args_file=None):
    """Load HVYM Collective constructor arguments.
    
    Args:
        opus_token_address: The OPUS token address (used for reward distribution)
        admin_account: The admin account address (always takes precedence)
        args_file: Optional path to args file. If None, looks for 'hvym-collective_args.json' in current dir.
    
    Returns:
        list: CLI arguments for the contract deployment
    """
    if args_file is None:
        args_file = "hvym-collective_args.json"
    
    # Default arguments (in stroops)
    default_args = {
        "admin": admin_account,
        "join_fee": 1000000,  # 0.1 XLM in stroops
        "mint_fee": 500000,   # 0.05 XLM in stroops  
        "token": "CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC",  # Default payment token (XLM)
        "reward": 100000     # 0.01 XLM in stroops
    }
    
    # Try to load from JSON file if it exists
    if os.path.exists(args_file):
        try:
            with open(args_file, 'r') as f:
                file_args = json.load(f)
            
            # Convert XLM values to stroops if needed (handles both string and number inputs)
            for key in ["join_fee", "mint_fee", "reward"]:
                if key in file_args:
                    try:
                        # Handle both string and numeric inputs
                        value = file_args[key]
                        if isinstance(value, str):
                            # If it's a string, try to convert XLM to stroops
                            file_args[key] = int(float(value) * 10_000_000)
                        else:
                            # Assume it's already in stroops if it's a number
                            file_args[key] = int(value)
                    except (ValueError, TypeError) as e:
                        print(f"⚠️ Invalid value for {key} in {args_file}, using default: {e}")
                        continue
            
            # Merge file args with defaults (file args take precedence)
            default_args.update(file_args)
            print(f"📄 Loaded constructor args from {args_file}")
            
        except Exception as e:
            print(f"⚠️ Error loading {args_file}: {e}, using defaults")
    else:
        print(f"📄 Using default constructor args (no {args_file} found)")
    
    # Always ensure admin is up-to-date from function arguments
    default_args["admin"] = admin_account
    
    # The 'token' field should remain as the payment token from the args file or defaults
    # We don't override it with opus_token_address here
    
    # Add opus_token as a separate argument
    default_args["opus_token"] = opus_token_address
    
    # Validate required arguments
    required_args = ["admin", "token", "join_fee", "mint_fee", "reward", "opus_token"]
    missing = [arg for arg in required_args if arg not in default_args]
    if missing:
        raise ValueError(f"Missing required constructor arguments: {', '.join(missing)}")
    
    # Convert to CLI argument format
    cli_args = []
    for key, value in default_args.items():
        cli_args.extend([f"--{key.replace('_', '-')}", str(value)])
        
    print(f"🔧 Using constructor args: {default_args}")
    print(f"   - Payment Token: {default_args['token']}")
    print(f"   - OPUS Token: {default_args['opus_token']}")
    
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

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Deploy contracts with XDR workaround')
    parser.add_argument('--mode', choices=['local', 'cloud'], default='local',
                      help='Deployment mode: local (build and deploy) or cloud (use pre-built WASM)')
    parser.add_argument('--wasm-dir', default='./target/wasm32-unknown-unknown/release',
                      help='Directory containing pre-built WASM files (required for cloud mode)')
    parser.add_argument('--deployer-account', help='Account to use for deployment (required for cloud mode)')
    parser.add_argument('--network', default='testnet', help='Network to deploy to (testnet, futurenet, mainnet)')
    parser.add_argument('--rpc-url', help='Custom RPC URL (default: based on network)')
    parser.add_argument('--strict', action='store_true', help='Fail on any error')
    parser.add_argument('--post-deploy-config', default='hvym-collective_post_deploy_args.json',
                      help='Path to post-deployment JSON config')
    parser.add_argument('--skip-post-deploy', action='store_true',
                      help='Skip post-deployment steps')
    return parser.parse_args()

def run_post_deployment(args, contract_id, network, deployments):
    """Run post-deployment steps for hvym-collective contract.
    
    Args:
        args: Command line arguments
        contract_id: ID of the deployed contract
        network: Network name (testnet/futurenet/mainnet)
        deployments: Deployments dictionary
        
    Returns:
        bool: True if post-deployment succeeded or was skipped, False on error
    """
    if args.skip_post_deploy:
        print("ℹ️  Skipping post-deployment steps as requested")
        return True
        
    config_path = args.post_deploy_config
    if not os.path.exists(config_path):
        print(f"⚠️  Post-deployment config not found at {config_path}, skipping")
        return True
        
    try:
        with open(config_path) as f:
            config = json.load(f)
            
        if not config.get("enabled", True):
            print("ℹ️  Post-deployment steps are disabled in config")
            return True
            
        print("🚀 Starting post-deployment steps...")
        
        # Get opus-token contract ID from deployments
        opus_contract_id = None
        if "opus_token" in deployments:
            opus_contract_id = deployments["opus_token"].get("contract_id")
        
        if not opus_contract_id:
            raise ValueError("opus_token contract_id not found in deployments")
            
        # Run post-deployment commands
        cmd = [
            "python3", "hvym_post_deploy.py",
            "--deployer-acct", args.deployer_account,
            "--network", network,
            "--fund-amount", str(config["fund_amount"]),
            "--initial-opus-alloc", str(config["initial_opus_alloc"])
        ]
        
        print(f"  ↳ Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        
        print("✅ Post-deployment steps completed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        error_msg = f"❌ Post-deployment failed with exit code {e.returncode}"
        if e.stdout:
            error_msg += f"\n  Stdout: {e.stdout}"
        if e.stderr:
            error_msg += f"\n  Stderr: {e.stderr}"
        print(error_msg)
        if args.strict:
            raise
        return False
    except Exception as e:
        print(f"❌ Error during post-deployment: {str(e)}")
        if args.strict:
            raise
        return False

def main():
    """Main deployment function."""
    args = parse_args()
    
    print("🔧 Stellar Contract Deployment with XDR Workaround")
    print(f"🚀 Mode: {args.mode.upper()}")
    print(f"🌐 Network: {args.network}")
    
    # Set RPC URL based on network if not provided
    if not args.rpc_url:
        args.rpc_url = {
            'testnet': 'https://soroban-testnet.stellar.org',
            'futurenet': 'https://rpc-futurenet.stellar.org',
            'mainnet': 'https://horizon.stellar.org'
        }.get(args.network, 'https://soroban-testnet.stellar.org')
    
    # Set default deployer account for local mode if not provided
    if not args.deployer_account:
        if args.mode == 'cloud':
            print("❌ --deployer-account is required in cloud mode")
            sys.exit(1)
        args.deployer_account = 'test-deployer'
    
    # In cloud mode, verify WASM directory exists
    if args.mode == 'cloud':
        wasm_dir = Path(args.wasm_dir)
        if not wasm_dir.exists() or not wasm_dir.is_dir():
            print(f"❌ WASM directory not found: {wasm_dir}")
            sys.exit(1)
        print(f"📦 Using WASM files from: {wasm_dir.absolute()}")
    
    # Handle account setup based on mode
    if args.mode == 'local':
        print("💰 Setting up local test account...")
        # For local mode, generate a new keypair if deployer_account is not provided
        if not args.deployer_account:
            keypair = Keypair.random()
            print(f"🔑 Generated new test account: {keypair.public_key}")
            print(f"   Secret Key: {keypair.secret}")
            print("   Note: Save this key if you need to reuse this account")
        else:
            keypair = Keypair.from_secret(args.deployer_account)
            print(f"🔑 Using provided deployer account: {keypair.public_key}")
        
        # Setup and fund the account
        try:
            keypair = setup_account(
                secret_key=keypair.secret,
                network=args.network,
                rpc_url=args.rpc_url
            )
            source_account = keypair.secret  # Use secret key for CLI compatibility
        except Exception as e:
            print(f"❌ Failed to set up account: {str(e)}")
            sys.exit(1)
    else:
        # In cloud mode, use the provided deployer account
        if not args.deployer_account:
            print("❌ --deployer-account is required in cloud mode")
            sys.exit(1)
            
        try:
            keypair = Keypair.from_secret(args.deployer_account)
            print(f"🔑 Using provided deployer account: {keypair.public_key}")
            
            # Verify and setup the account
            keypair = setup_account(
                secret_key=args.deployer_account,
                network=args.network,
                rpc_url=args.rpc_url
            )
            source_account = args.deployer_account  # Use the full secret key
        except Exception as e:
            print(f"❌ Failed to set up deployer account: {str(e)}")
            sys.exit(1)
    
    # Build contracts if in local mode
    if args.mode == 'local':
        print("\n🔨 Building contracts locally...")
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
    else:
        print("\n🔍 Using pre-built WASM files from cloud...")
    
    # Deploy contracts in dependency order
    deployments = []
    
    # Step 1: Deploy dependency contracts (upload only - these are imported by hvym-collective)
    dependency_contracts = [
        {
            "name": "pintheon-node-token",
            "local_wasm": "pintheon-node-deployer/pintheon-node-token/target/wasm32-unknown-unknown/release/pintheon_node_token.wasm",
            "cloud_wasm": "pintheon-node-token.wasm",
            "upload_only": True
        },
        {
            "name": "pintheon-ipfs-token",
            "local_wasm": "pintheon-ipfs-deployer/pintheon-ipfs-token/target/wasm32-unknown-unknown/release/pintheon_ipfs_token.wasm",
            "cloud_wasm": "pintheon-ipfs-token.wasm",
            "upload_only": True
        }
    ]
    
    dependency_hashes = {}
    for dep in dependency_contracts:
        wasm_path = dep["local_wasm"] if args.mode == 'local' else str(Path(args.wasm_dir) / dep["cloud_wasm"])
        
        if os.path.exists(wasm_path):
            print(f"\n📤 Uploading dependency: {dep['name']} ({wasm_path})")
            upload_result = upload_wasm_with_workaround(
                dep["name"],
                wasm_path,
                network=args.network,
                source_account=source_account,
                rpc_url=args.rpc_url
            )
            if upload_result:
                dependency_hashes[dep["name"]] = upload_result["wasm_hash"]
                deployments.append({
                    "name": dep["name"],
                    "wasm_hash": upload_result["wasm_hash"],
                    "upload_only": True,
                    "tx_hash": upload_result.get("tx_hash")
                })
        else:
            print(f"⚠️ Dependency WASM not found: {wasm_path}")
    
    # Step 2: Deploy Opus Token
    opus_result = None
    opus_wasm = "opus_token/target/wasm32-unknown-unknown/release/opus_token.wasm"
    if args.mode == 'cloud':
        opus_wasm = str(Path(args.wasm_dir) / "opus_token.wasm")
    
    if os.path.exists(opus_wasm):
        opus_result = deploy_contract_with_workaround(
            "opus_token",
            opus_wasm,
            f"--admin {source_account}",
            network=args.network,
            source_account=source_account,
            rpc_url=args.rpc_url
        )
        if opus_result:
            deployments.append(opus_result)
    
    # Step 3: Deploy HVYM Collective
    collective_wasm = "hvym-collective/target/wasm32-unknown-unknown/release/hvym_collective.wasm"
    if args.mode == 'cloud':
        collective_wasm = str(Path(args.wasm_dir) / "hvym_collective.wasm")
    
    if os.path.exists(collective_wasm) and opus_result:
        # In cloud mode, check for args file in the wasm directory first
        args_file = None
        if args.mode == 'cloud':
            cloud_args_file = Path(args.wasm_dir) / "hvym-collective_args.json"
            if cloud_args_file.exists():
                args_file = str(cloud_args_file)
                print(f"ℹ️  Using hvym-collective_args.json from wasm directory")
        
        # Load constructor arguments with the latest opus token address
        constructor_args = load_hvym_collective_args(
            opus_token_address=opus_result['address'],
            admin_account=source_account,
            args_file=args_file
        )
        
        collective_result = deploy_contract_with_workaround(
            "hvym-collective",
            collective_wasm,
            constructor_args,
            network=args.network,
            source_account=source_account,
            rpc_url=args.rpc_url
        )
        if collective_result:
            deployments.append(collective_result)
    else:
        if not os.path.exists(collective_wasm):
            print(f"⚠️ HVYM Collective WASM not found: {collective_wasm}")
        if not opus_result:
            print("⚠️ Cannot deploy HVYM Collective: Opus Token deployment failed")
    
    # Save results in the same format as deployments.json
    if deployments:
        # Load existing deployments to preserve any existing data
        try:
            with open("deployments.json", "r") as f:
                all_deployments = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            all_deployments = {}
        
        # Update with new deployments
        for deployment in deployments:
            contract_name = deployment['name']
            if 'upload_only' in deployment and deployment['upload_only']:
                # For upload-only contracts, we only update the wasm_hash
                if contract_name in all_deployments:
                    all_deployments[contract_name]['wasm_hash'] = deployment['wasm_hash']
                else:
                    all_deployments[contract_name] = {
                        'contract_dir': f"wasm_release/{contract_name}",
                        'wasm_hash': deployment['wasm_hash']
                    }
            else:
                # For deployed contracts, update or add the full deployment info
                all_deployments[contract_name] = {
                    'contract_dir': f"wasm_release/{contract_name}",
                    'wasm_hash': deployment['wasm_hash'],
                    'contract_id': deployment.get('address', '')
                }
        
        # Save the updated deployments
        with open("deployments.json", "w") as f:
            json.dump(all_deployments, f, indent=2)
        
        # Also update the deployments.md file
        try:
            with open("deployments.md", "w") as f:
                f.write("# Soroban Contract Deployments\n\n")
                f.write("| Contract | Contract ID | WASM Hash |\n")
                f.write("|----------|-------------|-----------|\n")
                for name, data in all_deployments.items():
                    contract_id = data.get('contract_id', 'N/A')
                    wasm_hash = data.get('wasm_hash', 'N/A')
                    f.write(f"| {name} | {contract_id} | {wasm_hash} |\n")
        except Exception as e:
            print(f"⚠️ Failed to update deployments.md: {e}")
        
        print(f"\n🎉 Deployment completed! {len(deployments)} contracts processed")
        print("📄 Results saved to deployments.json and deployments.md")
        
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
