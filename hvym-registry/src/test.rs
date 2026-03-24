#![cfg(test)]

use crate::{Network, RegistryContract, RegistryContractClient, RegistryEvent, RemoveEvent};
use soroban_sdk::{symbol_short, testutils::Events, Address, Env, IntoVal, String, Vec};
use soroban_sdk::testutils::Address as _;

fn setup(env: &Env) -> (RegistryContractClient, Address) {
    let admin = Address::generate(env);
    let client = RegistryContractClient::new(
        env,
        &env.register(RegistryContract, (&admin,)),
    );
    (client, admin)
}

// ── Constructor tests ───────────────────────────────────────────────────────

#[test]
fn test_constructor_sets_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    assert!(client.is_admin(&admin));
    assert_eq!(client.get_admin_list().len(), 1);
}

// ── Set / get contract ID ───────────────────────────────────────────────────

#[test]
fn test_set_and_get_contract_id() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let name = String::from_str(&env, "opus_token");
    let contract_id = Address::generate(&env);

    client.set_contract_id(&admin, &name, &Network::Testnet, &contract_id);
    assert_eq!(client.get_contract_id(&name, &Network::Testnet), contract_id);
}

#[test]
fn test_set_contract_id_both_networks() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let name = String::from_str(&env, "opus_token");
    let testnet_id = Address::generate(&env);
    let mainnet_id = Address::generate(&env);

    client.set_contract_id(&admin, &name, &Network::Testnet, &testnet_id);
    client.set_contract_id(&admin, &name, &Network::Mainnet, &mainnet_id);

    assert_eq!(client.get_contract_id(&name, &Network::Testnet), testnet_id);
    assert_eq!(client.get_contract_id(&name, &Network::Mainnet), mainnet_id);
}

#[test]
fn test_set_contract_id_update_existing() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let name = String::from_str(&env, "hvym_collective");
    let old_id = Address::generate(&env);
    let new_id = Address::generate(&env);

    client.set_contract_id(&admin, &name, &Network::Testnet, &old_id);
    assert_eq!(client.get_contract_id(&name, &Network::Testnet), old_id);

    client.set_contract_id(&admin, &name, &Network::Testnet, &new_id);
    assert_eq!(client.get_contract_id(&name, &Network::Testnet), new_id);

    // Updating should not duplicate the name in the registry list
    let all = client.get_all_contracts(&Network::Testnet);
    assert_eq!(all.len(), 1);
}

#[test]
fn test_set_multiple_contracts() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let names = [
        "opus_token",
        "hvym_collective",
        "hvym_roster",
        "hvym_pin_service",
        "hvym_pin_service_factory",
    ];
    let mut ids = Vec::new(&env);

    for name_str in &names {
        let name = String::from_str(&env, name_str);
        let id = Address::generate(&env);
        ids.push_back(id.clone());
        client.set_contract_id(&admin, &name, &Network::Testnet, &id);
    }

    for (i, name_str) in names.iter().enumerate() {
        let name = String::from_str(&env, name_str);
        assert_eq!(
            client.get_contract_id(&name, &Network::Testnet),
            ids.get(i as u32).unwrap()
        );
    }

    assert_eq!(client.get_all_contracts(&Network::Testnet).len(), 5);
}

#[test]
#[should_panic(expected = "unauthorized")]
fn test_set_contract_id_unauthorized() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, _admin) = setup(&env);

    let non_admin = Address::generate(&env);
    let name = String::from_str(&env, "opus_token");
    let contract_id = Address::generate(&env);

    client.set_contract_id(&non_admin, &name, &Network::Testnet, &contract_id);
}

// ── Has contract ID ─────────────────────────────────────────────────────────

#[test]
fn test_has_contract_id() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let name = String::from_str(&env, "opus_token");
    assert!(!client.has_contract_id(&name, &Network::Testnet));

    let contract_id = Address::generate(&env);
    client.set_contract_id(&admin, &name, &Network::Testnet, &contract_id);
    assert!(client.has_contract_id(&name, &Network::Testnet));

    // Different network should not have it
    assert!(!client.has_contract_id(&name, &Network::Mainnet));
}

// ── Get contract ID (not found) ─────────────────────────────────────────────

