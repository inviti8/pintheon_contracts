#![cfg(test)]

use crate::{CollectiveContract, CollectiveContractClient};
use soroban_sdk::{
    token, BytesN, Symbol, Address, Env, String, FromVal, TryFromVal, symbol_short,
    testutils::Events
};
use soroban_sdk::testutils::Address as _;

// =============================================================================
// GITHUB WORKFLOW IMPORTS (for production releases)
// =============================================================================
// Uncomment these when pushing to GitHub for releases
// Comment out LOCAL BUILD section below

// mod pintheon_node_token {
//     soroban_sdk::contractimport!(
//         file = "../pintheon-node-deployer/pintheon-node-token/target/wasm32v1-none/release/pintheon-node-token_v0.0.6.wasm"
//     );
// }

// mod pintheon_ipfs_token {
//     soroban_sdk::contractimport!(
//         file = "../pintheon-node-deployer/pintheon-ipfs-token/target/wasm32v1-none/release/pintheon-ipfs-token_v0.0.6.wasm"
//     );
// }

// Note: opus_token is deployed separately and set via set_opus_token method

// =============================================================================
// WASM IMPORTS (standardized location for both local and cloud builds)
// =============================================================================
// These imports use the standardized wasm/ directory in the project root

// Load the WASM files as bytes
const PINTHEON_NODE_TOKEN_WASM: &[u8] = 
    include_bytes!("../../wasm/pintheon_node_token.optimized.wasm");

const PINTHEON_IPFS_TOKEN_WASM: &[u8] = 
    include_bytes!("../../wasm/pintheon_ipfs_token.optimized.wasm");

const COLLECTIVE_WASM: &[u8] = include_bytes!("../../wasm/hvym_collective.optimized.wasm");

// Note: opus_token is deployed separately and set via set_opus_token method

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

// Helper function to create an OPUS token without an admin
fn create_opus_token_contract<'a>(
    e: &Env,
    admin: &Address,
    _collective_address: &Address,  // Not used here anymore, will be set in set_opus_token
) -> (token::Client<'a>, Address) {
    // Create a new token contract without an admin
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

// Helper function to set up a test environment with a collective contract and OPUS token
fn setup_test_env_with_opus(e: &Env) -> (Address, Address, Address, token::Client<'static>, token::Client<'static>) {
    let admin = Address::generate(e);
    let user1 = Address::generate(e);
    
    // Create payment token first
    let (pay_token, pay_token_addr) = create_token_contract(e, &admin);
    
    // Deploy the collective contract with constructor parameters
    let collective_wasm = e.deployer().upload_contract_wasm(COLLECTIVE_WASM);
    let salt = BytesN::from_array(e, &[0u8; 32]);
    let collective_address = e.deployer().with_address(admin.clone(), salt)
        .deploy_v2(
            collective_wasm,
            (
                admin.clone(),  // admin
                100u32,         // join_fee
                10u32,          // mint_fee
                pay_token_addr, // payment token address
                100u32,         // opus_reward
            ),
        );
    
    // Create OPUS token with collective contract as admin
    let (opus_token, opus_token_addr) = create_opus_token_contract(e, &admin, &collective_address);
    
    // The contract is already initialized during deployment with constructor parameters
    let collective = CollectiveContractClient::new(e, &collective_address);
    
    // First, set the collective contract as the admin of the OPUS token
    let opus_admin = token::StellarAssetClient::new(e, &opus_token_addr);
    opus_admin.set_admin(&collective_address);
    
    // Then set the OPUS token in the collective contract
    collective.set_opus_token(&admin, &opus_token_addr, &100);
    
    (admin, user1, collective_address, opus_token, pay_token)
}

fn deploy_wasm_contract<'a>(
    e: &Env,
    wasm: &'a [u8],
    admin: &Address,
    salt: &BytesN<32>,
) -> Address {
    let wasm_hash = e.deployer().upload_contract_wasm(wasm);
    e.deployer()
        .with_address(admin.clone(), salt.clone())
        .deploy_v2(wasm_hash, ())
}

