#!/usr/bin/env python3
"""
Extract contract address from Stellar Expert API transaction data.
"""

import requests
import base64
import json
from stellar_sdk import xdr

def extract_contract_address_from_stellar_expert(tx_hash, network="testnet"):
    """Extract contract address from Stellar Expert API."""
    try:
        # Get transaction data from Stellar Expert API
        url = f"https://api.stellar.expert/explorer/{network}/tx/{tx_hash}"
        response = requests.get(url)
        
        if response.status_code != 200:
            print(f"Failed to fetch transaction: {response.status_code}")
            return None
            
        tx_data = response.json()
        
        # Decode the result XDR to find contract address
        result_xdr = tx_data.get('result')
        if not result_xdr:
            print("No result XDR found in transaction")
            return None
            
        try:
            # Decode the XDR result
            decoded_result = xdr.TransactionResult.from_xdr(result_xdr)
            
            # Look for contract creation in the result
            if hasattr(decoded_result, 'result') and hasattr(decoded_result.result, 'results'):
                for op_result in decoded_result.result.results:
                    if hasattr(op_result, 'tr') and hasattr(op_result.tr, 'invoke_host_function_result'):
                        invoke_result = op_result.tr.invoke_host_function_result
                        if hasattr(invoke_result, 'success') and invoke_result.success:
                            # Extract contract address from the success result
                            if hasattr(invoke_result.success, 'return_value'):
                                return_val = invoke_result.success.return_value
                                if hasattr(return_val, 'address'):
                                    contract_id = return_val.address.contract_id
                                    return contract_id.to_xdr()
            
            print("Could not find contract address in XDR result")
            return None
            
        except Exception as e:
            print(f"Error decoding XDR: {e}")
            return None
            
    except Exception as e:
        print(f"Error fetching transaction data: {e}")
        return None

def simple_contract_address_extraction(tx_hash, network="testnet"):
    """Simple approach to extract contract address from transaction metadata."""
    try:
        url = f"https://api.stellar.expert/explorer/{network}/tx/{tx_hash}"
        response = requests.get(url)
        
        if response.status_code != 200:
            return None
            
        tx_data = response.json()
        
        # Look for contract address in the metadata
        meta_xdr = tx_data.get('meta')
        if meta_xdr:
            # Decode base64 metadata
            meta_bytes = base64.b64decode(meta_xdr)
            
            # Look for contract address pattern (starts with 'C' and is 56 chars)
            # This is a simple heuristic approach
            meta_hex = meta_bytes.hex()
            
            # Contract addresses in Stellar start with 'C' which is 0x43 in hex
            # Look for patterns that might be contract addresses
            print(f"Transaction metadata (first 200 bytes): {meta_hex[:400]}")
            
        return None
        
    except Exception as e:
        print(f"Error in simple extraction: {e}")
        return None

if __name__ == "__main__":
    # Test with the known deployment transaction
    tx_hash = "a7767f81959a5267f72eb8357c9472f3ea29771654131c5747af2e2f36bfe510"
    
    print(f"Extracting contract address from transaction: {tx_hash}")
    
    # Try simple extraction first
    simple_contract_address_extraction(tx_hash)
    
    # Try XDR decoding approach
    address = extract_contract_address_from_stellar_expert(tx_hash)
    if address:
        print(f"Contract address: {address}")
    else:
        print("Could not extract contract address")