#[test]
#[should_panic(expected = "contract not registered")]
fn test_get_contract_id_not_found() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, _admin) = setup(&env);

    let name = String::from_str(&env, "nonexistent");
    client.get_contract_id(&name, &Network::Testnet);
}

// ── Remove contract ID ──────────────────────────────────────────────────────

#[test]
fn test_remove_contract_id() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let name = String::from_str(&env, "opus_token");
    let contract_id = Address::generate(&env);

    client.set_contract_id(&admin, &name, &Network::Testnet, &contract_id);
    assert!(client.has_contract_id(&name, &Network::Testnet));

    client.remove_contract_id(&admin, &name, &Network::Testnet);
    assert!(!client.has_contract_id(&name, &Network::Testnet));
    assert_eq!(client.get_all_contracts(&Network::Testnet).len(), 0);
}

#[test]
fn test_remove_one_network_keeps_other() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let name = String::from_str(&env, "opus_token");
    let testnet_id = Address::generate(&env);
    let mainnet_id = Address::generate(&env);

    client.set_contract_id(&admin, &name, &Network::Testnet, &testnet_id);
    client.set_contract_id(&admin, &name, &Network::Mainnet, &mainnet_id);

    client.remove_contract_id(&admin, &name, &Network::Testnet);
    assert!(!client.has_contract_id(&name, &Network::Testnet));
    assert_eq!(client.get_contract_id(&name, &Network::Mainnet), mainnet_id);
}

#[test]
#[should_panic(expected = "contract not registered")]
fn test_remove_contract_id_not_found() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let name = String::from_str(&env, "nonexistent");
    client.remove_contract_id(&admin, &name, &Network::Testnet);
}

#[test]
#[should_panic(expected = "unauthorized")]
fn test_remove_contract_id_unauthorized() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let name = String::from_str(&env, "opus_token");
    let contract_id = Address::generate(&env);
    client.set_contract_id(&admin, &name, &Network::Testnet, &contract_id);

    let non_admin = Address::generate(&env);
    client.remove_contract_id(&non_admin, &name, &Network::Testnet);
}

// ── Get all contracts ───────────────────────────────────────────────────────

#[test]
fn test_get_all_contracts_empty() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, _admin) = setup(&env);

    let all = client.get_all_contracts(&Network::Testnet);
    assert_eq!(all.len(), 0);
}

#[test]
fn test_get_all_contracts_per_network() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let opus = String::from_str(&env, "opus_token");
    let roster = String::from_str(&env, "hvym_roster");
    let opus_testnet = Address::generate(&env);
    let opus_mainnet = Address::generate(&env);
    let roster_testnet = Address::generate(&env);

    client.set_contract_id(&admin, &opus, &Network::Testnet, &opus_testnet);
    client.set_contract_id(&admin, &opus, &Network::Mainnet, &opus_mainnet);
    client.set_contract_id(&admin, &roster, &Network::Testnet, &roster_testnet);

    let testnet_all = client.get_all_contracts(&Network::Testnet);
    assert_eq!(testnet_all.len(), 2);

    let mainnet_all = client.get_all_contracts(&Network::Mainnet);
    assert_eq!(mainnet_all.len(), 1);
}

// ── Event emission ──────────────────────────────────────────────────────────

#[test]
fn test_set_contract_id_emits_event() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let name = String::from_str(&env, "opus_token");
    let contract_id = Address::generate(&env);
    client.set_contract_id(&admin, &name, &Network::Testnet, &contract_id);

    let events = env.events().all();
    let last = events.last().unwrap();
    assert_eq!(
        last.1,
        (symbol_short!("SET"), symbol_short!("contract")).into_val(&env)
    );
    let event_data: RegistryEvent = last.2.into_val(&env);
    assert_eq!(event_data.name, name);
    assert_eq!(event_data.contract_id, contract_id);
}

#[test]
fn test_remove_contract_id_emits_event() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let name = String::from_str(&env, "opus_token");
    let contract_id = Address::generate(&env);
    client.set_contract_id(&admin, &name, &Network::Testnet, &contract_id);
    client.remove_contract_id(&admin, &name, &Network::Testnet);

    let events = env.events().all();
    let last = events.last().unwrap();
    assert_eq!(
        last.1,
        (symbol_short!("REMOVE"), symbol_short!("contract")).into_val(&env)
    );
    let event_data: RemoveEvent = last.2.into_val(&env);
    assert_eq!(event_data.name, name);
}

