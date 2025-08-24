#!/usr/bin/env python3
"""
Deployment script that works around XDR processing errors by checking transaction success via API.
Supports both local development and cloud deployment modes.
"""

import subprocess
import json
import time
import re
import shlex
import requests
import sys
import os
import argparse
from pathlib import Path

# Stellar SDK imports - only import what we need for account management
from stellar_sdk import Keypair, Network
from stellar_sdk.exceptions import NotFoundError

def get_stellar_rpc(network, rpc_url=None):
    """Get the RPC URL for the specified network."""
    if not rpc_url:
        rpc_url = {
            'testnet': 'https://soroban-testnet.stellar.org',  # Testnet RPC
            'futurenet': 'https://rpc-futurenet.stellar.org',  # Futurenet RPC
            'mainnet': 'https://horizon.stellar.org',         # Mainnet Horizon
        }.get(network, 'https://soroban-testnet.stellar.org')
    
    return rpc_url

def get_network_passphrase(network):
    """Get the network passphrase for the specified network."""
    return {
        'testnet': Network.TESTNET_NETWORK_PASSPHRASE,
        'futurenet': Network.FUTURENET_NETWORK_PASSPHRASE,
        'mainnet': Network.PUBLIC_NETWORK_PASSPHRASE,
    }.get(network, Network.TESTNET_NETWORK_PASSPHRASE)

