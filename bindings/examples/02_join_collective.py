#!/usr/bin/env python3
"""
Example 2: Joining the Collective

This example demonstrates how to join the hvym_collective by
submitting a transaction. This requires a funded Stellar account.

Prerequisites:
    pip install stellar-sdk

WARNING: This example will submit real transactions on testnet.
Make sure you have testnet XLM in your account.
"""

import sys
sys.path.insert(0, '..')

from stellar_sdk import Keypair, Network

# Import the generated bindings
from hvym_collective.bindings import Client as CollectiveClient

from config import RPC_URL, CONTRACTS, NETWORK_PASSPHRASE


def join_collective(secret_key: str):
    """
    Join the collective by paying the join fee.

    Args:
        secret_key: The secret key of the account joining
    """
    # Create keypair from secret
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key

    print("=" * 50)
    print("Joining the Collective")
    print("=" * 50)
    print(f"Account: {public_key[:8]}...{public_key[-8:]}")

    # Create the contract client
    client = CollectiveClient(
        contract_id=CONTRACTS["hvym_collective"],
        rpc_url=RPC_URL,
    )

    # First, check if already a member
    try:
        check_result = client.is_member(public_key)
        check_result.simulate()
        if check_result.result():
            print("You are already a member!")
            return
    except Exception as e:
        print(f"Error checking membership: {e}")

    # Check the join fee
    try:
        fee_result = client.join_fee()
        fee_result.simulate()
        fee = fee_result.result()
        print(f"Join fee: {fee} stroops ({fee / 10_000_000} XLM)")
    except Exception as e:
        print(f"Error getting join fee: {e}")
        return

    # Join the collective
    print("\nSubmitting join transaction...")
    try:
        # Build and sign the transaction
        tx = client.join(
            caller=public_key,
            source=public_key,
            signer=keypair,
            base_fee=100,
            transaction_timeout=300,
        )

        # Simulate first to check for errors
        tx.simulate()
        print("Simulation successful!")

        # Sign and submit
        result = tx.sign_and_submit()
        print(f"Transaction submitted!")
        print(f"Transaction hash: {result.hash}")
        print(f"Status: {result.status}")

        if result.status == "SUCCESS":
            print("\nSuccessfully joined the collective!")
        else:
            print(f"\nTransaction failed: {result.status}")

    except Exception as e:
        print(f"Error joining collective: {e}")


def check_balance_before_join(secret_key: str):
    """Check account balance before attempting to join."""
    from stellar_sdk import Server

    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key

    # Use Horizon server for balance check
    horizon_url = "https://horizon-testnet.stellar.org"
    server = Server(horizon_url)

    try:
        account = server.accounts().account_id(public_key).call()
        for balance in account["balances"]:
            if balance["asset_type"] == "native":
                print(f"XLM Balance: {balance['balance']} XLM")
                return float(balance["balance"])
    except Exception as e:
        print(f"Error checking balance: {e}")
        return 0


if __name__ == "__main__":
    # IMPORTANT: Never commit your secret key!
    # Use environment variables in production
    import os

    secret_key = os.environ.get("STELLAR_SECRET_KEY")

    if not secret_key:
        print("Please set STELLAR_SECRET_KEY environment variable")
        print("Example: export STELLAR_SECRET_KEY=SXXXX...")
        print("\nTo create a testnet account:")
        print("1. Generate a keypair: stellar keys generate --global mykey --network testnet")
        print("2. Fund it: stellar keys fund mykey --network testnet")
        sys.exit(1)

    # Check balance first
    balance = check_balance_before_join(secret_key)
    if balance < 10:
        print("\nInsufficient balance. Please fund your account first.")
        print("Use: stellar keys fund <your-key-name> --network testnet")
        sys.exit(1)

    # Join the collective
    join_collective(secret_key)
