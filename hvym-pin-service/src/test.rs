#![cfg(test)]

use crate::{PinServiceContract, PinServiceContractClient};
use crate::types::{EPOCH_LENGTH, NUM_SLOTS};
use soroban_sdk::{
    token, Address, Env, String, FromVal, Symbol, symbol_short,
    testutils::{Address as _, Events, Ledger},
    TryFromVal,
};

// =============================================================================
// Test Helpers
// =============================================================================

fn create_token_contract<'a>(
    e: &Env,
    admin: &Address,
) -> (token::Client<'a>, Address) {
    let token_address = e.register_stellar_asset_contract(admin.clone());
    let token = token::Client::new(e, &token_address);
    let admin_client = token::StellarAssetClient::new(e, &token_address);
    admin_client.mint(admin, &1_000_000_000_000_000_000);
    (token, token_address.clone().into())
}

fn mint_tokens(token_client: &token::Client, _from: &Address, to: &Address, amount: &i128) {
    let admin_client = token::StellarAssetClient::new(&token_client.env, &token_client.address);
    admin_client.mint(to, amount);
}

/// Standard test config params
const PIN_FEE: u32 = 100;
const JOIN_FEE: u32 = 50;
const MIN_PIN_QTY: u32 = 3;
const MIN_OFFER_PRICE: u32 = 10;
const PINNER_STAKE: u32 = 10_000;
const MAX_CYCLES: u32 = 60;
const FLAG_THRESHOLD: u32 = 3;

fn setup_test_env<'a>() -> (
    Env,
    PinServiceContractClient<'a>,
    Address,       // admin
    token::Client<'a>,
    Address,       // pay_token_addr
) {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let client = PinServiceContractClient::new(
        &env,
        &env.register(
            PinServiceContract,
            (
                &admin,
                PIN_FEE,
                JOIN_FEE,
                MIN_PIN_QTY,
                MIN_OFFER_PRICE,
                PINNER_STAKE,
                &pay_token_addr,
                MAX_CYCLES,
                FLAG_THRESHOLD,
            ),
        ),
    );

    (env, client, admin, pay_token_client, pay_token_addr)
}

fn register_pinner<'a>(
    env: &Env,
    client: &PinServiceContractClient<'a>,
    pay_token_client: &token::Client,
    admin: &Address,
) -> Address {
    let pinner = Address::generate(env);
    mint_tokens(pay_token_client, admin, &pinner, &100_000);
    let node_id = String::from_val(env, &"12D3KooWtest");
    let multiaddr = String::from_val(env, &"/ip4/127.0.0.1/tcp/4001");
    client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);
    pinner
}

fn create_test_pin<'a>(
    env: &Env,
    client: &PinServiceContractClient<'a>,
    pay_token_client: &token::Client,
    admin: &Address,
    cid_str: &str,
) -> (Address, u32) {
    let publisher = Address::generate(env);
    mint_tokens(pay_token_client, admin, &publisher, &100_000);
    let cid = String::from_val(env, &cid_str);
    let gateway = String::from_val(env, &"https://gateway.test");
    let slot_id = client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);
    (publisher, slot_id)
}

// =============================================================================
// Constructor Tests
// =============================================================================

#[test]
fn test_constructor_initializes_config() {
    let (_, client, _, _, _) = setup_test_env();
    assert_eq!(client.pin_fee(), PIN_FEE);
    assert_eq!(client.join_fee(), JOIN_FEE);
    assert_eq!(client.min_pin_qty(), MIN_PIN_QTY);
    assert_eq!(client.min_offer_price(), MIN_OFFER_PRICE);
    assert_eq!(client.max_cycles(), MAX_CYCLES);
    assert_eq!(client.flag_threshold(), FLAG_THRESHOLD);
    assert_eq!(client.pinner_stake_amount(), PINNER_STAKE);
}

#[test]
fn test_constructor_sets_admin() {
    let (_, client, admin, _, _) = setup_test_env();
    assert_eq!(client.is_admin(&admin), true);
}

#[test]
fn test_constructor_creates_empty_slots() {
    let (_, client, _, _, _) = setup_test_env();
    assert_eq!(client.has_available_slots(), true);
    let all_slots = client.get_all_slots();
    assert_eq!(all_slots.len(), 0);
}

#[test]
#[should_panic(expected = "max_cycles must be > 0")]
fn test_constructor_rejects_zero_max_cycles() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);
    PinServiceContractClient::new(
        &env,
        &env.register(
            PinServiceContract,
            (&admin, PIN_FEE, JOIN_FEE, MIN_PIN_QTY, MIN_OFFER_PRICE, PINNER_STAKE, &pay_token_addr, 0_u32, FLAG_THRESHOLD),
        ),
    );
}

#[test]
#[should_panic(expected = "min_pin_qty must be > 0")]
fn test_constructor_rejects_zero_min_pin_qty() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);
    PinServiceContractClient::new(
        &env,
        &env.register(
            PinServiceContract,
            (&admin, PIN_FEE, JOIN_FEE, 0_u32, MIN_OFFER_PRICE, PINNER_STAKE, &pay_token_addr, MAX_CYCLES, FLAG_THRESHOLD),
        ),
    );
}

// =============================================================================
// Pinner Registration Tests
// =============================================================================

