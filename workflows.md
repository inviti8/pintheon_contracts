# Soroban Contract Workflows

This document describes the step-by-step workflows for building, testing, deploying, and post-deployment actions for the contracts in this repository. Each script is designed to automate a part of the process and should be run from the project root.

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

## 2. Download Official Release WASM Files

**Script:** `download_wasm_releases.py`

Downloads the latest WASM files from GitHub releases and organizes them into a clean directory structure for deployment.

### Usage

```bash
python3 download_wasm_releases.py
```

This creates the directory structure:
```
wasm_release/
├── hvym-collective/
│   └── hvym-collective_v0.0.1.wasm
├── opus-token/
│   └── opus-token_v0.0.6.wasm
├── pintheon-node-token/
│   └── pintheon-node-token_v0.0.6.wasm
└── pintheon-ipfs-token/
    └── pintheon-ipfs-token_v0.0.6.wasm
```

### Arguments
- No command-line arguments required. The script automatically:
  - Fetches the latest releases from GitHub
  - Downloads WASM files for all expected contracts
  - Organizes files by contract name in `wasm_release/` directory

### Environment Variables
- `GITHUB_TOKEN`: (Optional) GitHub personal access token for higher rate limits or private repository access.

### Notes
- Downloads the most recent release for each contract
- Organizes files by contract name for easy access
- Used for production deployments with official release files
- Requires internet connection to access GitHub API

---

## 3. Test Contracts

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

### Official Release Mode

Use WASM files downloaded from GitHub releases:

```bash
# Deploy all contracts using official release WASM files
python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --official-release

# Deploy a specific contract using official release
python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --contract hvym-collective --official-release

# Deploy with custom constructor arguments (official release)
python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --contract hvym-collective --official-release --constructor-args --admin G... --join-fee 100 --mint-fee 10 --token G... --reward 5
```

### Arguments
- `--deployer-acct <name>`: (Required) Stellar CLI account name or secret to use as deployer. This account will be used as the source account for all upload and deploy operations.
- `--network <name>`: (Optional) Network name for deployment. Default: `testnet`. Options: `testnet`, `mainnet`, or custom network name.
- `--contract <short_name>`: (Optional) Deploy only the specified contract. If omitted, deploys all contracts in order. Valid short names: `pintheon-ipfs-token`, `pintheon-node-token`, `opus_token`, `hvym-collective`.
- `--constructor-args ...`: (Optional) Arguments for the contract constructor. If omitted, arguments are loaded from `<contract>_args.json`. All arguments after this flag are passed to the contract constructor.
- `--official-release`: (Optional) Use WASM files from the `wasm_release` directory instead of locally built files. Requires running `download_wasm_releases.py` first.

### Notes
- For `hvym-collective`, ensure you have a `hvym-collective_args.json` file with all required constructor arguments.
- The script updates `deployments.json` and `deployments.md` with contract hashes and IDs.
- When using `--official-release`, ensure you have run `download_wasm_releases.py` first.
- Upload-only contracts (`pintheon-ipfs-token`, `pintheon-node-token`, `opus_token`) are uploaded but not deployed.
- Deploy-only contracts (`hvym-collective`) are both uploaded and deployed.

---

## 5. Deploy Node and IPFS Tokens

**Script:** `deploy_node_and_ipfs.py`

Deploys `pintheon-ipfs-token` and `pintheon-node-token` contracts. Can use either WASM hashes from `deployments.json` or official release WASM files.

### Development Mode (Default)

Use WASM hashes from `deployments.json` (requires contracts to be uploaded first):

```bash
# Deploy both contracts using hashes from deployments.json
python3 deploy_node_and_ipfs.py --deployer-acct <ACCOUNT_NAME>

# Deploy a specific contract using hash from deployments.json
python3 deploy_node_and_ipfs.py --deployer-acct <ACCOUNT_NAME> --contract pintheon-ipfs-token
```

### Official Release Mode

Use WASM files downloaded from GitHub releases:

```bash
# Deploy both contracts using official release WASM files
python3 deploy_node_and_ipfs.py --deployer-acct <ACCOUNT_NAME> --official-release

# Deploy a specific contract using official release
python3 deploy_node_and_ipfs.py --deployer-acct <ACCOUNT_NAME> --contract pintheon-ipfs-token --official-release
```

### Arguments
- `--deployer-acct <name>`: (Required) Stellar CLI account name or secret to use as deployer. This account will be used as the source account for deploy operations.
- `--network <name>`: (Optional) Network name for deployment. Default: `testnet`. Options: `testnet`, `mainnet`, or custom network name.
- `--contract <name>`: (Optional) Deploy only the specified contract. If omitted, deploys both contracts. Valid options: `pintheon-ipfs-token` or `pintheon-node-token`.
- `--official-release`: (Optional) Use WASM files from the `wasm_release` directory instead of hashes from `deployments.json`. Requires running `download_wasm_releases.py` first.

### Notes
- **Development mode**: Requires `pintheon-ipfs-token_args.json` and `pintheon-node-token_args.json` files with constructor arguments. Uses WASM hashes from `deployments.json` (contracts must be uploaded first via `deploy_contracts.py`).
- **Official release mode**: Requires `pintheon-ipfs-token_args.json` and `pintheon-node-token_args.json` files with constructor arguments. Uploads and deploys contracts directly from official release WASM files.
- Only prints contract IDs to terminal; does not update deployment records.
- When using `--official-release`, ensure you have run `download_wasm_releases.py` first.

---

## 6. Post-Deployment Actions

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

## 7. Constructor Argument JSON Files

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
4. **Deploy node and IPFS tokens** (optional): `python3 deploy_node_and_ipfs.py --deployer-acct <ACCOUNT_NAME>`
5. **Post-deploy** actions: `python3 hvym_post_deploy.py --deployer-acct <ACCOUNT_NAME> --fund-amount ... --initial-opus-alloc ...`

### For Production:
1. **Download** official releases: `python3 download_wasm_releases.py`
2. **Deploy** contracts: `python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --official-release`
3. **Deploy node and IPFS tokens** (optional): `python3 deploy_node_and_ipfs.py --deployer-acct <ACCOUNT_NAME> --official-release`
4. **Post-deploy** actions: `python3 hvym_post_deploy.py --deployer-acct <ACCOUNT_NAME> --fund-amount ... --initial-opus-alloc ...`

### Alternative Production Workflow:
1. **Download** official releases: `python3 download_wasm_releases.py`
2. **Deploy all contracts** (including node and IPFS tokens): `python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --official-release`
3. **Post-deploy** actions: `python3 hvym_post_deploy.py --deployer-acct <ACCOUNT_NAME> --fund-amount ... --initial-opus-alloc ...`

---

For any questions or to add new contracts, update the relevant scripts and JSON files accordingly. 