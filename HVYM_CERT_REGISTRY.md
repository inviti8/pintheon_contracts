# HVYM_CERT_REGISTRY Contract Specification

## Overview

`hvym-cert-registry` is a Soroban smart contract that anchors the X.509
trust list for Heavymeta app instances on the Stellar ledger. It records,
per app instance, the **fingerprint of a self-signed X.509 CA cert** and
the **ed25519 pubkey of the cooperative member who authorized that app
instance** at registration time. C2PA verifiers consult the registry to
decide whether a given Inkternity / Andromica install is trusted, and
which member authorized it.

Companion docs:
- `hvym-market-muscle/C2PA.md` — the full architectural picture
  (Stellar-anchored C2PA trust list, dual-auth registration, leaf
  ephemerality, proof-of-active-use via storage rent). Read it for
  context; this doc covers the on-chain contract only.
- `heavymeta_collective/INKTERNITY.md` — the precedent token-signing
  flow (Banker + Guardian unlock + member ed25519 signature). The
  Portal's `mint_app_ca_registration_token` helper will mirror
  Inkternity Distribution's `mint_inkternity_token`.

**Status:** Design doc, pre-implementation. Phase 1 of C2PA adoption.

---

## Architectural commitments (locked, do not compromise)

These are inherited from `C2PA.md §0` and must hold for this contract:

1. **No admin.** The contract has no admin list, no admin-gated entry
   points, and no cooperative override. Either the app keypair
   authenticates (`require_auth`) or the member key authenticates
   (`ed25519_verify`), or both. The cooperative can govern the protocol
   but cannot register, rotate, or revoke a CA on a member's behalf.
2. **Persistent storage for `AppCaRecord`.** Soroban persistent-storage
   rent is the proof-of-active-use mechanic
   (`C2PA.md §8.1`): active artists keep their record alive; abandoned
   apps let their record decay. This is by design — do not substitute
   instance/temporary storage and do not add an admin-bump path that
   subsidizes inactive accounts.
3. **`member_pubkey: BytesN<32>`** (raw 32-byte ed25519 pubkey), not
   `Address`. The contract calls `e.crypto().ed25519_verify(...)`
   directly. A Stellar `G…` address converts to this 32-byte form via
   strkey decode (strip version byte + 2-byte CRC). Clients do this
   conversion; the contract just consumes the raw bytes.
4. **`pubkey_alg` locked to `"ed25519"` for v1.** Field reserved for
   future `"ecdsa-p256"`; any other value panics.
5. **Independence.** No cross-contract calls. Do not touch
   `hvym-roster` (live on mainnet). The contract is queryable
   stand-alone.
6. **License: Apache-2.0**, matching every other contract in this repo.

---

## Empirical unknowns — to measure on testnet before mainnet

The design ships with three numbers `C2PA.md §4.4` currently estimates
but does not lock. These need a testnet run before §4.4's funding-floor
guidance can be hardened:

1. **Soroban resource fees for `register_app_ca`.** CPU + memory + a
   persistent-storage write of one `AppCaRecord` plus appends to the
   two index Vecs (`AllApps`, `AppsByMember(...)`). `C2PA.md §4.4`
   currently estimates ~0.5–1.5 XLM for the initial rent and
   ~0.05–0.2 XLM for compute. Verify on testnet.
2. **Persistent-storage rent rate for the `AppCaRecord` size.** Record
   the final serialized struct size in bytes after the first testnet
   write, then quote the rent cost in XLM per ledger-period from the
   testnet result. This feeds the funding-floor recommendation.
3. **`e.crypto().ed25519_verify` accepts raw strkey-decoded pubkey
   bytes without transformation.** A Stellar G-address is
   `base32(version || pubkey || crc16)`. Clients decode and pass the
   middle 32 bytes. Confirm with a unit test that uses a known
   keypair: derive G-address client-side via `stellar_sdk`, strkey-
   decode to 32 bytes, sign a known message with the same secret,
   submit to the contract — `ed25519_verify` must accept.

These belong on the next person's plate, not in this commit.

---

## Data model

### Storage keys