#[test]
fn test_join_as_pinner_success() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &pinner, &100_000);
    let node_id = String::from_val(&env, &"12D3KooWtest");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");

    let result = client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);
    assert_eq!(result.address, pinner);
    assert_eq!(result.active, true);
    assert_eq!(result.staked, PINNER_STAKE);
    assert_eq!(client.is_pinner(&pinner), true);
    assert_eq!(client.get_pinner_count(), 1);
}

#[test]
fn test_join_as_pinner_transfers_fee() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = Address::generate(&env);
    let initial = 100_000_i128;
    mint_tokens(&pay_token_client, &admin, &pinner, &initial);
    let node_id = String::from_val(&env, &"12D3KooWtest");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");

    client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);

    let expected = initial - (JOIN_FEE as i128 + PINNER_STAKE as i128);
    assert_eq!(pay_token_client.balance(&pinner), expected);
}

#[test]
fn test_join_as_pinner_emits_event() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &pinner, &100_000);
    let node_id = String::from_val(&env, &"12D3KooWtest");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");

    client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);

    let events = env.events().all();
    let last = events.last().unwrap();
    let (_, topics, _) = last;
    let sym: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0)).unwrap();
    assert_eq!(sym, symbol_short!("JOIN"));
}

#[test]
#[should_panic(expected = "already pinner")]
fn test_join_as_pinner_rejects_duplicate() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &pinner, &200_000);
    let node_id = String::from_val(&env, &"12D3KooWtest");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");

    client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);
    client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);
}

#[test]
fn test_update_pinner_updates_fields() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);

    let new_node = String::from_val(&env, &"12D3KooWnew");
    let updated = client.update_pinner(
        &pinner,
        &Some(new_node.clone()),
        &None::<String>,
        &Some(20_u32),
        &None::<bool>,
    );
    assert_eq!(updated.node_id, new_node);
    assert_eq!(updated.min_price, 20);
}

#[test]
fn test_leave_as_pinner_removes_registration() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);

    assert_eq!(client.is_pinner(&pinner), true);
    let refund = client.leave_as_pinner(&pinner);
    assert_eq!(refund, PINNER_STAKE);
    assert_eq!(client.is_pinner(&pinner), false);
    assert_eq!(client.get_pinner_count(), 0);
}

#[test]
fn test_admin_remove_pinner() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);

    assert_eq!(client.is_pinner(&pinner), true);
    client.remove_pinner(&admin, &pinner);
    assert_eq!(client.is_pinner(&pinner), false);
}

#[test]
#[should_panic(expected = "unauthorized")]
fn test_non_admin_cannot_remove_pinner() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    let non_admin = Address::generate(&env);
    client.remove_pinner(&non_admin, &pinner);
}

// =============================================================================
// Pinner Staking Tests
// =============================================================================

#[test]
fn test_join_as_pinner_collects_stake() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &pinner, &100_000);
    let node_id = String::from_val(&env, &"12D3KooWtest");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");

    let result = client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);
    assert_eq!(result.staked, PINNER_STAKE);

    // Balance should be initial - (join_fee + stake)
    let expected = 100_000 - (JOIN_FEE as i128 + PINNER_STAKE as i128);
    assert_eq!(pay_token_client.balance(&pinner), expected);
}

#[test]
fn test_leave_as_pinner_returns_stake() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = Address::generate(&env);
    let initial = 100_000_i128;
    mint_tokens(&pay_token_client, &admin, &pinner, &initial);
    let node_id = String::from_val(&env, &"12D3KooWtest");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");

    client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);
    let after_join = pay_token_client.balance(&pinner);

    let refund = client.leave_as_pinner(&pinner);
    assert_eq!(refund, PINNER_STAKE);
    assert_eq!(pay_token_client.balance(&pinner), after_join + PINNER_STAKE as i128);
}

#[test]
fn test_leave_as_pinner_no_stake_if_deactivated() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    // Create the pinner to be flagged
    let target = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &target, &100_000);
    let node_id = String::from_val(&env, &"12D3KooWtarget");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");
    client.join_as_pinner(&target, &node_id, &multiaddr, &5);

    // Create flaggers (who are also pinners)
    for i in 0..FLAG_THRESHOLD {
        let flagger = Address::generate(&env);
        mint_tokens(&pay_token_client, &admin, &flagger, &100_000);
        let fnode = String::from_val(&env, &"12D3KooWflagger");
        let faddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4002");
        client.join_as_pinner(&flagger, &fnode, &faddr, &5);
        client.flag_pinner(&flagger, &target);
    }

    // Target should be deactivated now
    let pinner_data = client.get_pinner(&target).unwrap();
    assert_eq!(pinner_data.active, false);
    assert_eq!(pinner_data.staked, 0);

    // Leave should return 0
    let balance_before = pay_token_client.balance(&target);
    let refund = client.leave_as_pinner(&target);
    assert_eq!(refund, 0);
    // Balance should not change
    assert_eq!(pay_token_client.balance(&target), balance_before);
}

#[test]
fn test_flag_threshold_forfeits_stake() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    let target = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &target, &100_000);
    let node_id = String::from_val(&env, &"12D3KooWtarget");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");
    client.join_as_pinner(&target, &node_id, &multiaddr, &5);

    for _ in 0..FLAG_THRESHOLD {
        let flagger = Address::generate(&env);
        mint_tokens(&pay_token_client, &admin, &flagger, &100_000);
        let fnode = String::from_val(&env, &"12D3KooWflag");
        let faddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4002");
        client.join_as_pinner(&flagger, &fnode, &faddr, &5);
        client.flag_pinner(&flagger, &target);
    }

    let pinner_data = client.get_pinner(&target).unwrap();
    assert_eq!(pinner_data.active, false);
    assert_eq!(pinner_data.staked, 0);
}

