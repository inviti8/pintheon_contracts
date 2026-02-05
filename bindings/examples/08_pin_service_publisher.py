#!/usr/bin/env python3
"""
Example 8: Pin Service - Publisher Workflow

Demonstrates the publisher side of the pin service:
    1. Create a pin request (escrow funds into a slot)
    2. Monitor slot status (check claims and remaining pins)
    3. Cancel a pin request (reclaim escrow)
    4. Clear an expired slot (anyone can trigger, refunds publisher)

The pin service has 10 reusable slots. Each slot holds one pin
request at a time. Slots expire after max_cycles epochs.

Prerequisites:
    pip install stellar-sdk

WARNING: This example submits real transactions on testnet.
"""

import sys
sys.path.insert(0, '..')

from stellar_sdk import Keypair

from hvym_pin_service.bindings import Client as PinServiceClient
from config import RPC_URL, CONTRACTS, NETWORK_PASSPHRASE, stroops_to_xlm


def get_client():
    return PinServiceClient(
        contract_id=CONTRACTS["hvym_pin_service"],
        rpc_url=RPC_URL,
    )


def show_costs(offer_price: int, pin_qty: int):
    """Calculate and display the total cost of a pin request."""
    client = get_client()

    try:
        fee_result = client.pin_fee()
        fee_result.simulate()
        pin_fee = fee_result.result()

        escrow = offer_price * pin_qty
        total = escrow + pin_fee

        print(f"\n  Cost Breakdown:")
        print(f"    Offer Price: {offer_price} stroops x {pin_qty} pinners = {escrow} stroops escrow")
        print(f"    Pin Fee:     {pin_fee} stroops (non-refundable)")
        print(f"    Total:       {total} stroops ({stroops_to_xlm(total):.7f} XLM)")

        return total
    except Exception as e:
        print(f"  Error calculating costs: {e}")
        return None


