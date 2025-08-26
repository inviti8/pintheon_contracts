#!/usr/bin/env python3
"""
Setup Stellar Deployer Identity

This script creates a Stellar identity file for deployment purposes.
It takes a secret key from an environment variable and creates the necessary
identity file that can be used by the Stellar CLI.
"""

import os
import sys
import toml
from pathlib import Path
from typing import Optional, Dict, Any

# Constants
DEFAULT_IDENTITY_NAME = "deployer"
IDENTITY_DIR = os.path.join(os.path.expanduser("~"), ".stellar", "identity")
NETWORK_DIR = os.path.join(os.path.expanduser("~"), ".stellar", "network")

def ensure_directories() -> None:
    """Ensure that the required directories exist."""
    os.makedirs(IDENTITY_DIR, exist_ok=True)
    os.makedirs(NETWORK_DIR, exist_ok=True)

def create_identity_file(secret_key: str, identity_name: str = DEFAULT_IDENTITY_NAME) -> Dict[str, Any]:
    """
    Create a Stellar identity file.
    
    Args:
        secret_key: The Stellar secret key
        identity_name: Name for the identity file
        
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

def save_identity_file(identity_data: Dict[str, Any], identity_name: str = DEFAULT_IDENTITY_NAME) -> str:
    """
    Save the identity data to a TOML file.
    
    Args:
        identity_data: Dictionary containing identity data
        identity_name: Name for the identity file
        
    Returns:
        Path to the saved identity file
    """
    try:
        identity_file = os.path.join(IDENTITY_DIR, f"{identity_name}.toml")
        with open(identity_file, 'w') as f:
            toml.dump(identity_data, f)
        
        # Set restrictive permissions (read/write for owner only)
        os.chmod(identity_file, 0o600)
        
        return identity_file
    except Exception as e:
        print(f"❌ Error saving identity file: {str(e)}", file=sys.stderr)
        sys.exit(1)

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
        print(f"⚠️  Warning: Could not save network configuration: {str(e)}")

def get_network_passphrase(network: str) -> str:
    """Get the passphrase for the specified network."""
    passphrases = {
        'testnet': 'Test SDF Network ; September 2015',
        'public': 'Public Global Stellar Network ; September 2015',
        'futurenet': 'Test SDF Future Network ; October 2022'
    }
    return passphrases.get(network.lower(), passphrases['testnet'])

def main():
    """Main function to set up the deployer identity."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Set up Stellar deployer identity')
    parser.add_argument('--secret-key-env', default='STELLAR_SECRET_KEY',
                      help='Environment variable containing the secret key (default: STELLAR_SECRET_KEY)')
    parser.add_argument('--identity-name', default=DEFAULT_IDENTITY_NAME,
                      help=f'Name for the identity (default: {DEFAULT_IDENTITY_NAME})')
    parser.add_argument('--network', default='testnet',
                      help='Stellar network (testnet/public/futurenet) (default: testnet)')
    parser.add_argument('--rpc-url',
                      help='RPC URL for the network (default: based on network)')
    
    args = parser.parse_args()
    
    # Get secret key from environment
    secret_key = os.environ.get(args.secret_key_env)
    if not secret_key:
        print(f"❌ Error: {args.secret_key_env} environment variable not set", file=sys.stderr)
        sys.exit(1)
    
    # Set default RPC URL based on network if not provided
    if not args.rpc_url:
        args.rpc_url = {
            'testnet': 'https://soroban-testnet.stellar.org',
            'public': 'https://horizon.stellar.org',
            'futurenet': 'https://rpc-futurenet.stellar.org'
        }.get(args.network.lower(), 'https://soroban-testnet.stellar.org')
    
    print(f"Setting up Stellar deployer identity for network: {args.network}")
    
    # Ensure directories exist
    ensure_directories()
    
    # Create and save identity
    identity_data = create_identity_file(secret_key, args.identity_name)
    identity_file = save_identity_file(identity_data, args.identity_name)
    
    # Set up network configuration
    setup_network_config(args.network, args.rpc_url)
    
    print(f"✅ Deployer identity created successfully")
    print(f"   Identity file: {identity_file}")
    print(f"   Public key: {identity_data['public_key']}")
    print(f"   Network: {args.network}")
    print(f"   RPC URL: {args.rpc_url}")
    
    # Set environment variables for the workflow
    print(f"::set-output name=public_key::{identity_data['public_key']}")
    print(f"::set-output name=identity_file::{identity_file}")
    print(f"::set-output name=network::{args.network}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
