#![cfg(test)]

use crate::{CollectiveContract, CollectiveContractClient};
use crate::{token};
use soroban_sdk::{
    testutils::{Address as _, Events}, testutils::arbitrary::std,
    Symbol, Address, Env, String, FromVal, TryFromVal, symbol_short
};

mod pintheon_node_token {
    soroban_sdk::contractimport!(
        file = "../pintheon-node-deployer/pintheon-node-token/target/wasm32-unknown-unknown/release/pintheon_node_token.optimized.wasm"
    );
}

mod pintheon_ipfs_token {
    soroban_sdk::contractimport!(
        file = "../pintheon-ipfs-deployer/pintheon-ipfs-token/target/wasm32-unknown-unknown/release/pintheon_ipfs_token.optimized.wasm"
    );
}

mod opus_token {
    soroban_sdk::contractimport!(
        file = "../opus_token/target/wasm32-unknown-unknown/release/opus_token.optimized.wasm"
    );
}

fn create_token_contract<'a>(
    e: &Env,
    admin: &Address,
) -> (token::Client<'a>, token::StellarAssetClient<'a>) {
    let sac = e.register_stellar_asset_contract_v2(admin.clone());
    (
        token::Client::new(e, &sac.address()),
        token::StellarAssetClient::new(e, &sac.address()),
    )
}

#[test]
fn test_join_and_remove() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    assert_eq!(collective.is_member(&user), false);
    collective.join(&user);
    assert_eq!(collective.is_member(&user), true);
    assert_eq!(collective.member_paid(&user), 10);
    assert_eq!(collective.remove(&admin, &user), true);
    assert_eq!(collective.is_member(&user), false);
}

#[test]
#[should_panic(expected = "already part of collective")]
fn test_double_join_should_fail() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    collective.join(&user);
    collective.join(&user); // should panic
}

#[test]
#[should_panic(expected = "not enough to cover fee")]
fn test_join_with_insufficient_balance() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &5);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    collective.join(&user); // should panic
}

#[test]
fn test_update_fees_and_reward() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    assert_eq!(collective.update_join_fee(&admin, &20_u32), 20);
    assert_eq!(collective.update_mint_fee(&admin, &15_u32), 15);
    assert_eq!(collective.update_opus_reward(&admin, &8_u32), 8);
}

#[test]
fn test_fund_and_withdraw() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    collective.fund_contract(&user, &50);
    assert_eq!(pay_token_client.balance(&collective.address), 50);
    collective.withdraw(&admin, &admin);
    assert_eq!(pay_token_client.balance(&admin), 50);
}

#[test]
fn test_deploy_opus() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 10_u32))
    );

    let opus_address = collective.launch_opus(&admin, &100);
    let opus_client = opus_token::Client::new(&env, &opus_address);
    assert_eq!(opus_client.balance(&admin), 100);
}

#[test]
#[should_panic(expected = "opus already up")]
fn test_deploy_opus_twice_should_fail() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 10_u32))
    );

    collective.launch_opus(&admin, &100);
    collective.launch_opus(&admin, &100); // should panic
}

#[test]
fn test_deploy_node_token() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 5_u32))
    );

    collective.join(&user);
    let name = String::from_val(&env, &"MyNode");
    let descriptor = String::from_val(&env, &"This is a node");
    let contract_id = collective.deploy_node_token(&user, &name, &descriptor);

    let token = pintheon_node_token::Client::new(&env, &contract_id);
    assert_eq!(token.balance(&user), 1);
}

#[test]
fn test_deploy_ipfs_token() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 5_u32))
    );

    collective.join(&user);
    collective.launch_opus(&admin, &100);

    let name = String::from_val(&env, &"MyFile");
    let ipfs_hash = String::from_val(&env, &"QmHash");
    let file_type = String::from_val(&env, &"image/png");
    let gateways = String::from_val(&env, &"https://ipfs.io");
    let ipns_hash: Option<String> = None;

    let contract_id = collective.deploy_ipfs_token(&user, &name, &ipfs_hash, &file_type, &gateways, &ipns_hash);
    let token = pintheon_ipfs_token::Client::new(&env, &contract_id);
    assert_eq!(token.name(), name);
}

