# hvym_contracts — Soroban smart contracts for the Heavymeta / Pintheon ecosystem

This repository contains the Soroban smart contracts that power the Heavymeta
Cooperative's Pintheon ecosystem: membership (`hvym-collective`), the protected
member roster (`hvym-roster`), IPFS pin management (`hvym-pin-service` +
`hvym-pin-service-factory`), the on-chain contract registry (`hvym-registry`),
and the `opus_token` / `pintheon_node_token` / `pintheon_ipfs_token` SEP-41
tokens.

> **Repo note:** this repository was previously named `pintheon_contracts`;
> the canonical GitHub location is now `inviti8/hvym_contracts`. GitHub
> redirects the old URL, but please update local remotes:
> `git remote set-url origin git@github.com:inviti8/hvym_contracts.git`.

## Requirements

| Tool | Version |
|---|---|
| Soroban SDK | `23.0.1` (locked; resolves higher at build time) |
| Stellar CLI | `23.0.1`+ (see `cli_version` in `deployments.public.json`) |
| Rust | latest stable with the `wasm32v1-none` target (`rustup target add wasm32v1-none`) |
| Python | 3.10+ (for tooling scripts — see `requirements.txt` / `requirements-dev.txt`) |

## License

Apache-2.0. Smart contracts are on-chain by definition; permissive licensing
keeps them transparent and auditable. See [LICENSE](LICENSE).

---

## Contract layout

| Directory | Contract | Purpose |
|---|---|---|
| `hvym-collective/` | `hvym_collective` | Membership, join fees, OPUS allocation, payout routing |
| `hvym-roster/` | `hvym_roster` | Admin-managed member roster (canon metadata); `join()` is admin-gated |
| `hvym-pin-service/` | `hvym_pin_service` | IPFS pin slot pool with epoch expiration and flag-based CID Hunter reputation |
| `hvym-pin-service-factory/` | `hvym_pin_service_factory` | Deploys per-pinner pin-service instances; embeds the pin-service WASM |
| `hvym-registry/` | `hvym_registry` | On-chain source-of-truth for contract IDs per network (Testnet / Mainnet) |
| `opus_token/` | `opus_token` | OPUS SEP-41 token |
| `pintheon-node-deployer/pintheon-node-token/` | `pintheon_node_token` | Node-identity SEP-41 token (upload-only, deployed via factory flow) |
| `pintheon-ipfs-deployer/pintheon-ipfs-token/` | `pintheon_ipfs_token` | IPFS-asset SEP-41 token (upload-only) |
| `custom_crates/hvym-file-token/` | — | Shared crate: file-metadata token helpers |
| `custom_crates/hvym-node-token/` | — | Shared crate: node-metadata token helpers |

### Dependencies between contracts

- `hvym-collective` imports `pintheon-node-token`, `pintheon-ipfs-token`, and
  `opus-token` via `contractimport!`. Those must be built **first**.
- `hvym-pin-service-factory` imports `hvym-pin-service`'s WASM via
  `contractimport!`. If the pin-service ABI changes, rebuild **both**.

See [`IMPORT_NAMING_GUIDE.md`](IMPORT_NAMING_GUIDE.md) for how
`contractimport!` resolves paths, and [`workflows.md`](workflows.md) for
full build order and command reference.

## Deployment records (per-network)

Deployments are tracked in **per-network** files. The legacy aggregated
`deployments.json` is retained only for historical reference.

| File | Network | Human-readable |
|---|---|---|
| `deployments.testnet.json` | Stellar Testnet | [`deployments.testnet.md`](deployments.testnet.md) |
| `deployments.public.json` | Stellar Mainnet (Public) | [`deployments.public.md`](deployments.public.md) |

Tooling selects the correct file from the `--network` flag or the
`STELLAR_NETWORK` environment variable. See `deploy_contracts.py` and
`hvym_post_deploy.py`.

## Quickstart

### Build

```bash
# Build all contracts in dependency order
python build_contracts.py

# Build a single contract
python build_contracts.py --contract hvym-pin-service
```

### Test

```bash
# Run all tests across every contract crate
python test_all_contracts.py

# Or run a single crate's tests directly
cargo test -p hvym-roster
```

### Deploy

```bash
# Testnet (reads deployments.testnet.json)
python deploy_contracts.py --deployer-acct TESTNET_DEPLOYER --network testnet

# Mainnet (reads deployments.public.json)
python deploy_contracts.py --deployer-acct lepus-luminary-1 --network public

# Force re-deploy even when WASM hash is unchanged
python deploy_contracts.py --deployer-acct TESTNET_DEPLOYER --network testnet --force
```