#[test]
fn test_flag_threshold_distributes_bounty_equally() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    let target = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &target, &100_000);
    let node_id = String::from_val(&env, &"12D3KooWtarget");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");
    client.join_as_pinner(&target, &node_id, &multiaddr, &5);

    let mut flaggers = soroban_sdk::Vec::new(&env);
    let mut balances_before = soroban_sdk::Vec::new(&env);

    for _ in 0..FLAG_THRESHOLD {
        let flagger = Address::generate(&env);
        mint_tokens(&pay_token_client, &admin, &flagger, &100_000);
        let fnode = String::from_val(&env, &"12D3KooWflag");
        let faddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4002");
        client.join_as_pinner(&flagger, &fnode, &faddr, &5);

        let bal = pay_token_client.balance(&flagger);
        balances_before.push_back(bal);
        flaggers.push_back(flagger);
    }

    // Flag from each
    for i in 0..FLAG_THRESHOLD {
        let flagger = flaggers.get(i).unwrap();
        client.flag_pinner(&flagger, &target);
    }

    // Each flagger should have received stake / num_flaggers
    let share = PINNER_STAKE as i128 / FLAG_THRESHOLD as i128;
    for i in 0..FLAG_THRESHOLD {
        let flagger = flaggers.get(i).unwrap();
        let before = balances_before.get(i).unwrap();
        let after = pay_token_client.balance(&flagger);
        assert_eq!(after - before, share);
    }
}

#[test]
fn test_flag_bounty_remainder_goes_to_fees() {
    // Use a stake that doesn't divide evenly by threshold
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    // pinner_stake = 10, threshold = 3 -> 10/3 = 3 each, remainder = 1
    let client = PinServiceContractClient::new(
        &env,
        &env.register(
            PinServiceContract,
            (&admin, PIN_FEE, JOIN_FEE, MIN_PIN_QTY, MIN_OFFER_PRICE, 10_u32, &pay_token_addr, MAX_CYCLES, 3_u32),
        ),
    );

    let target = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &target, &100_000);
    let node_id = String::from_val(&env, &"12D3KooWtarget");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");
    client.join_as_pinner(&target, &node_id, &multiaddr, &5);

    let fees_before = client.fees_collected();

    for _ in 0..3 {
        let flagger = Address::generate(&env);
        mint_tokens(&pay_token_client, &admin, &flagger, &100_000);
        let fnode = String::from_val(&env, &"12D3KooWflag");
        let faddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4002");
        client.join_as_pinner(&flagger, &fnode, &faddr, &5);
        client.flag_pinner(&flagger, &target);
    }

    let fees_after = client.fees_collected();
    // Remainder of 10 % 3 = 1 should go to fees
    // Plus 3 * join_fee from flaggers + 1 * join_fee from target = 4 * 50 = 200
    // Total fees_before was join_fee for the target = 50
    // After: 50 + 3*50 + 1 = 201
    assert_eq!(fees_after - fees_before, 3 * JOIN_FEE as i128 + 1);
}

#[test]
fn test_admin_remove_pinner_returns_stake() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &pinner, &100_000);
    let node_id = String::from_val(&env, &"12D3KooWtest");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");
    client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);

    let balance_before = pay_token_client.balance(&pinner);
    client.remove_pinner(&admin, &pinner);
    let balance_after = pay_token_client.balance(&pinner);

    assert_eq!(balance_after - balance_before, PINNER_STAKE as i128);
}

#[test]
fn test_update_pinner_stake_applies_to_future_only() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    // Pinner 1 joins with original stake
    let pinner1 = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &pinner1, &200_000);
    let node_id = String::from_val(&env, &"12D3KooW1");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");
    client.join_as_pinner(&pinner1, &node_id, &multiaddr, &5);
    assert_eq!(client.get_pinner(&pinner1).unwrap().staked, PINNER_STAKE);

    // Update stake
    client.update_pinner_stake(&admin, &20_000);

    // Pinner 2 joins with new stake
    let pinner2 = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &pinner2, &200_000);
    let node_id2 = String::from_val(&env, &"12D3KooW2");
    let multiaddr2 = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4002");
    client.join_as_pinner(&pinner2, &node_id2, &multiaddr2, &5);
    assert_eq!(client.get_pinner(&pinner2).unwrap().staked, 20_000);

    // Pinner 1 still has original stake
    assert_eq!(client.get_pinner(&pinner1).unwrap().staked, PINNER_STAKE);
}

// =============================================================================
// Pin Request (Slot) Tests
// =============================================================================

#[test]
fn test_create_pin_success() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmTestCID1");
    let slot = client.get_slot(&slot_id);
    assert_eq!(slot.offer_price, MIN_OFFER_PRICE);
    assert_eq!(slot.pin_qty, MIN_PIN_QTY);
    assert_eq!(slot.pins_remaining, MIN_PIN_QTY);
    assert_eq!(slot.escrow_balance, MIN_OFFER_PRICE * MIN_PIN_QTY);
}

#[test]
fn test_create_pin_transfers_correct_amount() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    let initial = 100_000_i128;
    mint_tokens(&pay_token_client, &admin, &publisher, &initial);

    let cid = String::from_val(&env, &"QmTestCID");
    let gateway = String::from_val(&env, &"https://gateway.test");
    client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);

    let expected_deducted = (MIN_OFFER_PRICE * MIN_PIN_QTY + PIN_FEE) as i128;
    assert_eq!(pay_token_client.balance(&publisher), initial - expected_deducted);
}