def setup_account(secret_key, network, rpc_url=None):
    """Set up and fund an account using the provided secret key.
    
    Args:
        secret_key: The secret key of the account to set up
        network: The Stellar network to use (testnet, futurenet, mainnet)
        rpc_url: Optional custom RPC URL
        
    Returns:
        Keypair: The loaded keypair if successful
        
    Raises:
        Exception: If account setup fails
    """
    try:
        # Load the keypair from the secret key
        keypair = Keypair.from_secret(secret_key)
        print(f"🔑 Loaded account: {keypair.public_key}")
        
        # For testnet, we can try to fund the account if it doesn't exist
        if network == 'testnet':
            try:
                # Try to get the account info to check if it exists
                response = requests.get(
                    f"https://horizon-testnet.stellar.org/accounts/{keypair.public_key}",
                    timeout=10
                )
                
                if response.status_code == 200:
                    print(f"✅ Account exists and is funded: {keypair.public_key}")
                    return keypair
                elif response.status_code == 404:
                    # Account doesn't exist, try to fund it using friendbot
                    print(f"🔄 Funding new testnet account: {keypair.public_key}")
                    response = requests.get(
                        f"https://friendbot.stellar.org?addr={keypair.public_key}",
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        print(f"✅ Successfully funded account: {keypair.public_key}")
                        return keypair
                    else:
                        raise Exception(f"Friendbot funding failed: {response.text}")
                else:
                    raise Exception(f"Unexpected response from Horizon: {response.status_code}")
                    
            except requests.RequestException as e:
                print(f"⚠️ Network error checking/funding account: {e}")
                # Continue to try with the account anyway
        
        # For non-testnet or if funding failed, just return the keypair
        # The actual deployment will fail if the account doesn't exist or has no funds
        return keypair
        
    except Exception as e:
        print(f"❌ Error setting up account: {e}")
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

def check_transaction_success(tx_hash, network="testnet", rpc_url=None, max_retries=30):
    """Check if transaction succeeded using Stellar Horizon API.
    
    Args:
        tx_hash: The transaction hash to check
        network: The Stellar network (testnet, futurenet, mainnet)
        rpc_url: Not used, kept for backward compatibility
        max_retries: Maximum number of retry attempts
        
    Returns:
        tuple: (success, result_xdr) where success is a boolean and 
               result_xdr is the base64-encoded result XDR if successful
    """
    # Determine the Horizon URL based on the network
    horizon_url = {
        'testnet': 'https://horizon-testnet.stellar.org',
        'futurenet': 'https://horizon-futurenet.stellar.org',
        'mainnet': 'https://horizon.stellar.org'
    }.get(network, 'https://horizon-testnet.stellar.org')
    
    for attempt in range(max_retries):
        try:
            # Get transaction details from Horizon
            response = requests.get(
                f"{horizon_url}/transactions/{tx_hash}",
                timeout=10
            )
            
            if response.status_code == 200:
                tx_data = response.json()
                if tx_data.get('successful', False):
                    print(f"✅ Transaction {tx_hash} confirmed successfully")
                    return True, tx_data.get('result_xdr')
                else:
                    print(f"❌ Transaction {tx_hash} failed")
                    return False, None
                    
            elif response.status_code == 404:
                print(f"⌛ Transaction {tx_hash} not found yet, retrying... (attempt {attempt + 1}/{max_retries})")
            else:
                print(f"⚠️ Unexpected response from Horizon: {response.status_code}, retrying...")
                
        except requests.RequestException as e:
            print(f"⚠️ Error checking transaction status: {e}, retrying... (attempt {attempt + 1}/{max_retries})")
        
        time.sleep(2)  # Wait before retrying
    
    print(f"❌ Transaction {tx_hash} not confirmed after {max_retries} attempts")
    return False, None

def extract_contract_address_from_stellar_expert(tx_hash, network="testnet"):
    """Extract contract address from Stellar Expert API transaction data.
    
    This function extracts the contract address from the transaction data
    returned by the Stellar Expert API. It looks for the contract address
    in the transaction operations.
    """
    try:
        # Get transaction data from Stellar Expert API
        url = f"https://api.stellar.expert/explorer/{network}/tx/{tx_hash}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            print(f"⚠️ Failed to fetch transaction from Stellar Expert: {response.status_code}")
            return None
            
        tx_data = response.json()
        
        # Look for the contract address in the operations
        operations = tx_data.get('operations', [])
        for op in operations:
            if op.get('type') == 'invoke' and 'contract' in op:
                # Extract the contract ID from the operation
                contract_id = op['contract'].split(':')[-1]
                if contract_id:
                    print(f"✅ Found contract address: {contract_id}")
                    return contract_id
        
        # If not found in operations, check the XDR result
        result_xdr = tx_data.get('result_xdr')
        if result_xdr:
            try:
                import base64
                # Simple extraction of contract ID from result XDR
                # This is a simplified approach that worked before
                decoded = base64.b64decode(result_xdr)
                # Look for a potential contract ID in the decoded data
                # This is a heuristic and may need adjustment
                import re
                matches = re.findall(b'[A-Z0-9]{56}', decoded)
                if matches:
                    contract_id = matches[-1].decode()
                    print(f"✅ Extracted contract address from XDR: {contract_id}")
                    return contract_id
            except Exception as e:
                print(f"⚠️ Error parsing result XDR: {e}")
        
        print("⚠️ Could not extract contract address from transaction data")
        return None
        
    except Exception as e:
        print(f"⚠️ Error extracting contract address: {e}")
        return None

def run_stellar_command_with_xdr_workaround(cmd, cwd=None, network="testnet", rpc_url=None):
    """Run stellar CLI command and handle XDR errors by checking transaction success."""
    print(f"⚡ Running: {cmd}")
    
    try:
        # Run the command
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True
        )
        
        # Check if command was successful
        if result.returncode == 0:
            print("✅ Command executed successfully")
            return True, result.stdout
            
        # If command failed, try to extract transaction hash
        print(f"❌ Command failed with code {result.returncode}")
        print(f"Stderr: {result.stderr}")
        
        # Try to extract transaction hash from error output
        tx_hash = extract_transaction_hash(result.stderr) or extract_transaction_hash(result.stdout)
        if not tx_hash:
            print("⚠️ Could not extract transaction hash from output")
            return False, result.stderr
            
        print(f"🔍 Found transaction hash: {tx_hash}")
        
        # Check if transaction was successful
        success, result_xdr = check_transaction_success(tx_hash, network, rpc_url)
        if success:
            print("✅ Transaction was successful")
            # Try to extract contract address from transaction
            contract_address = extract_contract_address_from_stellar_expert(tx_hash, network)
            if contract_address:
                return True, contract_address
            return True, result_xdr or "Transaction successful but could not extract contract address"
        else:
            print("❌ Transaction failed")
            return False, f"Transaction {tx_hash} failed"
        
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return {'success': False, 'error': str(e)}

