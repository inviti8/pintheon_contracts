#!/usr/bin/env python3
"""
Example 10: Pin Service Factory - Read-Only Queries

Demonstrates how to query the hvym_pin_service_factory contract to discover
deployed pin service instances. These operations are free and don't require
a funded account.

The factory contract manages multiple hvym_pin_service instances:
    - Tracks all deployed instances in a registry
    - Provides routing to instances with available slots
    - Admin-only deployment of new instances

Covers:
    - Get factory admin
    - List all deployed instances
    - Get instance count
    - Get instance by index
    - Route to an available instance (finds one with open slots)

Prerequisites:
    pip install stellar-sdk
"""

import sys
sys.path.insert(0, '..')

from stellar_sdk import SorobanServer

from hvym_pin_service_factory.bindings import Client as FactoryClient
from hvym_pin_service.bindings import Client as PinServiceClient
from config import RPC_URL, CONTRACTS, NETWORK_PASSPHRASE, stroops_to_xlm


def query_factory_admin():
    """Query the factory's admin address."""
    print("=" * 60)
    print("Pin Service Factory - Admin")
    print("=" * 60)

    client = FactoryClient(
        contract_id=CONTRACTS["hvym_pin_service_factory"],
        rpc_url=RPC_URL,
        network_passphrase=NETWORK_PASSPHRASE,
    )

    try:
        result = client.get_admin()
        result.simulate()
        admin = result.result()
        print(f"  Admin Address: {admin}")
    except Exception as e:
        print(f"  Error querying admin: {e}")


def query_instance_count():
    """Query the total number of deployed pin service instances."""
    print("\n" + "=" * 60)
    print("Pin Service Factory - Instance Count")
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
        print(f"  Deployed Instances: {count}")
        return count
    except Exception as e:
        print(f"  Error querying instance count: {e}")
        return 0


def query_all_instances():
    """Query all deployed pin service instance addresses."""
    print("\n" + "=" * 60)
    print("Pin Service Factory - All Instances")
    print("=" * 60)

    client = FactoryClient(
        contract_id=CONTRACTS["hvym_pin_service_factory"],
        rpc_url=RPC_URL,
        network_passphrase=NETWORK_PASSPHRASE,
    )

    try:
        result = client.get_instances()
        result.simulate()
        instances = result.result()

        if not instances:
            print("  No instances deployed yet.")
            return []

        print(f"  Found {len(instances)} instance(s):\n")
        for i, addr in enumerate(instances):
            print(f"  [{i}] {addr}")

        return instances
    except Exception as e:
        print(f"  Error querying instances: {e}")
        return []


def query_instance_at(index: int):
    """Query a specific instance by index."""
    print("\n" + "=" * 60)
    print(f"Pin Service Factory - Instance at Index {index}")
    print("=" * 60)

    client = FactoryClient(
        contract_id=CONTRACTS["hvym_pin_service_factory"],
        rpc_url=RPC_URL,
        network_passphrase=NETWORK_PASSPHRASE,
    )

    try:
        result = client.get_instance_at(index)
        result.simulate()
        addr = result.result()
        print(f"  Instance Address: {addr}")
        return addr
    except Exception as e:
        print(f"  Error querying instance at index {index}: {e}")
        return None


def route_to_available():
    """Find an instance with available slots.

    This performs cross-contract calls to check each instance's
    has_available_slots() method and returns the first one that
    has open slots.
    """
    print("\n" + "=" * 60)
    print("Pin Service Factory - Route to Available Instance")
    print("=" * 60)

    client = FactoryClient(
        contract_id=CONTRACTS["hvym_pin_service_factory"],
        rpc_url=RPC_URL,
        network_passphrase=NETWORK_PASSPHRASE,
    )

    try:
        # Check up to 10 instances
        result = client.route_to_available(max_check=10)
        result.simulate()
        available = result.result()

        if available:
            print(f"  Found available instance: {available}")
            return available
        else:
            print("  No instances with available slots found.")
            return None
    except Exception as e:
        print(f"  Error routing to available: {e}")
        return None


def query_instance_details(instance_addr: str):
    """Query details of a specific pin service instance.

    Uses the hvym_pin_service bindings to query the deployed instance.
    """
    print("\n" + "=" * 60)
    print(f"Pin Service Instance Details")
    print(f"  {instance_addr}")
    print("=" * 60)

    client = PinServiceClient(
        contract_id=instance_addr,
        rpc_url=RPC_URL,
        network_passphrase=NETWORK_PASSPHRASE,
    )

    # Query various config values
    try:
        result = client.symbol()
        result.simulate()
        print(f"  Symbol:          {result.result()}")
    except Exception as e:
        print(f"  Error querying symbol: {e}")

    try:
        result = client.pin_fee()
        result.simulate()
        fee = result.result()
        print(f"  Pin Fee:         {fee} stroops ({stroops_to_xlm(fee):.7f} XLM)")
    except Exception as e:
        print(f"  Error querying pin_fee: {e}")

    try:
        result = client.join_fee()
        result.simulate()
        fee = result.result()
        print(f"  Join Fee:        {fee} stroops ({stroops_to_xlm(fee):.7f} XLM)")
    except Exception as e:
        print(f"  Error querying join_fee: {e}")

    try:
        result = client.has_available_slots()
        result.simulate()
        print(f"  Has Slots:       {result.result()}")
    except Exception as e:
        print(f"  Error checking slots: {e}")

    try:
        result = client.get_pinner_count()
        result.simulate()
        print(f"  Pinner Count:    {result.result()}")
    except Exception as e:
        print(f"  Error querying pinner count: {e}")


if __name__ == "__main__":
    # Query factory info
    query_factory_admin()
    count = query_instance_count()

    # List all instances
    instances = query_all_instances()

    # Query specific instance by index (if any exist)
    if count > 0:
        query_instance_at(0)

    # Try to find an available instance
    available = route_to_available()

    # If we found instances, query details of the first one
    if instances:
        query_instance_details(str(instances[0]))
