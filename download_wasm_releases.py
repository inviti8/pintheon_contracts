import os
import requests

REPO = "inviti8/pintheon_contracts"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Optional, for private repos or higher rate limits

# Map each WASM asset name to its explicit target directory
WASM_PATHS = {
    "hvym_collective.optimized.wasm": "hvym-collective/target/release",
    "opus_token.optimized.wasm": "opus_token/target/release",
    "pintheon_node_token.optimized.wasm": "pintheon-node-deployer/pintheon-node-token/target/release",
    "pintheon_ipfs_token.optimized.wasm": "pintheon-ipfs-deployer/pintheon-ipfs-token/target/release",
    # Add more mappings as needed
}

API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

# Fetch latest release info
resp = requests.get(API_URL, headers=HEADERS)
resp.raise_for_status()
release = resp.json()

print(f"Latest release: {release['name']} ({release['tag_name']})")

# Download each WASM asset
for asset in release["assets"]:
    if asset["name"].endswith(".wasm"):
        if asset["name"] not in WASM_PATHS:
            print(f"Warning: No target path mapped for {asset['name']}, skipping.")
            continue
        target_dir = WASM_PATHS[asset["name"]]
        print(f"Downloading {asset['name']} to {target_dir} ...")
        download_url = asset["browser_download_url"]
        wasm_data = requests.get(download_url, headers=HEADERS)
        wasm_data.raise_for_status()

        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, asset["name"])

        with open(target_path, "wb") as f:
            f.write(wasm_data.content)
        print(f"Saved to {target_path}")

print("All mapped WASM assets downloaded and placed in their target/release folders.")