def create_pin(secret_key: str, cid: str, gateway: str, offer_price: int, pin_qty: int):
    """
    Create a pin request by escrowing funds into a slot.

    The contract will:
    - Find the next available slot (or reclaim an expired one)
    - Hash the CID with SHA-256 and check for duplicates
    - Transfer escrow (offer_price * pin_qty) + pin_fee from your account
    - Store the pin request in the slot

    Pinners can then collect from this slot to earn the offer_price.
    When all pins are collected, the slot is freed automatically.

    Args:
        secret_key: Stellar secret key
        cid: The IPFS CID to pin (e.g., "QmYourContentHash...")
        gateway: Preferred IPFS gateway URL (e.g., "https://ipfs.io")
        offer_price: Price per pin in stroops (must be >= min_offer_price)
        pin_qty: Number of pinners requested (must be >= min_pin_qty)
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print("Creating Pin Request")
    print("=" * 60)
    print(f"  Account:     {public_key[:8]}...{public_key[-8:]}")
    print(f"  CID:         {cid}")
    print(f"  Gateway:     {gateway}")
    print(f"  Offer Price: {offer_price} stroops per pinner")
    print(f"  Pin Qty:     {pin_qty} pinners")

    # Check constraints
    try:
        min_qty_result = client.min_pin_qty()
        min_qty_result.simulate()
        min_qty = min_qty_result.result()

        min_price_result = client.min_offer_price()
        min_price_result.simulate()
        min_price = min_price_result.result()

        if pin_qty < min_qty:
            print(f"\n  Error: pin_qty ({pin_qty}) < min_pin_qty ({min_qty})")
            return
        if offer_price < min_price:
            print(f"\n  Error: offer_price ({offer_price}) < min_offer_price ({min_price})")
            return
    except Exception as e:
        print(f"Error checking constraints: {e}")

    # Check slot availability
    try:
        avail_result = client.has_available_slots()
        avail_result.simulate()
        if not avail_result.result():
            print("\n  No slots available! All 10 slots are occupied.")
            print("  Wait for slots to expire or be cleared.")
            return
    except Exception as e:
        print(f"Error checking availability: {e}")

    # Show costs
    show_costs(offer_price, pin_qty)

    # Create the pin
    print("\nSubmitting create_pin transaction...")
    try:
        tx = client.create_pin(
            caller=public_key,
            cid=cid.encode('utf-8'),
            gateway=gateway.encode('utf-8'),
            offer_price=offer_price,
            pin_qty=pin_qty,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        print("Simulation successful!")

        result = tx.sign_and_submit()
        print(f"Transaction hash: {result.hash}")

        if result.status == "SUCCESS":
            slot_id = result.result()
            print(f"\nPin request created in slot {slot_id}!")
            print(f"Pinners can now collect from this slot.")
            return slot_id
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error creating pin: {e}")

    return None


def monitor_slot(slot_id: int):
    """
    Monitor a slot's progress - check claims and remaining pins.

    Args:
        slot_id: The slot ID to monitor (0-9)
    """
    client = get_client()

    print("=" * 60)
    print(f"Monitoring Slot {slot_id}")
    print("=" * 60)

    try:
        slot_result = client.get_slot(slot_id)
        slot_result.simulate()
        slot = slot_result.result()

        if not slot:
            print("  Slot is empty (no active pin request)")
            return

        print(f"  Publisher:       {slot.publisher}")
        print(f"  CID Hash:        {slot.cid_hash.hex()[:16]}...")
        print(f"  Offer Price:     {slot.offer_price} stroops per pin")
        print(f"  Progress:        {slot.pin_qty - slot.pins_remaining}/{slot.pin_qty} collected")
        print(f"  Pins Remaining:  {slot.pins_remaining}")
        print(f"  Escrow Balance:  {slot.escrow_balance} stroops ({stroops_to_xlm(slot.escrow_balance):.7f} XLM)")
        print(f"  Created At:      ledger {slot.created_at}")
        print(f"  Claims ({len(slot.claims)}):")
        for i, claimer in enumerate(slot.claims):
            print(f"    {i+1}. {claimer}")

        # Check expiration
        try:
            exp_result = client.is_slot_expired(slot_id)
            exp_result.simulate()
            expired = exp_result.result()
            if expired:
                print(f"\n  ** This slot has EXPIRED **")
                print(f"  Call clear_expired_slot({slot_id}) to refund the publisher.")
        except Exception:
            pass

    except Exception as e:
        print(f"Error reading slot: {e}")


def cancel_pin(secret_key: str, slot_id: int):
    """
    Cancel your pin request and reclaim the remaining escrow.

    Only the original publisher can cancel. The full remaining
    escrow_balance is refunded. The pin_fee is NOT refunded.

    Args:
        secret_key: Stellar secret key
        slot_id: The slot ID to cancel (0-9)
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print(f"Cancelling Pin in Slot {slot_id}")
    print("=" * 60)

    # Preview refund
    try:
        slot_result = client.get_slot(slot_id)
        slot_result.simulate()
        slot = slot_result.result()

        if not slot:
            print("  Slot is empty!")
            return

        if str(slot.publisher) != public_key:
            print(f"  Error: You are not the publisher of this slot!")
            print(f"  Publisher: {slot.publisher}")
            return

        print(f"  Escrow Refund: {slot.escrow_balance} stroops ({stroops_to_xlm(slot.escrow_balance):.7f} XLM)")
        print(f"  Pins Collected: {slot.pin_qty - slot.pins_remaining}/{slot.pin_qty}")
    except Exception as e:
        print(f"Error reading slot: {e}")

    print("\nSubmitting cancel transaction...")
    try:
        tx = client.cancel_pin(
            caller=public_key,
            slot_id=slot_id,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            refund = result.result()
            print(f"Pin cancelled! Refund: {refund} stroops ({stroops_to_xlm(refund):.7f} XLM)")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error cancelling: {e}")


def clear_expired_slot(secret_key: str, slot_id: int):
    """
    Clear an expired slot. Anyone can call this.

    The remaining escrow is refunded to the original publisher.
    The slot becomes available for new pin requests.

    Args:
        secret_key: Stellar secret key (any funded account)
        slot_id: The slot ID to clear (0-9)
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print(f"Clearing Expired Slot {slot_id}")
    print("=" * 60)

    # Verify it's expired
    try:
        exp_result = client.is_slot_expired(slot_id)
        exp_result.simulate()
        if not exp_result.result():
            print("  Slot is not expired yet!")
            return
    except Exception as e:
        print(f"Error checking expiration: {e}")

    print("\nSubmitting clear transaction...")
    try:
        tx = client.clear_expired_slot(
            slot_id=slot_id,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            refund = result.result()
            print(f"Slot cleared! Escrow refunded to publisher: {refund} stroops")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error clearing: {e}")


if __name__ == "__main__":
    import os

    secret_key = os.environ.get("STELLAR_SECRET_KEY")

    if not secret_key:
        print("Please set STELLAR_SECRET_KEY environment variable")
        print("Example: export STELLAR_SECRET_KEY=SXXXX...")
        sys.exit(1)

    # 1. Create a pin request
    slot_id = create_pin(
        secret_key=secret_key,
        cid="QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG",
        gateway="https://ipfs.io",
        offer_price=100,   # 100 stroops per pinner
        pin_qty=3,         # request 3 pinners
    )

    # 2. Monitor the slot
    if slot_id is not None:
        monitor_slot(slot_id)

    # 3. Cancel (uncomment to test)
    # cancel_pin(secret_key, slot_id=0)

    # 4. Clear expired slot (uncomment to test)
    # clear_expired_slot(secret_key, slot_id=0)
