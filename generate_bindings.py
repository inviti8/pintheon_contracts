#!/usr/bin/env python3
"""
Script to generate Python bindings for Soroban contracts.

This script supports two modes:

1. Deploy mode (default):
   - Upload all optimized WASM files from the wasm/ directory
   - Deploy instances of each contract with their respective arguments
   - Generate Python bindings for each deployed contract

2. GitHub Release mode (--github-release):
   - Download WASM files from a GitHub release URL
   - Generate Python bindings directly from WASM files (no deployment needed)
   - Example: python generate_bindings.py --github-release https://github.com/owner/repo/releases/tag/v1.0.0
"""

import os
import sys
import json
import time
import subprocess
import argparse
import tempfile
import re
from pathlib import Path
from typing import Dict, Optional, List
from urllib.parse import urlparse

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Configuration
DEPLOYMENTS_FILE = "bindings_deployments.json"
BINDINGS_DIR = "bindings"
WASM_DIR = "wasm"

# Network configurations (aligned with deploy_contracts.py)
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
        "rpc_url": "https://mainnet.sorobanrpc.com"
    },
    "standalone": {
        "passphrase": "Standalone Network ; February 2017",
        "rpc_url": "http://localhost:8000"
    }
}

# Default to testnet
NETWORK = "testnet"
NETWORK_PASSPHRASE = NETWORK_CONFIGS[NETWORK]["passphrase"]
RPC_URL = NETWORK_CONFIGS[NETWORK]["rpc_url"]

# Contract categories (aligned with deploy_contracts.py)
# These contracts are only uploaded (wasm hash), not deployed as standalone contracts
# They are deployed dynamically by hvym_collective when members join
UPLOAD_ONLY_CONTRACTS = [
    "pintheon_ipfs_token",
    "pintheon_node_token"
]

# These contracts are deployed as standalone and will have contract IDs
DEPLOYABLE_CONTRACTS = [
    "opus_token",
    "hvym_collective",
    "hvym_roster",
    "hvym_pin_service",
    "hvym_pin_service_factory"
]

def load_account() -> Optional[str]:
    """Load deployment account from account.json."""
    account_file = Path("account.json")
    if not account_file.exists():
        print(f"❌ Error: {account_file} not found. Please create this file with your deployment account.")
        return None
    
    try:
        with open(account_file) as f:
            account_data = json.load(f)
            account = account_data.get('secret')  # Changed from 'secret_key' to 'secret'
            if not account:
                print("❌ Error: 'secret' not found in account.json")
                return None
            print("✅ Loaded deployment account")
            return account
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing {account_file}: {e}")
        return None

def load_contract_args(contract_name: str) -> dict:
    """Load constructor arguments from {contract_name}_args.json if it exists."""
    args_file = Path(f"{contract_name}_args.json")
    if not args_file.exists():
        print(f"⚠️  No arguments file found for {contract_name}, using empty arguments")
        return {}
    
    try:
        with open(args_file) as f:
            args = json.load(f)
            # Convert float values to stroops (1 XLM = 10,000,000 stroops)
            for key, value in args.items():
                if isinstance(value, float):
                    args[key] = int(value * 10_000_000)
            print(f"✅ Loaded arguments for {contract_name}: {args}")
            return args
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing {args_file}: {e}")
        return {}