#[test]
fn test_create_pin_emits_pin_event() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    create_test_pin(&env, &client, &pay_token_client, &admin, "QmTestCID");

    let events = env.events().all();
    let last = events.last().unwrap();
    let (_, topics, _) = last;
    let sym: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0)).unwrap();
    assert_eq!(sym, symbol_short!("PIN"));
}

#[test]
fn test_create_pin_assigns_first_available_slot() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot0) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmCID0");
    let (_, slot1) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmCID1");
    assert_eq!(slot0, 0);
    assert_eq!(slot1, 1);
}

#[test]
fn test_create_pin_reuses_expired_slot_with_refund() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    let (publisher1, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmOld");
    let balance_after_create = pay_token_client.balance(&publisher1);

    // Advance past expiration
    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * MAX_CYCLES + 1;
    });

    // New publisher creates pin - should lazily cleanup the old slot
    let (_, new_slot) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmNew");
    assert_eq!(new_slot, slot_id); // Should reuse same slot

    // Old publisher should have been refunded escrow
    let escrow = (MIN_OFFER_PRICE * MIN_PIN_QTY) as i128;
    assert_eq!(pay_token_client.balance(&publisher1), balance_after_create + escrow);
}

#[test]
#[should_panic(expected = "no slots available")]
fn test_create_pin_rejects_when_all_slots_full() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    for i in 0..NUM_SLOTS {
        let cid_str = &alloc::format!("QmCID{}", i);
        create_test_pin(&env, &client, &pay_token_client, &admin, cid_str);
    }

    // 11th should fail
    create_test_pin(&env, &client, &pay_token_client, &admin, "QmCIDOverflow");
}

#[test]
#[should_panic(expected = "insufficient pin quantity")]
fn test_create_pin_rejects_low_qty() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &100_000);
    let cid = String::from_val(&env, &"QmTest");
    let gateway = String::from_val(&env, &"https://gateway.test");
    client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &1);
}

#[test]
#[should_panic(expected = "pin qty exceeds max")]
fn test_create_pin_rejects_qty_over_10() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &1_000_000);
    let cid = String::from_val(&env, &"QmTest");
    let gateway = String::from_val(&env, &"https://gateway.test");
    client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &11);
}

#[test]
#[should_panic(expected = "offer price too low")]
fn test_create_pin_rejects_low_offer_price() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &100_000);
    let cid = String::from_val(&env, &"QmTest");
    let gateway = String::from_val(&env, &"https://gateway.test");
    client.create_pin(&publisher, &cid, &gateway, &1, &MIN_PIN_QTY);
}

#[test]
#[should_panic(expected = "offer overflow")]
fn test_create_pin_rejects_overflow() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &10_000_000_000_i128);

    // Update min_offer_price to allow large values
    client.update_min_offer_price(&admin, &1);

    let cid = String::from_val(&env, &"QmTest");
    let gateway = String::from_val(&env, &"https://gateway.test");
    // u32::MAX * 10 will overflow
    client.create_pin(&publisher, &cid, &gateway, &u32::MAX, &10);
}

#[test]
#[should_panic(expected = "duplicate cid")]
fn test_create_pin_rejects_duplicate_cid() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    create_test_pin(&env, &client, &pay_token_client, &admin, "QmSameCID");
    create_test_pin(&env, &client, &pay_token_client, &admin, "QmSameCID");
}

#[test]
fn test_same_publisher_multiple_slots_different_cids() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &1_000_000);

    let cid1 = String::from_val(&env, &"QmCID1");
    let cid2 = String::from_val(&env, &"QmCID2");
    let gateway = String::from_val(&env, &"https://gateway.test");

    let s1 = client.create_pin(&publisher, &cid1, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);
    let s2 = client.create_pin(&publisher, &cid2, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);

    assert_ne!(s1, s2);
    assert_eq!(client.get_all_slots().len(), 2);
}

// =============================================================================
// Pin Collection Tests
// =============================================================================

#[test]
fn test_collect_pin_success() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmCollect");

    let amount = client.collect_pin(&pinner, &slot_id);
    assert_eq!(amount, MIN_OFFER_PRICE);
}

#[test]
fn test_collect_pin_transfers_offer_price_to_pinner() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmCollect");

    let before = pay_token_client.balance(&pinner);
    client.collect_pin(&pinner, &slot_id);
    let after = pay_token_client.balance(&pinner);
    assert_eq!(after - before, MIN_OFFER_PRICE as i128);
}

#[test]
fn test_collect_pin_decrements_pins_remaining() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmCollect");

    client.collect_pin(&pinner, &slot_id);
    let slot = client.get_slot(&slot_id);
    assert_eq!(slot.pins_remaining, MIN_PIN_QTY - 1);
}

#[test]
fn test_collect_pin_adds_pinner_to_claims() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmCollect");

    client.collect_pin(&pinner, &slot_id);
    let slot = client.get_slot(&slot_id);
    assert!(slot.claims.contains(&pinner));
}

#[test]
fn test_collect_pin_emits_pinned_event() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmCollect");

    client.collect_pin(&pinner, &slot_id);

    let events = env.events().all();
    let last = events.last().unwrap();
    let (_, topics, _) = last;
    let sym: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0)).unwrap();
    assert_eq!(sym, symbol_short!("PINNED"));
}

