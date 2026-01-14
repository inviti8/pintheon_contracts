#!/usr/bin/env python3
"""
Example 4: Publishing Files to IPFS via the Collective

This example demonstrates how to publish files and deploy
IPFS tokens through the hvym_collective contract.

Prerequisites:
    pip install stellar-sdk

WARNING: This requires membership in the collective and will
submit real transactions on testnet.
"""

import sys
sys.path.insert(0, '..')

from stellar_sdk import Keypair

# Import the generated bindings
from hvym_collective.bindings import Client as CollectiveClient

from config import RPC_URL, CONTRACTS


def publish_file(secret_key: str, ipfs_hash: str, publisher_name: str):
    """
    Publish a file event to the collective.

    This creates an on-chain event that can be indexed by applications.

    Args:
        secret_key: The secret key of the member publishing
        ipfs_hash: The IPFS CID of the file
        publisher_name: Name/identifier of the publisher
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key

    print("=" * 50)
    print("Publishing File Event")
    print("=" * 50)
    print(f"Publisher: {publisher_name}")
    print(f"IPFS Hash: {ipfs_hash}")

    client = CollectiveClient(
        contract_id=CONTRACTS["hvym_collective"],
        rpc_url=RPC_URL,
    )

    # Verify membership first
    try:
        check = client.is_member(public_key)
        check.simulate()
        if not check.result():
            print("Error: You must be a member to publish files")
            return
    except Exception as e:
        print(f"Error checking membership: {e}")
        return

    # Publish the file
    try:
        tx = client.publish_file(
            caller=public_key,
            publisher=publisher_name.encode('utf-8'),
            ipfs_hash=ipfs_hash.encode('utf-8'),
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        print("Simulation successful!")

        result = tx.sign_and_submit()
        print(f"Transaction hash: {result.hash}")

        if result.status == "SUCCESS":
            print("\nFile published successfully!")
            print("The PublishFileEvent has been emitted on-chain.")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error publishing file: {e}")


def deploy_ipfs_token(
    secret_key: str,
    name: str,
    ipfs_hash: str,
    file_type: str,
    gateways: str,
    ipns_hash: str = None
):
    """
    Deploy an IPFS token contract for a file.

    This creates a new token contract that represents ownership
    of the IPFS file.

    Args:
        secret_key: The secret key of the member deploying
        name: Name of the token/file
        ipfs_hash: The IPFS CID of the file
        file_type: MIME type of the file (e.g., "image/png")
        gateways: Comma-separated list of IPFS gateways
        ipns_hash: Optional IPNS hash for mutable reference
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key

    print("=" * 50)
    print("Deploying IPFS Token")
    print("=" * 50)
    print(f"Name: {name}")
    print(f"IPFS Hash: {ipfs_hash}")
    print(f"File Type: {file_type}")
    print(f"Gateways: {gateways}")

    client = CollectiveClient(
        contract_id=CONTRACTS["hvym_collective"],
        rpc_url=RPC_URL,
    )

    # Verify membership
    try:
        check = client.is_member(public_key)
        check.simulate()
        if not check.result():
            print("Error: You must be a member to deploy tokens")
            return
    except Exception as e:
        print(f"Error checking membership: {e}")
        return

    # Deploy the IPFS token
    try:
        tx = client.deploy_ipfs_token(
            caller=public_key,
            name=name.encode('utf-8'),
            ipfs_hash=ipfs_hash.encode('utf-8'),
            file_type=file_type.encode('utf-8'),
            gateways=gateways.encode('utf-8'),
            ipns_hash=ipns_hash.encode('utf-8') if ipns_hash else None,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        print("Simulation successful!")

        result = tx.sign_and_submit()
        print(f"Transaction hash: {result.hash}")

        if result.status == "SUCCESS":
            # Get the deployed contract address from the result
            token_address = result.result()
            print(f"\nIPFS Token deployed successfully!")
            print(f"Token Contract Address: {token_address}")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error deploying IPFS token: {e}")


def deploy_node_token(secret_key: str, name: str, descriptor: str):
    """
    Deploy a node token contract.

    Node tokens represent nodes in a graph/network structure.

    Args:
        secret_key: The secret key of the member deploying
        name: Name of the node
        descriptor: JSON descriptor of the node
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key

    print("=" * 50)
    print("Deploying Node Token")
    print("=" * 50)
    print(f"Name: {name}")
    print(f"Descriptor: {descriptor[:50]}...")

    client = CollectiveClient(
        contract_id=CONTRACTS["hvym_collective"],
        rpc_url=RPC_URL,
    )

    try:
        tx = client.deploy_node_token(
            caller=public_key,
            name=name.encode('utf-8'),
            descriptor=descriptor.encode('utf-8'),
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            token_address = result.result()
            print(f"\nNode Token deployed!")
            print(f"Token Contract Address: {token_address}")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error deploying node token: {e}")


if __name__ == "__main__":
    import os

    secret_key = os.environ.get("STELLAR_SECRET_KEY")

    if not secret_key:
        print("Please set STELLAR_SECRET_KEY environment variable")
        sys.exit(1)

    # Example: Publish a file event
    publish_file(
        secret_key=secret_key,
        ipfs_hash="QmExample1234567890abcdefghijklmnopqrstuvwxyz",
        publisher_name="MyApp"
    )

    # Example: Deploy an IPFS token
    # deploy_ipfs_token(
    #     secret_key=secret_key,
    #     name="My Artwork",
    #     ipfs_hash="QmExample1234567890abcdefghijklmnopqrstuvwxyz",
    #     file_type="image/png",
    #     gateways="https://ipfs.io,https://gateway.pinata.cloud",
    # )