def upload_wasm(wasm_path: Path, source_key: str) -> Optional[str]:
    """Upload a WASM file and return its hash."""
    print(f"\nUploading WASM: {wasm_path.name}")
    
    try:
        # Set environment variables
        env = os.environ.copy()
        env['STELLAR_NETWORK_PASSPHRASE'] = NETWORK_PASSPHRASE
        
        # Upload the WASM
        upload_cmd = [
            "stellar", "contract", "upload",
            "--wasm", str(wasm_path),
            "--source-account", source_key,
            f"--network={NETWORK}",
            f"--rpc-url={RPC_URL}",
            "--fee=1000000"
        ]
        
        result = subprocess.run(
            upload_cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        wasm_hash = result.stdout.strip()
        print(f"✅ Uploaded with hash: {wasm_hash}")
        return wasm_hash
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to upload WASM: {e.stderr}")
        return None

def deploy_contract_instance(contract_name: str, wasm_hash: str, source_key: str) -> Optional[str]:
    """Deploy a contract instance and return its ID."""
    print(f"Deploying {contract_name} instance...")
    
    # Load contract arguments
    contract_args = load_contract_args(contract_name)
    
    try:
        # Set environment variables
        env = os.environ.copy()
        env['STELLAR_NETWORK_PASSPHRASE'] = NETWORK_PASSPHRASE
        
        # If we don't have a hash, upload the WASM first
        if not wasm_hash:
            wasm_path = Path(WASM_DIR) / f"{contract_name}.optimized.wasm"
            if not wasm_path.exists():
                print(f"❌ WASM file not found: {wasm_path}")
                return None
                
            wasm_hash = upload_wasm(wasm_path, source_key)
            if not wasm_hash:
                return None
        
        # Build deployment command
        cmd = [
            "stellar", "contract", "deploy",
            f"--wasm-hash={wasm_hash}",
            f"--source-account={source_key}",
            f"--network={NETWORK}",
            f"--rpc-url={RPC_URL}",
            "--fee=1000000",
            "--"  # End of options, start of constructor args
        ]
        
        # Add constructor arguments if any
        if contract_args:
            for key, value in contract_args.items():
                cmd.append(f"--{key.replace('_', '-')}")
                cmd.append(str(value))
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        
        contract_id = result.stdout.strip()
        print(f"✅ Deployed with ID: {contract_id}")
        return contract_id
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to deploy contract: {e.stderr}")
        return None

def generate_bindings(contract_name: str, contract_id: str) -> bool:
    """Generate Python bindings for a contract using stellar-contract-bindings."""
    output_dir = Path(BINDINGS_DIR) / contract_name
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\nGenerating bindings for {contract_name}...")
    print(f"Contract ID: {contract_id}")
    print(f"Output: {output_dir}")
    
    try:
        # Generate bindings using stellar-contract-bindings
        # The contract spec will be fetched automatically by the bindings tool
        bindings_cmd = [
            "stellar-contract-bindings", "python",
            f"--contract-id={contract_id}",
            f"--output={output_dir}",
            f"--rpc-url={RPC_URL}",
            "--client-type=both"
        ]
        
        print("Running command:", " ".join(bindings_cmd))
        
        result = subprocess.run(
            bindings_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if result.stderr:
            print(f"   Info: {result.stderr.strip()}")
            
        print(f"✅ Successfully generated bindings for {contract_name}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate bindings for {contract_name}")
        if e.stderr:
            print(f"   Error: {e.stderr.strip()}")
        if e.stdout:
            print(f"   Output: {e.stdout.strip()}")
        return False

def load_deployments() -> dict:
    """Load existing deployments from bindings_deployments.json."""
    if not os.path.exists(DEPLOYMENTS_FILE):
        return {}
    
    try:
        with open(DEPLOYMENTS_FILE) as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("⚠️  Error parsing bindings_deployments.json, starting fresh")
        return {}

def save_deployments(deployments: dict) -> None:
    """Save deployments to bindings_deployments.json."""
    with open(DEPLOYMENTS_FILE, 'w') as f:
        json.dump(deployments, f, indent=2)
    print(f"💾 Saved deployments to {DEPLOYMENTS_FILE}")


def parse_github_release_url(url: str) -> Optional[Dict[str, str]]:
    """
    Parse a GitHub release URL and extract owner, repo, and tag.

    Supports formats:
    - https://github.com/owner/repo/releases/tag/tag-name
    - https://github.com/owner/repo/releases/download/tag-name/asset.wasm

    Returns dict with 'owner', 'repo', 'tag' or None if invalid.
    """
    parsed = urlparse(url)

    if parsed.netloc != 'github.com':
        print(f"❌ Error: URL must be a github.com URL")
        return None

    # Match release tag URL: /owner/repo/releases/tag/tag-name
    tag_match = re.match(r'^/([^/]+)/([^/]+)/releases/tag/(.+)$', parsed.path)
    if tag_match:
        return {
            'owner': tag_match.group(1),
            'repo': tag_match.group(2),
            'tag': tag_match.group(3)
        }

    # Match release download URL: /owner/repo/releases/download/tag-name/asset
    download_match = re.match(r'^/([^/]+)/([^/]+)/releases/download/([^/]+)/', parsed.path)
    if download_match:
        return {
            'owner': download_match.group(1),
            'repo': download_match.group(2),
            'tag': download_match.group(3)
        }

    print(f"❌ Error: Could not parse GitHub release URL: {url}")
    print("   Expected format: https://github.com/owner/repo/releases/tag/tag-name")
    return None


def fetch_release_assets(owner: str, repo: str, tag: str, github_token: Optional[str] = None) -> Optional[List[Dict]]:
    """
    Fetch release assets from GitHub API.

    Returns list of asset dicts with 'name', 'url', 'browser_download_url'.
    """
    if not HAS_REQUESTS:
        print("❌ Error: 'requests' library is required for github-release mode")
        print("   Install with: pip install requests")
        return None

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"

    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'generate-bindings-script'
    }

    if github_token:
        headers['Authorization'] = f'token {github_token}'

    print(f"📡 Fetching release info from: {api_url}")

    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        release_data = response.json()

        assets = release_data.get('assets', [])
        print(f"✅ Found {len(assets)} assets in release '{tag}'")

        return assets

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"❌ Error: Release '{tag}' not found in {owner}/{repo}")
        elif e.response.status_code == 403:
            print(f"❌ Error: Rate limited or authentication required")
            print("   Try setting GITHUB_TOKEN environment variable")
        else:
            print(f"❌ Error fetching release: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return None


def download_wasm_assets(assets: List[Dict], output_dir: Path, github_token: Optional[str] = None) -> List[Path]:
    """
    Download WASM assets from a GitHub release.

    Returns list of paths to downloaded WASM files.
    """
    downloaded = []

    # Filter for WASM files
    wasm_assets = [a for a in assets if a['name'].endswith('.wasm')]

    if not wasm_assets:
        print("❌ No WASM files found in release assets")
        return []

    print(f"\n📥 Downloading {len(wasm_assets)} WASM files...")

    headers = {
        'Accept': 'application/octet-stream',
        'User-Agent': 'generate-bindings-script'
    }

    if github_token:
        headers['Authorization'] = f'token {github_token}'

    for asset in wasm_assets:
        name = asset['name']
        download_url = asset.get('url')  # API URL for authenticated download
        browser_url = asset.get('browser_download_url')  # Direct download URL

        output_path = output_dir / name

        print(f"   Downloading {name}...", end=" ")

        try:
            # Try API URL first (works with private repos when authenticated)
            if download_url and github_token:
                response = requests.get(download_url, headers=headers, stream=True)
            else:
                # Fall back to browser download URL
                response = requests.get(browser_url, stream=True)

            response.raise_for_status()

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            size_kb = output_path.stat().st_size / 1024
            print(f"✅ ({size_kb:.1f} KB)")
            downloaded.append(output_path)

        except requests.exceptions.RequestException as e:
            print(f"❌ Failed: {e}")
            continue

    return downloaded


def generate_json_spec_from_wasm(wasm_path: Path, output_dir: Path) -> Optional[Path]:
    """
    Generate JSON spec from a WASM file using stellar contract bindings json.

    Returns path to the generated JSON file, or None on failure.
    """
    contract_name = wasm_path.stem.replace('.optimized', '')
    json_output = output_dir / f"{contract_name}.json"

    print(f"\n📄 Generating JSON spec for {contract_name}...")
    print(f"   WASM: {wasm_path}")

    try:
        result = subprocess.run(
            ["stellar", "contract", "bindings", "json", f"--wasm={wasm_path}"],
            capture_output=True,
            text=True,
            check=True
        )

        # Write the JSON output to file
        with open(json_output, 'w') as f:
            f.write(result.stdout)

        print(f"✅ Generated JSON spec: {json_output}")
        return json_output

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate JSON spec for {contract_name}")
        if e.stderr:
            print(f"   Error: {e.stderr.strip()}")
        return None


def generate_bindings_from_contract_id(contract_name: str, contract_id: str,
                                        output_dir: Path, rpc_url: str) -> bool:
    """
    Generate Python bindings from a deployed contract ID.

    Uses stellar-contract-bindings with --contract-id flag.
    """
    bindings_output = output_dir / contract_name
    os.makedirs(bindings_output, exist_ok=True)

    print(f"\nGenerating bindings for {contract_name}...")
    print(f"   Contract ID: {contract_id}")
    print(f"   Output: {bindings_output}")

    try:
        bindings_cmd = [
            "stellar-contract-bindings", "python",
            f"--contract-id={contract_id}",
            f"--output={bindings_output}",
            f"--rpc-url={rpc_url}",
            "--client-type=both"
        ]

        print(f"   Command: {' '.join(bindings_cmd)}")

        result = subprocess.run(
            bindings_cmd,
            capture_output=True,
            text=True,
            check=True
        )

        if result.stderr:
            print(f"   Info: {result.stderr.strip()}")

        print(f"Successfully generated bindings for {contract_name}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Failed to generate bindings for {contract_name}")
        if e.stderr:
            print(f"   Error: {e.stderr.strip()}")
        if e.stdout:
            print(f"   Output: {e.stdout.strip()}")
        return False
    except FileNotFoundError:
        print("stellar-contract-bindings not found. Install with:")
        print("   uv add stellar-contract-bindings")
        return False


def fetch_deployments_from_release(owner: str, repo: str, tag: str,
                                    github_token: Optional[str] = None) -> Optional[Dict]:
    """
    Fetch deployments.json from a GitHub release.

    Looks for deployments.json in release assets or parses release body.
    Returns dict of contract deployments or None on failure.
    """
    if not HAS_REQUESTS:
        return None

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"

    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'generate-bindings-script'
    }

    if github_token:
        headers['Authorization'] = f'token {github_token}'

    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        release_data = response.json()

        # Try to find deployments.json in assets
        assets = release_data.get('assets', [])
        for asset in assets:
            if asset['name'] == 'deployments.json':
                print(f"📥 Downloading deployments.json from release...")
                download_headers = {
                    'Accept': 'application/octet-stream',
                    'User-Agent': 'generate-bindings-script'
                }
                if github_token:
                    download_headers['Authorization'] = f'token {github_token}'

                asset_response = requests.get(asset['url'], headers=download_headers)
                asset_response.raise_for_status()
                return asset_response.json()

        # If no deployments.json asset, try to parse from release body
        body = release_data.get('body', '')
        if body:
            # Look for contract IDs in the release body (markdown table format)
            # Pattern: | contract_name | network | `CONTRACT_ID` | `WASM_HASH` |
            import re
            deployments = {}
            # Match contract IDs (C followed by 55 alphanumeric chars)
            contract_pattern = r'\|\s*(\w+)\s*\|[^|]*\|\s*`?(C[A-Z0-9]{55})`?\s*\|'
            matches = re.findall(contract_pattern, body)
            for name, contract_id in matches:
                deployments[name] = {'contract_id': contract_id}

            if deployments:
                print(f"📋 Parsed {len(deployments)} contract IDs from release notes")
                return deployments

        return None

    except requests.exceptions.RequestException as e:
        print(f"⚠️  Could not fetch deployments: {e}")
        return None


