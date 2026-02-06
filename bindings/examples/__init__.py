"""
Pintheon Contract Bindings Examples

This package contains examples demonstrating how to interact with
Pintheon smart contracts using the generated Python bindings.

Examples:
---------

HVYM Collective:
    01_basic_queries.py     - Read-only queries for collective state
    02_join_collective.py   - Joining the collective as a member
    03_async_example.py     - Async/await usage patterns
    04_publish_file.py      - Publishing files to the collective

HVYM Roster:
    05_roster_example.py    - Roster contract interactions

HVYM Pin Service:
    06_pin_service_queries.py   - Read-only queries (fees, slots, pinners)
    07_pin_service_pinner.py    - Pinner operations (join, update, leave)
    08_pin_service_publisher.py - Publisher operations (create_pin, collect)
    09_pin_service_admin.py     - Admin operations (fees, flags, withdrawals)

HVYM Pin Service Factory:
    10_pin_service_factory_queries.py - Query deployed instances, routing
    11_pin_service_factory_deploy.py  - Deploy new pin service instances (admin)

Configuration:
    config.py               - Network settings and contract addresses

Prerequisites:
    pip install stellar-sdk

Usage:
    cd bindings/examples
    python 01_basic_queries.py
"""
