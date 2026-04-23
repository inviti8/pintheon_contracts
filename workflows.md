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
hvym-collective                ← embeds the three token WASMs via contractimport!
hvym-roster
hvym-pin-service
hvym-pin-service-factory       ← depends on hvym-pin-service (embeds its WASM)
hvym-registry                  ← independent (no contractimport dependencies)
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

Uploads and/or deploys all contracts from the `wasm/` directory in the correct
order. Reads constructor arguments from `<contract>_args.json` files in the
project root. Updates `deployments.{network}.json` and
`deployments.{network}.md` after each contract.

By default, the deploy step is skipped when the local WASM hash already matches
the hash recorded in the per-network deployments file (avoiding a pointless
redeploy). Pass `--force` to override.

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
- `hvym_registry`

### Usage

```bash
# Deploy all contracts to testnet
python deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --network testnet

# Deploy all contracts to mainnet
python deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --network public

# Force redeploy even when WASM hash matches the recorded hash
python deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --network testnet --force

# Deploy using WASM files from a custom directory
python deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --wasm-dir ./wasm
```

### Arguments

| Argument | Default | Description |
|---|---|---|
| `--deployer-acct` | (required) | Stellar CLI account name or secret key to use as deployer. |
| `--network` | `public` | Network to deploy to (`testnet`, `futurenet`, `public`, `standalone`). Resolution order: `--network` flag → `STELLAR_NETWORK` env var → `public`. |
| `--wasm-dir` | `./wasm` | Directory containing optimized `.wasm` files. |
| `--force` | off | Redeploy even when the WASM hash matches the hash recorded in `deployments.{network}.json`. |

### Args-file placeholders

Values inside `<contract>_args.json` support two magic strings resolved at
deploy time:

| Placeholder | Resolved to |
|---|---|
| `"deployer"` | The deployer identity's G-address (from `--deployer-acct`) |
| `"native"`   | The network's XLM SAC address (`stellar contract id asset --asset native`) |

This keeps the args files network-agnostic — the same file works against
testnet and mainnet without edits.

### Notes
- Constructor arguments are loaded from `<contract_name>_args.json` files automatically.
- Monetary values in args files (fees, prices) are specified in XLM and automatically converted to stroops (×10,000,000).
- `STELLAR_NETWORK` environment variable can set the network before running the script.
- Upload retries now handle both `TimeoutExpired` and `CalledProcessError` with fee escalation across attempts.

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
- Requires `hvym-collective` to be deployed and its contract ID to be in `deployments.{network}.json`.
- Updates `deployments.{network}.json` with the opus token contract ID.

---

## 5. Generate Bindings

**Script:** `generate_bindings.py`

Generates Python client bindings for deployed contracts using `stellar-contract-bindings`. Requires the venv to be activated.

### Activate the Virtual Environment

```bash
# Replace `hvym-contracts` with your local venv name (any name is fine)
source hvym-contracts/Scripts/activate
```

### From Deployments File (recommended)

Reads contract IDs from a per-network deployments file (`deployments.testnet.json` or `deployments.public.json`) and generates bindings for all contracts that have a `contract_id`:

```bash
# Testnet
python generate_bindings.py --from-file deployments.testnet.json

# Mainnet
python generate_bindings.py --from-file deployments.public.json
```

### Filter Specific Contracts

```bash
python generate_bindings.py --from-file deployments.testnet.json \
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
- `hvym_registry`

---

## 6. Constructor Arguments

Each deployable contract reads its constructor arguments from a JSON file at the project root: `<contract_name>_args.json`.

The placeholder strings `"deployer"` and `"native"` are resolved at deploy
time — see **Args-file placeholders** in Section 3. Use them to keep the
same args file network-agnostic.

### `hvym_collective_args.json`
```json
{
  "admin": "deployer",
  "token": "native",
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
  "admin": "deployer",
  "token": "native",
  "join_fee": 16.0
}
```
*`join_fee` is in XLM and converted to stroops.*

### `hvym_pin_service_args.json`
```json
{
  "admin_addr": "deployer",
  "pin_fee": 1.0,
  "join_fee": 5.0,
  "min_pin_qty": 3,
  "min_offer_price": 1.0,
  "pinner_stake": 100.0,
  "pay_token": "native",
  "max_cycles": 60,
  "flag_threshold": 3
}
```
*`pin_fee`, `join_fee`, `min_offer_price`, `pinner_stake` are in XLM and converted to stroops.*

### `hvym_pin_service_factory_args.json`
```json
{
  "admin": "deployer"
}
```

### `hvym_registry_args.json`
```json
{
  "admin": "deployer"
}
```

### `opus_token_args.json`
```json
{
  "admin": "deployer"
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

Deployments are tracked in **per-network** files so testnet and mainnet state
cannot clobber each other. `deploy_contracts.py` reads/writes the file that
matches `--network`.

| File | Network |
|---|---|
| `deployments.testnet.json` / `.md` | Testnet |
| `deployments.public.json` / `.md`  | Mainnet (Public) |

The legacy aggregated `deployments.json` / `deployments.md` are kept only for
historical reference and should no longer be edited.

### `deployments.{network}.json` Format

```json
{
  "network": "testnet",
  "timestamp": 1234567890,
  "cli_version": "23.0.1",
  "pintheon_ipfs_token": {
    "wasm_hash": "<64-char hex>",
    "network": "testnet",
    "deployer": "TESTNET_DEPLOYER",
    "timestamp": 1234567890
  },
  "hvym_pin_service": {
    "wasm_hash": "<64-char hex>",
    "contract_id": "C...<56-char contract ID>",
    "network": "testnet",
    "deployer": "TESTNET_DEPLOYER",
    "timestamp": 1234567890
  },
  "hvym_registry": {
    "wasm_hash": "<64-char hex>",
    "contract_id": "C...<56-char contract ID>",
    "network": "testnet",
    "deployer": "TESTNET_DEPLOYER",
    "timestamp": 1234567890
  }
}
```

### Verifying hashes

```bash
# Verify a specific file
python verify_deployment_hashes.py deployments.public.json

# Or scan every deployments.*.json in the repo
python verify_deployment_hashes.py
```

---

## 8. Workflow Order

### Full Development Cycle

```bash
# 1. Build all contracts (factory must come after pin-service)
python build_contracts.py

# 2. Test all contracts
python test_all_contracts.py

# 3. Deploy all contracts to a specific network
python deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --network testnet

# 4. Post-deployment: fund collective and mint OPUS
python hvym_post_deploy.py \
  --deployer-acct <ACCOUNT_NAME> \
  --network testnet \
  --fund-amount 30 \
  --initial-opus-alloc 40

# 5. Generate Python bindings (use the matching per-network file)
source hvym-contracts/Scripts/activate
python generate_bindings.py --from-file deployments.testnet.json
# or: python generate_bindings.py --from-file deployments.public.json
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
4. Updates `deployments.{network}.json` as a release artifact
5. Attestations are generated for each WASM hash
