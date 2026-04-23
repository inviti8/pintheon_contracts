# GitHub Workflows

This directory contains the CI/CD workflows for `hvym_contracts`.

## Workflow files

| File | Trigger | Purpose |
|---|---|---|
| `custom-deploy.yml` | workflow_dispatch (manual) | Build + test + deploy all contracts for a chosen network. Writes `deployments.{network}.json` + `.md` back to the repo. |
| `custom-release.yml` | git tag push | Build and publish a GitHub Release with optimized WASMs, SHA-256 hashes, and build attestations. Submits validation data to stellar.expert. |
| `mainnet-release.yml` | git tag push (mainnet) | Mainnet-specific release packaging. |

## Secrets required

| Secret | Used by | Purpose |
|---|---|---|
| `ACCT_SECRET` | `custom-deploy.yml` | Deployer identity secret key. Loaded into the Stellar CLI keystore at job start via `setup_deployer_identity.py`. Never echoed. |
| `TESTNET_DEPLOYER` | `custom-deploy.yml` | Fallback alias expected by some steps if ACCT_SECRET is not set for the testnet branch. |
| `HVYM_SECRET` | `custom-release.yml` / `mainnet-release.yml` | Release-signing / validation submission credential. |

All secrets flow through `${{ secrets.NAME }}` and are never printed to
workflow logs.

## WASM embedding in contracts

Two contracts embed the WASM of sibling contracts. The workflow must build
them in dependency order:

- `hvym-collective` uses `include_bytes!("../../wasm/pintheon_node_token.optimized.wasm")`
  and the equivalent for `pintheon_ipfs_token`. Those two tokens must be
  built *first* and their optimized WASM copied into `wasm/` at the repo
  root.
- `hvym-pin-service-factory` uses `contractimport!` against
  `../hvym-pin-service/target/wasm32v1-none/release/hvym_pin_service.optimized.wasm`.
  `hvym-pin-service` must be built *first*.

Both contracts build against the `wasm32v1-none` Rust target — the legacy
`wasm32-unknown-unknown` target is no longer used.

See [`../../IMPORT_NAMING_GUIDE.md`](../../IMPORT_NAMING_GUIDE.md) for the
full embedding mechanics.

## Dependency build order (matches `build_contracts.py`)

```
pintheon-node-token
pintheon-ipfs-token
opus_token
hvym-collective              ← embeds node + ipfs token WASMs via include_bytes!
hvym-roster
hvym-pin-service
hvym-pin-service-factory     ← contractimport! hvym-pin-service
hvym-registry
```

## Triggering workflows

### Deploy (manual)
1. GitHub → **Actions** → **Custom Deploy Soroban Contracts**
2. **Run workflow** → select network (`testnet` / `public`)
3. The workflow commits the updated `deployments.{network}.json` and
   `deployments.{network}.md` back to the repository on success.

### Release (tag-triggered)
```bash
git tag v1.1.0
git push origin v1.1.0
```

Mainnet releases use a separate tag convention — see
`mainnet-release.yml` for the exact prefix it listens for.

## Validation on stellar.expert

`custom-release.yml` submits binary hash, repository slug, and commit SHA
to the stellar.expert validation API. The explorer verifies the
on-chain contract WASM hash against the GitHub release artifact, enabling
the "verified source" badge.
