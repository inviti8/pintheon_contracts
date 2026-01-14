#!/usr/bin/env python3
"""
Temporary test file to verify roster bindings work.

Available methods in RosterClient:
- join(caller, name, canon)
- remove(admin_caller, member_to_remove)
- symbol()
- is_admin(address)
- join_fee()
- withdraw(caller, recipient)
- add_admin(caller, new_admin)
- is_member(caller)
- member_paid(caller)
- get_canon(member_address) -> Option<String>  # NEW
- remove_admin(caller, admin_to_remove)
- update_canon(caller, member_address, new_canon)
- fund_contract(caller, fund_amount)
- get_admin_list()
- update_join_fee(caller, new_fee)
"""

import sys
sys.path.insert(0, '..')

import time
from stellar_sdk import Keypair, Server, SorobanServer

# Import the generated bindings
from hvym_roster.bindings import Client as RosterClient

from config import RPC_URL, CONTRACTS

# Horizon server for account queries
HORIZON_URL = "https://horizon-testnet.stellar.org"


def submit_and_wait(tx, rpc_url: str, timeout: int = 30) -> dict:
    """
    Submit a signed transaction and wait for it to complete.

    Returns a dict with:
        - success: bool
        - hash: transaction hash
        - status: final status string
        - result: result data if available
        - error: error message if failed
    """
    # Ensure transaction is signed
    tx.sign()

    server = SorobanServer(rpc_url)

    # Submit the transaction
    send_response = server.send_transaction(tx.built_transaction)

    result = {
        "success": False,
        "hash": send_response.hash,
        "status": str(send_response.status),
        "result": None,
        "error": None
    }

    if "ERROR" in str(send_response.status):
        result["error"] = getattr(send_response, 'error_result_xdr', 'Unknown error')
        return result

    # Poll for transaction completion
    for i in range(timeout):
        time.sleep(1)
        get_response = server.get_transaction(send_response.hash)
        status_str = str(get_response.status)

        if "SUCCESS" in status_str:
            result["success"] = True
            result["status"] = status_str
            if hasattr(get_response, 'result_value'):
                result["result"] = get_response.result_value
            return result
        elif "FAILED" in status_str:
            result["status"] = status_str
            result["error"] = getattr(get_response, 'result_xdr', 'Transaction failed')
            return result
        elif "NOT_FOUND" not in status_str:
            result["status"] = status_str
            break

    result["error"] = "Transaction timed out"
    return result

# Test account for joining
SECRET_KEY = "SD6QCVHJLSZO6G3K2LGOXTEWBBF6ROK24UKPA4D6BOE6U7XXIMGNK4E4"
NETWORK_PASSPHRASE = "Test SDF Network ; September 2015"


def check_account_balance(public_key: str) -> float:
    """Check the account balance on testnet."""
    print("\n" + "=" * 60)
    print("Account Balance Check")
    print("=" * 60)

    try:
        server = Server(HORIZON_URL)
        account = server.accounts().account_id(public_key).call()

        for balance in account['balances']:
            if balance['asset_type'] == 'native':
                xlm_balance = float(balance['balance'])
                print(f"  XLM Balance: {xlm_balance:.7f} XLM")
                return xlm_balance

        return 0.0
    except Exception as e:
        print(f"  Error checking balance: {e}")
        print("  Account may not exist or be unfunded.")
        return 0.0


def test_read_operations(client: RosterClient, public_key: str):
    """Test read-only operations."""
    print("=" * 60)
    print("Read-Only Tests")
    print("=" * 60)

    # Test 1: Query symbol
    print("\nTest 1: Query symbol...")
    try:
        result = client.symbol()
        result.simulate()
        symbol = result.result()
        print(f"  Symbol: {symbol}")
    except Exception as e:
        print(f"  Error: {e}")

    # Test 2: Query join fee
    print("\nTest 2: Query join fee...")
    try:
        result = client.join_fee()
        result.simulate()
        fee = result.result()
        print(f"  Join Fee: {fee} stroops ({fee / 10_000_000} XLM)")
    except Exception as e:
        print(f"  Error: {e}")

    # Test 3: Check membership
    print(f"\nTest 3: Check membership for test account...")
    try:
        result = client.is_member(public_key)
        result.simulate()
        is_member = result.result()
        print(f"  Is Member: {is_member}")
    except Exception as e:
        print(f"  Error: {e}")
        is_member = False

    # Test 4: Check admin status
    print(f"\nTest 4: Check admin status for test account...")
    try:
        result = client.is_admin(public_key)
        result.simulate()
        is_admin = result.result()
        print(f"  Is Admin: {is_admin}")
    except Exception as e:
        print(f"  Error: {e}")

    # Test 5: Get admin list
    print(f"\nTest 5: Get admin list...")
    try:
        result = client.get_admin_list()
        result.simulate()
        admins = result.result()
        print(f"  Admin List ({len(admins)} admins):")
        for admin in admins:
            print(f"    - {admin}")
    except Exception as e:
        print(f"  Error: {e}")

    return is_member


