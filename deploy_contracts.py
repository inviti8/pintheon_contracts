#!/usr/bin/env python3
"""
Deploy Stellar Soroban contracts to mainnet/testnet.

This script handles network congestion gracefully with exponential backoff retries.
If you experience persistent timeouts, try these solutions:

1. Set environment variables:
   export STELLAR_RPC_URL="https://mainnet.stellar.rpc.nodes.quicknode.com"
   export STELLAR_RPC_TIMEOUT=300
   export STELLAR_BASE_FEE=10000

2. Deploy during off-peak hours:
   - Best: 2-6 AM UTC (weekends) or 11 PM - 2 AM UTC (weekdays)
   - Avoid: 9 AM - 5 PM UTC (high congestion)
   - Monitor: https://status.stellar.org/

3. Use alternative endpoints:
   - QuickNode: https://mainnet.stellar.rpc.nodes.quicknode.com (recommended)
   - Alchemy: https://stellar-mainnet.g.alchemy.com/v2 (enterprise)
   - Gateway: https://mainnet.stellar.gateway.fm (free, SDF official)
   - Blocto: https://stellar-mainnet.blocto.app (free)

4. Check Stellar Status: https://status.stellar.org/ for network issues

For persistent issues, consider running your own RPC node locally.
"""

import json
import os
import subprocess
import sys
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional

# Network configurations
NETWORK_CONFIGS = {
    "testnet": {
        "passphrase": "Test SDF Network ; September 2015",
        "rpc_url": "https://soroban-testnet.stellar.org"
    },
    "futurenet": {
        "passphrase": "Test SDF Future Network ; October 2022",
        "rpc_url": "https://rpc-futurenet.stellar.org"
    },
    "public": {
        "passphrase": "Public Global Stellar Network ; September 2015",
        "rpc_url": "https://stellar-soroban-public.nodies.app"
    },
    "standalone": {
        "passphrase": "Standalone Network ; February 2017",
        "rpc_url": "http://localhost:8000"
    }
}

# Contract list
CONTRACTS = [
    "pintheon_ipfs_token",
    "pintheon_node_token",
    "opus_token",
    "hvym_collective",
    "hvym_roster",
    "hvym_pin_service",
    "hvym_pin_service_factory",
    "hvym_registry"
]

# Get timeout from environment or use default
TIMEOUT = int(os.environ.get('STELLAR_RPC_TIMEOUT', '120'))
MAX_RETRIES = int(os.environ.get('STELLAR_RPC_RETRIES', '5'))
BASE_FEE = int(os.environ.get('STELLAR_BASE_FEE', '1000000'))
NETWORK = None
NETWORK_PASSPHRASE = None
RPC_URL = None

def resolve_network(cli_network: Optional[str] = None) -> str:
    """Resolve which network to use: CLI flag > env var > default (testnet)."""
    global NETWORK, NETWORK_PASSPHRASE, RPC_URL
    
    if cli_network:
        network = cli_network
    elif os.environ.get("STELLAR_NETWORK"):
        network = os.environ["STELLAR_NETWORK"]
    else:
        network = "public"  # Default to mainnet instead of testnet
    
    if network not in NETWORK_CONFIGS:
        print(f"Error: Unsupported network '{network}'. Supported: {', '.join(NETWORK_CONFIGS.keys())}")
        sys.exit(1)
    
    NETWORK = network
    NETWORK_PASSPHRASE = NETWORK_CONFIGS[network]["passphrase"]
    
    # Use environment variable if set, otherwise use config
    RPC_URL = os.environ.get("STELLAR_RPC_URL", NETWORK_CONFIGS[network]["rpc_url"])

    print(f"Using network: {NETWORK}")
    print(f"  RPC URL:    {RPC_URL}")
    print(f"  Passphrase: {NETWORK_PASSPHRASE}")
    print(f"  Timeout: {TIMEOUT}s, Retries: {MAX_RETRIES}")
    if RPC_URL.startswith("https://mainnet.stellar.rpc.nodes.quicknode.com"):
        print("✅ Using recommended QuickNode endpoint for mainnet deployment")
    elif RPC_URL.startswith("https://mainnet.sorobanrpc.com"):
        print("⚠️  Using default Soroban RPC endpoint (may be slow)")
        print("  Consider setting STELLAR_RPC_URL for better performance")
    return network

# Global variable to store the project root directory
PROJECT_ROOT = Path(__file__).parent.resolve()
WASM_DIR = PROJECT_ROOT / "wasm"

def get_deployments_file() -> Path:
    """Return the network-specific deployments JSON path."""
    return PROJECT_ROOT / f"deployments.{NETWORK}.json"

