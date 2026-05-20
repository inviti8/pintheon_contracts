#![no_std]
//! hvym-cert-registry — Stellar-anchored trust list for Heavymeta app-instance
//! X.509 CAs. See `HVYM_CERT_REGISTRY.md` for the design doc and `C2PA.md` in
//! the `hvym-market-muscle` repo for the broader C2PA architecture.
//!
//! No admin. Every state-changing entry point requires either:
//!   - `app_address.require_auth()` (the app proves it holds its keypair), or
//!   - `e.crypto().ed25519_verify(member_pubkey, payload, signature)`
//!     (the authorizing member proves consent), or
//!   - both (register / rotate).
//!
//! Canonical signing payloads are sorted-key compact JSON. The contract
//! reconstructs those bytes from typed params and byte-compares to the
//! submitted `auth_payload` before calling `ed25519_verify`.

use soroban_sdk::{
    contract, contractimpl, contracttype, symbol_short, Address, Bytes, BytesN, Env, String, Vec,
};

mod test;

// ── Constants ───────────────────────────────────────────────────────────────

/// Only ed25519 is accepted in v1. Field reserved for future "ecdsa-p256".
const PUBKEY_ALG_ED25519: &[u8] = b"ed25519";

/// Stack buffer big enough for the largest canonical register payload (≈313
/// bytes worst case). Rotate and revoke payloads are smaller.
const PAYLOAD_BUF_LEN: usize = 512;

/// Stellar strkey addresses are 56 ASCII chars (G… for accounts, C… for
/// contracts). 80 leaves headroom for any future Address variants.
const ADDR_STR_BUF_LEN: usize = 80;

