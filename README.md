# Pintheon Contracts - Soroban Smart Contracts

This repository contains Soroban smart contracts for the Philos ecosystem, including HVYM Collective, Opus Token, and Pintheon tokens.

## Requirements

- **Soroban SDK**: 22.0.8
- **Stellar CLI**: 22.8.2
- **Rust**: Latest stable with `wasm32-unknown-unknown` target

## Contract Validation on stellar.expert

This repository is configured with a GitHub Actions workflow that automatically builds and releases contracts for validation on [stellar.expert](https://stellar.expert/explorer/testnet/contract/validation).

### Contract Dependencies

⚠️ **The `hvym-collective` contract depends on other contracts** in this repository. It uses `contractimport!` to import:
- `pintheon-node-token`
- `pintheon-ipfs-token` 
- `opus-token`

This means the standard stellar-expert workflow won't work because it builds contracts in isolation. **You must use the custom workflow.**

📖 **See [IMPORT_NAMING_GUIDE.md](IMPORT_NAMING_GUIDE.md)** for detailed instructions on how to determine the correct import file names when updating contract dependencies.

### Workflow

- Use `.github/workflows/custom-release.yml` 
- Handles dependency order correctly
- Builds dependencies first, then `hvym-collective`

### How to Trigger a Release

1. **Create and push a new tag** (this triggers the workflow):
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **The custom workflow will automatically:**
   - Build dependency contracts first (opus_token, pintheon_node_token, pintheon_ipfs_token)
   - Build hvym-collective with dependencies available
   - Create optimized WASM files
   - Generate GitHub releases with build artifacts
   - Include SHA256 hashes for verification
   - Generate build attestations
   - Submit contract validation data to StellarExpert

## Python Bindings

This repository includes scripts to generate Python bindings for interacting with the Soroban smart contracts using the `stellar-contract-bindings` tool.

### Prerequisites

1. Activate the Python virtual environment:
   ```bash
   pyenv activate pintheon_contracts
   ```

2. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

### Generating Bindings

1. First, ensure you have built the contract WASM files (they should be in the `wasm/` directory).

2. Generate Python bindings for all contracts:
   ```bash
   python generate_bindings.py
   ```

3. Or generate bindings for a specific contract:
   ```bash
   python generate_bindings.py --contract hvym-collective
   ```

### Using the Generated Bindings

Example of using the generated Python bindings:

```python
from stellar_sdk import Keypair, Network
from bindings.hvym_collective.client import Client as HvymCollectiveClient

# Initialize the client
client = HvymCollectiveClient(
    contract_id="YOUR_CONTRACT_ID",
    rpc_url="https://soroban-testnet.stellar.org",
    network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE
)

# Call contract methods
admin_list = client.get_admin_list()
print("Admin list:", admin_list)

# For transactions that require signing
source_kp = Keypair.from_secret("YOUR_SECRET_KEY")
tx = client.add_admin(
    admin_to_add="GB123...",
    source=source_kp
)
result = tx.sign_and_send()
print("Transaction result:", result)
```

## Contract ID Extraction

The deployment script includes a robust contract ID extraction mechanism that works around limitations in the Stellar network's transaction result processing. This is particularly important for Soroban smart contracts where the contract ID is not always directly available in the transaction result.

### How It Works

1. **Selenium-based Extraction (Primary Method)**
   - The script uses a headless Chrome browser to load the transaction page on Stellar Expert
   - It waits for the contract link to appear in the transaction details
   - The contract ID is extracted from the link URL
   - Includes automatic retries and error handling for reliability

2. **Fallback Methods**
   - If Selenium extraction fails, the script falls back to parsing the CLI output
   - As a last resort, it attempts to extract the contract ID from the Horizon API

### Requirements for Selenium

- Chrome or Chromium browser installed
- ChromeDriver (automatically managed by the script)
- Python packages: `selenium`, `webdriver-manager`

### Troubleshooting

If contract ID extraction fails:
1. Check that Chrome/Chromium is installed
2. Ensure the system has a graphical environment (even in headless mode)
3. Look for error logs in the script output
4. Check for screenshots saved as `stellar_expert_error_*.png` for debugging

## Contract Structure

- `hvym-collective/` - Main collective contract
- `opus_token/` - OPUS token contract
- `pintheon-node-deployer/pintheon-node-token/` - Node token contract
- `pintheon-ipfs-deployer/pintheon-ipfs-token/` - IPFS token contract

### Validation Process

After deployment, contracts are automatically validated on stellar.expert because:

1. The workflow submits binary hash, repository name, and commit SHA to StellarExpert's validation API
2. Contracts are built from GitHub releases with matching hashes
3. Source code is available for display on stellar.expert explorer

### Manual Workflow Trigger

You can also trigger the workflow manually:

1. Go to GitHub Actions tab
2. Select "Custom Build and Release Soroban Contracts"
3. Click "Run workflow"
4. Enter a unique release name
5. Click "Run workflow"

### Important Notes

- The custom workflow is required for `hvym-collective` and any contracts with dependencies
- Contracts must have unique names and versions to avoid conflicts
- Build attestations are generated for security verification

### Deployment

Use the deployment scripts in this repository to deploy contracts to the Stellar network:

- `deploy_contracts.py` - Main deployment script
- `hvym_post_deploy.py` - Post-deployment operations
- `deploy_node_and_ipfs.py` - Deploy Pintheon tokens

For more information about deployment, see `workflows.md`. 