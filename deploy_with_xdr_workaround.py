#!/usr/bin/env python3
"""
Stellar Smart Contract Deployment Script with XDR Workarounds

This script provides a robust deployment solution for Stellar smart contracts that works around
common XDR processing errors by verifying transaction success via the Stellar Horizon API.

Key Features:
- Supports both local and cloud deployment modes
- Uses Selenium for reliable contract ID extraction from Stellar Expert
- Implements comprehensive error handling and retry mechanisms
- Provides detailed logging and debugging information

Dependencies:
- stellar-sdk: For Stellar network interactions
- selenium: For web scraping Stellar Expert (with Chrome/Chromium and ChromeDriver)
- webdriver-manager: For automatic ChromeDriver management

Environment Setup:
1. Install Python dependencies: pip install -r requirements.txt
2. Install Chrome/Chromium browser
3. Ensure ChromeDriver is installed (handled automatically by webdriver-manager)
"""

import argparse
import datetime
import json
import os
import re
import requests
from stellar_sdk import Keypair
import subprocess
import sys
import time
import toml
from pathlib import Path
from typing import Optional, Dict, Any

# Cloud deployment configuration
CLOUD_IDENTITY_DIR = os.path.join(os.getcwd(), ".stellar", "identity")
CLOUD_CONFIG_DIR = os.path.join(os.getcwd(), ".stellar")
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

