# OPUS Token Icon — Block Explorer Integration

This document explains exactly how to make the OPUS token icon appear on Stellar block explorers (stellar.expert, stellarchain.io, Lobstr, etc.) for both testnet and mainnet deployments.

## How Discovery Works

Block explorers resolve Soroban token icons through this chain:

```
Explorer reads contract → looks at deployer/admin account
    → reads account's home_domain field (on-chain)
        → fetches https://<home_domain>/.well-known/stellar.toml
            → finds [[CURRENCIES]] entry where contract = "C..."
                → reads image = "https://..."
                    → displays icon
```

There is no contract-level `home_domain` field in Soroban. The link between the contract and its metadata is entirely through the **deployer account's `home_domain`** field on-chain.

---

## Step 1 — Prepare the Icon Image

### Requirements

| Property | Requirement |
|---|---|
| Format | **PNG** (required) |
| Background | **Transparent** |
| Shape | **Square** |
| Size | **128×128 pixels** (recommended minimum) |
| Hosting | **HTTPS URL** — plain HTTP will be rejected |
| Filename | e.g. `opus-token-128.png` |

Use exactly 128×128 for maximum compatibility. Some explorers accept up to 256×256, but 128×128 is the explicit SEP-0001 recommendation.

### Hosting

Host the image at a stable, permanent HTTPS URL. Good options:
- Your project's web domain: `https://pintheon.io/assets/opus-token-128.png`
- GitHub raw content (acceptable for testnet, not ideal for production): `https://raw.githubusercontent.com/org/repo/main/assets/opus-token-128.png`
- A CDN (S3, Cloudflare R2, etc.)

The image URL must remain permanently accessible — if it breaks, the icon disappears from explorers.

---

## Step 2 — Create the `stellar.toml` File

Create a file called `stellar.toml` and host it at:

```
https://<your-domain>/.well-known/stellar.toml
```

### Required Content

```toml
# stellar.toml — SEP-0001 compliance for Pintheon / OPUS token

VERSION = "2.0.0"

[DOCUMENTATION]
ORG_NAME = "Pintheon"
ORG_URL = "https://heavymeta.art"
ORG_DESCRIPTION = "Creator Collective on Stellar"

# ---------------------------------------------------------------
# TESTNET
# ---------------------------------------------------------------
[[CURRENCIES]]
contract = "CB3MM62JMDTNVJVOXORUOOPBFAWVTREJLA5VN4YME4MBNCHGBHQPQH7G"
status = "test"
name = "Opus"
desc = "OPUS is the utility token of HEAVYMETA network."
display_decimals = 7
image = "https://<your-domain>/assets/opus-token-128.png"

# ---------------------------------------------------------------
# MAINNET (add when deployed)
# ---------------------------------------------------------------
# [[CURRENCIES]]
# contract = "<mainnet-contract-id>"
# status = "live"
# name = "Opus"
# desc = "OPUS is the utility token of HEAVYMETA network."
# display_decimals = 7
# image = "https://<your-domain>/assets/opus-token-128.png"
```

### Important Notes

- Use `contract = "C..."` — **do not** use `code`/`issuer` (those are for classic Stellar assets, not Soroban contract tokens).
- The testnet contract ID comes from `deployments.testnet.json` (`opus_token.contract_id`). Current value: `CDPEWPM3B77Q3HBPLZQTKCUND6MAR6A73IQFIAVIPGKF2U2XBEDWMENU`. Update this whenever the contract is redeployed to a new address.
- `display_decimals = 7` matches Stellar's standard stroops precision.
- `status = "test"` for testnet, `status = "live"` for mainnet.

### Required HTTP Headers

The `stellar.toml` file **must** be served with:

```
Access-Control-Allow-Origin: *
Content-Type: text/plain; charset=utf-8
```

Without `Access-Control-Allow-Origin: *`, browser-based wallets and UIs will silently fail to fetch it due to CORS policy.

#### nginx example
```nginx
location /.well-known/stellar.toml {
    add_header Access-Control-Allow-Origin *;
    add_header Content-Type "text/plain; charset=utf-8";
}
```

#### Apache example
```apache
<Files "stellar.toml">
    Header set Access-Control-Allow-Origin "*"
    Header set Content-Type "text/plain; charset=utf-8"
</Files>
```

---

## Step 3 — Set `home_domain` on the Deployer Account

The deployer account (`TESTNET_DEPLOYER` in this repo) must have its `home_domain` field set on-chain. This is what links the account — and by extension the contracts it deployed — to your `stellar.toml`.

The `home_domain` value is the bare domain only (no `https://`, no trailing slash), and must be **32 characters or fewer**.

### Stellar CLI Commands

#### Testnet
```bash
stellar tx new set-options \
  --source TESTNET_DEPLOYER \
  --home-domain "heavymeta.art" \
  --network testnet \
  --build-only \
| stellar tx sign --sign-with-key TESTNET_DEPLOYER --network testnet \
| stellar tx send --network testnet
```

#### Mainnet
```bash
stellar tx new set-options \
  --source lepus-luminary-1 \
  --home-domain "heavymeta.art" \
  --network mainnet \
  --build-only | \
stellar tx sign --sign-with-key lepus-luminary-1 --network mainnet | \
stellar tx send --network mainnet
```