#[test]
fn test_collect_pin_frees_slot_when_filled() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmFill");

    // Collect all pins
    for _ in 0..MIN_PIN_QTY {
        let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
        client.collect_pin(&pinner, &slot_id);
    }

    // Slot should be freed (no longer in get_all_slots)
    let all = client.get_all_slots();
    assert_eq!(all.len(), 0);
}

#[test]
fn test_multiple_pinners_collect_same_slot() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmMulti");

    let pinner1 = register_pinner(&env, &client, &pay_token_client, &admin);
    let pinner2 = register_pinner(&env, &client, &pay_token_client, &admin);

    client.collect_pin(&pinner1, &slot_id);
    client.collect_pin(&pinner2, &slot_id);

    let slot = client.get_slot(&slot_id);
    assert_eq!(slot.pins_remaining, MIN_PIN_QTY - 2);
    assert!(slot.claims.contains(&pinner1));
    assert!(slot.claims.contains(&pinner2));
}

#[test]
#[should_panic(expected = "not pinner")]
fn test_collect_pin_requires_registration() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmTest");
    let non_pinner = Address::generate(&env);
    client.collect_pin(&non_pinner, &slot_id);
}

#[test]
#[should_panic(expected = "already claimed")]
fn test_collect_pin_prevents_double_claim() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmDouble");

    client.collect_pin(&pinner, &slot_id);
    client.collect_pin(&pinner, &slot_id);
}

#[test]
#[should_panic(expected = "slot not active")]
fn test_collect_pin_rejects_inactive_slot() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    client.collect_pin(&pinner, &99);
}

#[test]
#[should_panic(expected = "slot expired")]
fn test_collect_pin_rejects_expired_slot() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmExpired");

    // Advance past expiration
    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * MAX_CYCLES + 1;
    });

    client.collect_pin(&pinner, &slot_id);
}

// =============================================================================
// Cancellation Tests
// =============================================================================

#[test]
fn test_cancel_pin_refunds_remaining_escrow() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &100_000);
    let cid = String::from_val(&env, &"QmCancel");
    let gateway = String::from_val(&env, &"https://gateway.test");

    let slot_id = client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);
    let balance_after_create = pay_token_client.balance(&publisher);

    let refund = client.cancel_pin(&publisher, &slot_id);
    let expected_refund = MIN_OFFER_PRICE * MIN_PIN_QTY;
    assert_eq!(refund, expected_refund);
    assert_eq!(
        pay_token_client.balance(&publisher),
        balance_after_create + expected_refund as i128
    );
}

#[test]
fn test_cancel_pin_does_not_refund_pin_fee() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    let initial = 100_000_i128;
    mint_tokens(&pay_token_client, &admin, &publisher, &initial);
    let cid = String::from_val(&env, &"QmCancel");
    let gateway = String::from_val(&env, &"https://gateway.test");

    let slot_id = client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);
    client.cancel_pin(&publisher, &slot_id);

    // Should have lost pin_fee
    assert_eq!(
        pay_token_client.balance(&publisher),
        initial - PIN_FEE as i128
    );
}

#[test]
fn test_cancel_pin_after_partial_fill() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &100_000);
    let cid = String::from_val(&env, &"QmPartial");
    let gateway = String::from_val(&env, &"https://gateway.test");

    let slot_id = client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);

    // 1 pinner collects
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    client.collect_pin(&pinner, &slot_id);

    let balance_before_cancel = pay_token_client.balance(&publisher);
    let refund = client.cancel_pin(&publisher, &slot_id);

    // Refund should be (pin_qty - 1) * offer_price
    let expected = (MIN_PIN_QTY - 1) * MIN_OFFER_PRICE;
    assert_eq!(refund, expected);
    assert_eq!(
        pay_token_client.balance(&publisher),
        balance_before_cancel + expected as i128
    );
}

#[test]
fn test_cancel_pin_emits_unpin() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &100_000);
    let cid = String::from_val(&env, &"QmCancel");
    let gateway = String::from_val(&env, &"https://gateway.test");

    let slot_id = client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);
    client.cancel_pin(&publisher, &slot_id);

    let events = env.events().all();
    let last = events.last().unwrap();
    let (_, topics, _) = last;
    let sym: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0)).unwrap();
    assert_eq!(sym, symbol_short!("UNPIN"));
}

#[test]
fn test_cancel_pin_frees_slot() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &100_000);
    let cid = String::from_val(&env, &"QmCancel");
    let gateway = String::from_val(&env, &"https://gateway.test");

    let slot_id = client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);
    assert_eq!(client.get_all_slots().len(), 1);

    client.cancel_pin(&publisher, &slot_id);
    assert_eq!(client.get_all_slots().len(), 0);
    assert_eq!(client.has_available_slots(), true);
}

#[test]
#[should_panic(expected = "not slot publisher")]
fn test_cancel_pin_only_publisher() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmCancel");
    let other = Address::generate(&env);
    client.cancel_pin(&other, &slot_id);
}

// =============================================================================
// Expiration Tests
// =============================================================================

#[test]
fn test_slot_expires_after_max_cycles() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmExpire");

    assert_eq!(client.is_slot_expired(&slot_id), false);

    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * MAX_CYCLES + 1;
    });

    assert_eq!(client.is_slot_expired(&slot_id), true);
}

