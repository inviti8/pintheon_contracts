#![cfg(test)]
//! Tests for hvym-cert-registry. See HVYM_CERT_REGISTRY.md "Tests required"
//! for the matrix this file covers.
//!
//! The tests construct canonical JSON payloads independently of the contract
//! (via `alloc::format!`) so that any drift between the contract's
//! reconstruction and the agreed-on wire format causes test failures rather
//! than silent mismatches.

extern crate alloc;

use alloc::format;
use alloc::string::String as StdString;
use alloc::vec::Vec as StdVec;

use ed25519_dalek::{Signer, SigningKey};

use soroban_sdk::testutils::{Address as _, Events as _, Ledger as _, MockAuth, MockAuthInvoke};
use soroban_sdk::{Address, Bytes, BytesN, Env, IntoVal, String};

use crate::{
    AppCaRecord, AppKind, CertRegistryContract, CertRegistryContractClient, CertStatus,
    RegisterEvent, RevokeEvent, RotateEvent,
};

// ── Helpers ─────────────────────────────────────────────────────────────────

fn hex_encode(b: &[u8]) -> StdString {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut s = StdString::with_capacity(b.len() * 2);
    for &x in b.iter() {
        s.push(HEX[(x >> 4) as usize] as char);
        s.push(HEX[(x & 0x0f) as usize] as char);
    }
    s
}

fn make_member(env: &Env, seed: u8) -> (SigningKey, BytesN<32>) {
    let secret = [seed; 32];
    let sk = SigningKey::from_bytes(&secret);
    let pubkey_arr: [u8; 32] = sk.verifying_key().to_bytes();
    let pubkey = BytesN::from_array(env, &pubkey_arr);
    (sk, pubkey)
}

fn addr_strkey(addr: &Address) -> StdString {
    let s: String = addr.to_string();
    let len = s.len() as usize;
    let mut buf = [0u8; 80];
    s.copy_into_slice(&mut buf[..len]);
    StdString::from_utf8(buf[..len].to_vec()).expect("strkey is ASCII")
}

fn canonical_register(
    app: &Address,
    member: &BytesN<32>,
    kind: &AppKind,
    fingerprint: &BytesN<32>,
    expires_at: u64,
    nonce: u64,
) -> StdVec<u8> {
    let kind_str = match kind {
        AppKind::Inkternity => "Inkternity",
        AppKind::Andromica => "Andromica",
        AppKind::Pintheon => "Pintheon",
        AppKind::Other => "Other",
    };
    let s = format!(
        r#"{{"a":"{}","alg":"ed25519","exp":{},"fp":"{}","i":"register-app-ca","k":"{}","m":"{}","n":{}}}"#,
        addr_strkey(app),
        expires_at,
        hex_encode(&fingerprint.to_array()),
        kind_str,
        hex_encode(&member.to_array()),
        nonce,
    );
    s.into_bytes()
}

fn canonical_rotate(
    app: &Address,
    new_fp: &BytesN<32>,
    new_exp: u64,
    nonce: u64,
) -> StdVec<u8> {
    let s = format!(
        r#"{{"a":"{}","exp":{},"fp":"{}","i":"rotate-app-ca","n":{}}}"#,
        addr_strkey(app),
        new_exp,
        hex_encode(&new_fp.to_array()),
        nonce,
    );
    s.into_bytes()
}

fn canonical_revoke(app: &Address, nonce: u64) -> StdVec<u8> {
    let s = format!(
        r#"{{"a":"{}","i":"revoke-app-ca","n":{}}}"#,
        addr_strkey(app),
        nonce,
    );
    s.into_bytes()
}

fn sign(env: &Env, sk: &SigningKey, msg: &[u8]) -> BytesN<64> {
    let sig = sk.sign(msg);
    BytesN::from_array(env, &sig.to_bytes())
}

fn bytes_of(env: &Env, b: &[u8]) -> Bytes {
    let mut out = Bytes::new(env);
    out.copy_from_slice(0, b);
    out
}

fn setup(env: &Env) -> CertRegistryContractClient {
    let contract_id = env.register(CertRegistryContract, ());
    CertRegistryContractClient::new(env, &contract_id)
}

fn fingerprint(env: &Env, seed: u8) -> BytesN<32> {
    BytesN::from_array(env, &[seed; 32])
}

fn ed25519_alg(env: &Env) -> String {
    String::from_str(env, "ed25519")
}

