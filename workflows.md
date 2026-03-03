# Soroban Contract Workflows

This document describes the step-by-step workflows for building, testing, deploying, and generating bindings for the contracts in this repository. All scripts are run from the project root.

## Table of Contents

1. [Build Contracts](#1-build-contracts)
2. [Test Contracts](#2-test-contracts)
3. [Deploy Contracts](#3-deploy-contracts)
4. [Post-Deployment Actions](#4-post-deployment-actions)
5. [Generate Bindings](#5-generate-bindings)
6. [Constructor Arguments](#6-constructor-arguments)
7. [Deployment Records](#7-deployment-records)
8. [Workflow Order](#8-workflow-order)

---

## 1. Build Contracts

**Script:** `build_contracts.py`

Builds all Soroban contracts in dependency order, or a single contract if specified. Each contract is compiled and optimized to a `.wasm` file in the `wasm/` directory.

### Build Order

```
pintheon-node-deployer/pintheon-node-token
pintheon-ipfs-deployer/pintheon-ipfs-token
opus_token
hvym-collective
hvym-roster
hvym-pin-service
hvym-pin-service-factory   ← depends on hvym-pin-service (embeds its WASM)
```

### Usage

```bash
# Build all contracts in dependency order
python build_contracts.py

# Build a specific contract only
python build_contracts.py --contract hvym-pin-service
```

### Arguments

| Argument | Description |
|---|---|
| `--contract <dir>` | (Optional) Build only the specified contract directory. Omit to build all. |

### Notes
- `hvym-pin-service-factory` must be built **after** `hvym-pin-service` because it embeds the pin service WASM via `contractimport!`. If the pin service ABI changes, rebuild both.
- Optimized WASM files are copied to the `wasm/` directory for deployment.

---

## 2. Test Contracts

### Test All Contracts

**Script:** `test_all_contracts.py`

Runs `cargo test` for all contracts in the same order as the build.

```bash
python test_all_contracts.py
```

### Test a Single Contract

**Script:** `test_contract.py`

Runs `cargo test` in a single contract directory.

```bash
python test_contract.py hvym-pin-service
python test_contract.py hvym-pin-service-factory
python test_contract.py hvym-collective
```

### Arguments (`test_contract.py`)

| Argument | Description |
|---|---|
| `<target_dir>` | (Required) The contract directory containing a `Cargo.toml`. |

---

## 3. Deploy Contracts

**Script:** `deploy_contracts.py`

Uploads and/or deploys all contracts from the `wasm/` directory in the correct order. Reads constructor arguments from `<contract>_args.json` files in the project root. Updates `deployments.json` and `deployments.md` after each contract.

### Contract Categories

**Upload-only** (WASM hash stored, no contract ID — deployed dynamically by `hvym-collective`):
- `pintheon_ipfs_token`
- `pintheon_node_token`

**Deployed** (full deployment, contract ID stored):
- `opus_token`
- `hvym_collective`
- `hvym_roster`
- `hvym_pin_service`
- `hvym_pin_service_factory`

### Usage

```bash
# Deploy all contracts
python deploy_contracts.py --deployer-acct <ACCOUNT_NAME>

# Deploy to a specific network
python deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --network testnet

# Deploy using WASM files from a custom directory
python deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --wasm-dir ./wasm
```

### Arguments

| Argument | Default | Description |
|---|---|---|
| `--deployer-acct` | (required) | Stellar CLI account name or secret key to use as deployer. |
| `--network` | `testnet` | Network to deploy to (`testnet`, `futurenet`, `public`, `standalone`). Can also be set via `STELLAR_NETWORK` env var. |
| `--wasm-dir` | `./wasm` | Directory containing optimized `.wasm` files. |

### Notes
- Constructor arguments are loaded from `<contract_name>_args.json` files automatically.
- Monetary values in args files (fees, prices) are specified in XLM and automatically converted to stroops (×10,000,000).
- `STELLAR_NETWORK` environment variable can set the network before running the script.

---

## 4. Post-Deployment Actions

**Script:** `hvym_post_deploy.py`

Funds the `hvym-collective` contract with XLM and mints the initial OPUS token allocation to the admin. Run this after deploying `hvym-collective`.

### Usage

```bash
python hvym_post_deploy.py \
  --deployer-acct <ACCOUNT_NAME> \
  --fund-amount 30 \
  --initial-opus-alloc 40
```

### Arguments

| Argument | Description |
|---|---|
| `--deployer-acct` | (Required) Stellar CLI account name or secret key. |
| `--network` | (Optional) Network name. Default: `testnet`. |
| `--fund-amount` | (Required) XLM to fund the contract with (whole number, e.g. `30`). |
| `--initial-opus-alloc` | (Required) Initial OPUS token allocation to mint to admin in XLM (e.g. `40`). |

### Notes
- Values are specified in XLM — the script converts to stroops internally.
- Requires `hvym-collective` to be deployed and its contract ID to be in `deployments.json`.
- Updates `deployments.json` with the opus token contract ID.

---

## 5. Generate Bindings

**Script:** `generate_bindings.py`

Generates Python client bindings for deployed contracts using `stellar-contract-bindings`. Requires the venv to be activated.

### Activate the Virtual Environment

```bash
source pintheon-contracts/Scripts/activate
```

### From Deployments File (recommended)

Reads contract IDs from `deployments.json` and generates bindings for all contracts that have a `contract_id`:

```bash
python generate_bindings.py --from-file deployments.json
```

### Filter Specific Contracts

```bash
python generate_bindings.py --from-file deployments.json \
  --contracts hvym_pin_service hvym_pin_service_factory
```

### From GitHub Release

```bash
python generate_bindings.py \
  --github-release https://github.com/owner/repo/releases/tag/deploy-v1.0.0
```

### Arguments

| Argument | Description |
|---|---|
| `--from-file <FILE>` | Generate bindings from a local deployments JSON file. |
| `--github-release <URL>` | Generate bindings using contract IDs from a GitHub release. |
| `--contracts <names...>` | (Optional) Only process the listed contract names. |
| `--network <name>` | (Optional) Network for RPC calls. Default: `testnet`. |
| `--output <dir>` | (Optional) Output directory. Default: `./bindings`. |
| `--json-only` | Generate JSON specs from WASM only (no Python bindings). |
| `--keep-wasm` | Keep downloaded WASM files in `./wasm`. |

### Output

Bindings are written to `bindings/<contract_name>/`. Contracts without a `contract_id` (upload-only) are skipped automatically.

### Contracts that generate bindings

- `opus_token`
- `hvym_collective`
- `hvym_roster`
- `hvym_pin_service`
- `hvym_pin_service_factory`

---

## 6. Constructor Arguments

Each deployable contract reads its constructor arguments from a JSON file at the project root: `<contract_name>_args.json`.

### `hvym_collective_args.json`
```json
{
  "admin": "TESTNET_DEPLOYER",
  "token": "<XLM_CONTRACT_ID>",
  "join_fee": 210.0,
  "mint_fee": 0.5,
  "reward": 0.2,
  "split": 10
}
```
*`join_fee`, `mint_fee`, `reward` are in XLM and converted to stroops.*

### `hvym_roster_args.json`
```json
{
  "admin": "TESTNET_DEPLOYER",
  "token": "<XLM_CONTRACT_ID>",
  "join_fee": 16.0
}
```
*`join_fee` is in XLM and converted to stroops.*

### `hvym_pin_service_args.json`
```json
{
  "admin_addr": "TESTNET_DEPLOYER",
  "pin_fee": 1.0,
  "join_fee": 5.0,
  "min_pin_qty": 3,
  "min_offer_price": 1.0,
  "pinner_stake": 100.0,
  "pay_token": "<XLM_CONTRACT_ID>",
  "max_cycles": 60,
  "flag_threshold": 3
}
```
*`pin_fee`, `join_fee`, `min_offer_price`, `pinner_stake` are in XLM and converted to stroops.*

### `hvym_pin_service_factory_args.json`
```json
{
  "admin": "TESTNET_DEPLOYER"
}
```

### `opus_token_args.json`
```json
{
  "admin": "TESTNET_DEPLOYER"
}
```

### `pintheon_ipfs_token_args.json` / `pintheon_node_token_args.json`

These are upload-only contracts. Their args files are used if deploying directly, but in the standard pipeline they are only uploaded (no `contract_id`).

### Post-Deploy Config: `hvym_collective_post_deploy_args.json`
```json
{
  "fund_amount": 30.0,
  "initial_opus_alloc": 40.0,
  "enabled": true
}
```

---

## 7. Deployment Records

- **`deployments.json`** — Machine-readable record of all contract WASM hashes and contract IDs. Updated automatically by `deploy_contracts.py` after each contract.
- **`deployments.md`** — Human-readable markdown table of all deployments.

### `deployments.json` Format

```json
{
  "network": "testnet",
  "timestamp": 1234567890,
  "cli_version": "23.0.1",
  "pintheon_ipfs_token": {
    "wasm_hash": "<64-char hex>",
    "contract_id": "",
    "network": "testnet"
  },
  "hvym_pin_service": {
    "wasm_hash": "<64-char hex>",
    "contract_id": "<56-char contract ID>",
    "network": "testnet"
  },
  "hvym_pin_service_factory": {
    "wasm_hash": "<64-char hex>",
    "contract_id": "<56-char contract ID>",
    "network": "testnet"
  }
}
```

---

## 8. Workflow Order

### Full Development Cycle

```bash
# 1. Build all contracts (factory must come after pin-service)
python build_contracts.py

# 2. Test all contracts
python test_all_contracts.py

# 3. Deploy all contracts
python deploy_contracts.py --deployer-acct <ACCOUNT_NAME>

# 4. Post-deployment: fund collective and mint OPUS
python hvym_post_deploy.py \
  --deployer-acct <ACCOUNT_NAME> \
  --fund-amount 30 \
  --initial-opus-alloc 40

# 5. Generate Python bindings
source pintheon-contracts/Scripts/activate
python generate_bindings.py --from-file deployments.json
```

### Rebuild After Pin Service ABI Change

If `hvym-pin-service` contract interface changes (e.g. adding a parameter like `filename`), rebuild and re-test both contracts before deploying:

```bash
python build_contracts.py --contract hvym-pin-service
python build_contracts.py --contract hvym-pin-service-factory
python test_contract.py hvym-pin-service
python test_contract.py hvym-pin-service-factory
```

### CI/CD (GitHub Actions)

Pushing to `main` or creating a release tag triggers the automated pipeline which:
1. Builds all contracts in dependency order
2. Runs all tests
3. Deploys to testnet
4. Updates `deployments.json` as a release artifact
5. Attestations are generated for each WASM hash