#[test]
fn test_clear_expired_slot_refunds_publisher() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (publisher, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmExpire");
    let balance_after = pay_token_client.balance(&publisher);

    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * MAX_CYCLES + 1;
    });

    client.clear_expired_slot(&slot_id);
    let escrow = (MIN_OFFER_PRICE * MIN_PIN_QTY) as i128;
    assert_eq!(pay_token_client.balance(&publisher), balance_after + escrow);
}

#[test]
fn test_clear_expired_slot_emits_unpin() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmExpire");

    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * MAX_CYCLES + 1;
    });

    client.clear_expired_slot(&slot_id);

    let events = env.events().all();
    let last = events.last().unwrap();
    let (_, topics, _) = last;
    let sym: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0)).unwrap();
    assert_eq!(sym, symbol_short!("UNPIN"));
}

#[test]
fn test_clear_expired_slot_frees_slot() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmExpire");

    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * MAX_CYCLES + 1;
    });

    client.clear_expired_slot(&slot_id);
    assert_eq!(client.get_all_slots().len(), 0);
}

#[test]
#[should_panic(expected = "slot not expired")]
fn test_clear_expired_slot_rejects_active() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmActive");
    client.clear_expired_slot(&slot_id);
}

#[test]
fn test_epoch_computation() {
    let (env, client, _, _, _) = setup_test_env();

    let epoch0 = client.current_epoch();
    assert_eq!(epoch0, 0);

    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH;
    });
    assert_eq!(client.current_epoch(), 1);

    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * 9;
    });
    assert_eq!(client.current_epoch(), 10);
}

#[test]
fn test_lazy_cleanup_on_create_pin() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    // Fill all slots
    for i in 0..NUM_SLOTS {
        let cid_str = &alloc::format!("QmFill{}", i);
        create_test_pin(&env, &client, &pay_token_client, &admin, cid_str);
    }

    assert_eq!(client.has_available_slots(), false);

    // Advance past expiration
    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * MAX_CYCLES + 1;
    });

    // Now all slots should be available (expired)
    assert_eq!(client.has_available_slots(), true);

    // Create a new pin - should lazily cleanup an expired slot
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmNewAfterExpire");
    assert_eq!(slot_id, 0); // First slot should be reused
}

// =============================================================================
// Admin Tests
// =============================================================================

#[test]
fn test_add_admin() {
    let (env, client, admin, _, _) = setup_test_env();
    let new_admin = Address::generate(&env);

    assert_eq!(client.is_admin(&new_admin), false);
    client.add_admin(&admin, &new_admin);
    assert_eq!(client.is_admin(&new_admin), true);
    assert_eq!(client.get_admin_list().len(), 2);
}

#[test]
fn test_remove_admin() {
    let (env, client, admin, _, _) = setup_test_env();
    let new_admin = Address::generate(&env);
    client.add_admin(&admin, &new_admin);
    assert_eq!(client.is_admin(&new_admin), true);

    client.remove_admin(&admin, &new_admin);
    assert_eq!(client.is_admin(&new_admin), false);
    assert_eq!(client.get_admin_list().len(), 1);
}

#[test]
#[should_panic(expected = "cannot remove initial admin")]
fn test_cannot_remove_initial_admin() {
    let (_, client, admin, _, _) = setup_test_env();
    client.remove_admin(&admin, &admin);
}

#[test]
fn test_withdraw_fees() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let recipient = Address::generate(&env);

    // Create a pin to generate fees
    create_test_pin(&env, &client, &pay_token_client, &admin, "QmFees");
    assert_eq!(client.fees_collected(), PIN_FEE as i128);

    let amount = client.withdraw_fees(&admin, &recipient);
    assert_eq!(amount, PIN_FEE as i128);
    assert_eq!(pay_token_client.balance(&recipient), PIN_FEE as i128);
    assert_eq!(client.fees_collected(), 0);
}

#[test]
fn test_update_pin_fee() {
    let (_, client, admin, _, _) = setup_test_env();
    client.update_pin_fee(&admin, &200);
    assert_eq!(client.pin_fee(), 200);
}

#[test]
fn test_update_join_fee() {
    let (_, client, admin, _, _) = setup_test_env();
    client.update_join_fee(&admin, &100);
    assert_eq!(client.join_fee(), 100);
}

#[test]
fn test_update_min_pin_qty() {
    let (_, client, admin, _, _) = setup_test_env();
    client.update_min_pin_qty(&admin, &5);
    assert_eq!(client.min_pin_qty(), 5);
}

#[test]
fn test_update_min_offer_price() {
    let (_, client, admin, _, _) = setup_test_env();
    client.update_min_offer_price(&admin, &20);
    assert_eq!(client.min_offer_price(), 20);
}

#[test]
fn test_update_max_cycles() {
    let (_, client, admin, _, _) = setup_test_env();
    client.update_max_cycles(&admin, &120);
    assert_eq!(client.max_cycles(), 120);
}

#[test]
fn test_force_clear_slot_refunds_publisher() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (publisher, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmForce");
    let balance_after = pay_token_client.balance(&publisher);

    let refund = client.force_clear_slot(&admin, &slot_id);
    let expected_refund = MIN_OFFER_PRICE * MIN_PIN_QTY;
    assert_eq!(refund, expected_refund);
    assert_eq!(pay_token_client.balance(&publisher), balance_after + expected_refund as i128);
}

#[test]
fn test_force_clear_slot_frees_active_slot() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmForce");
    assert_eq!(client.get_all_slots().len(), 1);

    client.force_clear_slot(&admin, &slot_id);
    assert_eq!(client.get_all_slots().len(), 0);
}