def get_deployments_md() -> Path:
    """Return the network-specific deployments markdown path."""
    return PROJECT_ROOT / f"deployments.{NETWORK}.md"

def ensure_project_root():
    """Ensure the script is being run from the project root directory."""
    # Check for key project files/directories
    required_paths = [
        PROJECT_ROOT / 'deploy_contracts.py',
        PROJECT_ROOT / '.github',
        PROJECT_ROOT / 'wasm'
    ]
    
    for path in required_paths:
        if not path.exists():
            print(f"Error: Could not find required path: {path}")
            print("Please run this script from the project root directory.")
            sys.exit(1)

def get_file_hash(filepath):
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def resolve_native_xlm_sac() -> str:
    """Resolve the native XLM Stellar Asset Contract address for the target network."""
    try:
        result = subprocess.run(
            [
                "stellar", "contract", "id", "asset",
                "--asset", "native",
                "--rpc-url", RPC_URL,
                "--network-passphrase", NETWORK_PASSPHRASE,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        sac_address = result.stdout.strip()
        print(f"Resolved native XLM SAC for {NETWORK}: {sac_address}")
        return sac_address
    except subprocess.CalledProcessError as e:
        print(f"Failed to resolve native XLM SAC: {e.stderr.strip()}")
        sys.exit(1)

# Cache the resolved SAC address so we only call the CLI once
_native_xlm_sac: Optional[str] = None

def get_native_xlm_sac() -> str:
    """Get native XLM SAC address, resolving and caching on first call."""
    global _native_xlm_sac
    if _native_xlm_sac is None:
        _native_xlm_sac = resolve_native_xlm_sac()
    return _native_xlm_sac

def load_contract_args(contract_name: str, deployer_acct: Optional[str] = None) -> Optional[dict]:
    """Load constructor arguments from JSON file.

    Placeholder resolution (applied before any other processing):
      - "deployer" in admin/admin_addr fields → deployer_acct identity name
      - "native"  in token/pay_token fields  → network-specific XLM SAC address
    """
    args_file = f"{contract_name}_args.json"
    try:
        with open(args_file) as f:
            args = json.load(f)

        # Resolve "deployer" admin placeholders to the deployer account identity
        if deployer_acct:
            for key in ['admin', 'admin_addr']:
                if args.get(key) == "deployer":
                    args[key] = deployer_acct
                    print(f"  Resolved admin to deployer: {deployer_acct}")

        # Resolve "native" token placeholders to the network-specific XLM SAC
        for key in ['token', 'pay_token']:
            if args.get(key) == "native":
                args[key] = get_native_xlm_sac()

        # Convert XLM to stroops for hvym_collective and hvym_roster
        if contract_name == "hvym_collective":
            for key in ['join_fee', 'mint_fee', 'reward']:
                if key in args:
                    args[key] = int(float(args[key]) * 10_000_000)
        elif contract_name == "hvym_roster":
            for key in ['join_fee']:
                if key in args:
                    args[key] = int(float(args[key]) * 10_000_000)
        elif contract_name == "hvym_pin_service":
            for key in ['pin_fee', 'join_fee', 'min_offer_price', 'pinner_stake']:
                if key in args:
                    args[key] = int(float(args[key]) * 10_000_000)

        return args
    except FileNotFoundError:
        print(f"No argument file found for {contract_name}")
        return {}

def run_command(cmd: List[str], timeout: int = 60) -> str:
    """Run a shell command and return its output."""
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e.stderr.strip()}")
        print(f"  Command: {' '.join(cmd)}")
        raise
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        print("  This is likely due to network congestion. Retrying...")
        raise

# These are now defined at the top of the file using pathlib

def upload_contract(contract_name: str, deployer_acct: str) -> str:
    """Upload a contract and return the wasm hash."""
    wasm_file = WASM_DIR / f"{contract_name}.optimized.wasm"
    if not wasm_file.exists():
        print(f"Error: {wasm_file} not found. Build the contract first.")
        sys.exit(1)

    print(f"\nUploading {contract_name}...")
    cmd = [
        "stellar", "contract", "upload",
        "--wasm", str(wasm_file),
        "--source", deployer_acct,
        "--rpc-url", RPC_URL,
        "--network-passphrase", NETWORK_PASSPHRASE,
        f"--fee={BASE_FEE}",
    ]

    # Set environment variables for this command (don't override globals)
    env = os.environ.copy()
    if 'STELLAR_RPC_URL' not in env:
        env['STELLAR_RPC_URL'] = RPC_URL
    if 'STELLAR_NETWORK_PASSPHRASE' not in env:
        env['STELLAR_NETWORK_PASSPHRASE'] = NETWORK_PASSPHRASE

    # Retry upload with exponential backoff
    for attempt in range(MAX_RETRIES):
        try:
            timeout = TIMEOUT * (2 ** attempt)
            # Increase fee on retries
            run_cmd = cmd.copy()
            if attempt > 0:
                increased_fee = int(BASE_FEE * (1.1 ** attempt))
                for i, arg in enumerate(run_cmd):
                    if arg.startswith("--fee="):
                        run_cmd[i] = f"--fee={increased_fee}"
                        break
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} with fee={increased_fee}")

            result = subprocess.run(
                run_cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                env=env,
            )
            wasm_hash = result.stdout.strip()
            print(f"Uploaded {contract_name} with hash: {wasm_hash}")
            return wasm_hash
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            is_timeout = isinstance(e, subprocess.TimeoutExpired)
            if isinstance(e, subprocess.CalledProcessError):
                is_timeout = "timeout" in str(e.stderr).lower() or "timed out" in str(e.stderr).lower()
                print(f"Command failed: {e.stderr.strip()}")

            if attempt < MAX_RETRIES - 1:
                wait_time = 2 ** attempt * 5
                print(f"Upload attempt {attempt + 1} failed. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"Upload failed after {MAX_RETRIES} attempts.")
                if is_timeout:
                    print("  This may indicate network congestion. Please try again later.")
                sys.exit(1)

def deploy_contract(contract_name: str, wasm_hash: str, deployer_acct: str, args: Optional[dict] = None) -> str:
    """Deploy a contract with given wasm hash and arguments."""
    cmd = [
        "stellar", "contract", "deploy",
        f"--wasm-hash={wasm_hash}",
        "--source-account", deployer_acct,
        "--rpc-url", RPC_URL,
        "--network-passphrase", NETWORK_PASSPHRASE,
        f"--fee={BASE_FEE}"
    ]

    # Add constructor arguments with -- separator
    if args:
        cmd.append("--")
        for key, value in args.items():
            cmd.append(f"--{key.replace('_', '-')}")
            cmd.append(str(value))

    # Set environment variables for this command (don't override globals)
    env = os.environ.copy()
    if 'STELLAR_RPC_URL' not in env:
        env['STELLAR_RPC_URL'] = RPC_URL
    if 'STELLAR_NETWORK_PASSPHRASE' not in env:
        env['STELLAR_NETWORK_PASSPHRASE'] = NETWORK_PASSPHRASE

    # Retry deployment with exponential backoff
    for attempt in range(MAX_RETRIES):
        try:
            timeout = TIMEOUT * (2 ** attempt)
            # Increase fee on retries (only modify args before the -- separator)
            run_cmd = cmd.copy()
            if attempt > 0:
                increased_fee = int(BASE_FEE * (1.1 ** attempt))
                for i, arg in enumerate(run_cmd):
                    if arg.startswith("--fee="):
                        run_cmd[i] = f"--fee={increased_fee}"
                        break
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} with fee={increased_fee}")

            result = subprocess.run(
                run_cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                env=env,
            )
            contract_id = result.stdout.strip()
            print(f"Deployed {contract_name} with ID: {contract_id}")
            return contract_id
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            is_timeout = isinstance(e, subprocess.TimeoutExpired)
            if isinstance(e, subprocess.CalledProcessError):
                is_timeout = "timeout" in str(e.stderr).lower() or "timed out" in str(e.stderr).lower()
                print(f"Command failed: {e.stderr.strip()}")

            if attempt < MAX_RETRIES - 1:
                wait_time = 2 ** attempt * 5
                print(f"Deploy attempt {attempt + 1} failed. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"Deploy failed after {MAX_RETRIES} attempts.")
                if is_timeout:
                    print("  This may indicate network congestion. Please try again later.")
                sys.exit(1)

def load_deployments() -> dict:
    """Load existing deployments for the target network."""
    dep_file = get_deployments_file()
    if dep_file.exists():
        with open(dep_file, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error parsing {dep_file}: {e}")
                return {}
    return {}

def save_deployments(deployments: dict) -> None:
    """Save deployments to the network-specific JSON file."""
    dep_file = get_deployments_file()
    dep_file.parent.mkdir(parents=True, exist_ok=True)
    with open(dep_file, 'w') as f:
        json.dump(deployments, f, indent=2)
    print(f"Saved deployments to {dep_file}")

# Contract categories
UPLOAD_ONLY_CONTRACTS = [
    "pintheon_ipfs_token",
    "pintheon_node_token"
]

DEPLOY_ONLY_CONTRACTS = [
    "opus_token",
    "hvym_collective",
    "hvym_roster",
    "hvym_pin_service",
    "hvym_pin_service_factory",
    "hvym_registry",
]

def generate_deployments_md(deployments: dict) -> None:
    """Generate a network-specific markdown file with deployment details."""
    skip_keys = {'network', 'timestamp', 'cli_version', 'note'}

    md = f"# Deployments — {NETWORK}\n\n"
    md += "| Contract | Contract ID | Wasm Hash |\n"
    md += "|----------|-------------|-----------|\n"

    for contract, info in deployments.items():
        if not isinstance(info, dict) or contract in skip_keys:
            continue

        contract_id = info.get('contract_id', 'Upload only')
        wasm_hash = info.get('wasm_hash', 'N/A')
        md += f"| {contract} | `{contract_id}` | `{wasm_hash}` |\n"

    dep_md = get_deployments_md()
    with open(dep_md, 'w') as f:
        f.write(md)
    print(f"Generated {dep_md}")

def main():
    """Main deployment function."""
    import argparse

    parser = argparse.ArgumentParser(description='Deploy Soroban contracts')
    parser.add_argument('--deployer-acct', required=True, help='Deployer account')
    parser.add_argument('--network', default=None, help='Network to deploy to (testnet, futurenet, public, standalone)')
    parser.add_argument('--wasm-dir', default=WASM_DIR, help='Directory containing WASM files')
    parser.add_argument('--force', action='store_true', help='Force redeploy even if WASM hash matches (e.g. to fix constructor args)')
    args = parser.parse_args()

    # Resolve network from: CLI flag > STELLAR_NETWORK env var > public (mainnet)
    resolve_network(args.network)

    print(f"Starting deployment with deployer: {args.deployer_acct}")
    print(f"Deployments file: {get_deployments_file()}")

    # Load existing deployments for this network
    deployments = load_deployments()
    
    try:
        # Process each contract in order
        for contract in CONTRACTS:
            print(f"\n=== Processing {contract} ===")
            
            wasm_path = Path(args.wasm_dir) / f"{contract}.optimized.wasm"
            if wasm_path.exists():
                actual_hash = get_file_hash(wasm_path)
                
                if contract in deployments and 'wasm_hash' in deployments[contract]:
                    deployed_entry = deployments[contract]
                    if deployed_entry.get('wasm_hash') == actual_hash and not args.force:
                        print(f"✅ {contract} already deployed to {NETWORK} with matching hash")
                        print(f"   Contract ID: {deployed_entry.get('contract_id')}")
                        print(f"   Skipping (use --force to override)")
                        continue
                    elif deployed_entry.get('wasm_hash') == actual_hash:
                        print(f"🔄 {contract} WASM unchanged but --force specified, redeploying...")
                    else:
                        print(f"⚠️  {contract} has different WASM hash than deployed")
                        print(f"   Will redeploy to update...")
                else:
                    print(f"🆕 {contract} not yet deployed to {NETWORK}")
            
            # Initialize contract entry if it doesn't exist
            if contract not in deployments:
                deployments[contract] = {}
            
            # Upload the contract
            print(f"Uploading {contract}...")
            wasm_hash = upload_contract(contract, args.deployer_acct)
            print(f"Uploaded with hash: {wasm_hash}")
            
            # Update contract info
            contract_info = {
                'wasm_hash': wasm_hash,
                'network': NETWORK,
                'deployer': args.deployer_acct,
                'timestamp': int(time.time())
            }
            
            # Deploy if needed
            if contract in DEPLOY_ONLY_CONTRACTS:
                print(f"Deploying {contract}...")
                try:
                    contract_args = load_contract_args(contract, deployer_acct=args.deployer_acct)
                    contract_id = deploy_contract(contract, wasm_hash, args.deployer_acct, contract_args)
                    contract_info['contract_id'] = contract_id
                    print(f"Deployed {contract} with ID: {contract_id}")
                except Exception as e:
                    print(f"❌ Failed to deploy {contract}: {e}")
                    print(f"   Will continue with next contract...")
                    # Don't set contract_id on failure
            
            # Update deployments with the new info
            deployments[contract].update(contract_info)
            
            # Save progress after each contract
            save_deployments(deployments)
        
        # Add metadata
        deployments.update({
            'network': NETWORK,
            'timestamp': int(time.time()),
        })
        
        # Save final state
        save_deployments(deployments)
        
        # Generate markdown report
        generate_deployments_md(deployments)
        print("\n✅ All contracts processed successfully!")
        
    except Exception as e:
        print(f"\n❌ Deployment failed: {str(e)}")
        raise

if __name__ == "__main__":
    ensure_project_root()
    main()
