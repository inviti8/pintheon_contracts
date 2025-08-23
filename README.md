# Pintheon Contracts - Soroban Smart Contracts

This repository contains Soroban smart contracts for the Philos ecosystem, including HVYM Collective, Opus Token, and Pintheon tokens.

## Requirements

- **Soroban SDK**: 22.0.8
- **Stellar CLI**: 22.0.0
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

### Contract Structure

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