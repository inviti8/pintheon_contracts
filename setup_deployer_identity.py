#!/usr/bin/env python3
"""
Setup Stellar Deployer Identity

This script creates a Stellar identity file for deployment purposes.
It takes a secret key from an environment variable and creates the necessary
identity file that can be used by the Stellar CLI in the current working directory.
"""

import os
import sys
import toml
import shutil
import logging
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('stellar_identity_setup.log')
    ]
)
logger = logging.getLogger(__name__)

# Constants
STELLAR_DIR = os.path.join(os.getcwd(), ".stellar")
IDENTITY_DIR = os.path.join(STELLAR_DIR, "identity")
NETWORK_DIR = os.path.join(STELLAR_DIR, "network")

# Map network names to identity file names
NETWORK_IDENTITY_NAMES = {
    'testnet': 'TESTNET_DEPLOYER',
    'public': 'PUBLIC_DEPLOYER',
    'futurenet': 'FUTURENET_DEPLOYER'
}

def get_identity_name(network: str) -> str:
    """Get the identity filename for the given network."""
    return NETWORK_IDENTITY_NAMES.get(network.lower(), 'DEPLOYER') + '.toml'

def check_soroban_cli() -> bool:
    """Verify that Soroban CLI is installed and in PATH."""
    try:
        result = subprocess.run(
            ["soroban", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"Soroban CLI check failed: {result.stderr}")
            return False
        logger.info(f"Soroban CLI version: {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        logger.error("Soroban CLI not found in PATH")
        return False
    except Exception as e:
        logger.error(f"Error checking Soroban CLI: {str(e)}")
        return False

def ensure_directories() -> Tuple[bool, str]:
    """
    Ensure that the required directories exist and are clean.
    
    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    try:
        # Debug current working directory and permissions
        cwd = os.getcwd()
        logger.info(f"Current working directory: {cwd}")
        logger.info(f"Directory contents: {os.listdir(cwd)}")
        
        # Check if we can write to the current directory
        test_file = os.path.join(cwd, '.write_test')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except IOError as e:
            return False, f"Cannot write to directory {cwd}: {str(e)}"
        
        # Create fresh .stellar directory
        if os.path.exists(STELLAR_DIR):
            logger.info(f"Removing existing directory: {STELLAR_DIR}")
            try:
                shutil.rmtree(STELLAR_DIR)
            except Exception as e:
                return False, f"Failed to remove {STELLAR_DIR}: {str(e)}"
        
        logger.info(f"Creating directory: {IDENTITY_DIR}")
        os.makedirs(IDENTITY_DIR, exist_ok=True)
        logger.info(f"Creating directory: {NETWORK_DIR}")
        os.makedirs(NETWORK_DIR, exist_ok=True)
        
        # Verify directories were created
        if not os.path.isdir(IDENTITY_DIR) or not os.path.isdir(NETWORK_DIR):
            return False, f"Failed to create required directories in {STELLAR_DIR}"
            
        logger.info(f"✅ Created Stellar directories in {STELLAR_DIR}")
        logger.info(f"Directory structure created at: {os.path.abspath(STELLAR_DIR)}")
        return True, ""
        
    except Exception as e:
        logger.error(f"Error in ensure_directories: {str(e)}", exc_info=True)
        return False, str(e)

def create_identity_file(secret_key: str) -> Dict[str, Any]:
    """
    Create a Stellar identity file.
    
    Args:
        secret_key: The Stellar secret key
        
    Returns:
        Dict containing the identity data
    """
    from stellar_sdk import Keypair
    
    try:
        keypair = Keypair.from_secret(secret_key)
        public_key = keypair.public_key
        
        identity_data = {
            'public_key': public_key,
            'type': 'private_key',
            'secret_key': secret_key
        }
        
        return identity_data
    except Exception as e:
        print(f"❌ Error creating identity: {str(e)}", file=sys.stderr)
        sys.exit(1)

def save_identity_file(identity_data: Dict[str, Any], network: str) -> str:
    """
    Save the identity data to a TOML file using network-specific naming.
    
    Args:
        identity_data: Dictionary containing identity data
        network: Network name (e.g., 'testnet', 'public')
        
    Returns:
        Path to the saved identity file
    """
    try:
        identity_name = get_identity_name(network)
        identity_file = os.path.join(IDENTITY_DIR, identity_name)
        
        with open(identity_file, 'w') as f:
            toml.dump(identity_data, f)
        
        # Set restrictive permissions (read/write for owner only)
        os.chmod(identity_file, 0o600)
        print(f"✅ Saved identity to {identity_file}")
        return identity_file
    except Exception as e:
        print(f"❌ Error saving identity file: {str(e)}", file=sys.stderr)
        sys.exit(1)

def verify_with_cli(network: str) -> bool:
    """
    Verify the identity works with the Stellar CLI.
    
    Returns:
        bool: True if verification succeeded, False otherwise
    """
    try:
        identity_name = get_identity_name(network).replace('.toml', '')
        logger.info(f"🔍 Verifying identity with Stellar CLI: {identity_name}")
        
        # Check if Soroban CLI is available
        if not check_soroban_cli():
            logger.error("Soroban CLI verification failed")
            return False
        
        # List all identities to verify ours exists
        success, stdout, stderr = run_command(["soroban", "config", "identity", "list"])
        
        if not success:
            logger.error(f"Failed to list identities: {stderr}")
            return False
            
        logger.info(f"Available identities: {stdout.strip() or 'None found'}")
        
        if identity_name not in stdout:
            logger.error(f"Identity '{identity_name}' not found in CLI configuration")
            logger.error(f"Available identities: {stdout}")
            return False
            
        # Try to get the public key
        success, stdout, stderr = run_command(
            ["soroban", "config", "identity", "show", identity_name]
        )
        
        if not success:
            logger.error(f"Failed to get public key for identity '{identity_name}': {stderr}")
            return False
            
        public_key = stdout.strip()
        logger.info(f"✅ Verified identity with public key: {public_key}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error verifying identity: {str(e)}", exc_info=True)
        return False

def setup_network_config(network: str, rpc_url: str) -> None:
    """
    Set up the network configuration for the Stellar CLI.
    
    Args:
        network: Network name (e.g., 'testnet', 'public', 'futurenet')
        rpc_url: RPC URL for the network
    """
    try:
        network_config = {
            'network': network,
            'rpc_url': rpc_url,
            'network_passphrase': get_network_passphrase(network)
        }
        
        network_file = os.path.join(NETWORK_DIR, f"{network}.toml")
        with open(network_file, 'w') as f:
            toml.dump(network_config, f)
        
        print(f"✅ Network configuration saved to {network_file}")
    except Exception as e:
        print(f"❌ Error saving network configuration: {str(e)}", file=sys.stderr)
        sys.exit(1)

def get_network_passphrase(network: str) -> str:
    """Get the passphrase for the specified network."""
    passphrases = {
        'testnet': 'Test SDF Network ; September 2015',
        'public': 'Public Global Stellar Network ; September 2015',
        'futurenet': 'Test SDF Future Network ; October 2022'
    }
    return passphrases.get(network.lower(), passphrases['testnet'])

def run_command(command: list, env: Optional[Dict[str, str]] = None) -> Tuple[bool, str, str]:
    """
    Run a shell command with proper environment and error handling.
    
    Args:
        command: List of command arguments
        env: Optional environment variables to use
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    env = env or os.environ.copy()
    
    # Ensure we have a proper PATH
    if 'PATH' not in env:
        env['PATH'] = os.environ.get('PATH', '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')
    
    # Ensure HOME is set
    if 'HOME' not in env:
        env['HOME'] = os.environ.get('HOME', os.getcwd())
    
    logger.info(f"Running command: {' '.join(command)}")
    logger.debug(f"Environment: {json.dumps({k: v for k, v in env.items() if 'SECRET' not in k}, indent=2)}")
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=env
        )
        
        logger.debug(f"Command exited with code {result.returncode}")
        logger.debug(f"stdout: {result.stdout}")
        if result.stderr:
            logger.debug(f"stderr: {result.stderr}")
            
        return result.returncode == 0, result.stdout, result.stderr
        
    except Exception as e:
        error_msg = f"Error running command {' '.join(command)}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, "", error_msg

def main() -> int:
    """
    Main function to set up the deployer identity.
    
    Returns:
        int: 0 on success, non-zero on error
    """
    try:
        # Log environment information
        logger.info("=" * 80)
        logger.info("Starting Stellar Deployer Identity Setup")
        logger.info("=" * 80)
        
        # Log environment variables (excluding sensitive ones)
        env_vars = {k: v for k, v in os.environ.items() if 'SECRET' not in k and 'KEY' not in k}
        logger.info(f"Environment variables: {json.dumps(env_vars, indent=2)}")
        
        # Get environment variables
        secret_key = os.environ.get("ACCT_SECRET")
        if not secret_key:
            error_msg = "❌ Error: ACCT_SECRET environment variable not set"
            logger.error(error_msg)
            print(error_msg)
            return 1
            
        # Get network (default to testnet if not specified)
        network = os.environ.get("NETWORK", "testnet").lower()
        rpc_url = os.environ.get("RPC_URL", "https://soroban-testnet.stellar.org")
        
        logger.info(f"🔧 Setting up Stellar deployer identity for network: {network}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"RPC URL: {rpc_url}")
        
        # Check if Soroban CLI is available
        if not check_soroban_cli():
            error_msg = "❌ Soroban CLI is not available or not in PATH"
            logger.error(error_msg)
            print(error_msg)
            return 1
        
        # Ensure directories exist
        success, error_msg = ensure_directories()
        if not success:
            logger.error(f"Failed to ensure directories: {error_msg}")
            print(f"❌ {error_msg}")
            return 1
        
        # Create identity file
        try:
            identity_data = create_identity_file(secret_key)
            identity_file = save_identity_file(identity_data, network)
            logger.info(f"Created identity file: {identity_file}")
        except Exception as e:
            error_msg = f"Failed to create identity file: {str(e)}"
            logger.error(error_msg, exc_info=True)
            print(f"❌ {error_msg}")
            return 1
        
        # Set up network config
        try:
            setup_network_config(network, rpc_url)
            logger.info(f"Network configuration set up for {network}")
        except Exception as e:
            error_msg = f"Failed to set up network configuration: {str(e)}"
            logger.error(error_msg, exc_info=True)
            print(f"❌ {error_msg}")
            return 1
        
        # Verify with CLI
        logger.info("Starting CLI verification...")
        if not verify_with_cli(network):
            error_msg = "❌ Failed to verify identity with Stellar CLI"
            logger.error(error_msg)
            print(error_msg)
            return 1
            
        success_msg = "✅ Stellar deployer identity setup completed successfully"
        logger.info(success_msg)
        print(success_msg)
        
        # Log final directory structure
        logger.info("Final directory structure:")
        for root, dirs, files in os.walk(STELLAR_DIR):
            level = root.replace(STELLAR_DIR, '').count(os.sep)
            indent = ' ' * 4 * level
            logger.info(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 4 * (level + 1)
            for f in files:
                logger.info(f"{subindent}{f}")
        
        return 0
        
    except Exception as e:
        error_msg = f"❌ Unhandled error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        print(error_msg)
        return 1
        
        print("\n✅ Deployer identity created and verified successfully")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