const FUTURE_EXP: u64 = 10_000_000_000; // far in the future

// Build the full register-args tuple the test will pass to the contract,
// including the canonical payload + signature.
struct RegisterArgs {
    app: Address,
    member_pk: BytesN<32>,
    kind: AppKind,
    fp: BytesN<32>,
    alg: String,
    expires_at: u64,
    nonce: u64,
    payload: Bytes,
    signature: BytesN<64>,
}

fn make_register_args(
    env: &Env,
    sk: &SigningKey,
    app: Address,
    member_pk: BytesN<32>,
    kind: AppKind,
    fp: BytesN<32>,
    expires_at: u64,
    nonce: u64,
) -> RegisterArgs {
    let canon = canonical_register(&app, &member_pk, &kind, &fp, expires_at, nonce);
    let payload = bytes_of(env, &canon);
    let signature = sign(env, sk, &canon);
    RegisterArgs {
        app,
        member_pk,
        kind,
        fp,
        alg: ed25519_alg(env),
        expires_at,
        nonce,
        payload,
        signature,
    }
}

// ── register_app_ca — happy path ────────────────────────────────────────────

#[test]
fn register_happy_path_writes_record() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0x11);
    let app = Address::generate(&env);
    let fp = fingerprint(&env, 0xAB);
    let args = make_register_args(
        &env,
        &sk,
        app.clone(),
        member_pk.clone(),
        AppKind::Inkternity,
        fp.clone(),
        FUTURE_EXP,
        42,
    );

    client.register_app_ca(
        &args.app,
        &args.member_pk,
        &args.kind,
        &args.fp,
        &args.alg,
        &args.expires_at,
        &args.nonce,
        &args.payload,
        &args.signature,
    );

    let rec = client.get_app_ca(&app).unwrap();
    assert_eq!(rec.app_address, app);
    assert_eq!(rec.member_pubkey, member_pk);
    assert_eq!(rec.app_kind, AppKind::Inkternity);
    assert_eq!(rec.fingerprint, fp);
    assert_eq!(rec.expires_at, FUTURE_EXP);
    assert_eq!(rec.status, CertStatus::Active);
    assert_eq!(rec.serial, 1);
    assert_eq!(rec.issued_at, rec.updated_at);
}

#[test]
fn register_happy_path_pintheon_kind() {
    // Forward-compat: Pintheon AppKind round-trips through register + storage.
    // Per C2PA.md §5.1 the Pintheon C2PA integration itself is deferred, but
    // the registry must accept the kind so Pintheon nodes can register their
    // app CAs when that work lands.
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0x18);
    let app = Address::generate(&env);
    let fp = fingerprint(&env, 0x1F);
    let args = make_register_args(
        &env, &sk, app.clone(), member_pk,
        AppKind::Pintheon, fp.clone(), FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );

    let rec = client.get_app_ca(&app).unwrap();
    assert_eq!(rec.app_kind, AppKind::Pintheon);
}

#[test]
fn register_indexes_app_in_all_and_by_member() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0x22);
    let app1 = Address::generate(&env);
    let app2 = Address::generate(&env);

    for (app, nonce) in [(&app1, 1u64), (&app2, 2u64)] {
        let args = make_register_args(
            &env,
            &sk,
            app.clone(),
            member_pk.clone(),
            AppKind::Andromica,
            fingerprint(&env, 0x10),
            FUTURE_EXP,
            nonce,
        );
        client.register_app_ca(
            &args.app,
            &args.member_pk,
            &args.kind,
            &args.fp,
            &args.alg,
            &args.expires_at,
            &args.nonce,
            &args.payload,
            &args.signature,
        );
    }

    let by_member = client.apps_of_member(&member_pk);
    assert_eq!(by_member.len(), 2);

    let active = client.list_active_apps();
    assert_eq!(active.len(), 2);
}

#[test]
fn register_emits_event() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0x33);
    let app = Address::generate(&env);
    let fp = fingerprint(&env, 0xCD);
    let args = make_register_args(
        &env,
        &sk,
        app.clone(),
        member_pk.clone(),
        AppKind::Inkternity,
        fp.clone(),
        FUTURE_EXP,
        7,
    );
    client.register_app_ca(
        &args.app,
        &args.member_pk,
        &args.kind,
        &args.fp,
        &args.alg,
        &args.expires_at,
        &args.nonce,
        &args.payload,
        &args.signature,
    );

    let events = env.events().all();
    let last = events.last().unwrap();
    let evt: RegisterEvent = last.2.into_val(&env);
    assert_eq!(evt.app_address, app);
    assert_eq!(evt.member_pubkey, member_pk);
    assert_eq!(evt.fingerprint, fp);
    assert_eq!(evt.expires_at, FUTURE_EXP);
}

