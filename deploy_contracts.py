#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import glob
import json
from pathlib import Path

# Global variable to store the project root directory
PROJECT_ROOT = Path(__file__).parent.resolve()

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

CONTRACTS = {
    "pintheon_ipfs_token": "wasm/pintheon_ipfs_token.optimized.wasm",
    "pintheon_node_token": "wasm/pintheon_node_token.optimized.wasm",
    "opus_token": "wasm/opus_token.optimized.wasm",
    "hvym_collective": "wasm/hvym_collective.optimized.wasm",
}
CONTRACT_ORDER = list(CONTRACTS.keys())

# Official release contracts mapping (using wasm_release folder)
OFFICIAL_CONTRACTS = {
    "pintheon_ipfs_token": "wasm_release/pintheon_ipfs_token",
    "pintheon_node_token": "wasm_release/pintheon_node_token",
    "opus_token": "wasm_release/opus_token",
    "hvym_collective": "wasm_release/hvym_collective",
}

DEPLOYMENTS_FILE = "deployments.json"
DEPLOYMENTS_MD = "deployments.md"

UPLOAD_ONLY_CONTRACTS = [
    "pintheon_ipfs_token",
    "pintheon_node_token"
]
DEPLOY_ONLY_CONTRACTS = [
    "opus_token",
    "hvym_collective"
]

def find_optimized_wasm(contract_dir, official_release=False):
    """
    Find the optimized WASM file for a contract.
    
    Args:
        contract_dir: Path to the contract directory (relative to project root)
        official_release: Whether to look in the wasm_release directory
        
    Returns:
        Path to the optimized WASM file, or None if not found
    """
    contract_dir = Path(contract_dir)
    if not contract_dir.is_absolute():
        contract_dir = PROJECT_ROOT / contract_dir
    
    if official_release:
        # For official releases, look for WASM files in the wasm_release directory first
        print(f"  Official release mode, checking {contract_dir}")
        if contract_dir.is_dir():
            wasm_files = list(contract_dir.glob("*.wasm"))
            if wasm_files:
                print(f"  Found {len(wasm_files)} WASM files in release directory")
                # Return the first WASM file found (should be the only one)
                return str(wasm_files[0].resolve())
        print("  No WASM files found in release directory")
        return None
        
    # First check the wasm/ directory in the project root
    wasm_dir = PROJECT_ROOT / "wasm"
    if wasm_dir.exists():
        contract_name = os.path.basename(contract_dir).replace("-", "_")
        wasm_pattern = os.path.join(wasm_dir, f"{contract_name}.optimized.wasm")
        wasm_files = glob.glob(wasm_pattern)
        if wasm_files:
            return wasm_files[0]
    
    # Fall back to checking target directories (for backward compatibility)
    wasm_dirs = [
        contract_dir / "target" / "wasm32v1-none" / "release",  # New stellar CLI build
        contract_dir / "target" / "wasm32-unknown-unknown" / "release"  # Old cargo build
    ]
    
    for wasm_dir in wasm_dirs:
        if not os.path.isdir(wasm_dir):
            continue
        
        # Try optimized files first, then regular .wasm files
        wasm_files = glob.glob(os.path.join(wasm_dir, "*.optimized.wasm"))
        if not wasm_files:
            wasm_files = glob.glob(os.path.join(wasm_dir, "*.wasm"))
        
        if wasm_files:
            # Prefer the one matching the contract dir name if possible
            base = os.path.basename(contract_dir).replace("-", "_")
            for f in wasm_files:
                if base in os.path.basename(f):
                    return f
            # Return the first one if no name match
            return wasm_files[0]
    
    return None

def run_cmd(cmd, cwd=None, capture_output=True, env=None):
    """
    Run a shell command with proper working directory and environment handling.
    
    Args:
        cmd: Command to run (list of arguments)
        cwd: Working directory (defaults to project root if None)
        capture_output: Whether to capture and return command output
        env: Optional environment variables to use (dict)
        
    Returns:
        Command output if capture_output=True, else None
        
    Raises:
        subprocess.CalledProcessError: If the command returns a non-zero exit code
    """
    # Set default working directory to project root
    if cwd is None:
        cwd = PROJECT_ROOT
    elif not Path(cwd).is_absolute():
        cwd = PROJECT_ROOT / cwd
    
    # Ensure the working directory exists
    cwd.mkdir(parents=True, exist_ok=True)
    
    # Prepare environment - start with current environment and update with any provided vars
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    
    # Log the command for debugging
    print(f"\n📝 Running command: {' '.join(cmd)}")
    print(f"   Working directory: {cwd}")
    if env:
        print("   Environment variables:")
        for k, v in env.items():
            if 'SECRET' in k or 'KEY' in k or 'PASSWORD' in k:
                print(f"     {k}=[REDACTED]")
            else:
                print(f"     {k}={v}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            check=True,
            capture_output=capture_output,
            text=True,
            env=process_env
        )
        
        # Log the output if we captured it
        if capture_output and result.stdout:
            print("✅ Command succeeded with output:")
            print(result.stdout)
            
        return result.stdout.strip() if capture_output else None
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed with exit code {e.returncode}")
        print(f"   Command: {' '.join(cmd)}")
        print(f"   Working directory: {cwd}")
        
        if e.stdout:
            print("=== STDOUT ===")
            print(e.stdout)
            
        if e.stderr:
            print("=== STDERR ===")
            print(e.stderr)
            
        # Re-raise the exception to allow callers to handle it
        raise
        
    except Exception as e:
        print(f"❌ Unexpected error executing command: {str(e)}")
        raise
        sys.exit(1)