def test_join_roster(client: RosterClient, keypair: Keypair):
    """Test joining the roster."""
    public_key = keypair.public_key

    print("\n" + "=" * 60)
    print("Join Roster Test")
    print("=" * 60)

    # Check if already a member
    try:
        result = client.is_member(public_key)
        result.simulate()
        if result.result():
            print("  Already a member, skipping join test")
            return True
    except Exception as e:
        print(f"  Error checking membership: {e}")

    # Join the roster
    print("\nJoining roster...")
    print(f"  Name: TestUser")
    print(f"  Canon: Initial canon data")

    try:
        tx = client.join(
            caller=public_key,
            name=b"TestUser",
            canon=b"Initial canon data",
            source=public_key,
            signer=keypair,
            base_fee=100,
        )

        # Simulate first
        print("  Simulating transaction...")
        tx.simulate()
        print("  Simulation successful!")

        # Submit and wait for result using helper
        print("  Submitting transaction...")
        result = submit_and_wait(tx, RPC_URL)

        print(f"  Transaction hash: {result['hash']}")
        print(f"  Status: {result['status']}")

        if result['success']:
            print("  Successfully joined the roster!")
            return True
        else:
            print(f"  Join failed: {result['error']}")
            return False

    except Exception as e:
        print(f"  Error joining roster: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_update_canon(client: RosterClient, keypair: Keypair):
    """Test updating the canon for the member."""
    public_key = keypair.public_key

    print("\n" + "=" * 60)
    print("Update Canon Test")
    print("=" * 60)

    # First verify membership
    try:
        result = client.is_member(public_key)
        result.simulate()
        if not result.result():
            print("  Not a member, cannot update canon")
            return False
    except Exception as e:
        print(f"  Error checking membership: {e}")
        return False

    # Update canon
    new_canon = b'{"version": "1.0", "updated": true, "notes": "Updated via Python bindings test"}'
    print(f"\nUpdating canon to: {new_canon.decode('utf-8')}")

    try:
        tx = client.update_canon(
            caller=public_key,
            member_address=public_key,
            new_canon=new_canon,
            source=public_key,
            signer=keypair,
            base_fee=100,
        )

        # Simulate first
        print("  Simulating transaction...")
        tx.simulate()
        print("  Simulation successful!")

        # Submit and wait for result using helper
        print("  Submitting transaction...")
        result = submit_and_wait(tx, RPC_URL)

        print(f"  Transaction hash: {result['hash']}")
        print(f"  Status: {result['status']}")

        if result['success']:
            print("  Successfully updated canon!")
            return True
        else:
            print(f"  Update failed: {result['error']}")
            return False

    except Exception as e:
        print(f"  Error updating canon: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_member_paid(client: RosterClient, public_key: str):
    """Test checking how much a member has paid."""
    print("\n" + "=" * 60)
    print("Member Paid Test")
    print("=" * 60)

    try:
        result = client.member_paid(public_key)
        result.simulate()
        paid = result.result()
        print(f"  Amount Paid: {paid} stroops ({paid / 10_000_000} XLM)")
        return paid
    except Exception as e:
        print(f"  Error: {e}")
        return 0


def main():
    # Create keypair
    keypair = Keypair.from_secret(SECRET_KEY)
    public_key = keypair.public_key

    print("=" * 60)
    print("Roster Bindings Test")
    print("=" * 60)
    print(f"Test Account: {public_key}")
    print(f"Roster Contract: {CONTRACTS['hvym_roster']}")
    print(f"RPC URL: {RPC_URL}")

    # Check account balance first
    balance = check_account_balance(public_key)

    # Create client
    client = RosterClient(
        contract_id=CONTRACTS["hvym_roster"],
        rpc_url=RPC_URL,
        network_passphrase=NETWORK_PASSPHRASE,
    )

    # Run read-only tests first
    is_member = test_read_operations(client, public_key)

    # Get the join fee to compare with balance
    try:
        result = client.join_fee()
        result.simulate()
        join_fee_xlm = result.result() / 10_000_000
        print(f"\nRequired balance to join: {join_fee_xlm} XLM + transaction fees")
        print(f"Current balance: {balance} XLM")

        if balance < join_fee_xlm + 1:  # +1 XLM for transaction fees
            print(f"\n⚠️  WARNING: Account balance ({balance} XLM) may be insufficient!")
            print(f"    Need at least {join_fee_xlm + 1} XLM to join.")
            print("    Fund the account with: stellar keys fund <key-name> --network testnet")
    except Exception as e:
        print(f"Error checking join fee: {e}")

    # If not a member, try to join
    if not is_member:
        join_success = test_join_roster(client, keypair)
        if join_success:
            # Verify membership after joining
            print("\nVerifying membership after join...")
            result = client.is_member(public_key)
            result.simulate()
            print(f"  Is Member: {result.result()}")

            # Test update canon (requires membership)
            test_update_canon(client, keypair)

            # Check member paid amount
            test_member_paid(client, public_key)
    else:
        # Already a member, can test update and member_paid
        test_update_canon(client, keypair)
        test_member_paid(client, public_key)

    print("\n" + "=" * 60)
    print("All tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
