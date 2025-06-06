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
    assert_eq!(collective.remove(&user), true);
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

    assert_eq!(collective.update_join_fee(&20_u32), 20);
    assert_eq!(collective.update_mint_fee(&15_u32), 15);
    assert_eq!(collective.update_opus_reward(&8_u32), 8);
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
    collective.withdraw(&admin);
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

    let opus_address = collective.launch_opus(&100);
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

    collective.launch_opus(&100);
    collective.launch_opus(&100); // should panic
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
    collective.launch_opus(&100);

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

    collective.remove(&user);
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
    let recipient = Address::generate(&env);

    let (pay_token_client, pay_token_admin_client) = create_token_contract(&env, &admin);
    pay_token_admin_client.mint(&user, &100);

    let contract_id = env.register(
        CollectiveContract,
        (&admin, 10_u32, 5_u32, &pay_token_client.address, 3_u32),
    );
    let collective = CollectiveContractClient::new(&env, &contract_id);

    let ipfs_hash = String::from_val(&env, &"SomeHash");

    collective.publish_file(&user, &ipfs_hash);
    let events_1: std::vec::Vec<_> = env.events().all().into_iter().collect();
    let event1 = &events_1[1];

    let (_contract_id, topics, _data) = event1;
    let symbol1: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0))
        .expect("Expected first topic to be a Symbol");

    assert_eq!(symbol1, symbol_short!("PUBLISH"));

    collective.publish_encrypted_share(&user, &recipient, &ipfs_hash);
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
