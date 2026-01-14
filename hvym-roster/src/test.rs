#![cfg(test)]

use crate::{RosterContract, RosterContractClient};
use soroban_sdk::{
    token, Symbol, Address, Env, String, FromVal, TryFromVal, symbol_short,
    testutils::Events
};
use soroban_sdk::testutils::Address as _;

fn create_token_contract<'a>(
    e: &Env,
    admin: &Address,
) -> (token::Client<'a>, Address) {
    // Create a new token contract using the built-in token
    let token_address = e.register_stellar_asset_contract(admin.clone());
    let token = token::Client::new(e, &token_address);

    // Mint initial supply to admin
    let admin_client = token::StellarAssetClient::new(e, &token_address);
    admin_client.mint(admin, &1_000_000_000_000_000_000);

    (token, token_address.clone().into())
}

// Helper function to mint tokens
fn mint_tokens(token_client: &token::Client, _from: &Address, to: &Address, amount: &i128) {
    let admin_client = token::StellarAssetClient::new(&token_client.env, &token_client.address);
    admin_client.mint(to, amount);
}

#[test]
fn test_join_and_remove() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon");

    assert_eq!(roster.is_member(&user), false);
    roster.join(&user, &name, &canon);
    assert_eq!(roster.is_member(&user), true);
    assert_eq!(roster.remove(&admin, &user), true);
    assert_eq!(roster.is_member(&user), false);
}

#[test]
#[should_panic(expected = "already part of roster")]
fn test_double_join_should_fail() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &200);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon");

    roster.join(&user, &name, &canon);
    roster.join(&user, &name, &canon); // should panic
}

#[test]
fn test_update_join_fee() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    assert_eq!(roster.join_fee(), 10);
    assert_eq!(roster.update_join_fee(&admin, &20_u32), 20);
    assert_eq!(roster.join_fee(), 20);
}

#[test]
fn test_fund_and_withdraw() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &1000);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 100_u32, &pay_token_addr))
    );

    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon");

    // User joins the roster
    let current_ledger = env.ledger().sequence();
    pay_token_client.approve(&user, &roster.address, &1000, &(current_ledger + 1000));
    roster.join(&user, &name, &canon);

    // Verify balances after joining
    assert_eq!(pay_token_client.balance(&user), 900);
    assert_eq!(pay_token_client.balance(&roster.address), 100);

    // Admin withdraws to user
    roster.withdraw(&admin, &user);

    // Verify balances after withdrawal
    assert_eq!(pay_token_client.balance(&user), 1000);
    assert_eq!(pay_token_client.balance(&roster.address), 0);
}

#[test]
fn test_emits_join_and_remove_events() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);

    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let contract_id = env.register(
        RosterContract,
        (&admin, 10_u32, &pay_token_addr),
    );
    let roster = RosterContractClient::new(&env, &contract_id);

    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon");

    roster.join(&user, &name, &canon);
    let events = env.events().all();
    let join_event = events.last().unwrap();

    let (_contract_id, topics, _data) = join_event;
    let join_symbol: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0))
        .expect("Expected first topic to be a Symbol");

    assert_eq!(join_symbol, symbol_short!("JOIN"));

    roster.remove(&admin, &user);
    let events = env.events().all();
    let remove_event = events.last().unwrap();

    let (_contract_id, topics, _data) = remove_event;
    let remove_symbol: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0))
        .expect("Expected first topic to be a Symbol");

    assert_eq!(remove_symbol, symbol_short!("REMOVE"));
}

#[test]
#[should_panic(expected = "cannot fund with zero")]
fn test_zero_value_funding() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    roster.fund_contract(&user, &0);
}

#[test]
fn test_add_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Initial admin should be in the list
    assert_eq!(roster.is_admin(&admin), true);
    assert_eq!(roster.is_admin(&new_admin), false);

    // Add new admin
    let result = roster.add_admin(&admin, &new_admin);
    assert_eq!(result, true);
    assert_eq!(roster.is_admin(&new_admin), true);

    // Check admin list
    let admin_list = roster.get_admin_list();
    assert_eq!(admin_list.len(), 2);
    assert!(admin_list.contains(&admin));
    assert!(admin_list.contains(&new_admin));
}

#[test]
#[should_panic(expected = "admin already exists")]
fn test_add_admin_duplicate() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Try to add admin twice
    roster.add_admin(&admin, &admin);
}

