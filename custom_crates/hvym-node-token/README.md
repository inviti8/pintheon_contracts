# hvym-node-token

Shared Soroban crate used by `pintheon-node-token` to model Pintheon
node-identity tokens. Based on the Soroban Token SDK with Heavymeta-specific
extensions:

- `NodeMetadata` type — fields exposed on node-identity tokens
- Custom event types for node-token lifecycle
- Token-standard helpers (transfer, balance, etc.) inherited from Soroban
  Token SDK

This crate compiles to both `cdylib` (for use as a standalone Wasm) and
`rlib` (for use as a dependency of other contracts). It is not deployed
directly — it is consumed by `pintheon-node-deployer/pintheon-node-token`.

## Layout

- `src/lib.rs` — contract entry points
- `src/nodemetadata.rs` — `NodeMetadata` type and helpers
- `src/event.rs` — node-token event types

## License

Apache-2.0 (matches the parent repository). See `../../LICENSE`.
