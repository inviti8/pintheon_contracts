# Soroban Contract Workflows

This document describes the step-by-step workflows for building, testing, deploying, and post-deployment actions for the contracts in this repository. Each script is designed to automate a part of the process and should be run from the project root.

## Table of Contents

1. [Build Contracts](#1-build-contracts)
2. [Test Contracts](#2-test-contracts)
3. [Deploy Contracts](#3-deploy-contracts)
4. [Deploy with XDR Workaround](#4-deploy-with-xdr-workaround)
5. [Deploy Released Contracts](#5-deploy-released-contracts)
6. [Deploy Collective Dependency Contracts](#6-deploy-collective-dependency-contracts)
7. [Post-Deployment Actions](#7-post-deployment-actions)
8. [Constructor Arguments](#8-constructor-arguments)

---

## 1. Build Contracts

**Script:** `build_contracts.py`

Builds all Soroban contracts in the correct order, or a specific contract if requested. Cleans build artifacts, builds, and optimizes the contract WASM.

### Usage

- Build all contracts in order:
  ```bash
  python3 build_contracts.py
  ```
- Build a specific contract (by directory):
  ```bash
  python3 build_contracts.py --contract opus_token
  ```

### Arguments
- `--contract <dir>`: (Optional) Build only the specified contract directory. If omitted, builds all contracts in dependency order.

---

## 2. Test Contracts

**Script:** `test_contract.py`

Runs `cargo test` in a specified contract or crate directory.

### Usage

- Test a specific contract/crate:
  ```bash
  python3 test_contract.py opus_token
  ```

### Arguments
- `<target_dir>`: (Required) The directory containing a `Cargo.toml` to test. Must be a valid contract directory.

---

## 4. Deploy Contracts

**Script:** `deploy_contracts.py`

Uploads and/or deploys contracts in the correct order. Only `hvym-collective` is deployed; the other contracts are uploaded and their WASM hashes are stored. Constructor arguments are loaded from JSON files if not provided on the command line.

### Development Mode (Default)

Use locally built WASM files from the contract directories:

```bash
# Deploy all contracts using locally built WASM files
python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME>

# Deploy a specific contract
python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --contract hvym-collective

# Deploy with custom constructor arguments
python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --contract hvym-collective --constructor-args --admin G... --join-fee 100 --mint-fee 10 --token G... --reward 5
```

### Cloud Deployment

For production deployments, the CI/CD pipeline will automatically build and deploy the contracts. The pipeline will:

1. Build all contracts in the correct order
2. Run all tests to ensure code quality
3. Deploy the contracts to the specified network
4. Update the deployment records

To trigger a deployment, push your changes to the main branch or create a release tag.

### Arguments
- `--deployer-acct <name>`: (Required) Stellar CLI account name or secret to use as deployer.
- `--network <name>`: (Optional) Network name. Default: `testnet`.
- `--contract <short_name>`: (Optional) Deploy only the specified contract.
- `--constructor-args ...`: (Optional) Arguments for the contract constructor.
- `--official-release`: (Optional) Use WASM files from `wasm_release`.

### Notes
- Updates `deployments.json` and `deployments.md`.
- For `hvym-collective`, you need a `hvym-collective_args.json` file.
- The pipeline will handle building and deploying the contracts automatically.
- Upload-only contracts: `pintheon-ipfs-token`, `pintheon-node-token`, `opus_token`.
- Deploy-only contract: `hvym-collective`.

---

## 4. Deploy with XDR Workaround

**Script:** `deploy_with_xdr_workaround.py`

This script provides a workaround for XDR processing errors in the Stellar CLI by verifying transaction success via Stellar's API. It's the recommended way to deploy contracts as it handles network issues more gracefully.

### Features
- Works around XDR processing errors in the Stellar CLI
- Supports both local development and cloud deployment modes
- Uploads contract WASM files with automatic retries
- Deploys contracts with proper initialization
- Maintains a record of deployments in `deployments.json`
- Generates a markdown summary in `deployments.md`
- Supports testnet, futurenet, and mainnet deployments

### Usage

#### Local Development Mode
Builds and deploys contracts from source:
```bash
python3 deploy_with_xdr_workaround.py \
  --mode local \
  --network testnet
```

#### Cloud Deployment Mode
Uses pre-built WASM files (for CI/CD):
```bash
python3 deploy_with_xdr_workaround.py \
  --mode cloud \
  --wasm-dir ./release-wasm \
  --deployer-account YOUR_ACCOUNT \
  --network testnet \
  --rpc-url https://soroban-testnet.stellar.org
```

### Arguments
- `--mode`: Deployment mode - `local` (build and deploy) or `cloud` (use pre-built WASM)
- `--wasm-dir`: Directory containing pre-built WASM files (required for cloud mode)
- `--deployer-account`: Account to use for deployment (required for cloud mode)
- `--network`: Stellar network (`testnet`, `futurenet`, or `mainnet`)
- `--rpc-url`: Custom RPC URL (default: based on network)
- `--post-deploy-config`: Path to post-deployment JSON config (default: `hvym-collective_post_deploy_args.json`)
- `--skip-post-deploy`: Skip post-deployment steps
- `--strict`: Fail on any error during deployment or post-deployment

### Deployment Configuration

#### Constructor Arguments (`hvym-collective_args.json`)

The `hvym-collective` contract requires constructor arguments that can be provided in a JSON file. This file is automatically handled during deployment:

1. **Cloud Deployments**:
   - Looks for `hvym-collective_args.json` in the release artifacts
   - Falls back to default values if not found
   - Always uses the latest OPUS token address from the current deployment

2. **Local Development**:
   - Looks for `hvym-collective_args.json` in the project root
   - Falls back to default values if not found

Example `hvym-collective_args.json`:
```json
{
  "admin": "GABCD...",         // Admin account address
  "token": "CDLZFC3SYJYDZT...", // Payment token address (e.g., XLM or other asset)
  "join_fee": 1.0,             // In XLM (will be converted to stroops)
  "mint_fee": 0.5,             // In XLM (will be converted to stroops)
  "reward": 0.1                // In XLM (will be converted to stroops)
  // Note: opus_token is automatically added during deployment
}
```

#### Post-Deployment Configuration (`hvym-collective_post_deploy_args.json`)

Post-deployment steps for the `hvym-collective` contract are configured in a separate JSON file:

```json
{
  "fund_amount": 30.0,         // XLM to fund the contract with
  "initial_opus_alloc": 1000.0, // Initial OPUS token allocation
  "enabled": true             // Set to false to disable post-deployment
}
```

### GitHub Actions Integration

This script is used in the `custom-deploy.yml` workflow for cloud deployments. It automatically:
- Verifies WASM files
- Deploys contracts in the correct order
- Runs post-deployment steps if configured
- Saves deployment details as artifacts
- Generates a deployment summary

#### Post-Deployment Steps in CI/CD

1. The workflow creates a configuration file with default values
2. The deployment script runs with the `--post-deploy-config` parameter
3. After successful deployment, post-deployment steps are executed
4. Results are included in the deployment summary

### Arguments
- `--contract`: Name of the contract to deploy
- `--wasm`: Path to the WASM file
- `--network`: Network to deploy to (default: testnet)
- `--deployer-account`: Stellar account to use for deployment
- `--constructor-args`: JSON string of constructor arguments (optional)
- `--force`: Force deployment even if contract already exists
- `--debug`: Enable debug output

### Features
- Works around XDR processing errors
- Verifies transactions using Stellar Expert API
- Extracts contract addresses from successful deployments
- Handles both upload and deployment steps

---

## 7. Deploy Released Contracts

**Script:** `deploy_released_contracts.py`

Deploys pre-released contract versions from the `wasm_release` directory.

### Usage

```bash
# Deploy all released contracts
python3 deploy_released_contracts.py --deployer-account DEPLOYER_ACCOUNT --network testnet

# Deploy a specific contract
python3 deploy_released_contracts.py --contract opus-token --deployer-account test-deployer --network testnet

# Deploy with debug output
python3 deploy_released_contracts.py --contract pintheon-node-token --deployer-account test-deployer --debug
```

### Arguments
- `--contract`: Specific contract to deploy (default: all)
- `--deployer-account`: Stellar account to use for deployment
- `--network`: Network to deploy to (default: testnet)
- `--rpc-url`: Custom RPC URL (optional)
- `--debug`: Enable debug output

### Features
- Deploys from pre-built WASM files
- Handles XDR workarounds
- Verifies deployments
- Supports custom RPC endpoints

---

## 8. Deploy Collective Dependency Contracts

**Script:** `deploy_collective_dependency_contracts.py`

Deploys contracts that have dependencies on each other, specifically designed for the Pintheon IPFS and Node tokens.

### Usage

```bash
# Deploy all dependency contracts
python3 deploy_collective_dependency_contracts.py --deployer-account DEPLOYER_ACCOUNT --network testnet

# Deploy a specific contract
python3 deploy_collective_dependency_contracts.py --contract pintheon-ipfs-token --deployer-account test-deployer

# Use official release WASM files
python3 deploy_collective_dependency_contracts.py --official-release --deployer-account test-deployer
```

### Arguments
- `--contract`: Specific contract to deploy (pintheon-ipfs-token or pintheon-node-token)
- `--deployer-account`: Stellar account to use for deployment
- `--network`: Network to deploy to (default: testnet)
- `--official-release`: Use WASM files from wasm_release directory
- `--force`: Force deployment even if contract exists

### Features
- Handles contract dependencies
- Supports both local and official release WASM files

**Script:** `hvym_post_deploy.py`

Funds the `hvym-collective` contract and launches the opus token via contract invocation. Updates `deployments.json` with the opus token contract ID.

### Usage

```bash
python3 hvym_post_deploy.py --deployer-acct <ACCOUNT_NAME> --fund-amount 30 --initial-opus-alloc 10
```

### Arguments
- `--deployer-acct <name>`: (Required) Stellar CLI account name or secret to use as source. This account will be used as the source account for fund and mint operations.
- `--network <name>`: (Optional) Network name for operations. Default: `testnet`. Options: `testnet`, `mainnet`, or custom network name.
- `--fund-amount <XLM>`: (Required) Amount to fund the contract in XLM (whole number). The script automatically converts to stroops (1 XLM = 10^7 stroops). Example: `30` for 30 XLM.
- `--initial-opus-alloc <XLM>`: (Required) Initial opus token allocation to mint to admin in XLM (whole number). The script automatically converts to stroops. Example: `10` for 10 XLM.

### Notes
- `--fund-amount` and `--initial-opus-alloc` are specified as whole numbers in XLM (e.g., `30` for 30 XLM). The script automatically converts these to stroops (1 XLM = 10^7 stroops).
- Requires the `hvym-collective` contract to be deployed first.
- Updates `deployments.json` with the opus token contract ID.
- Performs contract invocations to fund the contract and launch the opus token.

---

## 6. Constructor Arguments JSON Files

For contracts that require constructor arguments, create a JSON file named `<contract>_args.json` (e.g., `hvym-collective_args.json`) with all required fields. Example:

```json
{
  "admin": "G...",
  "join_fee": 100,
  "mint_fee": 10,
  "token": "G...",
  "reward": 5
}
```

### File Naming Convention
- `hvym-collective_args.json` - Arguments for hvym-collective contract
- `pintheon-ipfs-token_args.json` - Arguments for pintheon-ipfs-token contract
- `pintheon-node-token_args.json` - Arguments for pintheon-node-token contract

### Notes
- All monetary values (fees, rewards) are automatically converted to stroops by the deployment scripts.
- Address values should be valid Stellar addresses (G... format).
- If constructor arguments are provided via command line, the JSON file is ignored.

---

## 8. Deployment Records

- `deployments.json`: Machine-readable record of all contract uploads and deployments (hashes and IDs). Used by scripts to track deployment state.
- `deployments.md`: Human-readable markdown table of all contract uploads and deployments. Provides a quick overview of deployment status.

### File Format
The `deployments.json` file contains:
```json
{
  "contract_name": {
    "contract_dir": "path/to/contract",
    "wasm_hash": "64-character-hex-hash",
    "contract_id": "56-character-contract-id"
  }
}
```

---

## Workflow Order

### For Development:
1. **Build** all contracts: `python3 build_contracts.py`
2. **Test** contracts as needed: `python3 test_contract.py <dir>`
3. **Deploy** contracts: `python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME>`
4. **Post-deploy** actions: `python3 hvym_post_deploy.py --deployer-acct <ACCOUNT_NAME> --fund-amount ... --initial-opus-alloc ...`

### For Production:
1. **Push** changes to the main branch or create a release tag
2. The CI/CD pipeline will automatically build, test, and deploy the contracts
3. **Post-deploy** actions will be handled by the pipeline

### Manual Deployment (if needed):
1. **Build** contracts: `python3 build_contracts.py`
2. **Deploy** contracts: `python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME>`
3. **Post-deploy** actions: `python3 hvym_post_deploy.py --deployer-acct <ACCOUNT_NAME> --fund-amount ... --initial-opus-alloc ...`

---

For any questions or to add new contracts, update the relevant scripts and JSON files accordingly. 