```rust
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DataKey {
    AppCa(Address),                  // app_address -> AppCaRecord (persistent)
    AppsByMember(BytesN<32>),        // member_pubkey -> Vec<Address> (persistent)
    AllApps,                         // -> Vec<Address> (persistent)
}
```

All three keys live in **persistent** storage. `AllApps` and
`AppsByMember(...)` are append-only indexes maintained by the contract;
they're scrubbed of revoked apps lazily by readers if needed (see
`list_active_apps` below).

### Enums

```rust
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AppKind {
    Inkternity,
    Andromica,
    Pintheon,    // Forward-compat — Pintheon C2PA integration deferred (C2PA.md §5.1)
    Other,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CertStatus {
    Active,
    Revoked,
    Expired,    // only ever returned by views; never stored
}
```

`CertStatus::Expired` is **never written to storage** — expiry is
computed at view time from `expires_at` against the current ledger
timestamp. The variant exists so view helpers (`get_app_ca`,
`is_trusted`) can communicate the effective state without callers
having to redo the timestamp math.

### `AppCaRecord`

```rust
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AppCaRecord {
    pub app_address:   Address,        // the app instance's Stellar address
    pub member_pubkey: BytesN<32>,     // ed25519 pubkey of authorizing member
    pub app_kind:      AppKind,
    pub fingerprint:   BytesN<32>,     // SHA-256 of the DER-encoded CA cert
    pub pubkey_alg:    String,         // "ed25519" (only accepted value in v1)
    pub issued_at:     u64,            // ledger timestamp at register_app_ca
    pub updated_at:    u64,            // ledger timestamp at last register/rotate/revoke
    pub expires_at:    u64,            // hard CA expiry (matches the X.509 notAfter)
    pub status:        CertStatus,     // Active | Revoked (never Expired in storage)
    pub serial:        u32,            // 1 on register; +1 each rotate
}
```

Notes:

- `app_address` duplicates the `DataKey::AppCa` lookup key for
  convenience of callers who only have the record handle.
- `member_pubkey` is **load-bearing** — it is the authoritative member
  identity for verifying any C2PA signature in the chain rooted at this
  CA. It is fixed at registration and is **not changed by rotation**
  (only fingerprint and expiry change on rotate).
- `updated_at` is included for verifiers building "is this a recent
  registration?" freshness heuristics. Storage cost is trivial (+8
  bytes); the practical signal it carries is worth it.

---

## Auth-payload encoding — decision

### Choice

**Sorted-keys compact JSON with single-letter keys**, matching the
shape of Inkternity Distribution's wire format
(`INKTERNITY.md §4.3`). The contract reconstructs canonical payload
bytes from the typed params, byte-compares to the submitted
`auth_payload`, and only then calls `e.crypto().ed25519_verify(...)`.

### Why JSON over scval

- The Portal already has battle-tested code that mints
  Inkternity-Distribution tokens by serializing
  `json.dumps(payload, separators=(",",":"), sort_keys=True)` and
  signing the result with `Keypair.from_secret(...).sign(payload)`.
  The C2PA Portal helper `mint_app_ca_registration_token` will be a
  copy-paste of that helper with a different schema — zero new
  serialization surface area for the Portal team.
- scval would be more "native" to Soroban but: (a) the Portal lives
  in `stellar_sdk` (Python), not `soroban_sdk`, so scval encoding is
  newly-imported risk; (b) JSON is easier to inspect, test against
  fixtures, and reason about cross-language.
- The downside — JSON encoding in `no_std` on-chain is mildly heavy —
  is bounded: we hand-roll u64-to-ASCII and bytes-to-hex helpers
  (~30 LoC), and the field set is small and fixed per intent.

### Why hex (not Stellar strkey) for addresses inside the payload

Stellar `G…` strkey is `base32(version_byte || pubkey || crc16_xmodem)`.
Implementing base32 + CRC-16/XModem inside a `no_std` Soroban contract
is a lot of code surface for what amounts to display-format prettiness
inside a byte string nobody reads with their eyes. The on-chain payload
uses **lowercase hex** for addresses and pubkeys instead.

This is a deliberate departure from Inkternity Distribution's preference
for `G…` strings on the wire — but Inkternity Distribution itself accepts
**both** hex and strkey for the `k` field (`INKTERNITY.md §4.3`), so we
are using a representation that's already on the supported list. The
Portal-side helper formats addresses as hex when building the C2PA
registration payload.

