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
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

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

def ensure_directories() -> None:
    """Ensure that the required directories exist and are clean."""
    # Create fresh .stellar directory
    if os.path.exists(STELLAR_DIR):
        shutil.rmtree(STELLAR_DIR)
    
    os.makedirs(IDENTITY_DIR, exist_ok=True)
    os.makedirs(NETWORK_DIR, exist_ok=True)
    print(f"✅ Created Stellar directories in {STELLAR_DIR}")

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
    
    Args:
        network: Network name (e.g., 'testnet', 'public')
        
    Returns:
        bool: True if verification succeeded, False otherwise
    """
    try:
        identity_name = get_identity_name(network).replace('.toml', '')
        print(f"🔍 Verifying identity with Stellar CLI: {identity_name}")
        
        # First, list all identities for debugging
        list_cmd = ["stellar", "keys", "list"]
        list_result = subprocess.run(
            list_cmd,
            cwd=os.getcwd(),
            capture_output=True,
            text=True
        )
        print(f"Available identities:\n{list_result.stdout}")
        
        # Try to get the public key
        result = subprocess.run(
            ["stellar", "keys", "public-key", identity_name],
            cwd=os.getcwd(),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            public_key = result.stdout.strip()
            print(f"✅ Successfully verified identity: {public_key}")
            return True
        else:
            print(f"❌ Failed to verify identity: {result.stderr}")
            print(f"Command output: {result.stdout}")
            return False
    except Exception as e:
        print(f"❌ Error during CLI verification: {str(e)}")
        import traceback
        traceback.print_exc()
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

def main() -> int:
    """
    Main function to set up the deployer identity.
    
    Returns:
        int: 0 on success, non-zero on error
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Set up Stellar deployer identity')
    parser.add_argument('--secret-key-env', default='STELLAR_SECRET_KEY',
                      help='Environment variable containing the secret key (default: STELLAR_SECRET_KEY)')
    parser.add_argument('--network', default='testnet',
                      help='Network name (default: testnet)')
    parser.add_argument('--rpc-url', default='https://soroban-testnet.stellar.org',
                      help='RPC URL for the network (default: https://soroban-testnet.stellar.org)')
    
    args = parser.parse_args()
    
    # Get secret key from environment
    secret_key = os.environ.get(args.secret_key_env)
    if not secret_key:
        print(f"❌ Error: Environment variable {args.secret_key_env} not set", file=sys.stderr)
        return 1
    
    print(f"Setting up Stellar deployer identity for network: {args.network}")
    print(f"Working directory: {os.getcwd()}")
    
    try:
        # Ensure directories exist and clean up old ones
        ensure_directories()
        
        # Create and save identity
        identity_data = create_identity_file(secret_key)
        identity_file = save_identity_file(identity_data, args.network)
        
        # Set up network configuration
        setup_network_config(args.network, args.rpc_url)
        
        # Verify with Stellar CLI
        if not verify_with_cli(args.network):
            print("❌ Failed to verify identity with Stellar CLI", file=sys.stderr)
            return 1
        
        print("\n✅ Deployer identity created and verified successfully")
        print(f"   Identity file: {os.path.relpath(identity_file)}")
        print(f"   Public key: {identity_data['public_key']}")
        print(f"   Network: {args.network}")
        print(f"   RPC URL: {args.rpc_url}")
        
        # Get or create the output file path
        output_file = os.environ.get('GITHUB_OUTPUT')
        if not output_file:
            print("::warning::GITHUB_OUTPUT not set, using default output file")
            output_file = os.path.join(os.getcwd(), 'github_output.txt')
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        
        # Write outputs in GitHub Actions format
        with open(output_file, 'a') as f:
            # Write in GitHub Actions output format
            f.write(f'public_key={identity_data["public_key"]}\n')
            f.write(f'identity_file={identity_file}\n')
            f.write(f'network={args.network}\n')
            f.write(f'rpc_url={args.rpc_url}\n')
        
        # Print success message for the log
        print("\n✅ Deployer identity created successfully")
        print(f"Output written to: {output_file}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
