# mock_c2pa — end-to-end mock for the C2PA app-CA registration flow

This package is the testable, runnable counterpart to
[`HVYM_CERT_REGISTRY.md`](../HVYM_CERT_REGISTRY.md) and
[`C2PA.md`](../../hvym-market-muscle/C2PA.md). It:

1. Generates an Ed25519 self-signed X.509 CA cert that meets the C2PA
   spec (CA:TRUE pathlen:0, critical KeyUsage, critical EKU
   `1.3.6.1.4.1.42038.1.5.0`, SAN `stellar:G...`).
2. Builds the registration bundle Andromica would show the user.
3. Mocks the Heavymeta Portal's `mint_app_ca_registration_token`,
   signing a sorted-keys compact JSON payload with a mock member
   Stellar keypair.
4. Verifies the signature and canonical bytes round-trip locally, then
   either:
   - Prints the SCVal arguments that **would** be submitted (dry-run mode), or
   - Submits `register_app_ca` to testnet and reads back via `get_app_ca`
     + `is_trusted` (testnet mode).

## Run it

From the **repo root** (not from inside `mock_c2pa/`):

```bash
pip install -r mock_c2pa/requirements.txt

# Dry-run — no network, no contract needed. Validates everything except
# the on-chain submission. Useful immediately.
python -m mock_c2pa.run_mock_flow --mode dry-run

# Testnet — requires hvym-cert-registry deployed to testnet first.
# See "Deploying the contract" below.
python -m mock_c2pa.run_mock_flow --mode testnet --app-kind Andromica
```

On first run, two fresh Stellar keypairs (app + member) are generated and
saved to `mock_c2pa/.mock_keystore.json` (gitignored). Subsequent runs
reuse them, which is what you want — `register_app_ca` is per-app
one-shot, so the second register call would fail with "app already
registered". Use `rotate` / `revoke` flows for follow-up testing once
those CLI handles are added.

## Layout

```
mock_c2pa/
├── README.md                — this file
├── requirements.txt         — cryptography + stellar-sdk
├── .gitignore               — ignores the local keystore + pycache
├── __init__.py
├── canonical.py             — sorted-keys JSON payload builders (mirrors
│                              the contract's build_*_payload exactly)
├── keystore.py              — load_or_create() + friendbot_fund()
├── register.py              — Soroban-side submit + read-back (scval-based,
│                              no generated bindings needed)
├── run_mock_flow.py         — CLI orchestrator
├── andromica/               — *** drop-in modules for glasswing ***
│   ├── __init__.py
│   ├── ca_generation.py     — generate_app_ca(), issue_member_leaf(),
│   │                          verify_chain()
│   └── bundle.py            — build_bundle().to_text()
└── portal_mock/             — stub of the heavymeta_collective Portal
    ├── __init__.py
    └── mint_token.py        — mint_register/rotate/revoke_token()
```

## Dropping into Andromica (glasswing)

The two modules under `mock_c2pa/andromica/` are written with no
Stellar SDK dependency at import time. They take and return primitive
types (`bytes`, `str`, `datetime`) so they lift directly into the
glasswing source tree.

What goes where, in the Andromica desktop install flow:

| Heavymeta C2PA step (per C2PA.md §4.2) | Glasswing module | Function |
|---|---|---|
| First run: generate the app's CA keypair + self-signed cert | new `glasswing/c2pa/ca_generation.py` (copy from here) | `generate_app_ca()` |
| First run: display the registration bundle to the user | new `glasswing/c2pa/bundle.py` (copy from here) | `build_bundle()` then `.to_text()` |
| First run: submit `register_app_ca` after user pastes the token | glasswing's existing Stellar client + `mock_c2pa.register` as a reference | `submit_register()` |
| Per publish: issue ephemeral member leaf | `glasswing/c2pa/ca_generation.py` | `issue_member_leaf()` |
| Per publish: sign manifest with `c2pa-rs` | glasswing-internal | (not in this mock) |
| Per import: verify against `hvym-cert-registry` | `glasswing/c2pa/verify.py` (reference: `register.is_trusted`) | `is_trusted()` |

The Portal-side mint (`portal_mock/mint_token.py`) is **NOT** for
glasswing — that runs in `heavymeta_collective/payments/` against the
member's Banker + Guardian decrypted secret. Glasswing only receives
the wire token; it doesn't mint.

## Mode comparison

| Mode | Network | Contract needed | What it verifies |
|---|---|---|---|
| `dry-run` | none | none | Cert spec compliance, bundle format, canonical-payload encoding agreement, signature round-trip, local leaf-CA chain |
| `testnet` | testnet RPC + Friendbot | `hvym_cert_registry` deployed to testnet (`contract_id` in `deployments.testnet.json`) | Everything above + on-chain `register_app_ca` + read-back via `get_app_ca`/`is_trusted` |

## Deploying the contract (prereq for testnet mode)

Not done in this commit. Manual step for the operator:

```bash
# 1. Build the cert-registry WASM. (Only this one contract.)
python build_contracts.py --contract hvym-cert-registry

# 2. Make sure TESTNET_DEPLOYER is in the stellar CLI keystore and funded.
#    (See workflows.md section 3.)
#
# 3. Deploy. deploy_contracts.py has no --contract flag — it iterates the
#    full CONTRACTS list with hash-skip logic, so only newly-built or
#    changed contracts actually deploy. For testnet this is harmless.
python deploy_contracts.py --network testnet \
  --deployer-acct TESTNET_DEPLOYER

# 4. The script writes hvym_cert_registry.contract_id into
#    deployments.testnet.json. Then the testnet mode of the mock works:
python -m mock_c2pa.run_mock_flow --mode testnet --app-kind Andromica
```

> **Why no `--contract` flag on deploy_contracts.py?** The script's
> hash-skip behavior already gives you the same effect: it computes
> SHA-256 of each `wasm/*.optimized.wasm` and skips any contract whose
> hash matches the recorded hash in `deployments.{network}.json`. New
> or changed contracts (like cert-registry on its first deploy) are the
> only ones that hit the network.

## What this mock deliberately does NOT do

- No `c2pa-rs` integration. The mock generates the X.509 chain but
  doesn't embed it into a real C2PA manifest on an image / asset file.
  That belongs in Andromica's publish pipeline.
- No real Portal session, no Banker + Guardian. The member secret is
  held in plaintext in `.mock_keystore.json` — fine for a mock, never
  for production.
- No coverage for `rotate_app_ca` / `revoke_by_app` / `revoke_by_member`
  in the CLI yet. The wire-format helpers (`mint_rotate_token`,
  `mint_revoke_token`) and the Soroban submitters (`submit_rotate`,
  `submit_revoke_by_app`, `submit_revoke_by_member`) are in place;
  wiring them into the CLI is a follow-up.
