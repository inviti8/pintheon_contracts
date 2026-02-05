#!/usr/bin/env python3
"""
Example 7: Pin Service - Pinner Registration & Lifecycle

Demonstrates the full pinner lifecycle:
    1. Join as pinner (pays join_fee + pinner_stake)
    2. Query your pinner profile
    3. Update pinner settings (node_id, multiaddr, min_price, active)
    4. Collect pins from active slots (earn offer_price per pin)
    5. Flag a misbehaving pinner (CID Hunter system)
    6. Leave as pinner (reclaim stake)

Prerequisites:
    pip install stellar-sdk

WARNING: This example submits real transactions on testnet.
Make sure you have testnet XLM in your account.
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


def join_as_pinner(secret_key: str, node_id: str, multiaddr: str, min_price: int):
    """
    Register as a pinner on the pin service.

    This transfers join_fee + pinner_stake from your account to the contract.
    The stake is returned when you leave (if not deactivated by flags).

    Args:
        secret_key: Stellar secret key
        node_id: Your IPFS peer ID (e.g., "12D3KooW...")
        multiaddr: Your IPFS multiaddress (e.g., "/ip4/1.2.3.4/tcp/4001")
        min_price: Minimum offer price you'll accept (in stroops)
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print("Joining as Pinner")
    print("=" * 60)
    print(f"  Account:    {public_key[:8]}...{public_key[-8:]}")
    print(f"  Node ID:    {node_id}")
    print(f"  Multiaddr:  {multiaddr}")
    print(f"  Min Price:  {min_price} stroops")

    # Check if already registered
    try:
        check = client.is_pinner(public_key)
        check.simulate()
        if check.result():
            print("\nAlready registered as a pinner!")
            return
    except Exception as e:
        print(f"Error checking pinner status: {e}")
        return

    # Show costs
    try:
        fee_result = client.join_fee()
        fee_result.simulate()
        join_fee = fee_result.result()

        stake_result = client.pinner_stake_amount()
        stake_result.simulate()
        stake = stake_result.result()

        total = join_fee + stake
        print(f"\n  Join Fee:     {join_fee} stroops ({stroops_to_xlm(join_fee):.7f} XLM)")
        print(f"  Pinner Stake: {stake} stroops ({stroops_to_xlm(stake):.7f} XLM)")
        print(f"  Total Cost:   {total} stroops ({stroops_to_xlm(total):.7f} XLM)")
    except Exception as e:
        print(f"Error getting fees: {e}")

    # Join
    print("\nSubmitting join transaction...")
    try:
        tx = client.join_as_pinner(
            caller=public_key,
            node_id=node_id.encode('utf-8'),
            multiaddr=multiaddr.encode('utf-8'),
            min_price=min_price,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        print("Simulation successful!")

        result = tx.sign_and_submit()
        print(f"Transaction hash: {result.hash}")

        if result.status == "SUCCESS":
            pinner = result.result()
            print(f"\nSuccessfully joined as pinner!")
            print(f"  Staked: {pinner.staked} stroops")
            print(f"  Active: {pinner.active}")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error joining: {e}")


def update_pinner(secret_key: str, node_id: str = None, multiaddr: str = None,
                  min_price: int = None, active: bool = None):
    """
    Update your pinner profile. Pass only the fields you want to change.

    Args:
        secret_key: Stellar secret key
        node_id: New IPFS peer ID (or None to keep current)
        multiaddr: New multiaddress (or None to keep current)
        min_price: New minimum price (or None to keep current)
        active: Set active/inactive (or None to keep current)
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print("Updating Pinner Profile")
    print("=" * 60)

    try:
        tx = client.update_pinner(
            caller=public_key,
            node_id=node_id.encode('utf-8') if node_id else None,
            multiaddr=multiaddr.encode('utf-8') if multiaddr else None,
            min_price=min_price,
            active=active,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            pinner = result.result()
            print("Profile updated!")
            print(f"  Node ID:    {pinner.node_id.decode('utf-8', errors='replace')}")
            print(f"  Multiaddr:  {pinner.multiaddr.decode('utf-8', errors='replace')}")
            print(f"  Min Price:  {pinner.min_price} stroops")
            print(f"  Active:     {pinner.active}")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error updating: {e}")


def collect_pin(secret_key: str, slot_id: int):
    """
    Collect a pin from an active slot. Earns the slot's offer_price.

    The pinner must be active and not already have claimed this slot.
    The slot must not be expired and must have remaining pins.

    Args:
        secret_key: Stellar secret key
        slot_id: The slot ID to collect from (0-9)
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print(f"Collecting Pin from Slot {slot_id}")
    print("=" * 60)

    # Preview the slot
    try:
        slot_result = client.get_slot(slot_id)
        slot_result.simulate()
        slot = slot_result.result()

        if slot:
            print(f"  CID Hash:        {slot.cid_hash.hex()[:16]}...")
            print(f"  Offer Price:     {slot.offer_price} stroops ({stroops_to_xlm(slot.offer_price):.7f} XLM)")
            print(f"  Pins Remaining:  {slot.pins_remaining} / {slot.pin_qty}")
        else:
            print("  Slot is empty!")
            return
    except Exception as e:
        print(f"Error reading slot: {e}")

    # Collect
    print("\nSubmitting collect transaction...")
    try:
        tx = client.collect_pin(
            caller=public_key,
            slot_id=slot_id,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            remaining = result.result()
            print(f"Pin collected! Pins remaining in slot: {remaining}")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error collecting pin: {e}")


def flag_pinner(secret_key: str, target_address: str):
    """
    Flag a misbehaving pinner (CID Hunter system).

    Both caller and target must be registered pinners.
    Each pinner can only flag a target once.
    When flags reach the threshold, the target is deactivated
    and their stake is distributed to the flaggers.

    Args:
        secret_key: Stellar secret key of the flagger
        target_address: Address of the pinner to flag
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print(f"Flagging Pinner: {target_address[:8]}...{target_address[-8:]}")
    print("=" * 60)

    # Check target's current flag count
    try:
        target_result = client.get_pinner(target_address)
        target_result.simulate()
        target = target_result.result()

        if target:
            threshold_result = client.flag_threshold()
            threshold_result.simulate()
            threshold = threshold_result.result()

            print(f"  Current Flags: {target.flags} / {threshold} (threshold)")
            print(f"  Target Active: {target.active}")
        else:
            print("  Target is not a registered pinner!")
            return
    except Exception as e:
        print(f"Error checking target: {e}")

    print("\nSubmitting flag transaction...")
    try:
        tx = client.flag_pinner(
            caller=public_key,
            pinner_addr=target_address,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            new_flags = result.result()
            print(f"Flag submitted! Target now has {new_flags} flags.")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error flagging: {e}")


def leave_as_pinner(secret_key: str):
    """
    Leave the pin service and reclaim your stake.

    If your pinner is still active (not deactivated by flags),
    you receive your full stake back. If deactivated, stake is
    already forfeited.

    Args:
        secret_key: Stellar secret key
    """
    keypair = Keypair.from_secret(secret_key)
    public_key = keypair.public_key
    client = get_client()

    print("=" * 60)
    print("Leaving as Pinner")
    print("=" * 60)

    # Check current stake
    try:
        pinner_result = client.get_pinner(public_key)
        pinner_result.simulate()
        pinner = pinner_result.result()

        if pinner:
            print(f"  Current Stake: {pinner.staked} stroops ({stroops_to_xlm(pinner.staked):.7f} XLM)")
            print(f"  Active:        {pinner.active}")
            if pinner.active:
                print(f"  Refund:        {pinner.staked} stroops (full stake returned)")
            else:
                print(f"  Refund:        0 (deactivated by flags, stake forfeited)")
        else:
            print("  Not registered as a pinner!")
            return
    except Exception as e:
        print(f"Error checking pinner: {e}")

    print("\nSubmitting leave transaction...")
    try:
        tx = client.leave_as_pinner(
            caller=public_key,
            source=public_key,
            signer=keypair,
        )

        tx.simulate()
        result = tx.sign_and_submit()

        if result.status == "SUCCESS":
            refund = result.result()
            print(f"Left pin service. Refund: {refund} stroops ({stroops_to_xlm(refund):.7f} XLM)")
        else:
            print(f"Transaction failed: {result.status}")

    except Exception as e:
        print(f"Error leaving: {e}")


if __name__ == "__main__":
    import os

    secret_key = os.environ.get("STELLAR_SECRET_KEY")

    if not secret_key:
        print("Please set STELLAR_SECRET_KEY environment variable")
        print("Example: export STELLAR_SECRET_KEY=SXXXX...")
        print("\nTo create a testnet account:")
        print("1. Generate a keypair: stellar keys generate --global mykey --network testnet")
        print("2. Fund it: stellar keys fund mykey --network testnet")
        sys.exit(1)

    # 1. Join as pinner
    join_as_pinner(
        secret_key=secret_key,
        node_id="12D3KooWExamplePeerId",
        multiaddr="/ip4/203.0.113.1/tcp/4001",
        min_price=10,  # minimum stroops per pin
    )

    # 2. Update settings (change min_price only)
    # update_pinner(secret_key, min_price=20)

    # 3. Collect a pin from slot 0
    # collect_pin(secret_key, slot_id=0)

    # 4. Flag a bad pinner
    # flag_pinner(secret_key, target_address="GXXXXXXX...")

    # 5. Leave and reclaim stake
    # leave_as_pinner(secret_key)