// ── register_app_ca — auth & semantic rejections ────────────────────────────

#[test]
#[should_panic]
fn register_rejects_when_app_auth_missing() {
    let env = Env::default();
    // No mock_all_auths — and we won't supply an explicit mock_auth for app.
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0x44);
    let app = Address::generate(&env);
    let args = make_register_args(
        &env,
        &sk,
        app.clone(),
        member_pk,
        AppKind::Inkternity,
        fingerprint(&env, 0x01),
        FUTURE_EXP,
        1,
    );

    // Call without any mocked auth — app_address.require_auth() panics.
    client.register_app_ca(
        &args.app,
        &args.member_pk,
        &args.kind,
        &args.fp,
        &args.alg,
        &args.expires_at,
        &args.nonce,
        &args.payload,
        &args.signature,
    );
}

#[test]
#[should_panic]
fn register_rejects_bad_signature() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0x55);
    let (sk_wrong, _) = make_member(&env, 0x99);
    let app = Address::generate(&env);
    let fp = fingerprint(&env, 0x02);

    // Valid canonical payload, but signed with the WRONG key.
    let canon = canonical_register(
        &app,
        &member_pk,
        &AppKind::Other,
        &fp,
        FUTURE_EXP,
        99,
    );
    let payload = bytes_of(&env, &canon);
    let bad_sig = sign(&env, &sk_wrong, &canon);
    let _ = sk; // suppress unused-var warning

    client.register_app_ca(
        &app,
        &member_pk,
        &AppKind::Other,
        &fp,
        &ed25519_alg(&env),
        &FUTURE_EXP,
        &99u64,
        &payload,
        &bad_sig,
    );
}

#[test]
#[should_panic(expected = "auth_payload does not match params")]
fn register_rejects_payload_param_mismatch() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0x66);
    let app = Address::generate(&env);
    let fp_a = fingerprint(&env, 0x03);
    let fp_b = fingerprint(&env, 0x04);

    // Sign over canonical bytes for fp_a but submit fp_b as the typed param.
    let canon = canonical_register(
        &app,
        &member_pk,
        &AppKind::Inkternity,
        &fp_a,
        FUTURE_EXP,
        5,
    );
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);

    client.register_app_ca(
        &app,
        &member_pk,
        &AppKind::Inkternity,
        &fp_b, // mismatched
        &ed25519_alg(&env),
        &FUTURE_EXP,
        &5u64,
        &payload,
        &signature,
    );
}

#[test]
#[should_panic(expected = "app already registered")]
fn register_rejects_double_registration() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0x77);
    let app = Address::generate(&env);

    let args1 = make_register_args(
        &env,
        &sk,
        app.clone(),
        member_pk.clone(),
        AppKind::Inkternity,
        fingerprint(&env, 0x05),
        FUTURE_EXP,
        1,
    );
    client.register_app_ca(
        &args1.app,
        &args1.member_pk,
        &args1.kind,
        &args1.fp,
        &args1.alg,
        &args1.expires_at,
        &args1.nonce,
        &args1.payload,
        &args1.signature,
    );

    // Second registration for the same app_address must panic.
    let args2 = make_register_args(
        &env,
        &sk,
        app.clone(),
        member_pk.clone(),
        AppKind::Inkternity,
        fingerprint(&env, 0x06),
        FUTURE_EXP,
        2,
    );
    client.register_app_ca(
        &args2.app,
        &args2.member_pk,
        &args2.kind,
        &args2.fp,
        &args2.alg,
        &args2.expires_at,
        &args2.nonce,
        &args2.payload,
        &args2.signature,
    );
}

#[test]
#[should_panic(expected = "unsupported pubkey_alg")]
fn register_rejects_non_ed25519_alg() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0x88);
    let app = Address::generate(&env);
    let fp = fingerprint(&env, 0x07);
    let canon = canonical_register(&app, &member_pk, &AppKind::Other, &fp, FUTURE_EXP, 1);
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);

    let bad_alg = String::from_str(&env, "ecdsa-p256");

    client.register_app_ca(
        &app,
        &member_pk,
        &AppKind::Other,
        &fp,
        &bad_alg,
        &FUTURE_EXP,
        &1u64,
        &payload,
        &signature,
    );
}