#[test]
fn test_emits_join_and_remove_events() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);

    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let contract_id = env.register(
        CollectiveContract,
        (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32),
    );
    let collective = CollectiveContractClient::new(&env, &contract_id);

    collective.join(&user);
    let events_1: std::vec::Vec<_> = env.events().all().into_iter().collect();
    let join_event = &events_1[1];

    let (_contract_id, topics, _data) = join_event;
    let join_symbol: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0))
        .expect("Expected first topic to be a Symbol");

    assert_eq!(join_symbol, symbol_short!("JOIN"));

    collective.remove(&admin, &user);
    let events_2: std::vec::Vec<_> = env.events().all().into_iter().collect();
    let remove_event = &events_2[0];

    let (_contract_id, topics, _data) = remove_event;
    let remove_symbol: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0))
        .expect("Expected first topic to be a Symbol");

    assert_eq!(remove_symbol, symbol_short!("REMOVE"));

}

#[test]
fn test_emits_publish_events() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);

    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let contract_id = env.register(
        CollectiveContract,
        (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32),
    );
    let collective = CollectiveContractClient::new(&env, &contract_id);

    let ipfs_hash = String::from_val(&env, &"SomeHash");
    let publisher_key = String::from_val(&env, &"SomePublisher");
    let recipient_key = String::from_val(&env, &"SomeReciever");

    collective.publish_file(&user, &publisher_key, &ipfs_hash);
    let events_1: std::vec::Vec<_> = env.events().all().into_iter().collect();
    let event1 = &events_1[1];

    let (_contract_id, topics, _data) = event1;
    let symbol1: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0))
        .expect("Expected first topic to be a Symbol");

    assert_eq!(symbol1, symbol_short!("PUBLISH"));

    collective.publish_encrypted_share(&user,  &publisher_key, &recipient_key, &ipfs_hash);
    let events_2: std::vec::Vec<_> = env.events().all().into_iter().collect();
    let event2 = &events_2[1];

    let (_contract_id, topics, _data) = event2;
    let symbol2: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0))
        .expect("Expected first topic to be a Symbol");

    assert_eq!(symbol2, symbol_short!("PUBLISH"));

}


#[test]
#[should_panic(expected = "cannot fund with zero")]
fn test_zero_value_funding() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    let result = collective.fund_contract(&user, &0);
    assert_eq!(result, 0);
}

#[test]
#[should_panic(expected = "unauthorized")]
fn test_deploy_contract_as_non_member() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    let name = String::from_val(&env, &"ForbiddenNode");
    let descriptor = String::from_val(&env, &"You shall not deploy");
    collective.deploy_node_token(&user, &name, &descriptor);
}

#[test]
#[should_panic(expected = "network not up")]
fn test_deploy_ipfs_before_opus() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    collective.join(&user);

    let name = String::from_val(&env, &"TestFile");
    let ipfs_hash = String::from_val(&env, &"SomeHash");
    let file_type = String::from_val(&env, &"image/jpeg");
    let gateways = String::from_val(&env, &"https://example.com");
    let ipns_hash: Option<String> = None;

    collective.deploy_ipfs_token(&user, &name, &ipfs_hash, &file_type, &gateways, &ipns_hash);
}

#[test]
fn test_add_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Initial admin should be in the list
    assert_eq!(collective.is_admin(&admin), true);
    assert_eq!(collective.is_admin(&new_admin), false);

    // Add new admin
    let result = collective.add_admin(&admin, &new_admin);
    assert_eq!(result, true);
    assert_eq!(collective.is_admin(&new_admin), true);

    // Check admin list
    let admin_list = collective.get_admin_list();
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
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Try to add admin twice
    collective.add_admin(&admin, &admin);
}

#[test]
#[should_panic(expected = "unauthorized: admin access required")]
fn test_add_admin_unauthorized() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let non_admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Non-admin tries to add admin
    collective.add_admin(&non_admin, &new_admin);
}

#[test]
fn test_remove_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Add new admin first
    collective.add_admin(&admin, &new_admin);
    assert_eq!(collective.is_admin(&new_admin), true);

    // Remove the new admin
    let result = collective.remove_admin(&admin, &new_admin);
    assert_eq!(result, true);
    assert_eq!(collective.is_admin(&new_admin), false);

    // Check admin list
    let admin_list = collective.get_admin_list();
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
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Try to remove initial admin
    collective.remove_admin(&admin, &admin);
}

#[test]
#[should_panic(expected = "admin not found")]
fn test_remove_nonexistent_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let non_admin = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Try to remove non-existent admin
    collective.remove_admin(&admin, &non_admin);
}