#[test]
fn test_join_and_remove() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &5);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
    );

    collective.join(&user); // should panic
}

#[test]
fn test_update_fees_and_reward() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
    );

    assert_eq!(collective.update_join_fee(&admin, &20_u32), 20);
    assert_eq!(collective.update_mint_fee(&admin, &15_u32), 15);
    assert_eq!(collective.update_opus_reward(&admin, &8_u32), 8);
}

#[test]
fn test_fund_and_withdraw() {
    let e = Env::default();
    e.mock_all_auths();
    
    // Set up test environment with collective and OPUS token
    let (admin, user1, collective_address, _, pay_token) = setup_test_env_with_opus(&e);
    
    let collective = CollectiveContractClient::new(&e, &collective_address);
    
    // Mint some tokens to user1
    mint_tokens(&pay_token, &admin, &user1, &1000);
    
    // User1 joins the collective
    // Use a valid live_until value (current ledger + 1000)
    let current_ledger = e.ledger().sequence();
    pay_token.approve(&user1, &collective_address, &1000, &(current_ledger + 1000));
    collective.join(&user1);
    
    // Verify balances after joining
    assert_eq!(pay_token.balance(&user1), 900);
    assert_eq!(pay_token.balance(&collective_address), 100);
    
    // Admin withdraws to user1
    collective.withdraw(&admin, &user1);
    
    // Verify balances after withdrawal
    // User1 should have their original 1000 tokens back (900 + 100 withdrawn)
    assert_eq!(pay_token.balance(&user1), 1000);
    assert_eq!(pay_token.balance(&collective_address), 0);
}

#[test]
fn test_set_opus_token() {
    let e = Env::default();
    e.mock_all_auths();
    
    // Set up test environment with collective and OPUS token
    let (admin, user1, collective_address, opus_token, _) = setup_test_env_with_opus(&e);
    
    let collective = CollectiveContractClient::new(&e, &collective_address);
    
    // Verify OPUS token was set
    assert_eq!(collective.opus_address(), opus_token.address);
    
    // Verify initial allocation was minted to admin (1e18 tokens in create_opus_token_contract + 100 in set_opus_token)
    assert_eq!(opus_token.balance(&admin), 1_000_000_000_000_000_100);
    
    // Verify non-admin cannot set OPUS token
    assert!(collective.try_set_opus_token(&user1, &opus_token.address, &100).is_err());
}

#[test]
#[should_panic(expected = "HostError: Error(WasmVm, InvalidAction)")]
fn test_set_opus_token_without_admin_should_fail() {
    let e = Env::default();
    e.mock_all_auths();
    
    let admin = Address::generate(&e);
    let non_admin = Address::generate(&e);
    
    // Deploy the collective contract with constructor parameters
    let collective_wasm = e.deployer().upload_contract_wasm(COLLECTIVE_WASM);
    let salt = BytesN::from_array(&e, &[0u8; 32]);
    
    // Create payment token first
    let (pay_token, pay_token_addr) = create_token_contract(&e, &admin);
    
    // Deploy with constructor parameters
    let collective_address = e.deployer().with_address(admin.clone(), salt)
        .deploy_v2(
            collective_wasm,
            (
                admin.clone(),  // admin
                100u32,         // join_fee
                10u32,          // mint_fee
                pay_token_addr, // payment token address
                100u32,         // opus_reward
            ),
        );
    
    // Create OPUS token but don't set the collective as admin
    let (opus_token, opus_token_addr) = create_token_contract(&e, &admin);
    
    let collective = CollectiveContractClient::new(&e, &collective_address);
    
    // Try to set OPUS token with non-admin - should panic with authorization error
    collective.set_opus_token(&non_admin, &opus_token.address, &100);
}

