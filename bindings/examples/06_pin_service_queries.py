#!/usr/bin/env python3
"""
Example 6: Pin Service - Read-Only Queries

Demonstrates how to query the hvym_pin_service contract state without
sending transactions. These operations are free and don't require
a funded account.

Covers:
    - Service configuration (fees, limits, thresholds)
    - Slot pool status (active slots, availability, expiration)
    - Pinner lookups and counts
    - Epoch and timing information

Prerequisites:
    pip install stellar-sdk
"""

import sys
sys.path.insert(0, '..')

from stellar_sdk import SorobanServer

from hvym_pin_service.bindings import Client as PinServiceClient
from config import RPC_URL, CONTRACTS, stroops_to_xlm


def query_service_config():
    """Query all pin service configuration parameters."""
    print("=" * 60)
    print("Pin Service Configuration")
    print("=" * 60)

    client = PinServiceClient(
        contract_id=CONTRACTS["hvym_pin_service"],
        rpc_url=RPC_URL,
    )

    # Symbol
    try:
        result = client.symbol()
        result.simulate()
        print(f"  Symbol:          {result.result()}")
    except Exception as e:
        print(f"  Error querying symbol: {e}")

    # Pin fee (paid by publishers on each create_pin)
    try:
        result = client.pin_fee()
        result.simulate()
        fee = result.result()
        print(f"  Pin Fee:         {fee} stroops ({stroops_to_xlm(fee):.7f} XLM)")
    except Exception as e:
        print(f"  Error querying pin_fee: {e}")

    # Join fee (paid by pinners to register)
    try:
        result = client.join_fee()
        result.simulate()
        fee = result.result()
        print(f"  Join Fee:        {fee} stroops ({stroops_to_xlm(fee):.7f} XLM)")
    except Exception as e:
        print(f"  Error querying join_fee: {e}")

    # Pinner stake
    try:
        result = client.pinner_stake_amount()
        result.simulate()
        stake = result.result()
        print(f"  Pinner Stake:    {stake} stroops ({stroops_to_xlm(stake):.7f} XLM)")
    except Exception as e:
        print(f"  Error querying pinner_stake: {e}")

    # Min offer price
    try:
        result = client.min_offer_price()
        result.simulate()
        price = result.result()
        print(f"  Min Offer Price: {price} stroops ({stroops_to_xlm(price):.7f} XLM)")
    except Exception as e:
        print(f"  Error querying min_offer_price: {e}")

    # Min pin quantity
    try:
        result = client.min_pin_qty()
        result.simulate()
        print(f"  Min Pin Qty:     {result.result()}")
    except Exception as e:
        print(f"  Error querying min_pin_qty: {e}")

    # Max cycles (epochs before expiration)
    try:
        result = client.max_cycles()
        result.simulate()
        print(f"  Max Cycles:      {result.result()} epochs")
    except Exception as e:
        print(f"  Error querying max_cycles: {e}")

    # Flag threshold
    try:
        result = client.flag_threshold()
        result.simulate()
        print(f"  Flag Threshold:  {result.result()} flags")
    except Exception as e:
        print(f"  Error querying flag_threshold: {e}")

    # Fees collected
    try:
        result = client.fees_collected()
        result.simulate()
        fees = result.result()
        print(f"  Fees Collected:  {fees} stroops ({stroops_to_xlm(fees):.7f} XLM)")
    except Exception as e:
        print(f"  Error querying fees_collected: {e}")

    # Contract balance
    try:
        result = client.balance()
        result.simulate()
        bal = result.result()
        print(f"  Balance:         {bal} stroops ({stroops_to_xlm(bal):.7f} XLM)")
    except Exception as e:
        print(f"  Error querying balance: {e}")

    # Pay token address
    try:
        result = client.pay_token()
        result.simulate()
        print(f"  Pay Token:       {result.result()}")
    except Exception as e:
        print(f"  Error querying pay_token: {e}")


