#!/usr/bin/env python3
"""
Example 9: Pin Service - Admin Operations

Demonstrates admin-only operations for managing the pin service:
    - View and manage the admin list
    - Update service configuration (fees, limits, thresholds)
    - Withdraw collected fees
    - Fund the contract
    - Force-clear slots
    - Remove pinners

Admin operations require the caller to be in the admin list.

Prerequisites:
    pip install stellar-sdk

WARNING: This example submits real transactions on testnet.
Only admins can execute these operations.
"""

import sys
sys.path.insert(0, '..')

from stellar_sdk import Keypair

from hvym_pin_service.bindings import Client as PinServiceClient
from config import RPC_URL, CONTRACTS, stroops_to_xlm, xlm_to_stroops


def get_client():
    return PinServiceClient(
        contract_id=CONTRACTS["hvym_pin_service"],
        rpc_url=RPC_URL,
    )


# ---------------------------------------------------------------------------
# Read-only admin queries
# ---------------------------------------------------------------------------

def view_admin_list():
    """Display the current admin list."""
    client = get_client()

    print("=" * 60)
    print("Admin List")
    print("=" * 60)

    try:
        result = client.get_admin_list()
        result.simulate()
        admins = result.result()
        print(f"  Total Admins: {len(admins)}")
        for i, admin in enumerate(admins):
            label = " (initial - protected)" if i == 0 else ""
            print(f"    {i+1}. {admin}{label}")
    except Exception as e:
        print(f"  Error: {e}")


def view_financials():
    """Show contract balance vs withdrawable fees."""
    client = get_client()

    print("=" * 60)
    print("Financial Summary")
    print("=" * 60)

    try:
        bal_result = client.balance()
        bal_result.simulate()
        balance = bal_result.result()

        fees_result = client.fees_collected()
        fees_result.simulate()
        fees = fees_result.result()

        escrow_held = balance - fees
        print(f"  Contract Balance:  {balance} stroops ({stroops_to_xlm(balance):.7f} XLM)")
        print(f"  Fees Collected:    {fees} stroops ({stroops_to_xlm(fees):.7f} XLM)")
        print(f"  Escrow Held:       {escrow_held} stroops ({stroops_to_xlm(escrow_held):.7f} XLM)")
        print(f"\n  Withdrawable:      {fees} stroops (fees only, escrow is protected)")
    except Exception as e:
        print(f"  Error: {e}")


# ---------------------------------------------------------------------------
# Admin write operations
# ---------------------------------------------------------------------------

def add_admin(secret_key: str, new_admin_address: str):
    """
    Add a new admin to the admin list.

    Args:
        secret_key: Current admin's secret key
        new_admin_address: Public key of the new admin
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print(f"Adding Admin: {new_admin_address[:8]}...{new_admin_address[-8:]}")
    print("=" * 60)

    try:
        tx = client.add_admin(
            caller=public_key,
            new_admin=new_admin_address,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            print("Admin added successfully!")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error: {e}")


def remove_admin(secret_key: str, admin_to_remove: str):
    """
    Remove an admin from the admin list.
    Cannot remove the initial admin (index 0).

    Args:
        secret_key: Current admin's secret key
        admin_to_remove: Public key of the admin to remove
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print(f"Removing Admin: {admin_to_remove[:8]}...{admin_to_remove[-8:]}")
    print("=" * 60)

    try:
        tx = client.remove_admin(
            caller=public_key,
            admin_to_remove=admin_to_remove,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            print("Admin removed successfully!")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error: {e}")


def withdraw_fees(secret_key: str, recipient: str, amount_xlm: float):
    """
    Withdraw collected fees to a recipient address.
    Only withdraws from fees_collected, never touches escrow.

    Args:
        secret_key: Admin's secret key
        recipient: Address to receive the fees
        amount_xlm: Amount to withdraw in XLM
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    amount_stroops = xlm_to_stroops(amount_xlm)

    print("=" * 60)
    print("Withdrawing Fees")
    print("=" * 60)
    print(f"  Recipient: {recipient[:8]}...{recipient[-8:]}")
    print(f"  Amount:    {amount_stroops} stroops ({amount_xlm} XLM)")

    # Check available fees
    try:
        fees_result = client.fees_collected()
        fees_result.simulate()
        available = fees_result.result()
        print(f"  Available: {available} stroops ({stroops_to_xlm(available):.7f} XLM)")

        if amount_stroops > available:
            print(f"\n  Error: Requested amount exceeds available fees!")
            return
    except Exception as e:
        print(f"Error checking fees: {e}")

    print("\nSubmitting withdrawal...")
    try:
        tx = client.withdraw_fees(
            caller=public_key,
            recipient=recipient,
            amount=amount_stroops,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            print(f"Withdrawal successful! {amount_xlm} XLM sent to {recipient[:8]}...")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error: {e}")


def update_service_config(secret_key: str):
    """
    Example of updating multiple service config parameters.

    Available update methods:
        update_pin_fee(caller, new_fee)
        update_join_fee(caller, new_fee)
        update_min_pin_qty(caller, new_qty)
        update_min_offer_price(caller, new_price)
        update_max_cycles(caller, new_max)
        update_flag_threshold(caller, new_threshold)
        update_pinner_stake(caller, new_stake)
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print("Updating Service Configuration")
    print("=" * 60)

    # Example: Update pin fee to 2 XLM
    new_pin_fee = xlm_to_stroops(2.0)
    print(f"  Setting pin_fee to {new_pin_fee} stroops (2 XLM)...")

    try:
        tx = client.update_pin_fee(
            caller=public_key,
            new_fee=new_pin_fee,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            print("  Pin fee updated!")
        else:
            print(f"  Failed: {result.status}")

    except Exception as e:
        print(f"  Error: {e}")


def force_clear_slot(secret_key: str, slot_id: int):
    """
    Admin-only: Force clear any slot regardless of expiration.
    Refunds escrow to the publisher.

    Args:
        secret_key: Admin's secret key
        slot_id: The slot ID to force clear (0-9)
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print(f"Force Clearing Slot {slot_id}")
    print("=" * 60)

    try:
        tx = client.force_clear_slot(
            caller=public_key,
            slot_id=slot_id,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            refund = result.result()
            print(f"Slot cleared! Escrow refunded: {refund} stroops")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error: {e}")


def remove_pinner(secret_key: str, pinner_address: str):
    """
    Admin-only: Remove a pinner. Returns their stake (non-punitive).

    Args:
        secret_key: Admin's secret key
        pinner_address: Address of the pinner to remove
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print(f"Removing Pinner: {pinner_address[:8]}...{pinner_address[-8:]}")
    print("=" * 60)

    try:
        tx = client.remove_pinner(
            admin_addr=public_key,
            pinner_addr=pinner_address,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            print("Pinner removed (stake returned to pinner).")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    # Read-only operations (no secret key needed)
    view_admin_list()
    view_financials()

    # Write operations (uncomment and set secret key)
    # import os
    # secret_key = os.environ.get("STELLAR_SECRET_KEY")
    # if not secret_key:
    #     print("Set STELLAR_SECRET_KEY for write operations")
    #     sys.exit(1)

    # add_admin(secret_key, "GNEWADMIN...")
    # withdraw_fees(secret_key, recipient="GRECIPIENT...", amount_xlm=1.0)
    # update_service_config(secret_key)
    # force_clear_slot(secret_key, slot_id=0)
    # remove_pinner(secret_key, pinner_address="GPINNER...")
