#![cfg(test)]
extern crate alloc;
extern crate std;

use crate::{PinServiceFactory, PinServiceFactoryClient};
use alloc::vec;
use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, AuthorizedFunction, AuthorizedInvocation},
    Address, Env, IntoVal, Symbol,
};

mod contract {
    soroban_sdk::contractimport!(
        file = "../hvym-pin-service/target/wasm32v1-none/release/hvym_pin_service.wasm"
    );
}

fn setup_factory(env: &Env) -> (PinServiceFactoryClient, Address, Address) {
    let admin = Address::generate(env);
    let xlm = Address::from_string(&soroban_sdk::String::from_str(
        env,
        "CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC",
    ));
    let factory_id = env.register(PinServiceFactory, (&admin,));
    let factory_client = PinServiceFactoryClient::new(env, &factory_id);
    (factory_client, admin, xlm)
}

#[test]
fn test_factory_initialization() {
    let env = Env::default();
    let (factory_client, admin, _xlm) = setup_factory(&env);

    assert_eq!(factory_client.get_admin(), admin);
    assert_eq!(factory_client.get_instance_count(), 0);
    let instances = factory_client.get_instances();
    assert_eq!(instances.len(), 0);
}

#[test]
fn test_single_deploy() {
    let env = Env::default();
    env.mock_all_auths();
    let (factory_client, admin, xlm) = setup_factory(&env);

    let pin_fee: u32 = 10;
    let join_fee: u32 = 50;
    let min_pin_qty: u32 = 3;
    let min_offer_price: u32 = 10;
    let pinner_stake: u32 = 100;
    let max_cycles: u32 = 60;
    let flag_threshold: u32 = 3;

    let contract_id = factory_client.deploy(
        &pin_fee,
        &join_fee,
        &min_pin_qty,
        &min_offer_price,
        &pinner_stake,
        &xlm,
        &max_cycles,
        &flag_threshold,
    );

    // Verify registry updated
    assert_eq!(factory_client.get_instance_count(), 1);
    let instances = factory_client.get_instances();
    assert_eq!(instances.len(), 1);
    assert_eq!(instances.get(0).unwrap(), contract_id);

    // Verify pin-service is functional
    let pin_service = contract::Client::new(&env, &contract_id);
    let symbol: Symbol = symbol_short!("HVYMPIN");
    assert_eq!(pin_service.symbol(), symbol);
    assert_eq!(pin_service.pin_fee(), pin_fee);
    assert_eq!(pin_service.join_fee(), join_fee);
}

#[test]
fn test_multiple_deploys() {
    let env = Env::default();
    env.mock_all_auths();
    let (factory_client, _admin, xlm) = setup_factory(&env);

    // Deploy first instance
    let id1 = factory_client.deploy(&10, &50, &3, &10, &100, &xlm, &60, &3);

    // Deploy second instance with different config
    let id2 = factory_client.deploy(&20, &100, &5, &20, &200, &xlm, &120, &5);

    // Verify unique addresses
    assert_ne!(id1, id2);

    // Verify registry
    assert_eq!(factory_client.get_instance_count(), 2);
    let instances = factory_client.get_instances();
    assert_eq!(instances.get(0).unwrap(), id1);
    assert_eq!(instances.get(1).unwrap(), id2);

    // Verify each has its own config
    let ps1 = contract::Client::new(&env, &id1);
    let ps2 = contract::Client::new(&env, &id2);
    assert_eq!(ps1.pin_fee(), 10);
    assert_eq!(ps2.pin_fee(), 20);
    assert_eq!(ps1.join_fee(), 50);
    assert_eq!(ps2.join_fee(), 100);
}

#[test]
fn test_admin_authorization() {
    let env = Env::default();
    env.mock_all_auths();
    let (factory_client, admin, xlm) = setup_factory(&env);

    let pin_fee: u32 = 10;
    let join_fee: u32 = 50;
    let min_pin_qty: u32 = 3;
    let min_offer_price: u32 = 10;
    let pinner_stake: u32 = 100;
    let max_cycles: u32 = 60;
    let flag_threshold: u32 = 3;

    factory_client.deploy(
        &pin_fee,
        &join_fee,
        &min_pin_qty,
        &min_offer_price,
        &pinner_stake,
        &xlm,
        &max_cycles,
        &flag_threshold,
    );

    // Verify admin auth was required
    let expected_auth = AuthorizedInvocation {
        function: AuthorizedFunction::Contract((
            factory_client.address,
            symbol_short!("deploy"),
            (
                pin_fee,
                join_fee,
                min_pin_qty,
                min_offer_price,
                pinner_stake,
                xlm,
                max_cycles,
                flag_threshold,
            )
                .into_val(&env),
        )),
        sub_invocations: vec![],
    };
    assert_eq!(env.auths(), vec![(admin, expected_auth)]);
}

#[test]
fn test_route_to_available() {
    let env = Env::default();
    env.mock_all_auths();
    let (factory_client, _admin, xlm) = setup_factory(&env);

    // Deploy an instance
    let id1 = factory_client.deploy(&10, &50, &3, &10, &100, &xlm, &60, &3);

    // Route should find available instance (fresh instance has empty slots)
    let available = factory_client.route_to_available(&10);
    assert!(available.is_some());
    assert_eq!(available.unwrap(), id1);
}

#[test]
fn test_get_instances_list() {
    let env = Env::default();
    env.mock_all_auths();
    let (factory_client, _admin, xlm) = setup_factory(&env);

    // Deploy three instances
    let id1 = factory_client.deploy(&10, &50, &3, &10, &100, &xlm, &60, &3);
    let id2 = factory_client.deploy(&20, &100, &5, &20, &200, &xlm, &120, &5);
    let id3 = factory_client.deploy(&30, &150, &2, &30, &300, &xlm, &90, &4);

    // Verify ordering
    let instances = factory_client.get_instances();
    assert_eq!(instances.len(), 3);
    assert_eq!(instances.get(0).unwrap(), id1);
    assert_eq!(instances.get(1).unwrap(), id2);
    assert_eq!(instances.get(2).unwrap(), id3);

    // Verify get_instance_at
    assert_eq!(factory_client.get_instance_at(&0), id1);
    assert_eq!(factory_client.get_instance_at(&1), id2);
    assert_eq!(factory_client.get_instance_at(&2), id3);
}

#[test]
#[should_panic]
fn test_get_instance_at_out_of_bounds() {
    let env = Env::default();
    let (factory_client, _admin, _xlm) = setup_factory(&env);

    // Should panic - no instances deployed
    factory_client.get_instance_at(&0);
}