#[test]
#[should_panic(expected = "expires_at must be in the future")]
fn register_rejects_past_expiry() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);
    // Force ledger timestamp ahead of our expires_at value.
    env.ledger().with_mut(|li| li.timestamp = 1_000);

    let (sk, member_pk) = make_member(&env, 0xAA);
    let app = Address::generate(&env);
    let fp = fingerprint(&env, 0x08);
    let past_exp: u64 = 999; // <= 1000
    let canon = canonical_register(&app, &member_pk, &AppKind::Inkternity, &fp, past_exp, 1);
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);

    client.register_app_ca(
        &app,
        &member_pk,
        &AppKind::Inkternity,
        &fp,
        &ed25519_alg(&env),
        &past_exp,
        &1u64,
        &payload,
        &signature,
    );
}

// ── rotate_app_ca ───────────────────────────────────────────────────────────

#[test]
fn rotate_happy_path() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xB1);
    let app = Address::generate(&env);
    let fp_v1 = fingerprint(&env, 0x10);
    let fp_v2 = fingerprint(&env, 0x20);

    // Register first
    let args = make_register_args(
        &env,
        &sk,
        app.clone(),
        member_pk.clone(),
        AppKind::Inkternity,
        fp_v1.clone(),
        FUTURE_EXP,
        1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );
    let before = client.get_app_ca(&app).unwrap();

    // Advance the ledger so updated_at can differ from issued_at.
    env.ledger().with_mut(|li| li.timestamp += 10);

    let new_exp = FUTURE_EXP + 1_000_000;
    let canon = canonical_rotate(&app, &fp_v2, new_exp, 50);
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);
    client.rotate_app_ca(&app, &fp_v2, &new_exp, &50u64, &payload, &signature);

    let after = client.get_app_ca(&app).unwrap();
    assert_eq!(after.fingerprint, fp_v2);
    assert_eq!(after.expires_at, new_exp);
    assert_eq!(after.serial, 2);
    assert_eq!(after.app_kind, before.app_kind);
    assert_eq!(after.member_pubkey, before.member_pubkey);
    assert_eq!(after.issued_at, before.issued_at);
    assert!(after.updated_at > before.updated_at);
    assert_eq!(after.status, CertStatus::Active);
}

#[test]
#[should_panic]
fn rotate_rejects_bad_signature() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xB2);
    let (sk_wrong, _) = make_member(&env, 0xCC);
    let app = Address::generate(&env);
    let fp_v1 = fingerprint(&env, 0x11);
    let fp_v2 = fingerprint(&env, 0x21);

    let args = make_register_args(
        &env, &sk, app.clone(), member_pk.clone(),
        AppKind::Inkternity, fp_v1, FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );

    let new_exp = FUTURE_EXP + 1;
    let canon = canonical_rotate(&app, &fp_v2, new_exp, 1);
    let payload = bytes_of(&env, &canon);
    let bad_sig = sign(&env, &sk_wrong, &canon);
    client.rotate_app_ca(&app, &fp_v2, &new_exp, &1u64, &payload, &bad_sig);
}

#[test]
#[should_panic(expected = "auth_payload does not match params")]
fn rotate_rejects_payload_mismatch() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xB3);
    let app = Address::generate(&env);
    let fp_v1 = fingerprint(&env, 0x12);
    let fp_v2 = fingerprint(&env, 0x22);
    let fp_v3 = fingerprint(&env, 0x32);

    let args = make_register_args(
        &env, &sk, app.clone(), member_pk.clone(),
        AppKind::Inkternity, fp_v1, FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );

    let new_exp = FUTURE_EXP + 1;
    // sign over fp_v2 but submit fp_v3 as the typed param
    let canon = canonical_rotate(&app, &fp_v2, new_exp, 1);
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);
    client.rotate_app_ca(&app, &fp_v3, &new_exp, &1u64, &payload, &signature);
}

#[test]
#[should_panic(expected = "app not registered")]
fn rotate_rejects_absent_record() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, _member_pk) = make_member(&env, 0xB4);
    let app = Address::generate(&env);
    let new_fp = fingerprint(&env, 0x40);
    let new_exp = FUTURE_EXP;
    let canon = canonical_rotate(&app, &new_fp, new_exp, 1);
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);

    client.rotate_app_ca(&app, &new_fp, &new_exp, &1u64, &payload, &signature);
}