Constructor arguments live in `<contract>_args.json` files in the repo root
and support two placeholders resolved by the deploy script at runtime:

- `"deployer"` → the deployer identity's public key (from `--deployer-acct`)
- `"native"`   → the network's XLM SAC address (resolved via
  `stellar contract id asset --asset native`)

### Post-deploy (collective funding + OPUS allocation)

```bash
python hvym_post_deploy.py \
  --deployer-acct <IDENTITY> \
  --network testnet \
  --fund-amount 30 \
  --initial-opus-alloc 40
```

### Verify hashes against on-file deployments

```bash
# Check a specific network
python verify_deployment_hashes.py deployments.testnet.json

# Or scan every deployments.*.json in the repo
python verify_deployment_hashes.py
```

### Generate Python bindings

```bash
# From a deployment file (recommended)
python generate_bindings.py --from-file deployments.testnet.json

# Or for a single contract
python generate_bindings.py --contract hvym-collective
```

Example usage of generated bindings:

```python
from stellar_sdk import Keypair, Network
from bindings.hvym_collective.bindings import Client as HvymCollectiveClient

client = HvymCollectiveClient(
    contract_id="C...",  # from deployments.{network}.json
    rpc_url="https://soroban-testnet.stellar.org",
    network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
)
print(client.get_admin_list())
```

## Tooling overview

| Script | Purpose |
|---|---|
| `build_contracts.py` | Build all (or one) contracts, optimize WASM, copy to `wasm/` |
| `test_all_contracts.py` | Run the full test suite across every contract crate |
| `deploy_contracts.py` | Upload + deploy all contracts for a given network; respects `--force` and hash-skip logic |
| `hvym_post_deploy.py` | Fund the collective contract and set the OPUS token address |
| `generate_bindings.py` | Generate Python bindings using `stellar-contract-bindings` |
| `verify_deployment_hashes.py` | Verify that locally-built WASM matches the hashes recorded in `deployments.*.json` |
| `setup_deployer_identity.py` | Load a deployer secret (from `ACCT_SECRET` / env) into the Stellar CLI keystore for CI |
| `setup_local_stellar.py` | Spin up a local Stellar / soroban-rpc node for standalone testing (see [LOCAL_STELLAR_NODE.md](LOCAL_STELLAR_NODE.md)) |
| `check_rpc.py` | Probe an RPC endpoint for basic reachability |

## CI / GitHub Actions

The repository ships three workflows under `.github/workflows/`:

- `custom-deploy.yml` — builds, tests, and deploys contracts in dependency
  order. Uses `${{ secrets.ACCT_SECRET }}` to inject the deployer secret
  into the Stellar CLI via `setup_deployer_identity.py`. Writes the matching
  per-network `deployments.{network}.json` and markdown summary back into
  the repo.
- `custom-release.yml` — builds optimized WASMs and publishes a GitHub
  release with SHA-256 hashes and build attestations for validation on
  [stellar.expert](https://stellar.expert/).
- `mainnet-release.yml` — mainnet-specific release packaging.

See [`.github/workflows/README.md`](.github/workflows/README.md) for the full
workflow description.

## Further reading

| Doc | Topic |
|---|---|
| [`workflows.md`](workflows.md) | Complete build / test / deploy / bindings workflow reference |
| [`HVYM_PIN_SERVICE.md`](HVYM_PIN_SERVICE.md) | `hvym-pin-service` design — slot pool, epoch expiration, CID Hunter |
| [`hvym-registry/USAGE.md`](hvym-registry/USAGE.md) | `hvym-registry` CLI guide |
| [`IMPORT_NAMING_GUIDE.md`](IMPORT_NAMING_GUIDE.md) | How to determine the correct `contractimport!` WASM path |
| [`LOCAL_STELLAR_NODE.md`](LOCAL_STELLAR_NODE.md) | Running a local Stellar / soroban-rpc node |
| [`OPUS_TOKEN_ICON.md`](OPUS_TOKEN_ICON.md) | Publishing the OPUS token icon via `stellar.toml` |
| [`TOKEN_TOML.md`](TOKEN_TOML.md) | SEP-1 `stellar.toml` conventions used for HVYM tokens |
| [`RELEASE_NOTES.md`](RELEASE_NOTES.md) | Release history |
