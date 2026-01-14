#!/usr/bin/env python3
"""
Example 1: Basic Read-Only Queries

This example demonstrates how to query contract state without
sending transactions. These operations are free and don't require
a funded account.

Prerequisites:
    pip install stellar-sdk
"""

import sys
sys.path.insert(0, '..')  # Add parent directory to import bindings

from stellar_sdk import SorobanServer

# Import the generated bindings
from hvym_collective.bindings import Client as CollectiveClient
from hvym_roster.bindings import Client as RosterClient

# Configuration
from config import RPC_URL, CONTRACTS


def query_collective_info():
    """Query basic information from the hvym_collective contract."""
    print("=" * 50)
    print("Querying hvym_collective contract")
    print("=" * 50)

    # Create a Soroban server connection
    server = SorobanServer(RPC_URL)

    # Create the contract client
    client = CollectiveClient(
        contract_id=CONTRACTS["hvym_collective"],
        rpc_url=RPC_URL,
    )

    # Query the collective symbol
    try:
        result = client.symbol()
        # Simulate the transaction to get the result without submitting
        result.simulate()
        print(f"Collective Symbol: {result.result()}")
    except Exception as e:
        print(f"Error querying symbol: {e}")

    # Query join fee
    try:
        result = client.join_fee()
        result.simulate()
        fee_stroops = result.result()
        fee_xlm = fee_stroops / 10_000_000
        print(f"Join Fee: {fee_stroops} stroops ({fee_xlm} XLM)")
    except Exception as e:
        print(f"Error querying join fee: {e}")

    # Query mint fee
    try:
        result = client.mint_fee()
        result.simulate()
        fee_stroops = result.result()
        fee_xlm = fee_stroops / 10_000_000
        print(f"Mint Fee: {fee_stroops} stroops ({fee_xlm} XLM)")
    except Exception as e:
        print(f"Error querying mint fee: {e}")

    # Query opus reward
    try:
        result = client.opus_reward()
        result.simulate()
        reward = result.result()
        print(f"Opus Reward: {reward} stroops")
    except Exception as e:
        print(f"Error querying opus reward: {e}")

    # Check if launched
    try:
        result = client.is_launched()
        result.simulate()
        print(f"Is Launched: {result.result()}")
    except Exception as e:
        print(f"Error checking launch status: {e}")


def check_membership(address: str):
    """Check if an address is a member of the collective."""
    print("\n" + "=" * 50)
    print(f"Checking membership for: {address[:8]}...{address[-8:]}")
    print("=" * 50)

    client = CollectiveClient(
        contract_id=CONTRACTS["hvym_collective"],
        rpc_url=RPC_URL,
    )

    try:
        result = client.is_member(address)
        result.simulate()
        is_member = result.result()
        print(f"Is Member: {is_member}")

        if is_member:
            # Query how much they've paid
            paid_result = client.member_paid(address)
            paid_result.simulate()
            paid = paid_result.result()
            print(f"Amount Paid: {paid} stroops ({paid / 10_000_000} XLM)")
    except Exception as e:
        print(f"Error checking membership: {e}")


def check_admin(address: str):
    """Check if an address is an admin."""
    print("\n" + "=" * 50)
    print(f"Checking admin status for: {address[:8]}...{address[-8:]}")
    print("=" * 50)

    client = CollectiveClient(
        contract_id=CONTRACTS["hvym_collective"],
        rpc_url=RPC_URL,
    )

    try:
        result = client.is_admin(address)
        result.simulate()
        print(f"Is Admin: {result.result()}")
    except Exception as e:
        print(f"Error checking admin status: {e}")


def get_admin_list():
    """Get the list of all admins."""
    print("\n" + "=" * 50)
    print("Getting admin list")
    print("=" * 50)

    client = CollectiveClient(
        contract_id=CONTRACTS["hvym_collective"],
        rpc_url=RPC_URL,
    )

    try:
        result = client.get_admin_list()
        result.simulate()
        admins = result.result()
        print(f"Number of admins: {len(admins)}")
        for i, admin in enumerate(admins):
            print(f"  {i + 1}. {admin}")
    except Exception as e:
        print(f"Error getting admin list: {e}")


if __name__ == "__main__":
    # Query basic collective info
    query_collective_info()

    # Example: Check membership for a specific address
    # Replace with an actual address to test
    test_address = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"
    check_membership(test_address)

    # Check admin status
    check_admin(test_address)

    # Get all admins
    get_admin_list()