def load_deployments():
    if os.path.isfile(DEPLOYMENTS_FILE):
        with open(DEPLOYMENTS_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}

def save_deployments(data):
    with open(DEPLOYMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    save_deployments_md(data)

def save_deployments_md(data):
    lines = [
        "# Soroban Contract Deployments\n",
        "| Contract Name | Contract Directory | Wasm Hash | Contract ID |",
        "|--------------|-------------------|--------------------------------------------------------------|----------------------------------------------------------|"
    ]
    
    # Check if we have the new format with a 'contracts' array
    if 'contracts' in data:
        for contract_info in data['contracts']:
            if isinstance(contract_info, dict):
                contract_name = contract_info.get('name', '')
                contract_dir = contract_info.get('contract_dir', '')
                wasm_hash = contract_info.get('wasm_hash', '')
                contract_id = contract_info.get('contract_id', contract_info.get('address', ''))
                lines.append(f"| `{contract_name}` | `{contract_dir}` | `{wasm_hash}` | `{contract_id}` |")
    
    # Also handle the old format where contracts are direct keys
    for key, value in data.items():
        if key not in ['network', 'timestamp', 'cli_version', 'note', 'contracts'] and isinstance(value, dict):
            contract_name = key
            contract_dir = value.get('contract_dir', '')
            wasm_hash = value.get('wasm_hash', '')
            contract_id = value.get('contract_id', value.get('address', ''))
            # Only add if not already in the list
            if not any(contract_name in line for line in lines):
                lines.append(f"| `{contract_name}` | `{contract_dir}` | `{wasm_hash}` | `{contract_id}` |")
    
    with open(DEPLOYMENTS_MD, "w") as f:
        f.write("\n".join(lines) + "\n")

def upload_and_deploy(contract_key, contract_dir, deployer_acct, network, deployments, constructor_args=None, official_release=False):
    mode = "OFFICIAL RELEASE" if official_release else "DEVELOPMENT"
    print(f"\n=== Uploading and deploying {contract_key} ({contract_dir}) [{mode}] ===")
    
    # Check if contract_dir is already a .wasm file
    if contract_dir.endswith('.wasm'):
        wasm_file = Path(contract_dir)
        if not wasm_file.exists():
            print(f"WASM file not found: {contract_dir}")
            sys.exit(1)
        wasm_file_rel = str(wasm_file)
        working_dir = PROJECT_ROOT  # Use project root as working directory for direct WASM files
    else:
        wasm_file = find_optimized_wasm(contract_dir, official_release)
        if not wasm_file:
            if official_release:
                print(f"No WASM file found in {contract_dir}")
                print(f"Expected file pattern: {contract_dir}/*.wasm")
            else:
                print(f"No optimized .wasm file found in {contract_dir}")
                print(f"Expected file pattern: {contract_dir}/target/wasm32-unknown-unknown/release/*.optimized.wasm")
            sys.exit(1)
        wasm_file_rel = os.path.relpath(wasm_file, contract_dir)
        working_dir = contract_dir
    # Set up environment with network passphrase for Stellar CLI
    env = os.environ.copy()
    if network == "testnet":
        env["STELLAR_NETWORK_PASSPHRASE"] = "Test SDF Network ; September 2015"
    elif network == "public":
        env["STELLAR_NETWORK_PASSPHRASE"] = "Public Global Stellar Network ; September 2015"

    # Upload
    print(f"Uploading {wasm_file_rel} ...")
    upload_cmd = [
        "stellar", "contract", "upload",
        "--source-account", deployer_acct,
        "--wasm", wasm_file_rel,
        "--network", network
    ]
    upload_out = run_cmd(upload_cmd, cwd=working_dir, env=env)
    # Refined: Use the last line if it's a 64-char hex string
    lines = [line.strip() for line in upload_out.splitlines() if line.strip()]
    wasm_hash = None
    if lines:
        last_line = lines[-1]
        if len(last_line) == 64 and all(c in '0123456789abcdefABCDEF' for c in last_line):
            wasm_hash = last_line
    if not wasm_hash:
        print(f"Could not extract wasm hash from upload output (expected last line to be hash):\n{upload_out}")
        sys.exit(1)
    print(f"Wasm hash: {wasm_hash}")
    # Deploy
    print(f"Deploying contract with hash {wasm_hash} ...")
    deploy_cmd = [
        "stellar", "contract", "deploy",
        "--wasm-hash", wasm_hash,
        "--source-account", deployer_acct,
        "--network", network
    ]
    if constructor_args:
        deploy_cmd.append("--")
        deploy_cmd.extend(constructor_args)
    deploy_out = run_cmd(deploy_cmd, cwd=working_dir, env=env)
    print(f"Deploy output:\n{deploy_out}")
    # Extract contract ID from last line
    deploy_lines = [line.strip() for line in deploy_out.splitlines() if line.strip()]
    contract_id = None
    if deploy_lines:
        last_line = deploy_lines[-1]
        if len(last_line) == 56 and last_line.isalnum() and last_line.isupper():
            contract_id = last_line
    if not contract_id:
        print(f"Could not extract contract ID from deploy output (expected last line to be contract ID):\n{deploy_out}")
        sys.exit(1)
    print(f"Contract ID: {contract_id}")
    # Update deployments.json
    deployments[contract_key] = {
        "contract_dir": contract_dir,
        "wasm_hash": wasm_hash,
        "contract_id": contract_id
    }
    save_deployments(deployments)
    print(f"Updated {DEPLOYMENTS_FILE} with {contract_key}")

def upload_only(contract_key, contract_dir, deployer_acct, network, deployments, official_release=False):
    mode = "OFFICIAL RELEASE" if official_release else "DEVELOPMENT"
    print(f"\n=== Uploading {contract_key} ({contract_dir}) (upload only, no deploy) [{mode}] ===")
    
    # Check if contract_dir is already a .wasm file
    if contract_dir.endswith('.wasm'):
        wasm_file = Path(contract_dir)
        if not wasm_file.exists():
            print(f"WASM file not found: {contract_dir}")
            sys.exit(1)
        working_dir = PROJECT_ROOT  # Use project root as working directory for direct WASM files
    else:
        wasm_file = find_optimized_wasm(contract_dir, official_release)
        if not wasm_file:
            if official_release:
                print(f"No WASM file found in {contract_dir}")
                print(f"Expected file pattern: {contract_dir}/*.wasm")
            else:
                print(f"No optimized .wasm file found in {contract_dir}")
                print(f"Expected file pattern: {contract_dir}/target/wasm32-unknown-unknown/release/*.optimized.wasm")
            sys.exit(1)
        working_dir = contract_dir
    
    print(f"Uploading {wasm_file.name} ...")
    # Set up environment with network passphrase for Stellar CLI
    env = os.environ.copy()
    if network == "testnet":
        env["STELLAR_NETWORK_PASSPHRASE"] = "Test SDF Network ; September 2015"
    elif network == "public":
        env["STELLAR_NETWORK_PASSPHRASE"] = "Public Global Stellar Network ; September 2015"
    
    upload_cmd = [
        "stellar", "contract", "upload",
        "--source-account", deployer_acct,
        "--wasm", str(wasm_file),
        "--network", network
    ]
    upload_out = run_cmd(upload_cmd, cwd=working_dir, env=env)
    lines = [line.strip() for line in upload_out.splitlines() if line.strip()]
    wasm_hash = None
    if lines:
        last_line = lines[-1]
        if len(last_line) == 64 and all(c in '0123456789abcdefABCDEF' for c in last_line):
            wasm_hash = last_line
    if not wasm_hash:
        print(f"Could not extract wasm hash from upload output (expected last line to be hash):\n{upload_out}")
        sys.exit(1)
    print(f"Wasm hash: {wasm_hash}")
    deployments[contract_key] = {
        "contract_dir": contract_dir,
        "wasm_hash": wasm_hash,
        "contract_id": None
    }
    save_deployments(deployments)
    print(f"Updated {DEPLOYMENTS_FILE} with {contract_key}")

def load_args_from_json(contract_key):
    import json
    # Handle naming mismatch for opus_token
    if contract_key == "opus_token":
        json_file = "opus-token_args.json"
    else:
        json_file = f"{contract_key}_args.json"
    
    if not os.path.isfile(json_file):
        print(f"Warning: No argument file found for {contract_key} (expected {json_file}), no constructor args will be used.")
        return []
    with open(json_file, "r") as f:
        data = json.load(f)
    args = []
    # For hvym-collective, convert join_fee, mint_fee, reward to stroops
    if contract_key == "hvym-collective":
        for key in ["join_fee", "mint_fee", "reward"]:
            if key in data:
                # Allow both int and float (for decimal XLM values)
                try:
                    data[key] = int(float(data[key]) * 10_000_000)
                except Exception as e:
                    print(f"Error converting {key} to stroops: {e}")
                    sys.exit(1)
    for k, v in data.items():
        args.append(f"--{k.replace('_', '-')}")
        args.append(str(v))
    return args

def main():
    # Ensure we're running from the project root
    ensure_project_root()
    
    parser = argparse.ArgumentParser(
        description="Upload and deploy Soroban contracts using Stellar CLI.\n"
        "If --constructor-args is not provided, the script will look for a JSON file "
        "named <contract>_args.json and use its fields as constructor arguments."
    )
    parser.add_argument(
        "--deployer-acct",
        required=True,
        help="Stellar CLI account name to use as deployer (must be in ~/.stellar/identity/)",
    )
    parser.add_argument(
        "--network",
        default="testnet",
        choices=["testnet", "public", "futurenet"],
        help="Network name for deployment (default: testnet)",
    )
    parser.add_argument(
        "--wasm-dir",
        default=PROJECT_ROOT / "wasm",
        help="Directory containing optimized WASM files (default: wasm in project root)",
    )
    parser.add_argument(
        "--contract",
        type=str,
        help="Target a specific contract by short name (see list below)",
    )
    parser.add_argument(
        "--constructor-args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to the contract constructor (everything after this flag is passed to the deploy command after --). If not provided, arguments will be loaded from <contract>_args.json.",
    )
    parser.add_argument(
        "--official-release",
        action="store_true",
        help="Use official release WASM files from the 'wasm_release' directory.",
    )
    args = parser.parse_args()
    
    # Convert relative paths to absolute
    if not Path(args.wasm_dir).is_absolute():
        args.wasm_dir = PROJECT_ROOT / args.wasm_dir
    
    # Validate wasm directory exists
    if not args.wasm_dir.exists():
        print(f"Error: WASM directory not found: {args.wasm_dir}")
        sys.exit(1)
    
    # Validate official release mode
    if args.official_release:
        if not os.path.exists("wasm_release"):
            print("Error: --official-release specified but 'wasm_release' directory not found.")
            print("Please run download_wasm_releases.py first to download the official release files.")
            sys.exit(1)
        print("Using official release WASM files from 'wasm_release' directory")
    
    deployments = load_deployments()
    if args.constructor_args is not None:
        constructor_args = args.constructor_args
        if '--admin' not in constructor_args:
            constructor_args = constructor_args + ['--admin', args.deployer_acct]
    else:
        if args.contract:
            constructor_args = load_args_from_json(args.contract)
            if '--admin' not in constructor_args:
                constructor_args = constructor_args + ['--admin', args.deployer_acct]
        else:
            constructor_args = None
    if args.contract:
        if args.contract not in CONTRACTS:
            print(f"Contract '{args.contract}' not in deploy list. Valid options:")
            for c in CONTRACT_ORDER:
                print(f"  {c}")
            sys.exit(1)
        contract_dir = CONTRACTS[args.contract]
        if args.official_release:
            contract_dir = OFFICIAL_CONTRACTS[args.contract]
        if args.contract in UPLOAD_ONLY_CONTRACTS:
            upload_only(contract_key=args.contract, contract_dir=contract_dir, deployer_acct=args.deployer_acct, network=args.network, deployments=deployments, official_release=args.official_release)
        elif args.contract in DEPLOY_ONLY_CONTRACTS:
            upload_and_deploy(args.contract, contract_dir, args.deployer_acct, args.network, deployments, constructor_args, args.official_release)
        else:
            print(f"Contract '{args.contract}' is not configured for upload or deploy.")
            sys.exit(1)
    else:
        for contract_key in CONTRACT_ORDER:
            contract_dir = CONTRACTS[contract_key]
            if args.official_release:
                contract_dir = OFFICIAL_CONTRACTS[contract_key]
            if contract_key in UPLOAD_ONLY_CONTRACTS:
                upload_only(contract_key, contract_dir, args.deployer_acct, args.network, deployments, args.official_release)
            elif contract_key in DEPLOY_ONLY_CONTRACTS:
                per_contract_args = constructor_args if constructor_args is not None else load_args_from_json(contract_key)
                if '--admin' not in per_contract_args:
                    per_contract_args = per_contract_args + ['--admin', args.deployer_acct]
                upload_and_deploy(contract_key, contract_dir, args.deployer_acct, args.network, deployments, per_contract_args, args.official_release)

if __name__ == "__main__":
    main() 