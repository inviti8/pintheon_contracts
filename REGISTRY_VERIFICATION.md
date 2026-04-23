# Registry Verification

`verify_registry.py` reconciles the repo's local deployment records
against the on-chain `hvym_registry` contract and — with `--verify-wasm`
— against the actual WASM bytes stored on ledger. This gives anyone (the
cooperative, members, auditors, regulators) a one-command path to answer:

> *"Does the code on mainnet match the code in this repository?"*

## Why this exists

Two properties the cooperative depends on:

1. **The contract IDs we publish are the ones we actually deployed.**
   Anything that reads `deployments.public.json` — bindings, docs, client
   apps, release notes, downstream tooling — trusts those IDs. If they
   drift, every downstream consumer is pointed at the wrong contracts.
2. **The contracts deployed at those IDs run the code in this repo.**
   Pintheon is source-available specifically so members and auditors can
   read the code that handles their keys, funds, and OPUS allocations.
   That guarantee is only real if the on-chain WASM matches the repo.

The script enforces both properties automatically. It was added after a
real incident: on 2026-04-23, verification against the mainnet registry at
`CA6KQ5GYGI33VZB5IGWW7XXLLHR2MPEBWVDREU4P5ZGCSKRGHXBCRKXV` revealed that
`deployments.public.json` had been published with five stale testnet
contract IDs copy-pasted into the mainnet file. The WASMs were correct;
the IDs weren't. A downstream consumer following the file would have
pointed at contracts that didn't exist on mainnet. The fix was to run the
verifier, take its output as ground truth, and correct the file. This doc
exists so that kind of drift gets caught the next time by default.

## What the script proves

When `python verify_registry.py --network public --registry-id <ID> --verify-wasm`
exits 0, these three statements are simultaneously true:

| Statement | How it's proven |
|---|---|
| Every contract in `deployments.public.json` has the same contract ID the on-chain registry reports. | `get_all_contracts(Mainnet)` on the registry contract, compared row-by-row. |
| Every WASM hash recorded in `deployments.public.json` matches the sha256 of the corresponding local `wasm/<name>.optimized.wasm` file. | Same logic as `verify_deployment_hashes.py`. |
| The WASM bytes actually stored on ledger at each contract ID are byte-identical to the repo's local `wasm/<name>.optimized.wasm`. | `stellar contract fetch --id <id>` → sha256 → compare. For upload-only contracts, `stellar contract fetch --wasm-hash <hash>` confirms the hash is present on ledger. |

Together these close the loop from "git repo" to "bytes executing on the
Stellar public network." No trust in any middle layer (the deployments
file, the release notes, the bindings, the registry-write flow, the CI
pipeline) is required — the script reaches past them to the ledger.

## Requirements

- Python 3.10+ with the packages in `requirements-dev.txt` installed
- Generated Python bindings present at `bindings/hvym_registry/` (they
  already live in the repo; regenerate with `python generate_bindings.py`
  if you rebuilt the contract)
- `stellar` CLI ≥ 23.0 on `PATH` (only needed for `--verify-wasm`)
- Network access to the chosen RPC endpoint

## Usage

### Basic — registry ↔ file only

```bash
# Mainnet
python verify_registry.py --network public \
  --registry-id CA6KQ5GYGI33VZB5IGWW7XXLLHR2MPEBWVDREU4P5ZGCSKRGHXBCRKXV

# Testnet (registry ID lives in deployments.testnet.json)
python verify_registry.py --network testnet \
  --registry-id CB6TWFLNGRFIYEHA7T2Y3VHDJ3VWC5OQHDZCSMGCSSOYWRBIVPKXMC6V
```

### Full verification — also compare on-ledger WASM to repo

```bash
python verify_registry.py --network public \
  --registry-id CA6KQ5GYGI33VZB5IGWW7XXLLHR2MPEBWVDREU4P5ZGCSKRGHXBCRKXV \
  --verify-wasm
```

This is the command to use before any release, after any deploy, and any
time a third party asks "can you prove mainnet is running your repo?"

### Flags