def run_github_release_mode(release_url: str, output_dir: Optional[str] = None,
                            keep_wasm: bool = False, contracts: Optional[List[str]] = None,
                            deploy_release_url: Optional[str] = None,
                            network: str = "testnet", json_only: bool = False) -> int:
    """
    Run in GitHub release mode: fetch contract IDs from deploy release and generate bindings.

    Python bindings require deployed contract IDs (not just WASM files).

    Args:
        release_url: GitHub release URL (for WASM files, used for JSON spec generation)
        output_dir: Output directory for bindings (default: ./bindings)
        keep_wasm: If True, keep downloaded WASM files in ./wasm directory
        contracts: Optional list of contract names to process (default: all)
        deploy_release_url: GitHub release URL with deployment info (contract IDs)
        network: Network name for RPC URL (default: testnet)
        json_only: If True, only generate JSON specs from WASM (no Python bindings)

    Returns:
        0 on success, 1 on failure
    """
    if not HAS_REQUESTS:
        print("❌ Error: 'requests' library is required for github-release mode")
        print("   Install with: uv add requests")
        return 1

    # Parse URL
    url_info = parse_github_release_url(release_url)
    if not url_info:
        return 1

    owner, repo, tag = url_info['owner'], url_info['repo'], url_info['tag']
    print(f"\n📦 GitHub Release Mode")
    print(f"   Repository: {owner}/{repo}")
    print(f"   Tag: {tag}")

    # Get GitHub token from environment
    github_token = os.environ.get('GITHUB_TOKEN')
    if github_token:
        print("   Using GITHUB_TOKEN for authentication")

    # Get RPC URL for the network
    rpc_url = NETWORK_CONFIGS.get(network, NETWORK_CONFIGS["testnet"])["rpc_url"]
    print(f"   Network: {network}")
    print(f"   RPC URL: {rpc_url}")

    # Fetch deployment info (contract IDs)
    deployments = {}
    if deploy_release_url:
        deploy_info = parse_github_release_url(deploy_release_url)
        if deploy_info:
            print(f"\n📋 Fetching deployment info from: {deploy_info['tag']}")
            deployments = fetch_deployments_from_release(
                deploy_info['owner'], deploy_info['repo'], deploy_info['tag'], github_token
            ) or {}
    else:
        # Try to fetch from the same release
        print(f"\n📋 Looking for deployment info in release...")
        deployments = fetch_deployments_from_release(owner, repo, tag, github_token) or {}

    # Also check for local deployments.json
    if not deployments and os.path.exists(DEPLOYMENTS_FILE):
        print(f"📋 Loading local {DEPLOYMENTS_FILE}...")
        try:
            with open(DEPLOYMENTS_FILE) as f:
                deployments = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    if not deployments and not json_only:
        print("\n⚠️  No deployment info found!")
        print("   Python bindings require deployed contract IDs.")
        print("\n   Options:")
        print("   1. Use --deploy-release to specify a release with deployment info")
        print("   2. Use --json-only to generate JSON specs from WASM (no Python bindings)")
        print("   3. Ensure deployments.json exists locally")
        print(f"\n   Example:")
        print(f"   python generate_bindings.py -g {release_url} \\")
        print(f"       --deploy-release https://github.com/{owner}/{repo}/releases/tag/deploy-xxx")
        return 1

    # Set up directories
    bindings_dir = Path(output_dir) if output_dir else Path(BINDINGS_DIR)
    os.makedirs(bindings_dir, exist_ok=True)

    # For JSON spec generation, we need WASM files
    if json_only or keep_wasm:
        # Fetch release assets for WASM files
        assets = fetch_release_assets(owner, repo, tag, github_token)

        if assets:
            wasm_dir = Path(WASM_DIR) if keep_wasm else Path(tempfile.mkdtemp(prefix="soroban_wasm_"))
            os.makedirs(wasm_dir, exist_ok=True)
            wasm_files = download_wasm_assets(assets, wasm_dir, github_token)

            if json_only and wasm_files:
                print("\n📄 Generating JSON specs from WASM files...")
                success_count = 0
                for wasm_file in wasm_files:
                    contract_name = wasm_file.stem.replace('.optimized', '')
                    if contracts and contract_name not in contracts:
                        continue
                    if generate_json_spec_from_wasm(wasm_file, bindings_dir):
                        success_count += 1

                print(f"\n{'='*50}")
                print(f"📊 Generated {success_count} JSON spec files")
                print(f"📁 Output: {bindings_dir.absolute()}")
                return 0

    # Generate Python bindings using contract IDs
    success_count = 0
    skip_count = 0
    fail_count = 0

    # Filter deployments to only process contracts with contract_id
    for contract_name, info in deployments.items():
        # Skip metadata keys
        if contract_name in ('network', 'timestamp', 'cli_version', 'note', 'release', 'version'):
            continue

        if not isinstance(info, dict):
            continue

        # Apply contract filter
        if contracts and contract_name not in contracts:
            continue

        contract_id = info.get('contract_id')
        if not contract_id:
            print(f"\n⏭️  Skipping {contract_name} (no contract ID)")
            skip_count += 1
            continue

        if generate_bindings_from_contract_id(contract_name, contract_id, bindings_dir, rpc_url):
            success_count += 1
        else:
            fail_count += 1

    # Summary
    print(f"\n{'='*50}")
    print(f"📊 Summary: {success_count} succeeded, {skip_count} skipped, {fail_count} failed")
    print(f"📁 Bindings generated in: {bindings_dir.absolute()}")

    # List generated bindings
    if bindings_dir.exists():
        print(f"\n📦 Generated bindings:")
        for binding_dir in sorted(bindings_dir.iterdir()):
            if binding_dir.is_dir():
                files = list(binding_dir.glob("*.py"))
                if files:
                    print(f"   {binding_dir.name}/ ({len(files)} files)")

    return 0 if fail_count == 0 else 1