// ── revoke_by_app ───────────────────────────────────────────────────────────

#[test]
fn revoke_by_app_happy_path() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xC1);
    let app = Address::generate(&env);
    let args = make_register_args(
        &env, &sk, app.clone(), member_pk,
        AppKind::Inkternity, fingerprint(&env, 0x50), FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );

    client.revoke_by_app(&app);

    // Event emitted with by_app: true — read BEFORE any view call (view calls
    // reset env.events().all()).
    let events = env.events().all();
    let last = events.last().unwrap();
    let evt: RevokeEvent = last.2.into_val(&env);
    assert!(evt.by_app);
    assert_eq!(evt.app_address, app);

    let rec = client.get_app_ca(&app).unwrap();
    assert_eq!(rec.status, CertStatus::Revoked);
}

#[test]
#[should_panic(expected = "app not registered")]
fn revoke_by_app_rejects_absent_record() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let app = Address::generate(&env);
    client.revoke_by_app(&app);
}

#[test]
#[should_panic(expected = "app revoked")]
fn revoke_by_app_rejects_already_revoked() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xC2);
    let app = Address::generate(&env);
    let args = make_register_args(
        &env, &sk, app.clone(), member_pk,
        AppKind::Inkternity, fingerprint(&env, 0x51), FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );
    client.revoke_by_app(&app);
    // Second revoke must panic.
    client.revoke_by_app(&app);
}

// ── revoke_by_member ────────────────────────────────────────────────────────

#[test]
fn revoke_by_member_happy_path() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xD1);
    let app = Address::generate(&env);
    let args = make_register_args(
        &env, &sk, app.clone(), member_pk,
        AppKind::Andromica, fingerprint(&env, 0x60), FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );

    let canon = canonical_revoke(&app, 7);
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);
    client.revoke_by_member(&app, &7u64, &payload, &signature);

    // Read events BEFORE the view call.
    let events = env.events().all();
    let last = events.last().unwrap();
    let evt: RevokeEvent = last.2.into_val(&env);
    assert!(!evt.by_app);

    let rec = client.get_app_ca(&app).unwrap();
    assert_eq!(rec.status, CertStatus::Revoked);
}

#[test]
#[should_panic]
fn revoke_by_member_rejects_bad_signature() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xD2);
    let (sk_wrong, _) = make_member(&env, 0xEE);
    let app = Address::generate(&env);
    let args = make_register_args(
        &env, &sk, app.clone(), member_pk,
        AppKind::Inkternity, fingerprint(&env, 0x61), FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );

    let canon = canonical_revoke(&app, 1);
    let payload = bytes_of(&env, &canon);
    let bad_sig = sign(&env, &sk_wrong, &canon);
    client.revoke_by_member(&app, &1u64, &payload, &bad_sig);
}

#[test]
#[should_panic(expected = "auth_payload does not match params")]
fn revoke_by_member_rejects_payload_mismatch() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xD3);
    let app = Address::generate(&env);
    let args = make_register_args(
        &env, &sk, app.clone(), member_pk,
        AppKind::Inkternity, fingerprint(&env, 0x62), FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );

    // Sign payload for nonce=1 but submit nonce=2.
    let canon = canonical_revoke(&app, 1);
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);
    client.revoke_by_member(&app, &2u64, &payload, &signature);
}

// ── Finality: revoked is terminal ───────────────────────────────────────────

#[test]
#[should_panic(expected = "app revoked")]
fn rotate_after_revoke_panics() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xE1);
    let app = Address::generate(&env);
    let args = make_register_args(
        &env, &sk, app.clone(), member_pk,
        AppKind::Inkternity, fingerprint(&env, 0x70), FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );
    client.revoke_by_app(&app);

    // Try to rotate after revoke.
    let new_fp = fingerprint(&env, 0x71);
    let new_exp = FUTURE_EXP + 1;
    let canon = canonical_rotate(&app, &new_fp, new_exp, 99);
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);
    client.rotate_app_ca(&app, &new_fp, &new_exp, &99u64, &payload, &signature);
}