`TESTNET_DEPLOYER` / `MAINNET_DEPLOYER` are the Stellar CLI identity names as managed via `stellar keys add`.

### Verify It Worked

Check the account on Horizon to confirm `home_domain` is set:

```
https://horizon-testnet.stellar.org/accounts/<DEPLOYER_PUBLIC_KEY>
```

Look for `"home_domain": "pintheon.io"` in the response JSON.

---

## Step 4 — Verify the Full Chain

Use the Stellar TOML validator to confirm everything is wired up correctly:

```
https://stellar.expert/validator
```

Or test manually:

```bash
# 1. Confirm stellar.toml is reachable with correct headers
curl -I https://pintheon.io/.well-known/stellar.toml

# 2. Confirm the [[CURRENCIES]] entry is present
curl https://pintheon.io/.well-known/stellar.toml | grep -A 10 "CB3MM62J"

# 3. Confirm the image URL resolves
curl -I https://pintheon.io/assets/opus-token-128.png
```

Expected response headers on `stellar.toml`:
```
HTTP/2 200
access-control-allow-origin: *
content-type: text/plain; charset=utf-8
```

---

## Step 5 — Per-Deployment: Keep `stellar.toml` in Sync

Every time `deploy_contracts.py` deploys a new `opus_token` instance, the
contract ID in the matching per-network deployments file changes. The
`stellar.toml` must be updated to match.

### Where to find the current contract ID

```bash
# Testnet
python -c "import json; print(json.load(open('deployments.testnet.json'))['opus_token']['contract_id'])"

# Mainnet
python -c "import json; print(json.load(open('deployments.public.json'))['opus_token']['contract_id'])"
```

Or open `deployments.testnet.json` / `deployments.public.json` directly —
the `opus_token.contract_id` field.

### Suggested process after each deployment

1. Run `deploy_contracts.py --network {testnet|public}` — the matching
   `deployments.{network}.json` is updated automatically.
2. Read the new `opus_token.contract_id` from that file.
3. Update the `contract = "..."` line in `stellar.toml` with the new ID.
4. Deploy the updated `stellar.toml` to your web host.

Consider scripting this if deployments are frequent (e.g. have the deploy pipeline write the contract ID into a template and push the updated toml).

---

## Step 6 — Optional: Soroswap Token List

For visibility in Soroswap and other DeFi UIs, submit a pull request to:

```
https://github.com/soroswap/token-list
```

Add a file at `assets/<CONTRACT_ID>.json`:

```json
{
  "contract": "CA4NA27APFFWBEAML275ZT4HD6ALUUZJGHH6W27IW6GT6DQFPZWKTIPF",
  "name": "Opus",
  "code": "OPUS",
  "org": "Pintheon",
  "domain": "pintheon.io",
  "icon": "https://pintheon.io/assets/opus-token-128.png"
}
```

(Use the mainnet `opus_token.contract_id` from `deployments.public.json`.)

This is separate from stellar.toml and only affects DeFi protocol UIs, not block explorers.

---

## Step 7 — Optional: stellar.expert Contract Source Validation

stellar.expert supports linking a deployed contract to its GitHub source repository. This gives a verified source badge on the explorer page and can also embed `home_domain` directly in the WASM build metadata.

This repo's CI/CD already builds contracts via GitHub Actions. To add source validation:

1. Add the [stellar-expert/soroban-build-workflow](https://github.com/stellar-expert/soroban-build-workflow) step to `.github/workflows/custom-release.yml` for `opus_token`.
2. Set `home_domain: "pintheon.io"` as a workflow input — this embeds the domain in the WASM custom section.
3. Push a git tag — the workflow submits the build attestation to stellar.expert automatically.

See the workflow's README for the exact YAML syntax.

---

## Summary Checklist

| Step | Task | Notes |
|---|---|---|
| 1 | Create 128×128 transparent PNG icon | HTTPS-hosted, permanent URL |
| 2 | Create `stellar.toml` with `[[CURRENCIES]]` | `contract = "C..."`, `image = "https://..."` |
| 3 | Serve `stellar.toml` with CORS headers | `Access-Control-Allow-Origin: *` |
| 4 | Set `home_domain` on deployer account | Via `stellar tx new set-options --home-domain` |
| 5 | Verify with curl / stellar.expert validator | Confirm headers, TOML content, image URL |
| 6 | Update `stellar.toml` after each redeployment | Contract ID changes each time `deploy_contracts.py` runs; read from `deployments.{network}.json` |
| 7 | (Optional) Submit PR to soroswap/token-list | For DeFi UI visibility |
| 8 | (Optional) Add stellar-expert build workflow | For source verification badge |

---

## Current Contract IDs

| Network | Contract ID | Source |
|---|---|---|
| Testnet | `CDPEWPM3B77Q3HBPLZQTKCUND6MAR6A73IQFIAVIPGKF2U2XBEDWMENU` | `deployments.testnet.json` |
| Mainnet (Public) | `CA4NA27APFFWBEAML275ZT4HD6ALUUZJGHH6W27IW6GT6DQFPZWKTIPF` | `deployments.public.json` |

These IDs are authoritative in the matching per-network `deployments.{network}.json`. Always read from there after a deployment rather than hardcoding.
