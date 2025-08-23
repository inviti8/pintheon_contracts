#!/usr/bin/env python3
"""
Extract contract address from successful deployment transaction.
"""

import subprocess
import re

def get_contract_address_from_deployment(wasm_hash, source_account="test-deployer", network="testnet"):
    """Get contract address by simulating deployment with same parameters."""
    try:
        # Use the same deployment command but with simulation to get the contract address
        cmd = f"stellar contract deploy --wasm-hash {wasm_hash} --network {network} --source-account {source_account} --build-only -- --admin {source_account}"
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Now simulate the transaction to get the contract address
            sim_cmd = f"echo '{result.stdout.strip()}' | stellar tx simulate --network {network}"
            sim_result = subprocess.run(sim_cmd, shell=True, capture_output=True, text=True)
            
            if sim_result.returncode == 0:
                # Extract contract address from simulation output
                # The contract address should be in the XDR response
                print("Simulation successful, checking for contract address...")
                print(f"Simulation output: {sim_result.stdout}")
                
                # Try to get the address using a different approach
                addr_cmd = f"stellar contract id wasm {wasm_hash} --source-account {source_account}"
                addr_result = subprocess.run(addr_cmd, shell=True, capture_output=True, text=True)
                
                if addr_result.returncode == 0:
                    contract_address = addr_result.stdout.strip()
                    if contract_address and len(contract_address) == 56 and contract_address.startswith('C'):
                        return contract_address
                
                return None
        
        return None
        
    except Exception as e:
        print(f"Error getting contract address: {e}")
        return None

if __name__ == "__main__":
    # Get the contract address for the deployed Opus Token
    opus_wasm_hash = "c68ac2a6caad09df0801c3047d8a9e55f6b9064b3a811b63bcabcbb0a298eecb"
    
    address = get_contract_address_from_deployment(opus_wasm_hash)
    if address:
        print(f"Opus Token contract address: {address}")
    else:
        print("Could not determine contract address")
