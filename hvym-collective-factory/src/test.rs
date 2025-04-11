#![cfg(test)]
extern crate alloc;
extern crate std;

use crate::{CollectiveFactory, CollectiveFactoryClient};
use alloc::vec;
use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, AuthorizedFunction, AuthorizedInvocation},
    Address, Env, IntoVal, Symbol,
};

// The contract that will be deployed by the deployer contract.
mod contract {
    soroban_sdk::contractimport!(
        file =
            "../hvym-collective/target/wasm32-unknown-unknown/release/hvym_collective.optimized.wasm"
    );
}

#[test]
fn test() {
    let env = Env::default();
    let admin = Address::generate(&env);
    let deployer_client = CollectiveFactoryClient::new(&env, &env.register(CollectiveFactory, (&admin,)));
    let symbol: Symbol = symbol_short!("HVYM");

    // Deploy contract using deployer, and include an init function to call.
    env.mock_all_auths();
    let contract_id = deployer_client.launch();

    // An authorization from the admin is required.
    let expected_auth = AuthorizedInvocation {
        // Top-level authorized function is `deploy` with all the arguments.
        function: AuthorizedFunction::Contract((
            deployer_client.address,
            symbol_short!("launch"),
            ().into_val(&env),
        )),
        sub_invocations: vec![],
    };
    assert_eq!(env.auths(), vec![(admin, expected_auth)]);

    // Invoke contract to check that it is initialized.
    let collective = contract::Client::new(&env, &contract_id);

    assert_eq!(collective.symbol(), symbol);


}
