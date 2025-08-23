#!/usr/bin/env python3
"""
Robust deployment script with enhanced error handling for XDR processing issues.
"""

import subprocess
import json
import time
import sys
import os
from pathlib import Path

def run_command(cmd, cwd=None, capture_output=True):
    """Run command with better error handling."""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            timeout=300  # 5 minute timeout
        )
        return result
    except subprocess.TimeoutExpired:
        print(f"❌ Command timed out: {cmd}")
        return None
    except Exception as e:
        print(f"❌ Command failed: {cmd}, Error: {e}")
        return None

def wait_for_transaction(tx_hash, network="testnet", max_retries=30):
    """Wait for transaction to be processed."""
    for i in range(max_retries):
        print(f"⏳ Checking transaction status... ({i+1}/{max_retries})")
        
        # Check transaction status
        result = run_command(f"stellar tx info {tx_hash} --network {network}")
        if result and result.returncode == 0:
            print(f"✅ Transaction {tx_hash} confirmed")
            return True
            
        time.sleep(2)
    
    print(f"❌ Transaction {tx_hash} not confirmed after {max_retries} retries")
    return False

def deploy_contract_robust(contract_name, wasm_path, constructor_args=None, network="testnet", source_account="test-deployer"):
    """Deploy contract with robust error handling."""
    print(f"\n🚀 Deploying {contract_name}...")
    
    # Step 1: Upload WASM with retries
    print("📤 Uploading WASM...")
    upload_attempts = 3
    wasm_hash = None
    
    for attempt in range(upload_attempts):
        print(f"Upload attempt {attempt + 1}/{upload_attempts}")
        
        # Try upload
        result = run_command(
            f"stellar contract install --wasm {wasm_path} --network {network} --source-account {source_account}"
        )
        
        if result and result.returncode == 0:
            # Extract WASM hash from output
            output_lines = result.stdout.strip().split('\n')
            for line in output_lines:
                if len(line.strip()) == 64 and all(c in '0123456789abcdef' for c in line.strip()):
                    wasm_hash = line.strip()
                    break
            
            if wasm_hash:
                print(f"✅ WASM uploaded successfully: {wasm_hash}")
                break
        
        if attempt < upload_attempts - 1:
            print(f"⏳ Upload failed, retrying in 5 seconds...")
            time.sleep(5)
    
    if not wasm_hash:
        print("❌ Failed to upload WASM after all attempts")
        return None
    
    # Step 2: Deploy contract with retries
    print("🚀 Deploying contract...")
    deploy_attempts = 3
    contract_address = None
    
    for attempt in range(deploy_attempts):
        print(f"Deploy attempt {attempt + 1}/{deploy_attempts}")
        
        # Build deploy command
        deploy_cmd = f"stellar contract deploy --wasm-hash {wasm_hash} --network {network} --source-account {source_account}"
        
        if constructor_args:
            deploy_cmd += f" -- {constructor_args}"
        
        # Try deploy with simulation first
        print("🧪 Simulating deployment...")
        sim_result = run_command(deploy_cmd + " --sim-only")
        
        if sim_result and sim_result.returncode == 0:
            print("✅ Simulation successful")
            
            # Now try actual deployment
            result = run_command(deploy_cmd)
            
            if result and result.returncode == 0:
                # Extract contract address from output
                output_lines = result.stdout.strip().split('\n')
                for line in output_lines:
                    if line.startswith('C') and len(line.strip()) == 56:
                        contract_address = line.strip()
                        break
                
                if contract_address:
                    print(f"✅ Contract deployed successfully: {contract_address}")
                    return {
                        'name': contract_name,
                        'address': contract_address,
                        'wasm_hash': wasm_hash
                    }
            else:
                print(f"❌ Deploy failed: {result.stderr if result else 'Unknown error'}")
        else:
            print(f"❌ Simulation failed: {sim_result.stderr if sim_result else 'Unknown error'}")
        
        if attempt < deploy_attempts - 1:
            print(f"⏳ Deploy failed, retrying in 10 seconds...")
            time.sleep(10)
    
    print("❌ Failed to deploy contract after all attempts")
    return None

def main():
    """Main deployment function."""
    print("🔧 Robust Contract Deployment Script")
    
    # Check if we're in the right directory
    if not os.path.exists("opus_token"):
        print("❌ Please run this script from the project root directory")
        sys.exit(1)
    
    # Ensure test account exists and is funded
    print("💰 Setting up test account...")
    run_command("stellar keys generate --global --network testnet test-deployer --fund")
    
    # Build contracts first
    print("🔨 Building contracts...")
    contracts_to_build = [
        "opus_token",
        "hvym-collective",
        "hvym-collective-factory"
    ]
    
    for contract in contracts_to_build:
        if os.path.exists(contract):
            print(f"Building {contract}...")
            result = run_command("stellar contract build", cwd=contract)
            if not result or result.returncode != 0:
                print(f"❌ Failed to build {contract}")
                continue
    
    # Deploy contracts
    deployments = []
    
    # Deploy opus_token
    opus_result = deploy_contract_robust(
        "opus_token",
        "opus_token/target/wasm32-unknown-unknown/release/opus_token.wasm",
        "--admin test-deployer"
    )
    if opus_result:
        deployments.append(opus_result)
    
    # Deploy hvym-collective-factory
    factory_result = deploy_contract_robust(
        "hvym-collective-factory",
        "hvym-collective-factory/target/wasm32-unknown-unknown/release/hvym_collective_factory.wasm"
    )
    if factory_result:
        deployments.append(factory_result)
    
    # Deploy hvym-collective (if factory deployed successfully)
    if factory_result and opus_result:
        collective_result = deploy_contract_robust(
            "hvym-collective",
            "hvym-collective/target/wasm32-unknown-unknown/release/hvym_collective.wasm",
            f"--admin test-deployer --join_fee 100 --mint_fee 50 --token {opus_result['address']} --reward 10"
        )
        if collective_result:
            deployments.append(collective_result)
    
    # Save deployment results
    if deployments:
        deployment_data = {
            "network": "testnet",
            "timestamp": int(time.time()),
            "contracts": deployments
        }
        
        with open("robust_deployments.json", "w") as f:
            json.dump(deployment_data, f, indent=2)
        
        print(f"\n🎉 Deployment completed! {len(deployments)} contracts deployed")
        print("📄 Results saved to robust_deployments.json")
        
        for deployment in deployments:
            print(f"  • {deployment['name']}: {deployment['address']}")
    else:
        print("\n❌ No contracts were successfully deployed")
        sys.exit(1)

if __name__ == "__main__":
    main()