### Canonical payload schemas (locked for v1)

All payloads are sorted-key, compact JSON (`separators=(",",":")`),
UTF-8 encoded.

**Register intent:**

```json
{"a":"<app_addr_hex_64>","alg":"ed25519","exp":<u64>,"fp":"<fingerprint_hex_64>","i":"register-app-ca","k":"Inkternity","m":"<member_pubkey_hex_64>","n":<u64_nonce>}
```

Sorted key order: `a, alg, exp, fp, i, k, m, n`.

**Rotate intent:**

```json
{"a":"<app_addr_hex_64>","exp":<u64>,"fp":"<new_fingerprint_hex_64>","i":"rotate-app-ca","n":<u64_nonce>}
```

Sorted key order: `a, exp, fp, i, n`.

**Member-revoke intent:**

```json
{"a":"<app_addr_hex_64>","i":"revoke-app-ca","n":<u64_nonce>}
```

Sorted key order: `a, i, n`.

### Field meanings

| Key | Type | Meaning |
|---|---|---|
| `a`   | hex string (64 chars) | The app instance's Stellar address as raw 32-byte hex. Binds the token to one specific app. |
| `alg` | string | `"ed25519"` for v1. Field reserved; rejected if anything else. Present in register only — rotate/revoke inherit the alg from the stored record. |
| `exp` | u64   | CA expiry (Unix seconds, matches the X.509 `notAfter`). Present in register + rotate. |
| `fp`  | hex string (64 chars) | SHA-256 of the DER-encoded CA cert. Present in register + rotate. |
| `i`   | string | Intent discriminator — `register-app-ca`, `rotate-app-ca`, or `revoke-app-ca`. Prevents a token signed for one operation from being replayed as another. |
| `k`   | string | `AppKind` enum name: `Inkternity` \| `Andromica` \| `Pintheon` \| `Other`. Present in register only — app kind is immutable post-registration. `Pintheon` is forward-compat scaffolding for the deferred Pintheon C2PA integration (`C2PA.md §5.1`); accepted today, no special handling. |
| `m`   | hex string (64 chars) | Member ed25519 pubkey as 32-byte hex. Present in register only — member identity is immutable post-registration. |
| `n`   | u64   | Nonce. The Portal uses the current ledger timestamp + a small random salt to guarantee uniqueness. See **Replay** below. |

### Replay

The nonce `n` is a uniqueness tag, not a server-tracked counter. The
contract does not store nonces (would require per-`(member, intent)`
storage and rent — not worth it for the actual replay risk):

- **Register replay**: `register_app_ca` rejects if a record exists for
  `app_address`. Replay impossible after the first success.
- **Rotate replay**: each rotation requires the Portal to mint a fresh
  token (member must consent in-process). Replay would set the
  fingerprint to a *previously-signed* value, which is the kind of
  rollback the artist would notice if it mattered. We accept this in
  v1; tighter replay protection (e.g., monotonic `serial` check
  against the rotate payload) is on the menu if the testnet
  measurements show it's free.
- **Member-revoke replay**: `Active → Revoked` is terminal. Replaying
  a revoke against an already-revoked record is a no-op (panics with
  "already revoked"). No corruption surface.

The intent discriminator `i` prevents the cross-shape attack of taking
a register-signed token and submitting it to `rotate_app_ca` (or vice
versa). Without `i`, an attacker who got a register payload signed
could replay its bytes against `rotate_app_ca` if the field set
overlapped enough — `i` makes the canonical bytes disjoint by
construction.

---

## Contract surface

### Constructor

```rust
fn __constructor(e: Env) {
    // No admin to store, no config to seed. Persistent index keys are
    // lazily created on first write.
}
```

No arguments. `hvym_cert_registry_args.json` is `{}`.

### Registration — `register_app_ca`

```rust
fn register_app_ca(
    e: Env,
    app_address:    Address,
    member_pubkey:  BytesN<32>,
    app_kind:       AppKind,
    fingerprint:    BytesN<32>,
    pubkey_alg:     String,
    expires_at:     u64,
    nonce:          u64,
    auth_payload:   Bytes,
    auth_signature: BytesN<64>,
);
```

