import os
import requests
import re

REPO = "inviti8/pintheon_contracts"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Optional, for private repos or higher rate limits

# Base directory for downloaded WASM files
WASM_RELEASE_DIR = "wasm_release"

# Expected contract names from our workflow
EXPECTED_CONTRACTS = [
    "hvym-collective",
    "opus-token", 
    "pintheon-node-token",
    "pintheon-ipfs-token"
]

API_URL = f"https://api.github.com/repos/{REPO}/releases"
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

def extract_contract_name(asset_name):
    """Extract contract name from WASM asset name like 'pintheon-node-token_v0.0.6.wasm'"""
    # Remove version suffix and .wasm extension
    # Pattern: contract-name_vX.Y.Z.wasm -> contract-name
    match = re.match(r'^(.+?)_v\d+\.\d+\.\d+\.wasm$', asset_name)
    if match:
        return match.group(1)
    return None

def create_wasm_release_structure():
    """Create the wasm_release directory structure"""
    os.makedirs(WASM_RELEASE_DIR, exist_ok=True)
    print(f"Created directory: {WASM_RELEASE_DIR}")

def get_latest_release_for_contract(contract_name):
    """Get the most recent release that contains WASM files for a specific contract"""
    
    # Get all releases (we'll limit to recent ones for performance)
    resp = requests.get(f"{API_URL}?per_page=30", headers=HEADERS)
    resp.raise_for_status()
    releases = resp.json()
    
    for release in releases:
        # Skip drafts and prereleases
        if release.get("draft") or release.get("prerelease"):
            continue
            
        # Look for WASM assets for this contract
        for asset in release["assets"]:
            if asset["name"].endswith(".wasm"):
                extracted_contract = extract_contract_name(asset["name"])
                if extracted_contract == contract_name:
                    return release, asset
    
    return None, None

# Create directory structure
create_wasm_release_structure()

# Download WASM files for each expected contract
downloaded_files = []
for contract_name in EXPECTED_CONTRACTS:
    print(f"\nLooking for latest release for {contract_name}...")
    
    release, asset = get_latest_release_for_contract(contract_name)
    
    if not release or not asset:
        print(f"Warning: No recent release found for {contract_name}")
        continue
    
    print(f"Found release: {release['name']} ({release['tag_name']})")
    
    # Create contract-specific directory
    contract_dir = os.path.join(WASM_RELEASE_DIR, contract_name)
    os.makedirs(contract_dir, exist_ok=True)
    
    print(f"Downloading {asset['name']} to {contract_dir} ...")
    download_url = asset["browser_download_url"]
    wasm_data = requests.get(download_url, headers=HEADERS)
    wasm_data.raise_for_status()

    target_path = os.path.join(contract_dir, asset["name"])
    with open(target_path, "wb") as f:
        f.write(wasm_data.content)
    
    downloaded_files.append({
        "contract": contract_name,
        "file": asset["name"],
        "path": target_path,
        "release": release["name"],
        "tag": release["tag_name"]
    })
    print(f"Saved to {target_path}")

# Summary
print(f"\nDownload Summary:")
print(f"Total files downloaded: {len(downloaded_files)}")
for file_info in downloaded_files:
    print(f"  - {file_info['contract']}: {file_info['file']} (from {file_info['release']})")

print(f"\nAll WASM files downloaded to {WASM_RELEASE_DIR}/ directory structure.")
print("Directory structure:")
for file_info in downloaded_files:
    print(f"  {WASM_RELEASE_DIR}/{file_info['contract']}/{file_info['file']}")