def query_slot_pool():
    """Query the slot pool status."""
    print("\n" + "=" * 60)
    print("Slot Pool Status")
    print("=" * 60)

    client = PinServiceClient(
        contract_id=CONTRACTS["hvym_pin_service"],
        rpc_url=RPC_URL,
    )

    # Check availability
    try:
        result = client.has_available_slots()
        result.simulate()
        available = result.result()
        print(f"  Has Available Slots: {available}")
    except Exception as e:
        print(f"  Error checking availability: {e}")

    # Current epoch
    try:
        result = client.current_epoch()
        result.simulate()
        print(f"  Current Epoch:       {result.result()}")
    except Exception as e:
        print(f"  Error querying epoch: {e}")

    # Get all active slots
    try:
        result = client.get_all_slots()
        result.simulate()
        slots = result.result()
        print(f"  Active Slots:        {len(slots)} / 10")

        for slot in slots:
            expired_text = ""
            try:
                exp_result = client.is_slot_expired(slot.created_at)
                exp_result.simulate()
                if exp_result.result():
                    expired_text = " [EXPIRED]"
            except Exception:
                pass

            print(f"\n  --- Slot (created at ledger {slot.created_at}){expired_text} ---")
            print(f"    Publisher:       {slot.publisher}")
            print(f"    CID Hash:        {slot.cid_hash.hex()[:16]}...")
            print(f"    Offer Price:     {slot.offer_price} stroops")
            print(f"    Pin Qty:         {slot.pin_qty}")
            print(f"    Pins Remaining:  {slot.pins_remaining}")
            print(f"    Escrow Balance:  {slot.escrow_balance} stroops")
            print(f"    Claims:          {len(slot.claims)}")

    except Exception as e:
        print(f"  Error querying slots: {e}")


def query_pinner(address: str):
    """Look up a specific pinner by address."""
    print("\n" + "=" * 60)
    print(f"Pinner Lookup: {address[:8]}...{address[-8:]}")
    print("=" * 60)

    client = PinServiceClient(
        contract_id=CONTRACTS["hvym_pin_service"],
        rpc_url=RPC_URL,
    )

    # Check if registered
    try:
        result = client.is_pinner(address)
        result.simulate()
        is_pinner = result.result()
        print(f"  Is Pinner: {is_pinner}")

        if not is_pinner:
            return
    except Exception as e:
        print(f"  Error checking pinner: {e}")
        return

    # Get pinner details
    try:
        result = client.get_pinner(address)
        result.simulate()
        pinner = result.result()

        if pinner:
            print(f"  Node ID:         {pinner.node_id.decode('utf-8', errors='replace')}")
            print(f"  Multiaddr:       {pinner.multiaddr.decode('utf-8', errors='replace')}")
            print(f"  Min Price:       {pinner.min_price} stroops")
            print(f"  Joined At:       {pinner.joined_at}")
            print(f"  Pins Completed:  {pinner.pins_completed}")
            print(f"  Flags:           {pinner.flags}")
            print(f"  Staked:          {pinner.staked} stroops ({stroops_to_xlm(pinner.staked):.7f} XLM)")
            print(f"  Active:          {pinner.active}")
    except Exception as e:
        print(f"  Error getting pinner: {e}")


def query_pinner_count():
    """Get total registered pinner count."""
    print("\n" + "=" * 60)
    print("Pinner Count")
    print("=" * 60)

    client = PinServiceClient(
        contract_id=CONTRACTS["hvym_pin_service"],
        rpc_url=RPC_URL,
    )

    try:
        result = client.get_pinner_count()
        result.simulate()
        print(f"  Registered Pinners: {result.result()}")
    except Exception as e:
        print(f"  Error getting count: {e}")


if __name__ == "__main__":
    query_service_config()
    query_slot_pool()
    query_pinner_count()

    # Example: Look up a specific pinner
    # Replace with a real address to test
    # query_pinner("GXXXXXXX...")
