# hvym-collective

Membership contract for the Heavymeta Cooperative: join fees, OPUS-token
allocation, publisher/collective reward split, and payouts.

## Summary

- **Join** — members pay a `join_fee` (in XLM) to `join()` and become part of
  the collective.
- **Publish** — members emit `PublishFileEvent` / `PublishEncryptedEvent`
  events when they publish IPFS content; the contract routes an OPUS reward
  to the publisher and a cut (`opus_split`, default 10%) to the collective
  treasury.
- **Admin list** — multiple admins are supported; the initial admin
  (index 0) is protected from removal. Admin-gated actions use
  `require_admin_auth()`.

## Embedded WASMs

This contract embeds two sibling WASMs via `include_bytes!` so it can
deploy them at runtime:

- `../../wasm/pintheon_node_token.optimized.wasm`
- `../../wasm/pintheon_ipfs_token.optimized.wasm`

Those tokens must be built *before* `hvym-collective`. See
[`../IMPORT_NAMING_GUIDE.md`](../IMPORT_NAMING_GUIDE.md).

The OPUS token is **not** embedded — it is deployed separately and wired in
via `set_opus_token(opus_contract_id, initial_alloc)` after deploy (see
`hvym_post_deploy.py`).

## Constructor

```text
__constructor(admin: Address, token: Address, join_fee: u32, mint_fee: u32, reward: u32, split: u32)
```

See [`../hvym_collective_args.json`](../hvym_collective_args.json) for the
values used by `deploy_contracts.py`. `admin` and `token` accept the
placeholders `"deployer"` and `"native"` (resolved at deploy time).

## Current deployments

| Network | Contract ID |
|---|---|
| Testnet | see [`../deployments.testnet.md`](../deployments.testnet.md) |
| Mainnet | see [`../deployments.public.md`](../deployments.public.md) |

## Tests

```bash
cargo test -p hvym-collective
```

Covers constructor, join/membership flow, event emission, OPUS allocation,
admin protection, and rent estimation.