#[test]
#[should_panic(expected = "unauthorized")]
fn test_non_admin_cannot_force_clear_slot() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmForce");
    let non_admin = Address::generate(&env);
    client.force_clear_slot(&non_admin, &slot_id);
}

#[test]
#[should_panic(expected = "unauthorized")]
fn test_non_admin_cannot_update_config() {
    let (env, client, _, _, _) = setup_test_env();
    let non_admin = Address::generate(&env);
    client.update_pin_fee(&non_admin, &999);
}

// =============================================================================
// CID Hunter Flag Tests
// =============================================================================

#[test]
fn test_flag_pinner_increments_count() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let target = register_pinner(&env, &client, &pay_token_client, &admin);
    let flagger = register_pinner(&env, &client, &pay_token_client, &admin);

    let flags = client.flag_pinner(&flagger, &target);
    assert_eq!(flags, 1);
    assert_eq!(client.get_pinner(&target).unwrap().flags, 1);
}

#[test]
fn test_flag_pinner_auto_deactivates_at_threshold() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let target = register_pinner(&env, &client, &pay_token_client, &admin);

    for _ in 0..FLAG_THRESHOLD {
        let flagger = register_pinner(&env, &client, &pay_token_client, &admin);
        client.flag_pinner(&flagger, &target);
    }

    let pinner_data = client.get_pinner(&target).unwrap();
    assert_eq!(pinner_data.active, false);
}

#[test]
#[should_panic(expected = "pinner inactive")]
fn test_deactivated_pinner_cannot_collect() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let target = register_pinner(&env, &client, &pay_token_client, &admin);

    // Flag to threshold
    for _ in 0..FLAG_THRESHOLD {
        let flagger = register_pinner(&env, &client, &pay_token_client, &admin);
        client.flag_pinner(&flagger, &target);
    }

    // Create pin and try to collect
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmDeactivated");
    client.collect_pin(&target, &slot_id);
}

#[test]
#[should_panic(expected = "already flagged")]
fn test_flag_pinner_one_flag_per_publisher_per_pinner() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let target = register_pinner(&env, &client, &pay_token_client, &admin);
    let flagger = register_pinner(&env, &client, &pay_token_client, &admin);

    client.flag_pinner(&flagger, &target);
    client.flag_pinner(&flagger, &target);
}

#[test]
fn test_flag_persists_after_slot_reuse() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmFlag");

    // Pinner collects all pins to fill slot
    // We need more pinners since each can only claim once
    for i in 1..MIN_PIN_QTY {
        let extra = register_pinner(&env, &client, &pay_token_client, &admin);
        client.collect_pin(&extra, &slot_id);
    }
    client.collect_pin(&pinner, &slot_id);

    // Slot should now be freed
    assert_eq!(client.get_all_slots().len(), 0);

    // Can still flag the pinner
    let flagger = register_pinner(&env, &client, &pay_token_client, &admin);
    let flags = client.flag_pinner(&flagger, &pinner);
    assert_eq!(flags, 1);
}

#[test]
fn test_flag_threshold_update() {
    let (_, client, admin, _, _) = setup_test_env();
    client.update_flag_threshold(&admin, &10);
    assert_eq!(client.flag_threshold(), 10);
}

// =============================================================================
// Integration Tests
// =============================================================================

#[test]
fn test_full_pin_lifecycle() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    // Register pinners
    let mut pinners = soroban_sdk::Vec::new(&env);
    for _ in 0..MIN_PIN_QTY {
        let p = register_pinner(&env, &client, &pay_token_client, &admin);
        pinners.push_back(p);
    }

    // Publisher creates pin
    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &1_000_000);
    let cid = String::from_val(&env, &"QmLifecycle");
    let gateway = String::from_val(&env, &"https://gateway.test");
    let slot_id = client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);

    // All pinners collect
    for i in 0..MIN_PIN_QTY {
        let p = pinners.get(i).unwrap();
        client.collect_pin(&p, &slot_id);
    }

    // Slot should be freed
    assert_eq!(client.get_all_slots().len(), 0);
    assert_eq!(client.has_available_slots(), true);
}

#[test]
fn test_multiple_publishers_multiple_pinners() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    let pinner1 = register_pinner(&env, &client, &pay_token_client, &admin);
    let pinner2 = register_pinner(&env, &client, &pay_token_client, &admin);

    let (_, s1) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmPub1");
    let (_, s2) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmPub2");

    client.collect_pin(&pinner1, &s1);
    client.collect_pin(&pinner2, &s1);
    client.collect_pin(&pinner1, &s2);
    client.collect_pin(&pinner2, &s2);

    let all = client.get_all_slots();
    // Each slot has MIN_PIN_QTY = 3, 2 collected from each, so 1 remaining each
    assert_eq!(all.len(), 2);
    assert_eq!(all.get(0).unwrap().pins_remaining, MIN_PIN_QTY - 2);
}

#[test]
fn test_slot_reuse_after_fill() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmFill");

    // Fill completely
    for _ in 0..MIN_PIN_QTY {
        let p = register_pinner(&env, &client, &pay_token_client, &admin);
        client.collect_pin(&p, &slot_id);
    }
    assert_eq!(client.get_all_slots().len(), 0);

    // Reuse
    let (_, new_slot) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmReuse");
    assert_eq!(new_slot, 0); // Same slot index
}

