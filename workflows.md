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
- `--contract <dir>`: (Optional) Build only the specified contract directory.

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
- `<target_dir>`: (Required) The directory containing a `Cargo.toml` to test.

---

## 3. Deploy Contracts

**Script:** `deploy_contracts.py`

Uploads and/or deploys contracts in the correct order. Only `hvym-collective` is deployed; the other contracts are uploaded and their WASM hashes are stored. Constructor arguments are loaded from JSON files if not provided on the command line.

### Usage

- Deploy all contracts in order:
  ```bash
  python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME>
  ```
- Deploy a specific contract (by short name):
  ```bash
  python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --contract opus_token
  ```
- Pass custom constructor arguments:
  ```bash
  python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME> --contract hvym-collective --constructor-args --admin G... --join-fee 100 --mint-fee 10 --token G... --reward 5
  ```

### Arguments
- `--deployer-acct <name>`: (Required) Stellar CLI account name or secret to use as deployer.
- `--network <name>`: (Optional) Network name (default: testnet).
- `--contract <short_name>`: (Optional) Deploy only the specified contract (short names: pintheon-ipfs-token, pintheon-node-token, opus_token, hvym-collective).
- `--constructor-args ...`: (Optional) Arguments for the contract constructor. If omitted, arguments are loaded from `<contract>_args.json`.

### Notes
- For `hvym-collective`, ensure you have a `hvym-collective_args.json` file with all required constructor arguments.
- The script updates `deployments.json` and `deployments.md` with contract hashes and IDs.

---

## 4. Deploy Node and IPFS Tokens

**Script:** `deploy_node_and_ipfs.py`

Deploys `pintheon-ipfs-token` and `pintheon-node-token` contracts using their WASM hashes from `deployments.json`. Constructor arguments are loaded from JSON files. Only prints the contract IDs to the terminal; does not update `deployments.json`.

### Usage

- Deploy both contracts:
  ```bash
  python3 deploy_node_and_ipfs.py --deployer-acct <ACCOUNT_NAME>
  ```
- Deploy a specific contract:
  ```bash
  python3 deploy_node_and_ipfs.py --deployer-acct <ACCOUNT_NAME> --contract pintheon-ipfs-token
  ```

### Arguments
- `--deployer-acct <name>`: (Required) Stellar CLI account name or secret to use as deployer.
- `--network <name>`: (Optional) Network name (default: testnet).
- `--contract <name>`: (Optional) Deploy only the specified contract (pintheon-ipfs-token or pintheon-node-token).

### Notes
- Requires `pintheon-ipfs-token_args.json` and `pintheon-node-token_args.json` files with constructor arguments.
- Uses WASM hashes from `deployments.json` (contracts must be uploaded first via `deploy_contracts.py`).

---

## 5. Post-Deployment Actions

**Script:** `hvym_post_deploy.py`

Funds the `hvym-collective` contract and launches the opus token via contract invocation. Updates `deployments.json` with the opus token contract ID.

### Usage

```bash
python3 hvym_post_deploy.py --deployer-acct <ACCOUNT_NAME> --fund-amount 30 --initial-opus-alloc 10
```

- `--fund-amount` and `--initial-opus-alloc` are specified as whole numbers in XLM (e.g., `30` for 30 XLM). The script automatically converts these to stroops (1 XLM = 10^7 stroops).

### Arguments
- `--deployer-acct <name>`: (Required) Stellar CLI account name or secret to use as source.
- `--network <name>`: (Optional) Network name (default: testnet).
- `--fund-amount <XLM>`: (Required) Amount to fund the contract (whole number, in XLM).
- `--initial-opus-alloc <XLM>`: (Required) Initial opus token allocation to mint to admin (whole number, in XLM).

---

## 6. Constructor Argument JSON Files

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

---

## 7. Deployment Records

- `deployments.json`: Machine-readable record of all contract uploads and deployments (hashes and IDs).
- `deployments.md`: Human-readable markdown table of all contract uploads and deployments.

---

## Workflow Order

1. **Build** all contracts: `python3 build_contracts.py`
2. **Test** contracts as needed: `python3 test_contract.py <dir>`
3. **Deploy** contracts: `python3 deploy_contracts.py --deployer-acct <ACCOUNT_NAME>`
4. **Deploy node and IPFS tokens** (optional): `python3 deploy_node_and_ipfs.py --deployer-acct <ACCOUNT_NAME>`
5. **Post-deploy** actions: `python3 hvym_post_deploy.py --deployer-acct <ACCOUNT_NAME> --fund-amount ... --initial-opus-alloc ...`

---

For any questions or to add new contracts, update the relevant scripts and JSON files accordingly. 