#[test]
#[should_panic(expected = "unauthorized: admin access required")]
fn test_add_admin_unauthorized() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let non_admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Non-admin tries to add admin
    roster.add_admin(&non_admin, &new_admin);
}

#[test]
fn test_remove_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Add new admin first
    roster.add_admin(&admin, &new_admin);
    assert_eq!(roster.is_admin(&new_admin), true);

    // Remove the new admin
    let result = roster.remove(&admin, &new_admin);
    assert_eq!(result, true);
    assert_eq!(roster.is_admin(&new_admin), false);

    // Check admin list
    let admin_list = roster.get_admin_list();
    assert_eq!(admin_list.len(), 1);
    assert!(admin_list.contains(&admin));
    assert!(!admin_list.contains(&new_admin));
}

#[test]
#[should_panic(expected = "cannot remove initial admin")]
fn test_remove_initial_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Try to remove initial admin
    roster.remove(&admin, &admin);
}

#[test]
#[should_panic(expected = "admin not found")]
fn test_remove_nonexistent_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let non_admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Try to remove non-existent admin
    roster.remove_admin(&admin, &non_admin);
}

#[test]
#[should_panic(expected = "unauthorized: admin access required")]
fn test_remove_unauthorized() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let non_admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Add new admin
    roster.add_admin(&admin, &new_admin);

    // Non-admin tries to remove admin
    roster.remove(&non_admin, &new_admin);
}

#[test]
fn test_multi_admin_functionality() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let admin2 = Address::generate(&env);
    let admin3 = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Add multiple admins
    roster.add_admin(&admin, &admin2);
    roster.add_admin(&admin, &admin3);

    // All admins should be able to perform admin functions
    assert_eq!(roster.is_admin(&admin), true);
    assert_eq!(roster.is_admin(&admin2), true);
    assert_eq!(roster.is_admin(&admin3), true);

    // Admin2 can update fees
    assert_eq!(roster.update_join_fee(&admin2, &25_u32), 25);

    // Admin3 can remove members
    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon");
    roster.join(&user, &name, &canon);
    assert_eq!(roster.is_member(&user), true);
    roster.remove(&admin3, &user);
    assert_eq!(roster.is_member(&user), false);

    // Admin2 can remove admin3
    roster.remove(&admin2, &admin3);
    assert_eq!(roster.is_admin(&admin3), false);
    assert_eq!(roster.is_admin(&admin2), true);
}

#[test]
fn test_update_canon() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon");
    let new_canon = String::from_val(&env, &"alice_new_canon");

    // User joins
    roster.join(&user, &name, &canon);
    assert_eq!(roster.is_member(&user), true);

    // User updates their own canon
    let result = roster.update_canon(&user, &user, &new_canon);
    assert_eq!(result, true);
}

#[test]
fn test_admin_can_update_member_canon() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon");
    let new_canon = String::from_val(&env, &"admin_assigned_canon");

    // User joins
    roster.join(&user, &name, &canon);

    // Admin updates user's canon
    let result = roster.update_canon(&admin, &user, &new_canon);
    assert_eq!(result, true);
}

#[test]
#[should_panic(expected = "unauthorized: only admins or the member themselves can update canon")]
fn test_update_canon_unauthorized() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user1, &100);
    mint_tokens(&pay_token_client, &admin, &user2, &100);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    let name1 = String::from_val(&env, &"Alice");
    let canon1 = String::from_val(&env, &"alice_canon");
    let name2 = String::from_val(&env, &"Bob");
    let canon2 = String::from_val(&env, &"bob_canon");
    let new_canon = String::from_val(&env, &"hacked_canon");

    // Both users join
    roster.join(&user1, &name1, &canon1);
    roster.join(&user2, &name2, &canon2);

    // User2 tries to update user1's canon (should fail)
    roster.update_canon(&user2, &user1, &new_canon);
}

#[test]
#[should_panic(expected = "member not found")]
fn test_update_canon_nonexistent_member() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    let new_canon = String::from_val(&env, &"some_canon");

    // Try to update canon for non-existent member
    roster.update_canon(&admin, &user, &new_canon);
}

#[test]
fn test_symbol() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    let symbol = roster.symbol();
    assert_eq!(symbol, symbol_short!("HVYM"));
}