#[test]
fn test_slot_reuse_after_expiration() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (publisher, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmOldExp");

    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * MAX_CYCLES + 1;
    });

    let balance_before = pay_token_client.balance(&publisher);
    let (_, new_slot) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmNewReuse");
    assert_eq!(new_slot, slot_id);

    // Publisher should have gotten refund
    let escrow = (MIN_OFFER_PRICE * MIN_PIN_QTY) as i128;
    assert_eq!(pay_token_client.balance(&publisher), balance_before + escrow);
}

#[test]
fn test_slot_attack_scenario() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    // Attacker fills all 10 slots
    let attacker = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &attacker, &10_000_000);

    for i in 0..NUM_SLOTS {
        let cid = String::from_val(&env, &alloc::format!("QmAttack{}", i).as_str());
        let gateway = String::from_val(&env, &"https://evil.test");
        client.create_pin(&attacker, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);
    }

    assert_eq!(client.has_available_slots(), false);

    // Advance past expiration
    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * MAX_CYCLES + 1;
    });

    // All slots should be available now (expired)
    assert_eq!(client.has_available_slots(), true);

    // Can clear them all
    for i in 0..NUM_SLOTS {
        client.clear_expired_slot(&i);
    }
    assert_eq!(client.get_all_slots().len(), 0);
}

// =============================================================================
// Financial Tests
// =============================================================================

#[test]
fn test_fee_accounting() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    assert_eq!(client.fees_collected(), 0);

    create_test_pin(&env, &client, &pay_token_client, &admin, "QmFee1");
    assert_eq!(client.fees_collected(), PIN_FEE as i128);

    create_test_pin(&env, &client, &pay_token_client, &admin, "QmFee2");
    assert_eq!(client.fees_collected(), PIN_FEE as i128 * 2);
}

#[test]
fn test_withdraw_fees_respects_escrow() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let recipient = Address::generate(&env);

    create_test_pin(&env, &client, &pay_token_client, &admin, "QmEscrow");

    let contract_balance = client.balance();
    let fees = client.fees_collected();

    // Withdraw fees
    client.withdraw_fees(&admin, &recipient);

    // Contract should still hold escrow
    let escrow = (MIN_OFFER_PRICE * MIN_PIN_QTY) as i128;
    assert_eq!(client.balance(), contract_balance - fees);
    assert_eq!(client.balance(), escrow);
}

#[test]
fn test_escrow_accounting() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let (_, slot_id) = create_test_pin(&env, &client, &pay_token_client, &admin, "QmEscAcc");

    let slot = client.get_slot(&slot_id);
    let initial_escrow = slot.escrow_balance;
    assert_eq!(initial_escrow, MIN_OFFER_PRICE * MIN_PIN_QTY);

    let pinner = register_pinner(&env, &client, &pay_token_client, &admin);
    client.collect_pin(&pinner, &slot_id);

    let slot_after = client.get_slot(&slot_id);
    assert_eq!(slot_after.escrow_balance, initial_escrow - MIN_OFFER_PRICE);
}

#[test]
fn test_no_fund_leakage() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();

    // Create pin and fill completely
    let publisher = Address::generate(&env);
    let initial_pub = 1_000_000_i128;
    mint_tokens(&pay_token_client, &admin, &publisher, &initial_pub);

    let cid = String::from_val(&env, &"QmNoLeak");
    let gateway = String::from_val(&env, &"https://gateway.test");
    let slot_id = client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);

    let mut pinner_initial_sum = 0_i128;
    let mut pinners = soroban_sdk::Vec::new(&env);
    for _ in 0..MIN_PIN_QTY {
        let p = register_pinner(&env, &client, &pay_token_client, &admin);
        pinner_initial_sum += pay_token_client.balance(&p);
        pinners.push_back(p);
    }

    for i in 0..MIN_PIN_QTY {
        let p = pinners.get(i).unwrap();
        client.collect_pin(&p, &slot_id);
    }

    // Withdraw fees
    let recipient = Address::generate(&env);
    // fees_collected = pin_fee from create_pin + join_fee * num_pinners
    let expected_fees = PIN_FEE as i128 + (JOIN_FEE as i128 * MIN_PIN_QTY as i128);
    client.withdraw_fees(&admin, &recipient);

    // Verify: publisher paid (escrow + pin_fee), got 0 back (all collected)
    let pub_balance = pay_token_client.balance(&publisher);
    let pub_spent = initial_pub - pub_balance;
    assert_eq!(pub_spent, (MIN_OFFER_PRICE * MIN_PIN_QTY + PIN_FEE) as i128);

    // Pinners each earned offer_price from collecting
    let mut pinner_final_sum = 0_i128;
    for i in 0..MIN_PIN_QTY {
        let p = pinners.get(i).unwrap();
        pinner_final_sum += pay_token_client.balance(&p);
    }
    let pinner_earned = pinner_final_sum - pinner_initial_sum;
    assert_eq!(pinner_earned, (MIN_OFFER_PRICE * MIN_PIN_QTY) as i128);

    // Recipient gets all accumulated fees (pin_fee + join_fees)
    assert_eq!(pay_token_client.balance(&recipient), expected_fees);
}

#[test]
fn test_fund_contract() {
    let (env, client, admin, pay_token_client, _) = setup_test_env();
    let funder = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &funder, &100_000);

    let before = client.balance();
    client.fund_contract(&funder, &500);
    let after = client.balance();
    assert_eq!(after - before, 500);
}

// Need alloc for format!
extern crate alloc;
