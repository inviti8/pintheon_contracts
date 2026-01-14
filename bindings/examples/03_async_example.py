#!/usr/bin/env python3
"""
Example 3: Async Operations

This example demonstrates how to use the async client for
concurrent contract queries. Useful for applications that
need to query multiple contracts or make many queries efficiently.

Prerequisites:
    pip install stellar-sdk aiohttp
"""

import sys
sys.path.insert(0, '..')

import asyncio
from stellar_sdk import SorobanServerAsync

# Import the async client from generated bindings
from hvym_collective.bindings import ClientAsync as CollectiveClientAsync
from hvym_roster.bindings import ClientAsync as RosterClientAsync

from config import RPC_URL, CONTRACTS


async def query_collective_async():
    """Query collective info using async client."""
    print("=" * 50)
    print("Async: Querying hvym_collective")
    print("=" * 50)

    async with SorobanServerAsync(RPC_URL) as server:
        client = CollectiveClientAsync(
            contract_id=CONTRACTS["hvym_collective"],
            rpc_url=RPC_URL,
        )

        # Query multiple values concurrently
        tasks = [
            client.symbol(),
            client.join_fee(),
            client.mint_fee(),
            client.is_launched(),
        ]

        # Wait for all simulations to complete
        results = await asyncio.gather(*[t for t in tasks], return_exceptions=True)

        # Process results
        labels = ["Symbol", "Join Fee", "Mint Fee", "Is Launched"]
        for label, result in zip(labels, results):
            if isinstance(result, Exception):
                print(f"{label}: Error - {result}")
            else:
                try:
                    await result.simulate()
                    value = result.result()
                    if label in ["Join Fee", "Mint Fee"]:
                        print(f"{label}: {value} stroops ({value / 10_000_000} XLM)")
                    else:
                        print(f"{label}: {value}")
                except Exception as e:
                    print(f"{label}: Error - {e}")


async def check_multiple_members(addresses: list):
    """Check membership status for multiple addresses concurrently."""
    print("\n" + "=" * 50)
    print(f"Async: Checking {len(addresses)} members")
    print("=" * 50)

    client = CollectiveClientAsync(
        contract_id=CONTRACTS["hvym_collective"],
        rpc_url=RPC_URL,
    )

    async def check_one(address):
        try:
            result = await client.is_member(address)
            await result.simulate()
            return address, result.result()
        except Exception as e:
            return address, f"Error: {e}"

    # Check all addresses concurrently
    tasks = [check_one(addr) for addr in addresses]
    results = await asyncio.gather(*tasks)

    for address, is_member in results:
        short_addr = f"{address[:8]}...{address[-8:]}"
        print(f"{short_addr}: {'Member' if is_member is True else is_member}")


async def parallel_contract_queries():
    """Query multiple contracts in parallel."""
    print("\n" + "=" * 50)
    print("Async: Parallel contract queries")
    print("=" * 50)

    collective_client = CollectiveClientAsync(
        contract_id=CONTRACTS["hvym_collective"],
        rpc_url=RPC_URL,
    )

    roster_client = RosterClientAsync(
        contract_id=CONTRACTS["hvym_roster"],
        rpc_url=RPC_URL,
    )

    async def get_collective_symbol():
        result = await collective_client.symbol()
        await result.simulate()
        return "Collective Symbol", result.result()

    async def get_roster_symbol():
        result = await roster_client.symbol()
        await result.simulate()
        return "Roster Symbol", result.result()

    async def get_collective_fee():
        result = await collective_client.join_fee()
        await result.simulate()
        return "Collective Join Fee", result.result()

    async def get_roster_fee():
        result = await roster_client.join_fee()
        await result.simulate()
        return "Roster Join Fee", result.result()

    # Run all queries in parallel
    tasks = [
        get_collective_symbol(),
        get_roster_symbol(),
        get_collective_fee(),
        get_roster_fee(),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            print(f"Error: {result}")
        else:
            label, value = result
            if "Fee" in label:
                print(f"{label}: {value} stroops ({value / 10_000_000} XLM)")
            else:
                print(f"{label}: {value}")


async def main():
    """Run all async examples."""
    await query_collective_async()

    # Example addresses to check (replace with real addresses)
    test_addresses = [
        "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
        "GBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
    ]
    await check_multiple_members(test_addresses)

    await parallel_contract_queries()


if __name__ == "__main__":
    asyncio.run(main())