#[test]
#[should_panic(expected = "HostError: Error(WasmVm, InvalidAction)")]
fn test_set_opus_token_twice_should_fail() {
    let e = Env::default();
    e.mock_all_auths();
    
    // Set up test environment with collective and OPUS token
    let (admin, _, collective_address, opus_token, _) = setup_test_env_with_opus(&e);
    
    let collective = CollectiveContractClient::new(&e, &collective_address);
    
    // Try to set OPUS token again - should panic
    collective.set_opus_token(&admin, &opus_token.address, &100);
}

#[test]
fn test_deploy_node_token() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 5_u32))
    );

    collective.join(&user);
    let name = String::from_val(&env, &"MyNode");
    let descriptor = String::from_val(&env, &"This is a node");
    let contract_id = collective.deploy_node_token(&user, &name, &descriptor);

    let token = token::Client::new(&env, &contract_id);
    assert_eq!(token.balance(&user), 1);
}

#[test]
fn test_deploy_ipfs_token() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);
    
    // Create a mock opus token contract
    let (_opus_token_client, opus_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 5_u32))
    );

    collective.join(&user);
    
    // First, set the collective contract as the admin of the OPUS token
    let opus_admin = token::StellarAssetClient::new(&env, &opus_token_addr);
    opus_admin.set_admin(&collective.address);
    
    // Now set the opus token in the collective contract
    collective.set_opus_token(&admin, &opus_token_addr, &100);

    let name = String::from_val(&env, &"MyFile");
    let ipfs_hash = String::from_val(&env, &"QmHash");
    let file_type = String::from_val(&env, &"image/png");
    let gateways = String::from_val(&env, &"https://ipfs.io");
    let ipns_hash: Option<String> = None;

    let contract_id = collective.deploy_ipfs_token(&user, &name, &ipfs_hash, &file_type, &gateways, &ipns_hash);
    let token = token::Client::new(&env, &contract_id);
    
    // The IPFS token contract doesn't automatically mint tokens on deployment
    // So we expect the balance to be 0 initially
    assert_eq!(token.balance(&user), 0);
    
    // Also verify the OPUS reward was minted
    let opus_token = token::Client::new(&env, &opus_token_addr);
    assert_eq!(opus_token.balance(&user), 5); // 5 is the opus_reward from the test
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
        CollectiveContract,
        (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32),
    );
    let collective = CollectiveContractClient::new(&env, &contract_id);

    collective.join(&user);
    let events = env.events().all();
    let join_event = events.last().unwrap();

    let (_contract_id, topics, _data) = join_event;
    let join_symbol: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0))
        .expect("Expected first topic to be a Symbol");

    assert_eq!(join_symbol, symbol_short!("JOIN"));

    collective.remove(&admin, &user);
    let events = env.events().all();
    let remove_event = events.last().unwrap();

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

    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let contract_id = env.register(
        CollectiveContract,
        (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32),
    );
    let collective = CollectiveContractClient::new(&env, &contract_id);

    let ipfs_hash = String::from_val(&env, &"SomeHash");
    let publisher_key = String::from_val(&env, &"SomePublisher");
    let recipient_key = String::from_val(&env, &"SomeReciever");

    collective.publish_file(&user, &publisher_key, &ipfs_hash);
    let events = env.events().all();
    let event1 = events.last().unwrap();

    let (_contract_id, topics, _data) = event1;
    let symbol1: Symbol = Symbol::try_from_val(&env, &topics.get_unchecked(0))
        .expect("Expected first topic to be a Symbol");

    assert_eq!(symbol1, symbol_short!("PUBLISH"));

    collective.publish_encrypted_share(&user, &publisher_key, &recipient_key, &ipfs_hash);
    let events = env.events().all();
    let event2 = events.last().unwrap();

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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
    );

    // Generate test admins
    let admin2 = Address::generate(&env);
    let admin3 = Address::generate(&env);

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
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &100);
    mint_tokens(&pay_token_client, &admin, &user, &100);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, 10_u32, 5_u32, &pay_token_addr, 3_u32))
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
    // The withdraw function transfers the entire contract balance (50 tokens) to the recipient
    assert_eq!(pay_token_client.balance(&admin2), 50);
}








