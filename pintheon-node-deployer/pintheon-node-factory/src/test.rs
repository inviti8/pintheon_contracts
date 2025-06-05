#![cfg(test)]
extern crate alloc;
extern crate std;

use crate::{PintheonFactory, PintheonFactoryClient};
use alloc::vec;
use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, AuthorizedFunction, AuthorizedInvocation},
    Address, BytesN, Val, Env, FromVal, IntoVal, String, Vec,
};

// The contract that will be deployed by the deployer contract.
mod contract {
    soroban_sdk::contractimport!(
        file =
            "../pintheon-node-token/target/wasm32-unknown-unknown/release/pintheon_node_token.optimized.wasm"
    );
}

#[test]
fn test() {
    let env = Env::default();
    let ledger = env.ledger();
    let admin = Address::generate(&env);
    let deployer_client = PintheonFactoryClient::new(&env, &env.register(PintheonFactory, (&admin,)));
    let name = String::from_val(&env, &"name");
    let symbol = String::from_val(&env, &"symbol");
    let node_id = String::from_val(&env, &"NODE_ID");
    let descriptor = String::from_val(&env, &"DESCRIPTOR");
    let established = ledger.timestamp();

    // Upload the Wasm to be deployed from the deployer contract.
    // This can also be called from within a contract if needed.
    let wasm_hash = env.deployer().upload_contract_wasm(contract::WASM);

    // Deploy contract using deployer, and include an init function to call.
    let salt = BytesN::from_array(&env, &[0; 32]);
    let constructor_args: Vec<Val> = (admin.clone(), 5u32, name.clone(), symbol.clone(), node_id.clone(), descriptor.clone(), established.clone()).into_val(&env);
    env.mock_all_auths();
    let contract_id = deployer_client.deploy(&wasm_hash, &salt, &constructor_args);

    // An authorization from the admin is required.
    let expected_auth = AuthorizedInvocation {
        // Top-level authorized function is `deploy` with all the arguments.
        function: AuthorizedFunction::Contract((
            deployer_client.address,
            symbol_short!("deploy"),
            (wasm_hash.clone(), salt, constructor_args).into_val(&env),
        )),
        sub_invocations: vec![],
    };
    assert_eq!(env.auths(), vec![(admin, expected_auth)]);

    // Invoke contract to check that it is initialized.
    let token = contract::Client::new(&env, &contract_id);
    assert_eq!(token.name(), name);
    assert_eq!(token.symbol(), symbol);
    assert_eq!(token.node_id(), node_id);
    assert_eq!(token.descriptor(), descriptor);
    assert_eq!(token.established(), established);
}