def extract_contract_address_from_stellar_expert(tx_hash: str, network: str = "testnet", max_retries: int = 3, retry_delay: int = 5) -> Optional[str]:
    """
    Extract contract address from Stellar Expert using Selenium to render the page.
    
    This function attempts to load the transaction page on Stellar Expert in a headless
    browser, wait for the contract link to appear, and extract the contract ID.
    
    Args:
        tx_hash: The transaction hash to look up
        network: Network to check (testnet/public)
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
        
    Returns:
        str: The contract ID if found, None otherwise
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, 
        WebDriverException,
        NoSuchElementException
    )
    
    # Set up Chrome options for headless browsing
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-dev-tools")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")  # Suppress console logs
    
    # Initialize driver outside try to ensure it can be closed in finally
    driver = None
    
    # Build the Stellar Expert URL
    base_url = f"https://stellar.expert/explorer/{network}/tx/{tx_hash}"
    
    print(f"🔍 Attempting to extract contract address from Stellar Expert...")
    print(f"   URL: {base_url}")
    print(f"   Max retries: {max_retries}, Retry delay: {retry_delay}s")
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n🔄 Attempt {attempt}/{max_retries}")
            
            try:
                # Initialize Chrome driver with options
                driver = webdriver.Chrome(options=chrome_options)
                driver.set_page_load_timeout(60)  # 60 seconds to load the page
                
                # Load the page
                print(f"   Loading page...")
                driver.get(base_url)
                
                # Wait for the contract link to appear with a timeout
                wait = WebDriverWait(driver, 30)  # 30 seconds to find elements
                
                # Wait for the contract link to appear
                print("   Searching for contract link...")
                contract_selector = "a[href*='/contract/']"
                contract_element = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, contract_selector))
                )
                
                # Extract the contract ID from the href
                contract_href = contract_element.get_attribute("href")
                if contract_href:
                    contract_id = contract_href.split("/")[-1]
                    if contract_id.startswith('C') and len(contract_id) == 56:
                        print(f"✅ Successfully extracted contract ID: {contract_id}")
                        return contract_id
                    else:
                        print(f"⚠️ Found invalid contract ID format: {contract_id}")
                
                # If we get here, we didn't find a valid contract ID
                print("⚠️ Could not find valid contract ID in page")
                
                # Take a screenshot for debugging
                screenshot_path = f"stellar_expert_error_{int(time.time())}.png"
                driver.save_screenshot(screenshot_path)
                print(f"   Saved screenshot to {screenshot_path}")
                
            except TimeoutException:
                print("❌ Timed out waiting for contract link to appear")
                if attempt < max_retries:
                    print(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                continue
                
            except WebDriverException as e:
                print(f"❌ WebDriver error: {str(e)}")
                if attempt < max_retries:
                    print(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                continue
                
            except Exception as e:
                print(f"❌ Unexpected error: {str(e)}")
                if attempt < max_retries:
                    print(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                continue
                
            finally:
                # Close the browser after each attempt
                if driver:
                    driver.quit()
                    driver = None
        
        except Exception as e:
            print(f"❌ Fatal error in attempt {attempt}: {str(e)}")
            if attempt < max_retries:
                print(f"⏳ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            continue
    
    # If we get here, all attempts failed
    print(f"❌ Failed to extract contract address after {max_retries} attempts")
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
                        contract_address = None
                        
                        # First try to get from Stellar Expert API
                        contract_address = extract_contract_address_from_stellar_expert(tx_hash)
                        
                        # If Stellar Expert fails, try to extract from CLI output
                        if not contract_address:
                            print("⚠️ Could not get contract address from Stellar Expert, trying CLI output...")
                            # Look for contract address in the output
                            matches = re.findall(r'Contract: (C[0-9A-Z]{55})', output)
                            if matches:
                                contract_address = matches[0]
                                print(f"ℹ️ Extracted contract address from CLI output: {contract_address}")
                        
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

def is_valid_contract_address(address):
    """Check if a string is a valid Stellar contract address."""
    import re
    return bool(re.match(r'^C[0-9A-Z]{55}$', str(address)))

def is_valid_secret_key(secret_key):
    """Check if a string is a valid Stellar secret key."""
    import re
    return bool(re.match(r'^S[0-9A-Z]{55}$', str(secret_key)))

def load_hvym_collective_args(opus_token_address, admin_account):
    """Load HVYM Collective constructor arguments.
    
    Args:
        opus_token_address: Address of the deployed Opus token contract
        admin_account: The actual admin account public key to use, will override any value from file
        
    Returns:
        str: Space-separated CLI arguments for the contract constructor
    """
    args_file = "hvym-collective_args.json"
    
    # Validate token address
    if not is_valid_contract_address(opus_token_address):
        print(f"❌ Invalid Opus token address: {opus_token_address}")
        raise ValueError(f"Invalid Opus token address: {opus_token_address}")
    
    # Validate admin account
    if not is_valid_contract_address(admin_account) and not re.match(r'^G[0-9A-Z]{55}$', str(admin_account)):
        print(f"❌ Invalid admin account: {admin_account}")
        raise ValueError(f"Invalid admin account: {admin_account}")
    
    # Default arguments
    default_args = {
        "join_fee": 320000000,  # 32 XLM in stroops
        "mint_fee": 5000000,   # 0.5 XLM in stroops  
        "reward": 80000000,    # 8 XLM in stroops
        "token": opus_token_address,
        "admin": admin_account  # Always use the provided admin account
    }
    
    # Try to load from JSON file for other parameters
    if os.path.exists(args_file):
        try:
            with open(args_file, 'r') as f:
                file_args = json.load(f)
            
            # Convert XLM values to stroops if needed
            for key in ["join_fee", "mint_fee", "reward"]:
                if key in file_args:
                    try:
                        file_args[key] = int(float(file_args[key]) * 10_000_000)
                    except (ValueError, TypeError):
                        print(f"⚠️ Invalid value for {key} in {args_file}, using default")
            
            # Merge with defaults, but don't override admin from CLI args
            if 'admin' in file_args:
                print(f"ℹ️ Note: Ignoring admin from {args_file}, using CLI provided admin")
                del file_args['admin']
                
            default_args.update(file_args)
            print(f"📄 Loaded constructor args from {args_file}")
            
        except Exception as e:
            print(f"⚠️ Error loading {args_file}: {e}, using defaults")
    else:
        print(f"📄 Using default constructor args (no {args_file} found)")
    
    # Always use the provided admin account and token address
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
        tx_hash = deploy_result.get('tx_hash')
        
        if tx_hash:
            print(f"ℹ️ Extracting contract address for {contract_name} from transaction {tx_hash}")
            
            # Try to get from Stellar Expert using Selenium (primary method)
            print("🔍 Looking up contract address on Stellar Expert...")
            contract_address = extract_contract_address_from_stellar_expert(tx_hash, network=network)
            
            if contract_address:
                print(f"✅ Successfully extracted contract address: {contract_address}")
            else:
                # Fallback to CLI output if Selenium method fails
                print("⚠️ Could not get contract address from Stellar Expert, trying CLI output...")
                output = deploy_result.get('output', '')
                matches = re.findall(r'Contract: (C[0-9A-Z]{55})', output)
                if matches:
                    contract_address = matches[0]
                    print(f"ℹ️ Extracted contract address from CLI output: {contract_address}")
                else:
                    print("⚠️ Could not extract contract address from CLI output")
                    
                    # Try to get from Horizon API as last resort
                    try:
                        print("ℹ️ Trying to get contract address from Horizon API...")
                        from stellar_sdk import Server
                        server = Server(horizon_url=f"https://horizon-{network}.stellar.org" if network != 'public' else "https://horizon.stellar.org")
                        tx = server.transactions().transaction(tx_hash).call()
                        
                        # Look for create_contract operations in the transaction
                        for op in tx.get('operations', []):
                            if op.get('type') == 'create_contract' and 'contract_id' in op:
                                contract_address = op['contract_id']
                                print(f"✅ Extracted contract address from Horizon API: {contract_address}")
                                break
                    except Exception as e:
                        print(f"⚠️ Failed to get contract address from Horizon API: {str(e)}")
        
        # Prepare result
        result = {
            'name': contract_name,
            'wasm_hash': wasm_hash,
            'tx_hash': tx_hash,
            'address': contract_address,
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

def cleanup_failed_identity(identity_name: str) -> None:
    """Clean up a failed identity setup."""
    try:
        # Remove from Stellar CLI if it exists (with a shorter timeout)
        try:
            result = subprocess.run(
                ["stellar", "keys", "ls"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and f"{identity_name}:" in result.stdout:
                print(f"🧹 Removing identity from Stellar CLI: {identity_name}")
                subprocess.run(
                    ["stellar", "keys", "remove", identity_name, "--force", "--yes"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
        except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
            print(f"⚠️  Warning during CLI cleanup: {str(e)}")
        
        # Remove identity file
        identity_file = os.path.join(CLOUD_IDENTITY_DIR, f"{identity_name}.toml")
        if os.path.exists(identity_file):
            try:
                os.remove(identity_file)
                print(f"🧹 Removed identity file: {identity_file}")
            except Exception as e:
                print(f"⚠️  Failed to remove identity file: {str(e)}")
    except Exception as e:
        print(f"⚠️  Warning during cleanup of {identity_name}: {str(e)}")

def identity_exists_in_cli(identity_name: str, timeout: int = 5) -> bool:
    """Check if an identity exists in the Stellar CLI keyring."""
    try:
        # Try with a timeout to prevent hanging
        result = subprocess.run(
            ["stellar", "keys", "ls", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                keys = json.loads(result.stdout)
                if isinstance(keys, list):
                    return any(key.get("name") == identity_name for key in keys)
            except json.JSONDecodeError:
                # Fall back to text parsing if JSON parsing fails
                pass
        
        # Fall back to text output if JSON output is not available
        result = subprocess.run(
            ["stellar", "keys", "ls"],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            print(f"❌ Failed to list Stellar CLI keys: {result.stderr}")
            return False
            
        # Look for the identity name in the output
        return f"{identity_name}:" in result.stdout
        
    except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
        print(f"❌ Error checking for existing identity: {str(e)}")
        return False

def register_identity_with_cli(identity_name: str, _: str = None) -> bool:
    """Set the default identity using the local identity file.
    
    Args:
        identity_name: Name of the identity to use
        _: Unused parameter (kept for backward compatibility)
        
    Returns:
        bool: True if identity was set as default successfully, False otherwise
    """
    print(f"🔄 Setting up identity: {identity_name}")
    
    try:
        # Check if identity file exists
        identity_file = os.path.join(CLOUD_IDENTITY_DIR, f"{identity_name}.toml")
        if not os.path.exists(identity_file):
            print(f"❌ Identity file not found: {identity_file}")
            return False
            
        print(f"✅ Using local identity file: {identity_file}")
        return True
        
    except Exception as e:
        print(f"❌ Error setting up identity: {str(e)}")
        return False
        return False

def setup_cloud_identity(secret_key: str, identity_name: str = DEFAULT_IDENTITY_NAME) -> bool:
    """Set up a local Stellar identity file for deployment.
    
    Args:
        secret_key: The secret key or mnemonic phrase for the identity
        identity_name: Name to use for the identity file
        
    Returns:
        bool: True if setup was successful, False otherwise
    """
    print("\n=== Starting Local Identity Setup ===")
    print(f"Identity Name: {identity_name}")
    print(f"Key Type: {'Mnemonic' if ' ' in secret_key else 'Secret Key'}")
    
    identity_file = None
    try:
        # 1. Create identity directory
        print("\n[1/2] Setting up identity directory...")
        os.makedirs(CLOUD_IDENTITY_DIR, exist_ok=True)
        print(f"✅ Directory ready: {CLOUD_IDENTITY_DIR}")
        
        # 2. Create and save identity file
        print("\n[2/2] Creating identity file...")
        identity_file = os.path.join(CLOUD_IDENTITY_DIR, f"{identity_name}.toml")
        
        # Validate and process the key
        try:
            if ' ' in secret_key:  # Mnemonic phrase
                keypair = Keypair.from_mnemonic_phrase(secret_key)
                identity_data = {
                    'seed_phrase': secret_key,
                    'public_key': keypair.public_key,
                    'type': 'mnemonic'
                }
            else:  # Secret key
                keypair = Keypair.from_secret(secret_key)
                identity_data = {
                    'secret_key': secret_key,
                    'public_key': keypair.public_key,
                    'type': 'secret_key'
                }
                
            with open(identity_file, 'w') as f:
                toml.dump(identity_data, f)
                
            print(f"✅ Identity file created: {identity_file}")
            print(f"   Public Key: {keypair.public_key}")
            
            # Verify the file was written correctly
            if os.path.exists(identity_file):
                with open(identity_file, 'r') as f:
                    file_content = f.read()
                    print(f"\nIdentity file contents:\n{file_content}")
            
            print("\n=== Local Identity Setup Complete ===")
            print(f"✅ Successfully set up local Stellar identity: {identity_name}")
            return True
            
        except Exception as e:
            print(f"❌ Error processing key: {str(e)}")
            raise
            
    except Exception as e:
        print(f"❌ Failed to set up local identity: {str(e)}")
        # Clean up any partial setup
        if identity_file and os.path.exists(identity_file):
            try:
                os.remove(identity_file)
                print(f"🧹 Cleaned up identity file: {identity_file}")
            except Exception as cleanup_error:
                print(f"⚠️  Failed to clean up identity file: {str(cleanup_error)}")
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
        # In cloud mode, use the standard path with .wasm extension
        wasm_file = f"{contract_name}.wasm"
        return os.path.join(wasm_dir, wasm_file)
    else:
        # Map contract names to their specific paths
        contract_paths = {
            "hvym-collective": "hvym-collective/target/wasm32-unknown-unknown/release/hvym_collective.wasm",
            "opus-token": "opus_token/target/wasm32-unknown-unknown/release/opus_token.wasm",
            "pintheon-node-token": "pintheon-node-deployer/pintheon-node-token/target/wasm32-unknown-unknown/release/pintheon_node_token.wasm",
            "pintheon-ipfs-token": "pintheon-ipfs-deployer/pintheon-ipfs-token/target/wasm32-unknown-unknown/release/pintheon_ipfs_token.wasm"
        }
        
        # Try the specific path first
        if contract_name in contract_paths:
            specific_path = os.path.join(wasm_dir, contract_paths[contract_name])
            if os.path.exists(specific_path):
                return specific_path
        
        # Fallback to generic paths if specific path not found
        possible_paths = [
            # Standard path with wasm32-unknown-unknown target
            os.path.join(wasm_dir, f"{contract_name}/target/wasm32-unknown-unknown/release/{contract_name.replace('-', '_')}.wasm"),
            # Path with wasm32-v1-none target (used by some toolchains)
            os.path.join(wasm_dir, f"{contract_name}/target/wasm32-v1-none/release/{contract_name.replace('-', '_')}.wasm"),
            # Direct path if wasm_dir already points to the file
            os.path.join(wasm_dir, f"{contract_name.replace('-', '_')}.wasm"),
        ]
        
        # Check each possible path
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # If no path was found, return the first one as it's the most likely
        return possible_paths[0]

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
            print(f"🔑 Setting up identity from provided secret key")
            if not setup_cloud_identity(args.secret_key, args.identity_name):
                sys.exit(1)
            source_account = args.identity_name
        else:
            # Check if deployer_account is a secret key
            if is_valid_secret_key(args.deployer_account):
                print(f"🔑 Setting up identity from deployer account secret key")
                # It's a secret key, set it up as an identity
                if not setup_cloud_identity(args.deployer_account, 'deployer-key'):
                    sys.exit(1)
                source_account = 'deployer-key'
            else:
                # It's an account alias, verify it exists in the CLI
                print(f"🔍 Using existing identity: {args.deployer_account}")
                if not identity_exists_in_cli(args.deployer_account):
                    print(f"❌ Error: Identity '{args.deployer_account}' not found in Stellar CLI")
                    print("   Please add this identity using 'stellar keys add' or provide a secret key")
                    sys.exit(1)
                source_account = args.deployer_account
        
        # Verify the identity is properly set up
        try:
            # Test the identity by getting its public key
            result = subprocess.run(
                ["stellar", "keys", "show", source_account],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"❌ Error: Failed to verify identity '{source_account}': {result.stderr}")
                sys.exit(1)
                
            # Extract public key from the output (format: "<name>: <public_key>")
            output_lines = result.stdout.strip().split('\n')
            public_key = None
            for line in output_lines:
                if line.startswith(f"{source_account}:"):
                    public_key = line.split(':', 1)[1].strip()
                    break
                    
            if public_key:
                print(f"✅ Verified identity: {public_key} ({source_account})")
            else:
                print(f"⚠️  Verified identity but could not extract public key for: {source_account}")
            
        except (subprocess.SubprocessError, json.JSONDecodeError) as e:
            print(f"❌ Error verifying identity: {str(e)}")
            sys.exit(1)
            
        # Configure network
        print(f"🌐 Configuring network: {args.network}")
        if not configure_network(args.network, args.rpc_url):
            sys.exit(1)
            
        print("✅ Cloud deployment setup complete")
        print(f"   Using account: {source_account}")
        print(f"   Network: {args.network}")
        
        # If specific contract deployment was requested
        if args.contract:
            wasm_path = args.wasm_path or os.path.join(wasm_dir, f"{args.contract}.wasm")
            if not os.path.exists(wasm_path):
                # Try to find the WASM file using the get_wasm_path function
                wasm_path = get_wasm_path(args.contract, wasm_dir, cloud_mode)
                if not wasm_path or not os.path.exists(wasm_path):
                    print(f"❌ Error: WASM file not found for contract '{args.contract}'")
                    print(f"   Searched in: {os.path.abspath(wasm_dir)}")
                    sys.exit(1)
            
            print(f"🚀 Deploying contract: {args.contract}")
            print(f"   WASM path: {os.path.abspath(wasm_path)}")
                
            result = deploy_contract_with_workaround(
                contract_name=args.contract,
                wasm_path=wasm_path,
                network=args.network,
                source_account=source_account
            )
            
            if not result:
                print(f"❌ Failed to deploy contract: {args.contract}")
                sys.exit(1)
                
            print(f"✅ Successfully deployed contract: {args.contract}")
            print(f"   Contract ID: {result.get('address')}")
            print(f"   Transaction: {result.get('tx_hash')}")
            
            # Handle post-deployment configuration if specified
            if args.post_deploy_config and os.path.exists(args.post_deploy_config):
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
            if opus_result.get('address') == 'UNKNOWN':
                print("❌ Failed to extract Opus Token contract address. Cannot proceed with HVYM Collective deployment.")
                opus_result = None
            else:
                deployments.append(opus_result)
    else:
        print(f"⚠️ Opus Token WASM not found: {opus_wasm}")
    
    # Step 3: Deploy HVYM Collective (final contract with all dependencies)
    collective_wasm = get_wasm_path("hvym-collective", wasm_dir, cloud_mode)
    if not os.path.exists(collective_wasm):
        print(f"❌ HVYM Collective WASM not found: {collective_wasm}")
    elif not opus_result:
        print("❌ Cannot deploy HVYM Collective: Opus Token deployment failed or address not found")
    else:
        # Verify we have a valid opus token address
        opus_address = opus_result.get('address')
        if not opus_address or opus_address == 'UNKNOWN':
            print("❌ Cannot deploy HVYM Collective: Invalid Opus Token address")
        else:
            print(f"ℹ️ Using Opus Token address: {opus_address}")
            
            # Wait a moment to ensure the WASM is fully propagated
            print("⏳ Waiting for WASM to be fully propagated...")
            time.sleep(5)
            
            try:
                # Load and validate constructor arguments
                constructor_args = load_hvym_collective_args(opus_address, source_account)
                print(f"ℹ️ Constructor arguments: {constructor_args}")
                
                # Deploy HVYM Collective
                collective_result = deploy_contract_with_workaround(
                    "hvym-collective",
                    collective_wasm,
                    constructor_args,
                    source_account=source_account
                )
                
                if collective_result:
                    deployments.append(collective_result)
                    
                    # Verify the deployment
                    if collective_result.get('address') == 'UNKNOWN':
                        print("⚠️ HVYM Collective deployed but could not verify contract address")
                    else:
                        print(f"✅ Successfully deployed HVYM Collective at: {collective_result['address']}")
                
            except ValueError as e:
                print(f"❌ Error deploying HVYM Collective: {e}")
            except Exception as e:
                print(f"❌ Unexpected error deploying HVYM Collective: {e}")
                import traceback
                traceback.print_exc()
    
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