// ── Data types ──────────────────────────────────────────────────────────────

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AppKind {
    Inkternity,
    Andromica,
    Pintheon,
    Other,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CertStatus {
    Active,
    Revoked,
    Expired,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DataKey {
    AppCa(Address),
    AppsByMember(BytesN<32>),
    AllApps,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AppCaRecord {
    pub app_address: Address,
    pub member_pubkey: BytesN<32>,
    pub app_kind: AppKind,
    pub fingerprint: BytesN<32>,
    pub pubkey_alg: String,
    pub issued_at: u64,
    pub updated_at: u64,
    pub expires_at: u64,
    pub status: CertStatus,
    pub serial: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RegisterEvent {
    pub app_address: Address,
    pub member_pubkey: BytesN<32>,
    pub app_kind: AppKind,
    pub fingerprint: BytesN<32>,
    pub expires_at: u64,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RotateEvent {
    pub app_address: Address,
    pub new_fingerprint: BytesN<32>,
    pub new_expires_at: u64,
    pub serial: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RevokeEvent {
    pub app_address: Address,
    pub by_app: bool,
}

// ── Contract ────────────────────────────────────────────────────────────────

#[contract]
pub struct CertRegistryContract;

#[contractimpl]
impl CertRegistryContract {
    pub fn __constructor(_e: Env) {
        // No admin to store. No config. Index keys are lazily created on
        // first write. See HVYM_CERT_REGISTRY.md "Architectural commitments".
    }

    // ── register_app_ca ─────────────────────────────────────────────────

    pub fn register_app_ca(
        e: Env,
        app_address: Address,
        member_pubkey: BytesN<32>,
        app_kind: AppKind,
        fingerprint: BytesN<32>,
        pubkey_alg: String,
        expires_at: u64,
        nonce: u64,
        auth_payload: Bytes,
        auth_signature: BytesN<64>,
    ) {
        // 1. App-side auth.
        app_address.require_auth();

        // 2. v1 alg gate.
        if !string_eq_bytes(&pubkey_alg, PUBKEY_ALG_ED25519) {
            panic!("unsupported pubkey_alg");
        }

        // 3. Per-app one-shot.
        let key = DataKey::AppCa(app_address.clone());
        if e.storage().persistent().has(&key) {
            panic!("app already registered");
        }

        // 4. Future expiry.
        let now = e.ledger().timestamp();
        if expires_at <= now {
            panic!("expires_at must be in the future");
        }

        // 5. Reconstruct canonical bytes + verify.
        let canonical = build_register_payload(
            &e,
            &app_address,
            &member_pubkey,
            &app_kind,
            &fingerprint,
            expires_at,
            nonce,
        );
        if canonical != auth_payload {
            panic!("auth_payload does not match params");
        }
        e.crypto()
            .ed25519_verify(&member_pubkey, &auth_payload, &auth_signature);

        // 6. Write record.
        let record = AppCaRecord {
            app_address: app_address.clone(),
            member_pubkey: member_pubkey.clone(),
            app_kind,
            fingerprint,
            pubkey_alg,
            issued_at: now,
            updated_at: now,
            expires_at,
            status: CertStatus::Active,
            serial: 1,
        };
        e.storage().persistent().set(&key, &record);

        // 7. Append to indexes.
        let all_key = DataKey::AllApps;
        let mut all: Vec<Address> = e
            .storage()
            .persistent()
            .get(&all_key)
            .unwrap_or_else(|| Vec::new(&e));
        all.push_back(app_address.clone());
        e.storage().persistent().set(&all_key, &all);

        let by_member_key = DataKey::AppsByMember(member_pubkey.clone());
        let mut by_member: Vec<Address> = e
            .storage()
            .persistent()
            .get(&by_member_key)
            .unwrap_or_else(|| Vec::new(&e));
        by_member.push_back(app_address.clone());
        e.storage().persistent().set(&by_member_key, &by_member);

        // 8. Event.
        let evt = RegisterEvent {
            app_address,
            member_pubkey,
            app_kind: record.app_kind.clone(),
            fingerprint: record.fingerprint.clone(),
            expires_at,
        };
        e.events()
            .publish((symbol_short!("REGISTER"), symbol_short!("appca")), evt);
    }

    // ── rotate_app_ca ───────────────────────────────────────────────────

    pub fn rotate_app_ca(
        e: Env,
        app_address: Address,
        new_fingerprint: BytesN<32>,
        new_expires_at: u64,
        nonce: u64,
        auth_payload: Bytes,
        auth_signature: BytesN<64>,
    ) {
        app_address.require_auth();

        let key = DataKey::AppCa(app_address.clone());
        let mut record: AppCaRecord = e
            .storage()
            .persistent()
            .get(&key)
            .expect("app not registered");

        if record.status == CertStatus::Revoked {
            panic!("app revoked");
        }

        let now = e.ledger().timestamp();
        if new_expires_at <= now {
            panic!("new_expires_at must be in the future");
        }

        let canonical =
            build_rotate_payload(&e, &app_address, &new_fingerprint, new_expires_at, nonce);
        if canonical != auth_payload {
            panic!("auth_payload does not match params");
        }
        e.crypto()
            .ed25519_verify(&record.member_pubkey, &auth_payload, &auth_signature);

        record.fingerprint = new_fingerprint.clone();
        record.expires_at = new_expires_at;
        record.updated_at = now;
        record.serial += 1;
        e.storage().persistent().set(&key, &record);

        let evt = RotateEvent {
            app_address,
            new_fingerprint,
            new_expires_at,
            serial: record.serial,
        };
        e.events()
            .publish((symbol_short!("ROTATE"), symbol_short!("appca")), evt);
    }

    // ── revoke_by_app ───────────────────────────────────────────────────

    pub fn revoke_by_app(e: Env, app_address: Address) {
        app_address.require_auth();

        let key = DataKey::AppCa(app_address.clone());
        let mut record: AppCaRecord = e
            .storage()
            .persistent()
            .get(&key)
            .expect("app not registered");

        if record.status == CertStatus::Revoked {
            panic!("app revoked");
        }

        record.status = CertStatus::Revoked;
        record.updated_at = e.ledger().timestamp();
        e.storage().persistent().set(&key, &record);

        let evt = RevokeEvent {
            app_address,
            by_app: true,
        };
        e.events()
            .publish((symbol_short!("REVOKE"), symbol_short!("appca")), evt);
    }

    // ── revoke_by_member ────────────────────────────────────────────────

    pub fn revoke_by_member(
        e: Env,
        app_address: Address,
        nonce: u64,
        auth_payload: Bytes,
        auth_signature: BytesN<64>,
    ) {
        let key = DataKey::AppCa(app_address.clone());
        let mut record: AppCaRecord = e
            .storage()
            .persistent()
            .get(&key)
            .expect("app not registered");

        if record.status == CertStatus::Revoked {
            panic!("app revoked");
        }

        let canonical = build_revoke_payload(&e, &app_address, nonce);
        if canonical != auth_payload {
            panic!("auth_payload does not match params");
        }
        e.crypto()
            .ed25519_verify(&record.member_pubkey, &auth_payload, &auth_signature);

        record.status = CertStatus::Revoked;
        record.updated_at = e.ledger().timestamp();
        e.storage().persistent().set(&key, &record);

        let evt = RevokeEvent {
            app_address,
            by_app: false,
        };
        e.events()
            .publish((symbol_short!("REVOKE"), symbol_short!("appca")), evt);
    }

    // ── Views ───────────────────────────────────────────────────────────

    /// Returns the stored record if present. The returned `status` is
    /// transitioned `Active -> Expired` at view time if `expires_at <= now`,
    /// so callers don't need to recompute. Storage is not mutated.
    pub fn get_app_ca(e: Env, app_address: Address) -> Option<AppCaRecord> {
        let key = DataKey::AppCa(app_address);
        let mut rec: AppCaRecord = e.storage().persistent().get(&key)?;
        if rec.status == CertStatus::Active && rec.expires_at <= e.ledger().timestamp() {
            rec.status = CertStatus::Expired;
        }
        Some(rec)
    }

    /// Fast trust check used by C2PA verifiers. True iff record exists,
    /// stored status is `Active`, `now < expires_at`, and fingerprint matches.
    pub fn is_trusted(e: Env, app_address: Address, fingerprint: BytesN<32>) -> bool {
        let key = DataKey::AppCa(app_address);
        let rec: AppCaRecord = match e.storage().persistent().get(&key) {
            Some(r) => r,
            None => return false,
        };
        rec.status == CertStatus::Active
            && rec.expires_at > e.ledger().timestamp()
            && rec.fingerprint == fingerprint
    }

    /// Every app address ever registered under `member_pubkey`, including
    /// revoked ones. Callers filter via `get_app_ca` for active-only.
    pub fn apps_of_member(e: Env, member_pubkey: BytesN<32>) -> Vec<Address> {
        let key = DataKey::AppsByMember(member_pubkey);
        e.storage()
            .persistent()
            .get(&key)
            .unwrap_or_else(|| Vec::new(&e))
    }

    /// All registered apps whose stored status is `Active`. Does not filter
    /// by expiry — that requires per-record reads, which callers can do
    /// selectively via `is_trusted` or `get_app_ca`.
    pub fn list_active_apps(e: Env) -> Vec<Address> {
        let all: Vec<Address> = e
            .storage()
            .persistent()
            .get(&DataKey::AllApps)
            .unwrap_or_else(|| Vec::new(&e));

        let mut active = Vec::new(&e);
        for app in all.iter() {
            let key = DataKey::AppCa(app.clone());
            if let Some(rec) = e.storage().persistent().get::<_, AppCaRecord>(&key) {
                if rec.status == CertStatus::Active {
                    active.push_back(app);
                }
            }
        }
        active
    }
}

// ── Canonical payload encoding ──────────────────────────────────────────────
//
// Sorted-key compact JSON, mirroring Inkternity Distribution's wire format
// (`INKTERNITY.md §4.3`). Build into a stack buffer, then materialize as
// `Bytes` once at the end.

fn build_register_payload(
    env: &Env,
    app_address: &Address,
    member_pubkey: &BytesN<32>,
    app_kind: &AppKind,
    fingerprint: &BytesN<32>,
    expires_at: u64,
    nonce: u64,
) -> Bytes {
    // {"a":"<addr>","alg":"ed25519","exp":<u64>,"fp":"<hex>",
    //  "i":"register-app-ca","k":"<AppKind>","m":"<hex>","n":<u64>}
    let mut buf = [0u8; PAYLOAD_BUF_LEN];
    let mut pos = 0usize;

    pos = write_slice(&mut buf, pos, b"{\"a\":\"");
    pos = write_address_strkey(&mut buf, pos, env, app_address);
    pos = write_slice(&mut buf, pos, b"\",\"alg\":\"ed25519\",\"exp\":");
    pos = write_u64(&mut buf, pos, expires_at);
    pos = write_slice(&mut buf, pos, b",\"fp\":\"");
    pos = write_hex32(&mut buf, pos, &fingerprint.to_array());
    pos = write_slice(&mut buf, pos, b"\",\"i\":\"register-app-ca\",\"k\":\"");
    pos = write_slice(&mut buf, pos, app_kind_bytes(app_kind));
    pos = write_slice(&mut buf, pos, b"\",\"m\":\"");
    pos = write_hex32(&mut buf, pos, &member_pubkey.to_array());
    pos = write_slice(&mut buf, pos, b"\",\"n\":");
    pos = write_u64(&mut buf, pos, nonce);
    pos = write_slice(&mut buf, pos, b"}");

    let mut out = Bytes::new(env);
    out.copy_from_slice(0, &buf[..pos]);
    out
}

fn build_rotate_payload(
    env: &Env,
    app_address: &Address,
    new_fingerprint: &BytesN<32>,
    new_expires_at: u64,
    nonce: u64,
) -> Bytes {
    // {"a":"<addr>","exp":<u64>,"fp":"<hex>","i":"rotate-app-ca","n":<u64>}
    let mut buf = [0u8; PAYLOAD_BUF_LEN];
    let mut pos = 0usize;

    pos = write_slice(&mut buf, pos, b"{\"a\":\"");
    pos = write_address_strkey(&mut buf, pos, env, app_address);
    pos = write_slice(&mut buf, pos, b"\",\"exp\":");
    pos = write_u64(&mut buf, pos, new_expires_at);
    pos = write_slice(&mut buf, pos, b",\"fp\":\"");
    pos = write_hex32(&mut buf, pos, &new_fingerprint.to_array());
    pos = write_slice(&mut buf, pos, b"\",\"i\":\"rotate-app-ca\",\"n\":");
    pos = write_u64(&mut buf, pos, nonce);
    pos = write_slice(&mut buf, pos, b"}");

    let mut out = Bytes::new(env);
    out.copy_from_slice(0, &buf[..pos]);
    out
}

fn build_revoke_payload(env: &Env, app_address: &Address, nonce: u64) -> Bytes {
    // {"a":"<addr>","i":"revoke-app-ca","n":<u64>}
    let mut buf = [0u8; PAYLOAD_BUF_LEN];
    let mut pos = 0usize;

    pos = write_slice(&mut buf, pos, b"{\"a\":\"");
    pos = write_address_strkey(&mut buf, pos, env, app_address);
    pos = write_slice(&mut buf, pos, b"\",\"i\":\"revoke-app-ca\",\"n\":");
    pos = write_u64(&mut buf, pos, nonce);
    pos = write_slice(&mut buf, pos, b"}");

    let mut out = Bytes::new(env);
    out.copy_from_slice(0, &buf[..pos]);
    out
}

// ── Encoding helpers ────────────────────────────────────────────────────────

fn write_slice(buf: &mut [u8; PAYLOAD_BUF_LEN], pos: usize, src: &[u8]) -> usize {
    let end = pos + src.len();
    buf[pos..end].copy_from_slice(src);
    end
}

fn write_u64(buf: &mut [u8; PAYLOAD_BUF_LEN], pos: usize, mut n: u64) -> usize {
    if n == 0 {
        buf[pos] = b'0';
        return pos + 1;
    }
    // Write digits in reverse, then reverse the written range in-place.
    let start = pos;
    let mut end = pos;
    while n > 0 {
        buf[end] = b'0' + (n % 10) as u8;
        n /= 10;
        end += 1;
    }
    buf[start..end].reverse();
    end
}

fn write_hex32(buf: &mut [u8; PAYLOAD_BUF_LEN], pos: usize, src: &[u8; 32]) -> usize {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut p = pos;
    for &b in src.iter() {
        buf[p] = HEX[(b >> 4) as usize];
        buf[p + 1] = HEX[(b & 0x0f) as usize];
        p += 2;
    }
    p
}

fn write_address_strkey(
    buf: &mut [u8; PAYLOAD_BUF_LEN],
    pos: usize,
    _env: &Env,
    addr: &Address,
) -> usize {
    let s: String = addr.to_string();
    let len = s.len() as usize;
    let mut tmp = [0u8; ADDR_STR_BUF_LEN];
    s.copy_into_slice(&mut tmp[..len]);
    buf[pos..pos + len].copy_from_slice(&tmp[..len]);
    pos + len
}

fn app_kind_bytes(k: &AppKind) -> &'static [u8] {
    match k {
        AppKind::Inkternity => b"Inkternity",
        AppKind::Andromica => b"Andromica",
        AppKind::Pintheon => b"Pintheon",
        AppKind::Other => b"Other",
    }
}

fn string_eq_bytes(s: &String, target: &[u8]) -> bool {
    let len = s.len() as usize;
    if len != target.len() {
        return false;
    }
    let mut tmp = [0u8; 32];
    if len > tmp.len() {
        return false;
    }
    s.copy_into_slice(&mut tmp[..len]);
    &tmp[..len] == target
}