def upload_wasm_with_workaround(contract_name, wasm_path, network="testnet", source_account="test-deployer", rpc_url=None):
    """Upload WASM file with XDR workaround (for dependency contracts).
    
    Args:
        contract_name: Name of the contract (for logging)
        wasm_path: Path to the WASM file
        network: Stellar network to use (testnet, futurenet, mainnet)
        source_account: Source account to use for deployment
        rpc_url: Optional custom RPC URL
        
    Returns:
        str: Contract ID if successful, None otherwise
    """
    print(f"📤 Uploading {contract_name} WASM...")
    
    # Get network passphrase
    network_passphrases = {
        'testnet': 'Test SDF Network ; September 2015',
        'futurenet': 'Test SDF Future Network ; October 2022',
        'mainnet': 'Public Global Stellar Network ; September 2015'
    }
    network_passphrase = network_passphrases.get(network, network_passphrases['testnet'])
    
    # Build the upload command
    cmd = [
        'stellar', 'contract', 'deploy',
        '--wasm', wasm_path,
        '--source', source_account,
        '--network', network,
        '--network-passphrase', network_passphrase,
        '--fee', '1000000'  # Add a higher fee to ensure transaction goes through
    ]
    
    if rpc_url:
        cmd.extend(['--rpc-url', rpc_url])
    
    # Convert command list to string for logging (without sensitive data)
    safe_cmd = cmd.copy()
    if '--source' in safe_cmd and len(safe_cmd) > safe_cmd.index('--source') + 1:
        safe_cmd[safe_cmd.index('--source') + 1] = '***'
    if '--network-passphrase' in safe_cmd and len(safe_cmd) > safe_cmd.index('--network-passphrase') + 1:
        safe_cmd[safe_cmd.index('--network-passphrase') + 1] = '***'
    cmd_str = ' '.join(safe_cmd)
    print(f"Running: {cmd_str}")
    
    # Run the command with XDR workaround
    success, result = run_stellar_command_with_xdr_workaround(
        ' '.join(cmd), 
        network=network, 
        rpc_url=rpc_url
    )
    
    if success and isinstance(result, str) and len(result) == 56 and result.startswith('C'):
        print(f"✅ {contract_name} WASM uploaded successfully: {result}")
        return result
    
    print(f"❌ Failed to upload {contract_name} WASM")
    return None

def extract_wasm_hash_from_output(wasm_data):
    """Extract WASM hash from WASM file data or CLI output.
    
    Args:
        wasm_data: Either bytes (WASM file data) or str (CLI output)
        
    Returns:
        str: The WASM hash if found, None otherwise
    """
    import hashlib
    import re
    
    # If input is bytes, calculate SHA256 hash of WASM
    if isinstance(wasm_data, bytes):
        try:
            # Calculate SHA256 hash of the WASM file
            sha256_hash = hashlib.sha256(wasm_data).hexdigest()
            return sha256_hash
        except Exception as e:
            print(f"⚠️ Error calculating WASM hash: {e}")
            return None
    
    # If input is string, try to extract hash from CLI output
    if isinstance(wasm_data, str):
        # Look for 64-character hex strings in the output
        hash_matches = re.findall(r'\b[a-f0-9]{64}\b', wasm_data, re.IGNORECASE)
        if hash_matches:
            return hash_matches[-1].lower()  # Return the last one found in lowercase
    
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

