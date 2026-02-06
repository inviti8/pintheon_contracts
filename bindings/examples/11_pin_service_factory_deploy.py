#!/usr/bin/env python3
"""
Example 11: Pin Service Factory - Deploy New Instance (Admin Only)

Demonstrates how to deploy a new hvym_pin_service instance through the
factory contract. This is an ADMIN-ONLY operation that requires:
    1. The caller to be the factory admin
    2. A funded account to pay for the transaction

The factory contract:
    - Embeds the hvym_pin_service WASM
    - Uploads the WASM and deploys a new instance
    - Tracks all deployed instances in a registry
    - Generates unique salts for each deployment

Prerequisites:
    pip install stellar-sdk
    A funded Stellar account that is the factory admin

WARNING: This example will deploy a real contract on testnet!
         Only run this if you are the factory admin and want to deploy.
"""

import sys
sys.path.insert(0, '..')

from stellar_sdk import Keypair

from hvym_pin_service_factory.bindings import Client as FactoryClient
from hvym_pin_service.bindings import Client as PinServiceClient
from config import RPC_URL, CONTRACTS, NETWORK_PASSPHRASE, XLM_TOKEN, xlm_to_stroops, stroops_to_xlm


def deploy_new_instance(
    admin_secret: str,
    pin_fee_xlm: float = 1.0,
    join_fee_xlm: float = 5.0,
    min_pin_qty: int = 3,
    min_offer_price_xlm: float = 1.0,
    pinner_stake_xlm: float = 100.0,
    max_cycles: int = 60,
    flag_threshold: int = 3,
):
    """Deploy a new hvym_pin_service instance through the factory.

    Args:
        admin_secret: Secret key of the factory admin account
        pin_fee_xlm: Fee charged per pin request (in XLM)
        join_fee_xlm: Fee for pinners to join (in XLM)
        min_pin_qty: Minimum number of pins required per request
        min_offer_price_xlm: Minimum offer price per pin (in XLM)
        pinner_stake_xlm: Stake required from pinners (in XLM)
        max_cycles: Number of epochs before slot expiration
        flag_threshold: Number of flags before pinner removal

    Returns:
        The contract address of the newly deployed instance, or None on failure
    """
    print("=" * 60)
    print("Deploying New Pin Service Instance")
    print("=" * 60)

    # Convert XLM to stroops
    pin_fee = xlm_to_stroops(pin_fee_xlm)
    join_fee = xlm_to_stroops(join_fee_xlm)
    min_offer_price = xlm_to_stroops(min_offer_price_xlm)
    pinner_stake = xlm_to_stroops(pinner_stake_xlm)

    print(f"\nConfiguration:")
    print(f"  Pin Fee:         {pin_fee} stroops ({pin_fee_xlm} XLM)")
    print(f"  Join Fee:        {join_fee} stroops ({join_fee_xlm} XLM)")
    print(f"  Min Pin Qty:     {min_pin_qty}")
    print(f"  Min Offer Price: {min_offer_price} stroops ({min_offer_price_xlm} XLM)")
    print(f"  Pinner Stake:    {pinner_stake} stroops ({pinner_stake_xlm} XLM)")
    print(f"  Max Cycles:      {max_cycles} epochs")
    print(f"  Flag Threshold:  {flag_threshold} flags")
    print(f"  Pay Token:       {XLM_TOKEN}")

    # Set up keypair and client
    keypair = Keypair.from_secret(admin_secret)
    print(f"\nAdmin Account: {keypair.public_key}")

    client = FactoryClient(
        contract_id=CONTRACTS["hvym_pin_service_factory"],
        rpc_url=RPC_URL,
        network_passphrase=NETWORK_PASSPHRASE,
    )

    try:
        print("\nSubmitting deploy transaction...")

        # Call deploy with all parameters
        result = client.deploy(
            pin_fee=pin_fee,
            join_fee=join_fee,
            min_pin_qty=min_pin_qty,
            min_offer_price=min_offer_price,
            pinner_stake=pinner_stake,
            pay_token=XLM_TOKEN,
            max_cycles=max_cycles,
            flag_threshold=flag_threshold,
            source=keypair.public_key,
            signer=keypair,
        )

        # Sign and submit
        result.sign_and_submit()

        # Get the deployed contract address
        deployed_address = result.result()
        print(f"\n  SUCCESS! New instance deployed at:")
        print(f"  {deployed_address}")

        return deployed_address

    except Exception as e:
        print(f"\n  FAILED: {e}")
        return None