// ── Admin management ────────────────────────────────────────────────────────

#[test]
fn test_add_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let new_admin = Address::generate(&env);
    client.add_admin(&admin, &new_admin);

    assert!(client.is_admin(&new_admin));
    assert_eq!(client.get_admin_list().len(), 2);
}

#[test]
#[should_panic(expected = "already an admin")]
fn test_add_admin_duplicate() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    client.add_admin(&admin, &admin);
}

#[test]
#[should_panic(expected = "unauthorized")]
fn test_add_admin_unauthorized() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, _admin) = setup(&env);

    let non_admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    client.add_admin(&non_admin, &new_admin);
}

#[test]
fn test_remove_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let second_admin = Address::generate(&env);
    client.add_admin(&admin, &second_admin);
    assert_eq!(client.get_admin_list().len(), 2);

    client.remove_admin(&admin, &second_admin);
    assert!(!client.is_admin(&second_admin));
    assert_eq!(client.get_admin_list().len(), 1);
}

#[test]
#[should_panic(expected = "cannot remove initial admin")]
fn test_remove_initial_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    client.remove_admin(&admin, &admin);
}

#[test]
#[should_panic(expected = "address is not an admin")]
fn test_remove_nonexistent_admin() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let non_admin = Address::generate(&env);
    client.remove_admin(&admin, &non_admin);
}

#[test]
fn test_multi_admin_can_set_contracts() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    let second_admin = Address::generate(&env);
    client.add_admin(&admin, &second_admin);

    // Second admin can set contract IDs
    let name = String::from_str(&env, "hvym_roster");
    let contract_id = Address::generate(&env);
    client.set_contract_id(&second_admin, &name, &Network::Testnet, &contract_id);

    assert_eq!(client.get_contract_id(&name, &Network::Testnet), contract_id);
}

// ── Full registry workflow ──────────────────────────────────────────────────

#[test]
fn test_full_registry_workflow() {
    let env = Env::default();
    env.mock_all_auths();
    let (client, admin) = setup(&env);

    // Register all contracts on testnet
    let contracts = [
        "opus_token",
        "hvym_collective",
        "hvym_roster",
        "hvym_pin_service",
        "hvym_pin_service_factory",
        "pintheon_ipfs_token",
        "pintheon_node_token",
    ];

    for name_str in &contracts {
        let name = String::from_str(&env, name_str);
        let id = Address::generate(&env);
        client.set_contract_id(&admin, &name, &Network::Testnet, &id);
    }

    assert_eq!(client.get_all_contracts(&Network::Testnet).len(), 7);
    assert_eq!(client.get_all_contracts(&Network::Mainnet).len(), 0);

    // Register a few on mainnet
    for name_str in &contracts[..3] {
        let name = String::from_str(&env, name_str);
        let id = Address::generate(&env);
        client.set_contract_id(&admin, &name, &Network::Mainnet, &id);
    }

    assert_eq!(client.get_all_contracts(&Network::Mainnet).len(), 3);
    // Testnet unchanged
    assert_eq!(client.get_all_contracts(&Network::Testnet).len(), 7);

    // Update a testnet contract ID (simulating redeploy)
    let opus = String::from_str(&env, "opus_token");
    let old_id = client.get_contract_id(&opus, &Network::Testnet);
    let new_id = Address::generate(&env);
    assert_ne!(old_id, new_id);

    client.set_contract_id(&admin, &opus, &Network::Testnet, &new_id);
    assert_eq!(client.get_contract_id(&opus, &Network::Testnet), new_id);
    // Count unchanged
    assert_eq!(client.get_all_contracts(&Network::Testnet).len(), 7);

    // Remove a contract
    let node = String::from_str(&env, "pintheon_node_token");
    client.remove_contract_id(&admin, &node, &Network::Testnet);
    assert!(!client.has_contract_id(&node, &Network::Testnet));
    assert_eq!(client.get_all_contracts(&Network::Testnet).len(), 6);
}
