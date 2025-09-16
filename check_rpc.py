#!/usr/bin/env python3
import sys
import json
import requests

def check_rpc_health(rpc_url: str):
    """Sends a 'getHealth' request to a Soroban RPC endpoint and checks the response."""
    headers = {'Content-Type': 'application/json'}
    payload = {
        "jsonrpc": "2.0",
        "method": "getHealth",
        "id": 1
    }

    print(f"Checking endpoint: {rpc_url}...")

    try:
        response = requests.post(rpc_url, data=json.dumps(payload), headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        response_json = response.json()

        if response_json.get("error"):
            error_message = response_json["error"].get("message", "Unknown error")
            print(f"❌ Endpoint returned an error: {error_message}")
            return False

        result = response_json.get("result", {})
        status = result.get("status")

        if status == "healthy":
            print(f"✅ Endpoint is healthy.")
            return True
        else:
            print(f"❌ Endpoint is not healthy. Status: {status}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ Connection failed: {e}")
        return False
    except json.JSONDecodeError:
        print("❌ Failed to decode JSON response. The endpoint may not be a valid RPC server.")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_rpc.py <rpc_url>")
        sys.exit(1)

    url_to_check = sys.argv[1]
    if not check_rpc_health(url_to_check):
        sys.exit(1)
