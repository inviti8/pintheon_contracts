# hvym-file-token

Shared Soroban crate used by `pintheon-ipfs-token` to model file-metadata
tokens. Based on the Soroban Token SDK with Heavymeta-specific extensions:

- `FileMetadata` type — fields exposed on file-data tokens
- Custom event types for file-token lifecycle
- Token-standard helpers (transfer, balance, etc.) inherited from Soroban
  Token SDK

This crate compiles to both `cdylib` (for use as a standalone Wasm) and
`rlib` (for use as a dependency of other contracts). It is not deployed
directly — it is consumed by `pintheon-ipfs-deployer/pintheon-ipfs-token`.

## Layout

- `src/lib.rs` — contract entry points
- `src/filemetadata.rs` — `FileMetadata` type and helpers
- `src/event.rs` — file-token event types

## License

Apache-2.0 (matches the parent repository). See `../../LICENSE`.