def deploy_contract_with_workaround(contract_name, wasm_path, constructor_args="", network="testnet", source_account="test-deployer", rpc_url=None):
    """Deploy contract using the XDR workaround.
    
    Args:
        contract_name: Name of the contract (for logging)
        wasm_path: Path to the WASM file
        constructor_args: Constructor arguments as a string
        network: Network to deploy to (testnet, futurenet, mainnet)
        source_account: Source account for deployment
        rpc_url: Optional custom RPC URL
        
    Returns:
        str: Contract ID if successful, None otherwise
    """
    print(f"\n🚀 Deploying {contract_name} with XDR workaround...")
    
    # Step 1: Upload WASM
    wasm_hash = upload_wasm_with_workaround(
        contract_name,
        wasm_path,
        network=network,
        source_account=source_account,
        rpc_url=rpc_url
    )
    
    if not wasm_hash:
        print(f"❌ Failed to upload WASM for {contract_name}")
        return None
    
    # Get network passphrase
    network_passphrases = {
        'testnet': 'Test SDF Network ; September 2015',
        'futurenet': 'Test SDF Future Network ; October 2022',
        'mainnet': 'Public Global Stellar Network ; September 2015'
    }
    network_passphrase = network_passphrases.get(network, network_passphrases['testnet'])
    
    # Step 2: Deploy contract
    print("🚀 Deploying contract...")
    cmd = [
        'stellar', 'contract', 'deploy',
        '--wasm-hash', wasm_hash,
        '--source', source_account,
        '--network', network,
        '--network-passphrase', network_passphrase,
        '--fee', '1000000'  # Higher fee for better reliability
    ]
    
    if rpc_url:
        cmd.extend(['--rpc-url', rpc_url])
        
    # Create safe command for logging (without sensitive data)
    safe_cmd = cmd.copy()
    if '--source' in safe_cmd and len(safe_cmd) > safe_cmd.index('--source') + 1:
        safe_cmd[safe_cmd.index('--source') + 1] = '***'
    if '--network-passphrase' in safe_cmd and len(safe_cmd) > safe_cmd.index('--network-passphrase') + 1:
        safe_cmd[safe_cmd.index('--network-passphrase') + 1] = '***'
    print(f"Running: {' '.join(safe_cmd)}")
    
    # Add constructor arguments if provided
    if constructor_args:
        # Split the constructor args string into a list of arguments
        import shlex
        args_list = shlex.split(constructor_args)
        cmd.extend(['--'] + args_list)
    
    # Convert command list to string for logging and execution
    cmd_str = ' '.join(cmd)
    print(f"Running: {cmd_str}")
    
    # Run the deployment command with XDR workaround
    success, result = run_stellar_command_with_xdr_workaround(
        cmd_str,
        network=network,
        rpc_url=rpc_url
    )
    
    if success and isinstance(result, str) and len(result) == 56 and result.startswith('C'):
        print(f"✅ {contract_name} deployed successfully: {result}")
        return result
    
    print(f"❌ Failed to deploy {contract_name}")
    if not success and isinstance(result, str):
        print(f"Error: {result}")
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
        deployments: Deployments dictionary (not used in this simplified version)
        
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
        for dep in deployments:
            if dep.get('name') == 'opus_token' and 'contract_id' in dep:
                opus_contract_id = dep['contract_id']
                break
        
        if not opus_contract_id:
            print("⚠️  opus_token contract_id not found in deployments, skipping post-deployment")
            return True
            
        # Build the post-deployment command
        cmd = [
            "python3", "hvym_post_deploy.py",
            "--network", network,
            "--collective-contract", contract_id,
            "--opus-token", opus_contract_id,
            "--deployer-secret", args.deployer_account,
            "--fund-amount", str(config.get("fund_amount", "1000000000")),
            "--initial-opus-alloc", str(config.get("initial_opus_alloc", "100000000000000000"))
        ]
        
        # Add RPC URL if provided
        if args.rpc_url:
            cmd.extend(["--rpc-url", args.rpc_url])
        
        print(f"  ↳ Running: {' '.join(cmd)}")
        
        # Run the command with timeout and capture output
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            print(result.stdout)
            if result.stderr:
                print(f"⚠️  Post-deployment stderr: {result.stderr}")
                
            print("✅ Post-deployment steps completed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            print("❌ Post-deployment timed out after 5 minutes")
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
            'testnet': 'https://soroban-testnet.stellar.org',  # Testnet RPC
            'futurenet': 'https://rpc-futurenet.stellar.org',  # Futurenet RPC
            'mainnet': 'https://horizon.stellar.org'           # Mainnet Horizon
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
            wasm_hash = upload_wasm_with_workaround(
                contract_name=dep["name"],
                wasm_path=wasm_path,
                network=args.network,
                source_account=source_account,
                rpc_url=args.rpc_url
            )
            if wasm_hash:
                dependency_hashes[dep["name"]] = wasm_hash
                deployments.append({
                    "name": dep["name"],
                    "wasm_hash": wasm_hash,
                    "upload_only": True
                })
        else:
            print(f"⚠️ Dependency WASM not found: {wasm_path}")
    
    # Step 2: Deploy Opus Token
    opus_contract_id = None
    opus_wasm = "opus_token/target/wasm32-unknown-unknown/release/opus_token.wasm"
    if args.mode == 'cloud':
        opus_wasm = str(Path(args.wasm_dir) / "opus_token.wasm")
    
    if os.path.exists(opus_wasm):
        opus_contract_id = deploy_contract_with_workaround(
            contract_name="opus_token",
            wasm_path=opus_wasm,
            constructor_args=f"--admin {source_account}",
            network=args.network,
            source_account=source_account,
            rpc_url=args.rpc_url
        )
        if opus_contract_id:
            deployments.append({
                "name": "opus_token",
                "contract_id": opus_contract_id,
                "wasm_hash": extract_wasm_hash_from_output(open(opus_wasm, 'rb').read())
            })
    
    # Step 3: Deploy HVYM Collective
    collective_wasm = "hvym-collective/target/wasm32-unknown-unknown/release/hvym_collective.wasm"
    if args.mode == 'cloud':
        collective_wasm = str(Path(args.wasm_dir) / "hvym_collective.wasm")
    
    if os.path.exists(collective_wasm) and opus_contract_id:
        # In cloud mode, check for args file in the wasm directory first
        args_file = None
        if args.mode == 'cloud':
            cloud_args_file = Path(args.wasm_dir) / "hvym-collective_args.json"
            if cloud_args_file.exists():
                args_file = str(cloud_args_file)
                print(f"ℹ️  Using hvym-collective_args.json from wasm directory")
        
        # Load constructor arguments with the latest opus token address
        constructor_args = load_hvym_collective_args(
            opus_token_address=opus_contract_id,
            admin_account=source_account,
            args_file=args_file
        )
        
        collective_contract_id = deploy_contract_with_workaround(
            contract_name="hvym-collective",
            wasm_path=collective_wasm,
            constructor_args=constructor_args,
            network=args.network,
            source_account=source_account,
            rpc_url=args.rpc_url
        )
        
        if collective_contract_id:
            deployments.append({
                "name": "hvym-collective",
                "contract_id": collective_contract_id,
                "wasm_hash": extract_wasm_hash_from_output(open(collective_wasm, 'rb').read())
            })
            
            # Run post-deployment steps if successful
            if not run_post_deployment(args, collective_contract_id, args.network, {}):
                print("⚠️ Post-deployment steps completed with warnings")
    else:
        if not os.path.exists(collective_wasm):
            print(f"⚠️ HVYM Collective WASM not found: {collective_wasm}")
        if not opus_contract_id:
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
                    'wasm_hash': deployment.get('wasm_hash', ''),
                    'contract_id': deployment.get('contract_id', '')
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
                contract_id = deployment.get('contract_id', 'Deployment failed')
                print(f"  • {deployment['name']}: {contract_id}")
    else:
        print("\n❌ No contracts were successfully deployed")
        sys.exit(1)

if __name__ == "__main__":
    main()