| Flag | Default | Purpose |
|---|---|---|
| `--network {testnet,public}` | *required* | Which network to verify. `public` = Stellar mainnet. |
| `--registry-id <C...>` | *required* | Contract ID of the `hvym_registry` instance on that network. |
| `--file <path>` | `deployments.{network}.json` | Local deployments file to verify. |
| `--rpc-url <url>` | built-in per network; `STELLAR_RPC_URL` env var | Override the Soroban RPC endpoint. |
| `--verify-wasm` | off | Also run the on-ledger WASM check. Requires the `stellar` CLI. |
| `--wasm-dir <path>` | `wasm` | Directory containing local `.optimized.wasm` files. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Local file agrees with the on-chain registry. With `--verify-wasm`, also: all on-ledger WASM bytes match the repo. |
| `1` | At least one discrepancy. See the section headers in the output (`MISMATCHED contract IDs`, `In local file but NOT registered`, `On-chain but missing…`, suspicious metadata, WASM mismatch). |
| `2` | Could not reach the registry, registry call failed, or local file missing — fatal. |

## Reading the output

The script prints one section per category of finding. A clean run looks
like this:

```
Network         : public (Public Global Stellar Network ; September 2015)
RPC URL         : https://stellar-soroban-public.nodies.app
Registry        : CA6KQ5GYGI33VZB5IGWW7XXLLHR2MPEBWVDREU4P5ZGCSKRGHXBCRKXV
Local file      : .../deployments.public.json

Registry reports N contract(s):
  hvym_collective                C...
  hvym_pin_service               C...
  ...

======================================================================
On-ledger WASM verification
======================================================================
  hvym_collective              OK  (<sha256>)
  ...
  pintheon_ipfs_token          OK  ledger=<sha256>
  pintheon_node_token          OK  ledger=<sha256>

RESULT: local file agrees with on-chain registry.
        on-ledger WASM matches local wasm/ artifacts.
```

Diagnostic sections the script may print:

- **Suspicious metadata** — the row's `"network"` or `"deployer"` field
  doesn't match what's expected for this file (e.g. `"testnet"` / `"TESTNET_DEPLOYER"` in `deployments.public.json`). Typically copy-paste residue; fix the metadata.
- **MISMATCHED contract IDs** — local file and registry both have an
  entry for the same contract, but the IDs differ. The registry is the
  source of truth; update the local file.
- **In local file but NOT registered on-chain** — the local file claims a
  contract exists on this network but the registry doesn't list it. Either
  the contract was never registered (admin needs to run `set_contract_id`),
  or the local row is stale and should be removed.
- **On-chain but missing / empty in local file** — the registry has a
  contract the local file doesn't mention at all. Add the row.
- **WASM mismatch** — the bytes on ledger at a registered contract ID are
  not byte-identical to `wasm/<name>.optimized.wasm`. This means the
  deployed contract is running different code than what's in the repo.
  Either the local build is out of date (rebuild and compare hashes), or
  somebody deployed a non-repo WASM to this ID (investigate).

## Caveats

- **The registry is itself a contract, written by an admin.** The script
  trusts the registry's answers. If the admin registered a wrong ID, the
  script won't detect it by registry logic alone — but `--verify-wasm`
  will still catch it, because the on-ledger WASM at the wrong ID will
  not match the repo's local WASM.
- **The script does not verify the registry contract itself by default.**
  The `hvym_registry` row in `deployments.{network}.json` is compared to
  the registry's own `get_all_contracts` output, which typically omits
  the registry itself. That's expected — to fully close the loop, also
  run `stellar contract fetch --id <registry-id>` manually and sha256 it
  against `wasm/hvym_registry.optimized.wasm`.
- **Network and timestamp metadata drift is flagged, not fixed.** The
  script won't rewrite your deployments file — it prints discrepancies
  and exits non-zero. Editing the file is a human decision.
- **Upload-only contracts don't have contract IDs.** `pintheon_ipfs_token`
  and `pintheon_node_token` are uploaded by `deploy_contracts.py` and
  instantiated on demand by `hvym-collective`. The script verifies they
  have an on-ledger WASM entry with the recorded hash; it does not (and
  cannot) verify a contract instance ID for them.

## When to run it

| Trigger | Recommended flags |
|---|---|
| Before cutting a release | `--network public --verify-wasm` and again for `--network testnet` |
| After `deploy_contracts.py --network public --force` | `--network public --verify-wasm` |
| After a manual `set_contract_id` / `remove_contract_id` admin call | Basic run (no `--verify-wasm`) |
| On a scheduled CI cadence (e.g. weekly) against mainnet | `--network public --verify-wasm` |
| Any time a third party asks for verification | `--network public --verify-wasm` (hand them the command too — they can run it themselves) |