def verify_deployment(instance_addr: str):
    """Verify that a newly deployed instance is working correctly."""
    print("\n" + "=" * 60)
    print("Verifying Deployment")
    print("=" * 60)

    client = PinServiceClient(
        contract_id=instance_addr,
        rpc_url=RPC_URL,
        network_passphrase=NETWORK_PASSPHRASE,
    )

    # Verify symbol
    try:
        result = client.symbol()
        result.simulate()
        symbol = result.result()
        print(f"  Symbol:      {symbol}")
        assert str(symbol) == "HVYMPIN", f"Expected HVYMPIN, got {symbol}"
    except Exception as e:
        print(f"  Error verifying symbol: {e}")
        return False

    # Verify has_available_slots
    try:
        result = client.has_available_slots()
        result.simulate()
        available = result.result()
        print(f"  Has Slots:   {available}")
        assert available == True, "New instance should have available slots"
    except Exception as e:
        print(f"  Error checking slots: {e}")
        return False

    # Verify pinner count starts at 0
    try:
        result = client.get_pinner_count()
        result.simulate()
        count = result.result()
        print(f"  Pinners:     {count}")
        assert count == 0, "New instance should have 0 pinners"
    except Exception as e:
        print(f"  Error checking pinner count: {e}")
        return False

    print("\n  All verifications passed!")
    return True


def check_factory_registry():
    """Check the factory registry after deployment."""
    print("\n" + "=" * 60)
    print("Factory Registry After Deployment")
    print("=" * 60)

    client = FactoryClient(
        contract_id=CONTRACTS["hvym_pin_service_factory"],
        rpc_url=RPC_URL,
        network_passphrase=NETWORK_PASSPHRASE,
    )

    try:
        result = client.get_instance_count()
        result.simulate()
        count = result.result()
        print(f"  Total Instances: {count}")

        result = client.get_instances()
        result.simulate()
        instances = result.result()

        print(f"\n  Registered Instances:")
        for i, addr in enumerate(instances):
            print(f"    [{i}] {addr}")

    except Exception as e:
        print(f"  Error querying registry: {e}")


if __name__ == "__main__":
    print("\n" + "!" * 60)
    print("WARNING: This will deploy a real contract on testnet!")
    print("!" * 60 + "\n")

    # To actually deploy, uncomment below and provide your admin secret key
    # Make sure your account is:
    #   1. The factory admin
    #   2. Funded with enough XLM for the transaction

    """
    ADMIN_SECRET = "SXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

    deployed_addr = deploy_new_instance(
        admin_secret=ADMIN_SECRET,
        pin_fee_xlm=1.0,         # 1 XLM per pin request
        join_fee_xlm=5.0,        # 5 XLM for pinners to join
        min_pin_qty=3,           # Minimum 3 pins per request
        min_offer_price_xlm=1.0, # Minimum 1 XLM per pin
        pinner_stake_xlm=100.0,  # 100 XLM stake required
        max_cycles=60,           # 60 epochs before expiration
        flag_threshold=3,        # 3 flags to remove pinner
    )

    if deployed_addr:
        verify_deployment(str(deployed_addr))
        check_factory_registry()
    """

    # For now, just show the current registry state
    print("Current factory state (read-only):\n")
    check_factory_registry()
