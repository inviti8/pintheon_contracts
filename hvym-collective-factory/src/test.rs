#![cfg(test)]
extern crate alloc;
extern crate std;

use crate::{CollectiveFactory, CollectiveFactoryClient};
use alloc::vec;
use soroban_sdk::{
    symbol_short,
    testutils::{Address as _, AuthorizedFunction, AuthorizedInvocation},
    Address, Env, IntoVal, Symbol, String, BytesN,
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
    let num1: u32 = 30_u32;
    let num2: u32 = 30_u32;
    let num3: u32 = 30_u32;
    let str_addr = String::from_str(&env, &"CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC");
    let xlm: Address = Address::from_string(&str_addr);
    //let salt = BytesN::from_array(&env, &[0; 32]);

    // Deploy contract using deployer, and include an init function to call.
    env.mock_all_auths();
    let contract_id = deployer_client.deploy(&num1, &xlm, &num2, &num3);

    // An authorization from the admin is required.
    let expected_auth = AuthorizedInvocation {
        // Top-level authorized function is `deploy` with all the arguments.
        function: AuthorizedFunction::Contract((
            deployer_client.address,
            symbol_short!("deploy"),
            (num1, xlm, num2, num3).into_val(&env),
        )),
        sub_invocations: vec![],
    };
    assert_eq!(env.auths(), vec![(admin, expected_auth)]);

    // Invoke contract to check that it is initialized.
    let collective = contract::Client::new(&env, &contract_id);

    assert_eq!(collective.symbol(), symbol);


}
