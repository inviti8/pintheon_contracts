# Embedding WASM from other contracts

Two contracts in this repo pull WASM from sibling contracts at build time.
Each uses a different mechanism — this doc explains both and when to update
the paths.

## 1. `hvym-collective` — `include_bytes!` from `wasm/`

`hvym-collective/src/lib.rs` embeds the `pintheon-node-token` and
`pintheon-ipfs-token` WASMs as raw bytes so it can deploy them
programmatically at runtime (see `Env::deployer().upload_contract_wasm`).

```rust
const PINTHEON_NODE_TOKEN_WASM: &[u8] =
    include_bytes!("../../wasm/pintheon_node_token.optimized.wasm");

const PINTHEON_IPFS_TOKEN_WASM: &[u8] =
    include_bytes!("../../wasm/pintheon_ipfs_token.optimized.wasm");
```

**Build order:** the two tokens must be built (and their optimized WASM
copied to the repo-root `wasm/` directory) **before** `hvym-collective`.
`build_contracts.py` handles this automatically.

**opus_token** is *not* embedded — it's deployed separately and its address
is wired in via `set_opus_token(...)` after deploy (see
`hvym_post_deploy.py`).

## 2. `hvym-pin-service-factory` — `contractimport!`

`hvym-pin-service-factory/src/lib.rs` imports `hvym-pin-service`'s WASM
via `soroban_sdk::contractimport!`, which generates a typed client bound to
that contract at compile time.

```rust
mod hvym_pin_service {
    soroban_sdk::contractimport!(
        file = "../hvym-pin-service/target/wasm32v1-none/release/hvym_pin_service.optimized.wasm"
    );
}
```

**Build order:** `hvym-pin-service` must be built **before**
`hvym-pin-service-factory` — `build_contracts.py` enforces this.

**ABI changes:** if you change `hvym-pin-service`'s public ABI, rebuild the
factory **and** re-run its tests before deploying. The factory's generated
client is pinned to the ABI snapshot at compile time.

## Target directories

All contracts use the Soroban-standard `wasm32v1-none` Rust target. The
legacy `wasm32-unknown-unknown` target is no longer used in this repo.

Typical paths under each contract:

```
<contract>/target/wasm32v1-none/release/<underscore_name>.wasm            # raw
<contract>/target/wasm32v1-none/release/<underscore_name>.optimized.wasm  # after `stellar contract optimize`
```

## Current versions

The package name and version come from each contract's `Cargo.toml`:

| Contract | Package name | Version |
|---|---|---|
| `opus_token` | `opus-token` | `0.1.0` |
| `pintheon-node-token` | `pintheon-node-token` | `0.0.6` |
| `pintheon-ipfs-token` | `pintheon-ipfs-token` | `0.0.1` |
| `hvym-collective` | `hvym-collective` | `0.0.1` |
| `hvym-roster` | `hvym-roster` | `0.0.1` |
| `hvym-pin-service` | `hvym-pin-service` | `0.0.1` |
| `hvym-pin-service-factory` | `hvym-pin-service-factory` | `0.0.1` |
| `hvym-registry` | `hvym-registry` | `0.0.1` |

Re-verify with:

```bash
grep -E "^(name|version) = " \
  opus_token/Cargo.toml \
  pintheon-node-deployer/pintheon-node-token/Cargo.toml \
  pintheon-ipfs-deployer/pintheon-ipfs-token/Cargo.toml \
  hvym-collective/Cargo.toml \
  hvym-roster/Cargo.toml \
  hvym-pin-service/Cargo.toml \
  hvym-pin-service-factory/Cargo.toml \
  hvym-registry/Cargo.toml
```

## Troubleshooting

**`file not found` on `include_bytes!`:** run `python build_contracts.py`
(or at minimum the two upload-only token contracts plus the optimize step)
so the `wasm/` directory is populated before compiling `hvym-collective`.

**`file not found` on `contractimport!`:** run
`python build_contracts.py --contract hvym-pin-service` before building
`hvym-pin-service-factory`, so the factory's relative path exists.

**ABI-mismatch panics at runtime:** rebuild the importer *after* the
importee. Cargo does not detect WASM-file changes across crates without
`cargo clean` — when in doubt, `cargo clean -p hvym-pin-service-factory`
and rebuild.