#[test]
#[should_panic(expected = "app revoked")]
fn revoke_by_member_after_revoke_by_app_panics() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xE2);
    let app = Address::generate(&env);
    let args = make_register_args(
        &env, &sk, app.clone(), member_pk,
        AppKind::Inkternity, fingerprint(&env, 0x80), FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );
    client.revoke_by_app(&app);

    let canon = canonical_revoke(&app, 1);
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);
    client.revoke_by_member(&app, &1u64, &payload, &signature);
}

// ── Views ───────────────────────────────────────────────────────────────────

#[test]
fn get_app_ca_returns_none_for_unknown() {
    let env = Env::default();
    let client = setup(&env);
    let app = Address::generate(&env);
    assert!(client.get_app_ca(&app).is_none());
}

#[test]
fn get_app_ca_transitions_to_expired_at_view_time() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);
    env.ledger().with_mut(|li| li.timestamp = 100);

    let (sk, member_pk) = make_member(&env, 0xF1);
    let app = Address::generate(&env);
    let near_exp: u64 = 200;
    let canon = canonical_register(
        &app, &member_pk, &AppKind::Inkternity, &fingerprint(&env, 0x90),
        near_exp, 1,
    );
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);
    client.register_app_ca(
        &app, &member_pk, &AppKind::Inkternity, &fingerprint(&env, 0x90),
        &ed25519_alg(&env), &near_exp, &1u64, &payload, &signature,
    );

    // Before expiry — Active.
    assert_eq!(client.get_app_ca(&app).unwrap().status, CertStatus::Active);

    // Advance past expiry.
    env.ledger().with_mut(|li| li.timestamp = 300);

    let view = client.get_app_ca(&app).unwrap();
    assert_eq!(view.status, CertStatus::Expired);
}

#[test]
fn is_trusted_matrix() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);
    env.ledger().with_mut(|li| li.timestamp = 100);

    let (sk, member_pk) = make_member(&env, 0xF2);
    let app = Address::generate(&env);
    let fp = fingerprint(&env, 0xA0);
    let wrong_fp = fingerprint(&env, 0xA1);

    // (1) absent → false
    assert!(!client.is_trusted(&app, &fp));

    // Register
    let args = make_register_args(
        &env, &sk, app.clone(), member_pk,
        AppKind::Inkternity, fp.clone(), FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );

    // (2) active + correct fp → true
    assert!(client.is_trusted(&app, &fp));
    // (3) active + wrong fp → false
    assert!(!client.is_trusted(&app, &wrong_fp));

    // (4) expired → false
    env.ledger().with_mut(|li| li.timestamp = FUTURE_EXP + 1);
    assert!(!client.is_trusted(&app, &fp));

    // Reset clock and revoke to test the revoked branch
    env.ledger().with_mut(|li| li.timestamp = 200);
    client.revoke_by_app(&app);
    // (5) revoked → false
    assert!(!client.is_trusted(&app, &fp));
}

#[test]
fn list_active_apps_excludes_revoked_includes_expired() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);
    env.ledger().with_mut(|li| li.timestamp = 100);

    let (sk, member_pk) = make_member(&env, 0xF3);

    let active_app = Address::generate(&env);
    let expired_app = Address::generate(&env);
    let revoked_app = Address::generate(&env);

    // active_app: future expiry
    let a1 = make_register_args(
        &env, &sk, active_app.clone(), member_pk.clone(),
        AppKind::Inkternity, fingerprint(&env, 0xB0), FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &a1.app, &a1.member_pk, &a1.kind, &a1.fp, &a1.alg,
        &a1.expires_at, &a1.nonce, &a1.payload, &a1.signature,
    );

    // expired_app: near-future expiry, we'll advance the clock past it
    let near_exp: u64 = 250;
    let a2 = make_register_args(
        &env, &sk, expired_app.clone(), member_pk.clone(),
        AppKind::Inkternity, fingerprint(&env, 0xB1), near_exp, 2,
    );
    client.register_app_ca(
        &a2.app, &a2.member_pk, &a2.kind, &a2.fp, &a2.alg,
        &a2.expires_at, &a2.nonce, &a2.payload, &a2.signature,
    );

    // revoked_app
    let a3 = make_register_args(
        &env, &sk, revoked_app.clone(), member_pk.clone(),
        AppKind::Inkternity, fingerprint(&env, 0xB2), FUTURE_EXP, 3,
    );
    client.register_app_ca(
        &a3.app, &a3.member_pk, &a3.kind, &a3.fp, &a3.alg,
        &a3.expires_at, &a3.nonce, &a3.payload, &a3.signature,
    );
    client.revoke_by_app(&revoked_app);

    // Advance clock past expired_app's expiry but before FUTURE_EXP.
    env.ledger().with_mut(|li| li.timestamp = 300);

    let actives = client.list_active_apps();
    // Returns stored-Active set: active_app + expired_app, NOT revoked_app.
    assert_eq!(actives.len(), 2);
    let mut found_active = false;
    let mut found_expired_stored_active = false;
    for a in actives.iter() {
        if a == active_app {
            found_active = true;
        }
        if a == expired_app {
            found_expired_stored_active = true;
        }
        assert_ne!(a, revoked_app);
    }
    assert!(found_active);
    assert!(found_expired_stored_active);
}