#[test]
#[should_panic(expected = "unauthorized: admin access required")]
fn test_remove_admin_unauthorized() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let non_admin = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Add new admin
    collective.add_admin(&admin, &new_admin);

    // Non-admin tries to remove admin
    collective.remove_admin(&non_admin, &new_admin);
}

#[test]
fn test_multi_admin_functionality() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let admin2 = Address::generate(&env);
    let admin3 = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Add multiple admins
    collective.add_admin(&admin, &admin2);
    collective.add_admin(&admin, &admin3);

    // All admins should be able to perform admin functions
    assert_eq!(collective.is_admin(&admin), true);
    assert_eq!(collective.is_admin(&admin2), true);
    assert_eq!(collective.is_admin(&admin3), true);

    // Admin2 can update fees
    assert_eq!(collective.update_join_fee(&admin2, &25_u32), 25);
    assert_eq!(collective.update_mint_fee(&admin2, &20_u32), 20);

    // Admin3 can remove members
    collective.join(&user);
    assert_eq!(collective.is_member(&user), true);
    collective.remove(&admin3, &user);
    assert_eq!(collective.is_member(&user), false);

    // Admin2 can remove admin3
    collective.remove_admin(&admin2, &admin3);
    assert_eq!(collective.is_admin(&admin3), false);
    assert_eq!(collective.is_admin(&admin2), true);
}

#[test]
fn test_admin_events() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Add admin and check event
    collective.add_admin(&admin, &new_admin);
    let events = env.events().all();
    let add_event = events.last().unwrap();
    use soroban_sdk::{Symbol, Address, TryFromVal};
    let topic0: Symbol = Symbol::try_from_val(&env, &add_event.1.get_unchecked(0)).unwrap();
    let topic1: Symbol = Symbol::try_from_val(&env, &add_event.1.get_unchecked(1)).unwrap();
    let data_addr: Address = Address::try_from_val(&env, &add_event.2).unwrap();
    assert_eq!(topic0, symbol_short!("ADD_ADMIN"));
    assert_eq!(topic1, symbol_short!("admin"));
    assert_eq!(data_addr, new_admin);

    // Remove admin and check event
    collective.remove_admin(&admin, &new_admin);
    let events = env.events().all();
    let remove_event = events.last().unwrap();
    let topic0: Symbol = Symbol::try_from_val(&env, &remove_event.1.get_unchecked(0)).unwrap();
    let topic1: Symbol = Symbol::try_from_val(&env, &remove_event.1.get_unchecked(1)).unwrap();
    let data_addr: Address = Address::try_from_val(&env, &remove_event.2).unwrap();
    assert_eq!(topic0, symbol_short!("REM_ADMIN"));
    assert_eq!(topic1, symbol_short!("admin"));
    assert_eq!(data_addr, new_admin);
}

#[test]
fn test_admin_list_persistence() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let admin2 = Address::generate(&env);
    let admin3 = Address::generate(&env);
    let (pay_token_client, _) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Add multiple admins
    collective.add_admin(&admin, &admin2);
    collective.add_admin(&admin, &admin3);

    // Check admin list
    let admin_list = collective.get_admin_list();
    assert_eq!(admin_list.len(), 3);
    assert!(admin_list.contains(&admin));
    assert!(admin_list.contains(&admin2));
    assert!(admin_list.contains(&admin3));

    // Remove one admin
    collective.remove_admin(&admin, &admin2);
    
    // Check updated admin list
    let admin_list = collective.get_admin_list();
    assert_eq!(admin_list.len(), 2);
    assert!(admin_list.contains(&admin));
    assert!(!admin_list.contains(&admin2));
    assert!(admin_list.contains(&admin3));
}

#[test]
fn test_admin_authorization_in_existing_functions() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let admin2 = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);
    pay_token_admin_client.mint(&admin2, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32))
    );

    // Add admin2
    collective.add_admin(&admin, &admin2);

    // Admin2 should be able to perform all admin functions
    assert_eq!(collective.update_join_fee(&admin2, &30_u32), 30);
    assert_eq!(collective.update_mint_fee(&admin2, &25_u32), 25);
    assert_eq!(collective.update_opus_reward(&admin2, &10_u32), 10);

    // Admin2 should be considered a member
    assert_eq!(collective.is_member(&admin2), true);

    // Admin2 should be able to withdraw funds
    collective.fund_contract(&user, &50);
    collective.withdraw(&admin2, &admin2);
    assert_eq!(pay_token_client.balance(&admin2), 150);
}








