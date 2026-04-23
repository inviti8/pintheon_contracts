# Release Notes

## v1.1.0-alpha — April 2026

### Breaking changes

- **`hvym_roster.join()` now requires admin authorization.** The signature
  changed from `join(member, name, canon)` to
  `join(caller, member, name, canon)`. The `caller` must be an admin (checked
  via `require_admin_auth`) **and** `member` must also authorize the
  transaction. This closes a loophole where any funded Stellar account could
  join the roster. Callers using the previous bindings must regenerate
  bindings and update call sites.

### Contracts

| Contract | Testnet | Mainnet (Public) |
|---|---|---|
| `opus_token`              | `CDPEWPM3B77Q3HBPLZQTKCUND6MAR6A73IQFIAVIPGKF2U2XBEDWMENU` | `CA4NA27APFFWBEAML275ZT4HD6ALUUZJGHH6W27IW6GT6DQFPZWKTIPF` |
| `hvym_collective`         | `CDPDM3XDYZSQE4ZWWK2PGFJP74IS7UH3OYPGGPO7TI2KP4JDH7E54EL7` | `CC6GWVUM54FBCCWZ4YJUCQCXC22C3IIQZG5JCTN3NHRGY7RSL6ZIJKJT` |
| `hvym_roster`             | `CBDOEYS5Z6RXRBIHJK72JPE2GIPR2HTUGIVHKVCOASKXGKL73Y4HOMVM` | `CBUS33CAIMTV7T4M4G3FTH35QBAY6VWY3K4IZTYTRPD45ZDSQMSIZ2AB` |
| `hvym_pin_service`        | `CBWZFS3QRW67SHEX5KLY7OFOTA3V5TF6V5QIDQQ52GQT7FY5Y5OQXIWW` | `CDYUS4OXHGVX4AFNERP3CQAMI5JNDTPQZ6MAV3EH53NN3YYPJW2SW2FP` |
| `hvym_pin_service_factory`| `CD3OUO6BSCOQWMCPE5LFSG2F2TQSNNDZGA3EITKYSE74ZACO5OXGBQ5A` | `CBWEFPAAUYARY6SS4UAUFTJEF2YNCGBH2BGDMTSS7OJKLPYMDLDAWMFG` |
| `hvym_registry`           | `CB6TWFLNGRFIYEHA7T2Y3VHDJ3VWC5OQHDZCSMGCSSOYWRBIVPKXMC6V` | `CAYZSYW4XO7XU3PNYILG256VYLFJEBTNCA4DTPRJ6GP7QGS2U2Z2R2HN` |
| `pintheon_ipfs_token`     | *Upload only* (WASM `416704f4…`) | *Upload only* (WASM `416704f4…`) |
| `pintheon_node_token`     | *Upload only* (WASM `3dad7958…`) | *Upload only* (WASM `3dad7958…`) |

Authoritative records: [`deployments.testnet.json`](deployments.testnet.json)
/ [`deployments.public.json`](deployments.public.json) and their `.md`
siblings.

### New since v1.0.0

- **`hvym_registry` contract** — on-chain source-of-truth mapping of contract
  name + network → contract ID. Admin-gated writes, public reads. See
  [`hvym-registry/USAGE.md`](hvym-registry/USAGE.md).
- **Per-network deployment files.** `deployments.testnet.json` and
  `deployments.public.json` replace the single `deployments.json` so that
  testnet and mainnet state cannot clobber each other.
- **Placeholder resolution in `*_args.json`.** Constructor-arg files may now
  use `"deployer"` (resolved to the deployer identity's public key) and
  `"native"` (resolved to the network's XLM SAC address). This fixed a
  mainnet deployment bug where a hardcoded testnet XLM SAC was used as
  `pay_token`.
- **`--force` flag on `deploy_contracts.py`** — overrides the "skip if WASM
  hash unchanged" protection when you deliberately need to redeploy.
- **Fee escalation + retry fixes** in `deploy_contracts.py` upload/deploy
  paths: retries now apply to both `TimeoutExpired` and `CalledProcessError`,
  and fee escalation is honoured across attempts.
- **Admin-gated `hvym_roster.join()`** (see Breaking changes above).

### Recent commits

- `3ef863d` — update to latest roster contract on mainnet
- `4b5936b` — roster bindings updated
- `58e5187` — latest testnet contract deployment
- `48c97bb` — gate hvym-roster `join()` with admin authorization
- `f7b6775` — use per-network deployment files (`deployments.{network}.json`)

---

## v1.0.0 — March 3, 2026

Initial mainnet deployment of all contracts. Deployed via
`inviti8/pintheon_contracts` (repository has since been renamed to
`hvym_contracts`).