#[test]
fn test_admin_authorization_in_existing_functions() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let admin2 = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &200);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Add admin2
    roster.add_admin(&admin, &admin2);

    // Admin2 should be able to perform all admin functions
    assert_eq!(roster.update_join_fee(&admin2, &30_u32), 30);

    // Admin2 should be considered a member
    assert_eq!(roster.is_member(&admin2), true);

    // Admin2 should be able to withdraw funds
    roster.fund_contract(&user, &50);
    roster.withdraw(&admin2, &admin2);
    assert_eq!(pay_token_client.balance(&admin2), 50);
}

#[test]
#[should_panic(expected = "name and canon must be 100 characters or less")]
fn test_join_name_too_long() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Create a name that's too long (101 characters)
    let long_str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"; // 101 'a's
    let long_name = String::from_val(&env, &long_str);
    let canon = String::from_val(&env, &"valid_canon");

    roster.join(&user, &long_name, &canon);
}

#[test]
#[should_panic(expected = "canon must be 100 characters or less")]
fn test_update_canon_too_long() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"valid_canon");

    roster.join(&user, &name, &canon);

    // Try to update with a canon that's too long (101 characters)
    let long_str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"; // 101 'b's
    let long_canon = String::from_val(&env, &long_str);
    roster.update_canon(&user, &user, &long_canon);
}

#[test]
fn test_admin_events() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    // Generate test admins
    let admin2 = Address::generate(&env);
    let admin3 = Address::generate(&env);

    // Add multiple admins
    roster.add_admin(&admin, &admin2);
    roster.add_admin(&admin, &admin3);

    // Check admin list
    let admin_list = roster.get_admin_list();
    assert_eq!(admin_list.len(), 3);
    assert!(admin_list.contains(&admin));
    assert!(admin_list.contains(&admin2));
    assert!(admin_list.contains(&admin3));

    // Remove one admin
    roster.remove(&admin, &admin2);

    // Check updated admin list
    let admin_list = roster.get_admin_list();
    assert_eq!(admin_list.len(), 2);
    assert!(admin_list.contains(&admin));
    assert!(!admin_list.contains(&admin2));
    assert!(admin_list.contains(&admin3));
}

#[test]
fn test_member_paid() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &1000);

    let join_fee = 100_u32;
    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, join_fee, &pay_token_addr))
    );

    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon");

    // User joins the roster
    roster.join(&user, &name, &canon);

    // Check member_paid returns the join fee
    let paid = roster.member_paid(&user);
    assert_eq!(paid, join_fee);
}

#[test]
fn test_member_paid_returns_zero_for_non_member() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let non_member = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 100_u32, &pay_token_addr))
    );

    // Non-member should return 0
    let paid = roster.member_paid(&non_member);
    assert_eq!(paid, 0);
}

#[test]
fn test_member_paid_after_multiple_members() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user1, &1000);
    mint_tokens(&pay_token_client, &admin, &user2, &1000);

    let join_fee = 50_u32;
    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, join_fee, &pay_token_addr))
    );

    let name1 = String::from_val(&env, &"Alice");
    let canon1 = String::from_val(&env, &"alice_canon");
    let name2 = String::from_val(&env, &"Bob");
    let canon2 = String::from_val(&env, &"bob_canon");

    // Both users join
    roster.join(&user1, &name1, &canon1);
    roster.join(&user2, &name2, &canon2);

    // Check each member's paid amount
    assert_eq!(roster.member_paid(&user1), join_fee);
    assert_eq!(roster.member_paid(&user2), join_fee);
}

#[test]
fn test_get_canon() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &1000);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 100_u32, &pay_token_addr))
    );

    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon_data");

    // User joins the roster
    roster.join(&user, &name, &canon);

    // Get canon should return the canon
    let retrieved_canon = roster.get_canon(&user);
    assert_eq!(retrieved_canon, Some(canon));
}

#[test]
fn test_get_canon_returns_none_for_non_member() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let non_member = Address::generate(&env);
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 100_u32, &pay_token_addr))
    );

    // Non-member should return None
    let canon = roster.get_canon(&non_member);
    assert_eq!(canon, None);
}

#[test]
fn test_get_canon_after_update() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &1000);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 100_u32, &pay_token_addr))
    );

    let name = String::from_val(&env, &"Alice");
    let original_canon = String::from_val(&env, &"original_canon");
    let updated_canon = String::from_val(&env, &"updated_canon");

    // User joins with original canon
    roster.join(&user, &name, &original_canon);
    assert_eq!(roster.get_canon(&user), Some(original_canon));

    // Update canon
    roster.update_canon(&user, &user, &updated_canon);

    // Get canon should return the updated canon
    assert_eq!(roster.get_canon(&user), Some(updated_canon));
}
