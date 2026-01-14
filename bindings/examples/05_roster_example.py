#!/usr/bin/env python3
"""
Example 5: Using the Roster Contract

This example demonstrates how to interact with the hvym_roster
contract for member management and canon updates.

The roster is a simplified membership contract compared to
hvym_collective - it handles member lists and canon (configuration)
updates without the file publishing features.

Prerequisites:
    pip install stellar-sdk
"""

import sys
sys.path.insert(0, '..')

from stellar_sdk import Keypair

# Import the generated bindings
from hvym_roster.bindings import Client as RosterClient

from config import RPC_URL, CONTRACTS


def query_roster_info():
    """Query basic information from the roster contract."""
    print("=" * 50)
    print("Querying hvym_roster contract")
    print("=" * 50)

    client = RosterClient(
        contract_id=CONTRACTS["hvym_roster"],
        rpc_url=RPC_URL,
    )

    # Query symbol
    try:
        result = client.symbol()
        result.simulate()
        print(f"Roster Symbol: {result.result()}")
    except Exception as e:
        print(f"Error querying symbol: {e}")

    # Query join fee
    try:
        result = client.join_fee()
        result.simulate()
        fee = result.result()
        print(f"Join Fee: {fee} stroops ({fee / 10_000_000} XLM)")
    except Exception as e:
        print(f"Error querying join fee: {e}")

    # Get canon info
    try:
        result = client.get_canon()
        result.simulate()
        canon = result.result()
        print(f"Canon: {canon}")
    except Exception as e:
        print(f"Error getting canon: {e}")


def join_roster(secret_key: str):
    """Join the roster by paying the join fee."""
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key

    print("\n" + "=" * 50)
    print("Joining the Roster")
    print("=" * 50)
    print(f"Account: {public_key[:8]}...{public_key[-8:]}")

    client = RosterClient(
        contract_id=CONTRACTS["hvym_roster"],
        rpc_url=RPC_URL,
    )

    # Check if already a member
    try:
        check = client.is_member(public_key)
        check.simulate()
        if check.result():
            print("Already a member of the roster!")
            return
    except Exception as e:
        print(f"Error checking membership: {e}")

    # Join
    try:
        tx = client.join(
            caller=public_key,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        print("Simulation successful!")

        result = tx.sign_and_submit()
        print(f"Transaction hash: {result.hash}")

        if result.status == "SUCCESS":
            print("\nSuccessfully joined the roster!")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error joining roster: {e}")


def update_canon(secret_key: str, new_canon: str):
    """
    Update the roster's canon (configuration).

    Only admins can update the canon.

    Args:
        secret_key: Admin's secret key
        new_canon: New canon string (JSON configuration)
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key

    print("\n" + "=" * 50)
    print("Updating Canon")
    print("=" * 50)

    client = RosterClient(
        contract_id=CONTRACTS["hvym_roster"],
        rpc_url=RPC_URL,
    )

    # Verify admin status
    try:
        check = client.is_admin(public_key)
        check.simulate()
        if not check.result():
            print("Error: Only admins can update the canon")
            return
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return

    # Update canon
    try:
        tx = client.update_canon(
            caller=public_key,
            new_canon=new_canon.encode('utf-8'),
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        print("Simulation successful!")

        result = tx.sign_and_submit()
        print(f"Transaction hash: {result.hash}")

        if result.status == "SUCCESS":
            print("\nCanon updated successfully!")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error updating canon: {e}")


def admin_operations(secret_key: str):
    """Demonstrate admin operations on the roster."""
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key

    print("\n" + "=" * 50)
    print("Admin Operations")
    print("=" * 50)

    client = RosterClient(
        contract_id=CONTRACTS["hvym_roster"],
        rpc_url=RPC_URL,
    )

    # Get admin list
    try:
        result = client.get_admin_list()
        result.simulate()
        admins = result.result()
        print(f"Current admins ({len(admins)}):")
        for admin in admins:
            print(f"  - {admin}")
    except Exception as e:
        print(f"Error getting admin list: {e}")

    # Example: Add a new admin (uncomment to use)
    # new_admin_address = "GXXXXXX..."
    # try:
    #     tx = client.add_admin(
    #         caller=public_key,
    #         new_admin=new_admin_address,
    #         source=public_key,
    #         signer=keypair,
    #     )
    #     tx.simulate()
    #     result = tx.sign_and_submit()
    #     if result.status == "SUCCESS":
    #         print(f"Added new admin: {new_admin_address}")
    # except Exception as e:
    #     print(f"Error adding admin: {e}")


def check_member_info(address: str):
    """Check detailed member information."""
    print("\n" + "=" * 50)
    print(f"Member Info: {address[:8]}...{address[-8:]}")
    print("=" * 50)

    client = RosterClient(
        contract_id=CONTRACTS["hvym_roster"],
        rpc_url=RPC_URL,
    )

    # Check membership
    try:
        result = client.is_member(address)
        result.simulate()
        is_member = result.result()
        print(f"Is Member: {is_member}")

        if is_member:
            # Get payment info
            paid_result = client.member_paid(address)
            paid_result.simulate()
            paid = paid_result.result()
            print(f"Amount Paid: {paid} stroops ({paid / 10_000_000} XLM)")

    except Exception as e:
        print(f"Error checking member: {e}")


if __name__ == "__main__":
    import os

    # Query roster info (no secret key needed)
    query_roster_info()

    # Operations requiring a secret key
    secret_key = os.environ.get("STELLAR_SECRET_KEY")

    if secret_key:
        keypair = Keypair.from_secret(secret_key)

        # Check your own member info
        check_member_info(keypair.public_key)

        # Join the roster (uncomment to use)
        # join_roster(secret_key)

        # Admin operations (uncomment if you're an admin)
        # admin_operations(secret_key)

        # Update canon (uncomment if you're an admin)
        # update_canon(secret_key, '{"version": "1.0", "rules": []}')
    else:
        print("\nSet STELLAR_SECRET_KEY to run transaction examples")