Semantics:

1. `app_address.require_auth()` — the app proves it holds the private
   key for the address it's registering under.
2. Reject if `pubkey_alg != "ed25519"`.
3. Reject if a record already exists at `DataKey::AppCa(app_address)`
   (use `rotate_app_ca` for updates).
4. Reject if `expires_at <= e.ledger().timestamp()` (already expired).
5. Reconstruct the canonical register payload bytes from
   `(app_address, member_pubkey, app_kind, fingerprint, pubkey_alg,
   expires_at, nonce)` — sorted JSON, hex-encoded addresses — and
   compare byte-for-byte against `auth_payload`. Mismatch → panic.
6. `e.crypto().ed25519_verify(&member_pubkey, &auth_payload,
   &auth_signature)` — verifier panics on bad signature.
7. Write `AppCaRecord { ..., issued_at: now, updated_at: now,
   status: Active, serial: 1 }`.
8. Append `app_address` to `AllApps` and to
   `AppsByMember(member_pubkey)`.
9. Emit `REGISTER` event.

### Rotation — `rotate_app_ca`

```rust
fn rotate_app_ca(
    e: Env,
    app_address:     Address,
    new_fingerprint: BytesN<32>,
    new_expires_at:  u64,
    nonce:           u64,
    auth_payload:    Bytes,
    auth_signature:  BytesN<64>,
);
```

Semantics:

1. `app_address.require_auth()`.
2. Load record from `DataKey::AppCa(app_address)`. Panic if absent.
3. Panic if `record.status == Revoked` (revoked is terminal).
4. Reject if `new_expires_at <= e.ledger().timestamp()`.
5. Reconstruct canonical rotate payload bytes from `(app_address,
   new_fingerprint, new_expires_at, nonce)`, byte-compare to
   `auth_payload`.
6. `ed25519_verify(&record.member_pubkey, ...)` — using the stored
   member pubkey (rotation cannot change who authorized this app).
7. Update `record.fingerprint`, `record.expires_at`,
   `record.updated_at = now`, `record.serial += 1`.
8. Emit `ROTATE` event.

### Revocation — two entry points

Two separate functions instead of an enum-dispatched `caller_kind`
argument. Reasoning:

- Each entry point has its own tests (no
  `if caller_kind == Member but payload is None then panic` boolean
  ladder).
- The signature itself is the discriminator — easy to grep, easy to
  bind in Python/JS clients.
- Mirrors how `hvym-collective` and `hvym-pin-service` already
  separate related operations.

```rust
fn revoke_by_app(e: Env, app_address: Address);

fn revoke_by_member(
    e: Env,
    app_address:    Address,
    nonce:          u64,
    auth_payload:   Bytes,
    auth_signature: BytesN<64>,
);
```

Semantics for both:

1. Load record. Panic if absent. Panic if already `Revoked`.
2. `revoke_by_app`: `app_address.require_auth()`.
3. `revoke_by_member`: reconstruct canonical member-revoke payload from
   `(app_address, nonce)`, byte-compare to `auth_payload`,
   `ed25519_verify(&record.member_pubkey, ...)`.
4. Set `record.status = Revoked`, `record.updated_at = now`.
5. Emit `REVOKE` event (carries which side initiated).

`Active → Revoked` is **final**. There is no `unrevoke` path. If a
member wants to recover, they re-install the app under a fresh
keypair and register again — the protocol does not pretend a revoked
identity can be safely brought back.

### Views

```rust
fn get_app_ca(e: Env, app_address: Address) -> Option<AppCaRecord>;
```

Returns `Some(record)` if registered. The returned `record.status`
is `Revoked` when stored as revoked; otherwise the helper transitions
`Active → Expired` if `expires_at <= now` so callers don't have to
recompute. Storage is not mutated.

```rust
fn is_trusted(e: Env, app_address: Address, fingerprint: BytesN<32>) -> bool;
```

Returns `true` iff: record exists, `status == Active`,
`expires_at > now`, and `fingerprint == record.fingerprint`. This is
the fast verifier-side trust check.