#[test]
fn apps_of_member_returns_full_history() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xF4);

    let app1 = Address::generate(&env);
    let app2 = Address::generate(&env);
    for (app, nonce) in [(&app1, 1u64), (&app2, 2u64)] {
        let args = make_register_args(
            &env, &sk, app.clone(), member_pk.clone(),
            AppKind::Inkternity, fingerprint(&env, 0xC0), FUTURE_EXP, nonce,
        );
        client.register_app_ca(
            &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
            &args.expires_at, &args.nonce, &args.payload, &args.signature,
        );
    }

    // Revoke one; it still shows up in apps_of_member.
    client.revoke_by_app(&app1);

    let list = client.apps_of_member(&member_pk);
    assert_eq!(list.len(), 2);
}

// ── Auth-shape sanity: explicit MockAuth on the app side ────────────────────

#[test]
fn register_with_explicit_app_mock_auth_succeeds() {
    // This test demonstrates that the app-side auth requirement is satisfied
    // by a per-invocation MockAuth scoped to the app's address (the realistic
    // shape — not the global mock_all_auths blanket).
    let env = Env::default();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xF5);
    let app = Address::generate(&env);
    let fp = fingerprint(&env, 0xD0);
    let args = make_register_args(
        &env, &sk, app.clone(), member_pk.clone(),
        AppKind::Inkternity, fp.clone(), FUTURE_EXP, 1,
    );

    client
        .mock_auths(&[MockAuth {
            address: &app,
            invoke: &MockAuthInvoke {
                contract: &client.address,
                fn_name: "register_app_ca",
                args: (
                    args.app.clone(),
                    args.member_pk.clone(),
                    args.kind.clone(),
                    args.fp.clone(),
                    args.alg.clone(),
                    args.expires_at,
                    args.nonce,
                    args.payload.clone(),
                    args.signature.clone(),
                )
                    .into_val(&env),
                sub_invokes: &[],
            },
        }])
        .register_app_ca(
            &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
            &args.expires_at, &args.nonce, &args.payload, &args.signature,
        );

    let rec: AppCaRecord = client.get_app_ca(&app).unwrap();
    assert_eq!(rec.status, CertStatus::Active);
}

// ── Encoder sanity: rotate event surfaces correct serial ────────────────────

#[test]
fn rotate_emits_event_with_bumped_serial() {
    let env = Env::default();
    env.mock_all_auths();
    let client = setup(&env);

    let (sk, member_pk) = make_member(&env, 0xF6);
    let app = Address::generate(&env);
    let fp_v1 = fingerprint(&env, 0xE0);
    let fp_v2 = fingerprint(&env, 0xE1);

    let args = make_register_args(
        &env, &sk, app.clone(), member_pk,
        AppKind::Inkternity, fp_v1, FUTURE_EXP, 1,
    );
    client.register_app_ca(
        &args.app, &args.member_pk, &args.kind, &args.fp, &args.alg,
        &args.expires_at, &args.nonce, &args.payload, &args.signature,
    );

    let new_exp = FUTURE_EXP + 1;
    let canon = canonical_rotate(&app, &fp_v2, new_exp, 2);
    let payload = bytes_of(&env, &canon);
    let signature = sign(&env, &sk, &canon);
    client.rotate_app_ca(&app, &fp_v2, &new_exp, &2u64, &payload, &signature);

    let events = env.events().all();
    let last = events.last().unwrap();
    let evt: RotateEvent = last.2.into_val(&env);
    assert_eq!(evt.serial, 2);
    assert_eq!(evt.new_fingerprint, fp_v2);
    assert_eq!(evt.new_expires_at, new_exp);
}