def main():
    global NETWORK, NETWORK_PASSPHRASE, RPC_URL

    parser = argparse.ArgumentParser(
        description="Generate Python bindings for Soroban contracts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From file mode - generate bindings from existing deployments.json
  python generate_bindings.py --from-file deployments.json

  # From file mode - specific contracts only
  python generate_bindings.py --from-file deployments.json --contracts hvym_collective hvym_pin_service

  # Deploy mode (default) - deploys contracts and generates bindings
  python generate_bindings.py --network testnet

  # GitHub release mode - uses contract IDs from deploy release
  python generate_bindings.py --github-release https://github.com/owner/repo/releases/tag/deploy-v1.0.0

  # GitHub release mode with separate WASM and deploy releases
  python generate_bindings.py -g https://github.com/owner/repo/releases/tag/0.04 \\
      --deploy-release https://github.com/owner/repo/releases/tag/deploy-alpha-v0.04-testnet

  # Generate JSON specs only (from WASM, no contract ID needed)
  python generate_bindings.py -g https://github.com/owner/repo/releases/tag/0.04 --json-only

  # Filter specific contracts
  python generate_bindings.py -g https://github.com/owner/repo/releases/tag/deploy-v1.0.0 \\
      --contracts hvym_collective hvym_roster
        """
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--from-file", "-f",
        metavar="FILE",
        help="Generate bindings from an existing deployments JSON file (e.g., deployments.json)"
    )
    mode_group.add_argument(
        "--github-release", "-g",
        metavar="URL",
        help="GitHub release URL with deployment info (contract IDs)"
    )

    # Deploy mode options
    parser.add_argument("--network", default=NETWORK,
                        help="Network to use for RPC calls (default: testnet)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip contracts that already have bindings (deploy mode only)")

    # GitHub release mode options
    parser.add_argument("--deploy-release",
                        metavar="URL",
                        help="GitHub release URL with deployment info (if different from --github-release)")
    parser.add_argument("--json-only", action="store_true",
                        help="Only generate JSON specs from WASM (no Python bindings, no contract ID needed)")
    parser.add_argument("--keep-wasm", action="store_true",
                        help="Keep downloaded WASM files in ./wasm directory")
    parser.add_argument("--contracts", nargs="+",
                        help="Only process specific contracts (e.g., --contracts hvym_collective opus_token)")
    parser.add_argument("--output", "-o",
                        help="Output directory for bindings (default: ./bindings)")

    args = parser.parse_args()

    # From File Mode
    if args.from_file:
        print(f"\nFrom File Mode")
        print(f"   Reading contract IDs from: {args.from_file}\n")

        # Update network settings if specified
        if args.network != NETWORK and args.network in NETWORK_CONFIGS:
            NETWORK = args.network
            NETWORK_PASSPHRASE = NETWORK_CONFIGS[NETWORK]["passphrase"]
            RPC_URL = NETWORK_CONFIGS[NETWORK]["rpc_url"]

        rpc_url = NETWORK_CONFIGS.get(NETWORK, NETWORK_CONFIGS["testnet"])["rpc_url"]
        print(f"   Network: {NETWORK}")
        print(f"   RPC URL: {rpc_url}")

        # Load the deployments file
        deployments_path = Path(args.from_file)
        if not deployments_path.exists():
            print(f"Error: File not found: {args.from_file}")
            return 1

        try:
            with open(deployments_path) as f:
                deployments = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing {args.from_file}: {e}")
            return 1

        # Set up output directory
        bindings_dir = Path(args.output) if args.output else Path(BINDINGS_DIR)
        os.makedirs(bindings_dir, exist_ok=True)

        # Skip metadata keys
        skip_keys = {'network', 'timestamp', 'cli_version', 'note', 'release', 'version'}

        success_count = 0
        skip_count = 0
        fail_count = 0

        for contract_name, info in deployments.items():
            if contract_name in skip_keys or not isinstance(info, dict):
                continue

            # Apply contract filter
            if args.contracts and contract_name not in args.contracts:
                continue

            contract_id = info.get('contract_id')
            if not contract_id:
                print(f"\nSkipping {contract_name} (no contract ID)")
                skip_count += 1
                continue

            if generate_bindings_from_contract_id(contract_name, contract_id, bindings_dir, rpc_url):
                success_count += 1
            else:
                fail_count += 1

        # Summary
        print(f"\n{'='*50}")
        print(f"Summary: {success_count} succeeded, {skip_count} skipped, {fail_count} failed")
        print(f"Bindings generated in: {bindings_dir.absolute()}")

        if bindings_dir.exists():
            print(f"\nGenerated bindings:")
            for binding_dir in sorted(bindings_dir.iterdir()):
                if binding_dir.is_dir():
                    files = list(binding_dir.glob("*.py"))
                    if files:
                        print(f"   {binding_dir.name}/ ({len(files)} files)")

        return 0 if fail_count == 0 else 1

    # GitHub Release Mode
    if args.github_release:
        return run_github_release_mode(
            release_url=args.github_release,
            output_dir=args.output,
            keep_wasm=args.keep_wasm,
            contracts=args.contracts,
            deploy_release_url=args.deploy_release,
            network=args.network,
            json_only=args.json_only
        )

    # ========================================
    # Deploy Mode (default)
    # ========================================
    print("\n🚀 Deploy Mode")
    print("   Uploading WASM, deploying contracts, and generating bindings\n")

    # Load deployment account
    source_key = load_account()
    if not source_key:
        sys.exit(1)
    
    # Update network settings if specified
    if args.network != NETWORK and args.network in NETWORK_CONFIGS:
        NETWORK = args.network
        NETWORK_PASSPHRASE = NETWORK_CONFIGS[NETWORK]["passphrase"]
        RPC_URL = NETWORK_CONFIGS[NETWORK]["rpc_url"]
    
    print(f"Generating bindings for network: {NETWORK}")
    print(f"RPC URL: {RPC_URL}\n")
    
    # Ensure wasm directory exists
    wasm_dir = Path(WASM_DIR)
    if not wasm_dir.exists():
        print(f"❌ Error: {wasm_dir} directory not found")
        sys.exit(1)
    
    # Process each optimized WASM file
    wasm_files = list(wasm_dir.glob("*.optimized.wasm"))
    if not wasm_files:
        print("❌ No optimized WASM files found in the wasm directory")
        sys.exit(1)
    
    # Load existing deployments
    deployments = load_deployments()
    
    success_count = 0
    skip_count = 0
    fail_count = 0

    for wasm_file in wasm_files:
        contract_name = wasm_file.stem.replace('.optimized', '')
        print(f"\n=== Processing {contract_name} ===")

        # Skip upload-only contracts in deploy mode (they don't have contract IDs)
        if contract_name in UPLOAD_ONLY_CONTRACTS:
            print(f"⏭️  Skipping {contract_name} (upload-only contract, no contract ID)")
            print(f"   Use --github-release mode to generate bindings from WASM directly")
            skip_count += 1
            continue

        # Check if we should skip existing
        if args.skip_existing and contract_name in deployments:
            print(f"✓ Using existing deployment for {contract_name}")
            contract_id = deployments[contract_name].get('contract_id')
            if not contract_id:
                print(f"⚠️  No contract ID found for {contract_name} in deployments, skipping")
                skip_count += 1
                continue
        else:
            # 1. Upload WASM
            wasm_hash = upload_wasm(wasm_file, source_key)
            if not wasm_hash:
                fail_count += 1
                continue

            # 2. Deploy contract instance
            contract_id = deploy_contract_instance(contract_name, wasm_hash, source_key)
            if not contract_id:
                print(f"⚠️  Failed to deploy {contract_name}, skipping bindings generation")
                fail_count += 1
                continue

            # Update deployments
            deployments[contract_name] = {
                'contract_id': contract_id,
                'wasm_hash': wasm_hash,
                'network': NETWORK,
                'timestamp': int(time.time())
            }
            save_deployments(deployments)

        # 3. Generate bindings (only if we have a valid contract_id)
        if not contract_id:
            print(f"⚠️  No contract ID available for {contract_name}, skipping bindings")
            skip_count += 1
            continue

        if not generate_bindings(contract_name, contract_id):
            print(f"⚠️  Failed to generate bindings for {contract_name}")
            fail_count += 1
            continue

        success_count += 1

    # Summary
    print(f"\n{'='*50}")
    print(f"📊 Summary: {success_count} succeeded, {skip_count} skipped, {fail_count} failed")

    if skip_count > 0:
        print(f"\n💡 Tip: Use --github-release mode to generate bindings for upload-only contracts")
        print(f"   python generate_bindings.py --github-release <release-url> --keep-wasm")

    print("\n✅ Bindings generation complete!")
    return 0 if fail_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