```rust
fn apps_of_member(e: Env, member_pubkey: BytesN<32>) -> Vec<Address>;
```

Returns the list of app addresses that were ever registered under
this member pubkey. Includes revoked ones — callers filter via
`get_app_ca` if they want active-only.

```rust
fn list_active_apps(e: Env) -> Vec<Address>;
```

Returns the addresses of all registered apps whose
**stored** status is `Active`. Does not filter by expiry (use
`is_trusted` per-address for that — expiry filtering would force a
record read per app, which we leave as the caller's call).

### Events

All events use the `(symbol, symbol)` topic pattern this repo
already uses. Event topics:

| Topic | Payload struct |
|---|---|
| `(REGISTER, appca)` | `RegisterEvent { app_address, member_pubkey, app_kind, fingerprint, expires_at }` |
| `(ROTATE,   appca)` | `RotateEvent { app_address, new_fingerprint, new_expires_at, serial }` |
| `(REVOKE,   appca)` | `RevokeEvent { app_address, by_app: bool }` |

Symbols stay ≤ 9 chars (Soroban requirement: `symbol_short!`).

---

## Storage rent — proof of active use

This is repeated from `C2PA.md §8.1` because it's load-bearing for any
maintenance decisions on this contract:

Soroban persistent storage has a rent model. Entries that aren't
periodically bumped decay and eventually expire. In this design, rent
on an `AppCaRecord` is paid by the **app instance** that registered it
(the app holds a funded Stellar keypair; submitting any transaction
under that key implicitly funds rent or extends TTL through the
standard Soroban mechanics).

The structural property this gives us:

> **An active artist's app keeps their provenance record alive on
> chain. An abandoned app lets it decay.**

The trust list self-cleans through use. Abandoned app instances drop
off after extended inactivity; active ones stay on indefinitely.

For this contract, that means:

- **No `bump_record` admin entry point.** We deliberately do not
  expose a way for the cooperative (or anyone other than the app
  itself) to pay rent on someone else's `AppCaRecord`. Doing so would
  subsidize inactive accounts, breaking the proof-of-active-use
  property.
- **The app's own write path is the bump.** Every successful
  `rotate_app_ca` / `revoke_by_app` extends the record's TTL through
  the usual Soroban write semantics. Apps that never call back will
  decay.
- **Revoked records can decay freely.** A `Revoked` record's job is
  done after it propagates to verifier caches; if its rent isn't paid
  it's allowed to disappear from the registry. Verifiers cache
  revocations themselves.

---

## File structure

```
hvym-cert-registry/
├── Cargo.toml
└── src/
    ├── lib.rs   # types + entry points
    └── test.rs  # unit + integration tests
```

The file is small enough that splitting into `types.rs` / `storage.rs`
/ `auth.rs` would add navigation overhead without payoff. `hvym-registry`
takes the same approach; we mirror it.

---

## Tests required (matrix locked)

`src/test.rs` covers, at minimum:

| Group | Tests |
|---|---|
| **register_app_ca — happy path** | (a) valid app auth + valid member sig writes record; (b) record has expected fields; (c) record indexed in `AllApps` + `AppsByMember`; (d) event emitted. |
| **register_app_ca — auth rejections** | (a) missing app auth (no `mock_all_auths`, no `mock_auths` for this call) panics; (b) bad signature panics; (c) `auth_payload` bytes don't match reconstructed canonical bytes → panics with `payload mismatch`. |
| **register_app_ca — semantic rejections** | (a) double-register same `app_address` panics; (b) `pubkey_alg != "ed25519"` panics; (c) `expires_at <= now` panics. |
| **rotate_app_ca — happy path** | (a) valid dual-auth bumps `serial`, updates `fingerprint` / `expires_at` / `updated_at`, leaves `member_pubkey` + `app_kind` + `issued_at` unchanged. |
| **rotate_app_ca — rejections** | (a) missing app auth panics; (b) bad signature panics; (c) payload mismatch panics; (d) record absent panics; (e) record already revoked panics. |
| **revoke_by_app — happy path** | sets `status = Revoked`, emits event with `by_app: true`. |
| **revoke_by_app — rejections** | missing auth panics; absent record panics; already-revoked panics. |
| **revoke_by_member — happy path** | valid sig sets `status = Revoked`, emits event with `by_app: false`. |
| **revoke_by_member — rejections** | bad sig panics; payload mismatch panics; absent record panics; already-revoked panics. |
| **finality** | after revoke, neither `rotate_app_ca` nor either revoke entry point can run on the record — all panic. There is no `unrevoke` path; confirmed by the absence of any such function. |
| **views** | `get_app_ca` returns `None` for unknown; `Some` with stored fields for known; transitions `Active → Expired` in returned `status` when ledger advances past `expires_at` (storage unchanged). `is_trusted` returns the combined-check boolean (true/false matrix for each of `absent / active / expired / revoked / wrong-fingerprint`). `list_active_apps` excludes revoked but includes expired. `apps_of_member` returns the full ever-registered list. |
| **strkey ↔ raw-pubkey** *(empirical unknown #3)* | a fixture test using a hardcoded ed25519 keypair signs a known message; the test passes the raw 32-byte pubkey to `register_app_ca`; `ed25519_verify` accepts. (This locks the assumption that strkey-decoded bytes are what the verifier wants.) |

Auth-rejection tests use the per-invocation `mock_auths` pattern (not
the global `mock_all_auths`) so the test exerts the exact auth shape
being checked. Bad-signature tests construct a signature over a
different message.

---

## What this contract deliberately does NOT do

Surface to the user if any of these get questioned during review or
implementation:

- **Does not have an admin.** No admin list. No admin entry points.
  Removing this property breaks `C2PA.md §1.2`.
- **Does not touch `hvym-roster`.** Roster membership is not a
  precondition for registering an app CA; per `INKTERNITY.md §3.1`,
  every Heavymeta member (free or paid) has a Stellar keypair and can
  authorize registrations. Roster-gating would defeat that.
- **Does not store the CA cert itself.** Only its SHA-256 fingerprint.
  The cert lives on the user's machine; the registry confirms which
  fingerprint is currently authoritative for an app address.
- **Does not store leaf certs.** Leaf certs are ephemeral and issued
  per-publish; per `C2PA.md §4.3` they never touch the chain.
- **Does not bump rent on someone else's record.** Active-use is the
  rent mechanic; subsidizing abandoned apps would break the
  self-cleaning property (`C2PA.md §8.1`).
- **Does not "un-revoke".** `Active → Revoked` is terminal. Recovery
  is a new keypair + a new registration.
- **Does not validate that `app_address` and `member_pubkey` are
  different from each other.** That's a Portal-side concern; nothing
  on chain requires app and member to be distinct keys.

---

## Coordination — out of scope for this commit

Per `C2PA.md §7` (Phased rollout):

- **Portal-side `mint_app_ca_registration_token`** lives in
  `heavymeta_collective/payments/` and is handled by a different agent.
- **Inkternity desktop integration** lives in `D:/repos/infinipaint`.
- **Andromica desktop integration** lives in
  `metavinci/glasswing`.
- **Pintheon C2PA integration** is deferred — do not extend
  `hvym-pin-service` or `hvym-roster` in this commit
  (`C2PA.md §5.1`).

The contract is queryable on its own once deployed. Each downstream
integration only needs the deployed contract ID + the JSON schema
locked above.

---

## Deployment checklist (operator-facing — not in this commit)

1. Build with `python build_contracts.py --contract hvym-cert-registry`.
2. Test with `cargo test -p hvym-cert-registry` (or
   `python test_all_contracts.py` for the full suite).
3. Deploy to testnet:
   `python deploy_contracts.py --deployer-acct TESTNET_DEPLOYER
   --network testnet`. Constructor takes no args
   (`hvym_cert_registry_args.json` is `{}`).
4. **Measure the three empirical unknowns above** and fold the
   resulting numbers back into `C2PA.md §4.4`'s funding-floor
   guidance before mainnet deployment.
5. Generate Python bindings:
   `python generate_bindings.py --from-file deployments.testnet.json
   --contracts hvym_cert_registry`.
6. Self-register the cert registry in `hvym_registry` so downstream
   tooling can discover it via the on-chain registry pattern used by
   the other contracts.
7. Only then: mainnet deployment by the human reviewer.
