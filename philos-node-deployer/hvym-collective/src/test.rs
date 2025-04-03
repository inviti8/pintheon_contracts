#![cfg(test)]
extern crate std;

use crate::{CollectiveContract, CollectiveContractClient};
use soroban_sdk::{
    testutils::{Address as _, AuthorizedFunction, AuthorizedInvocation},
    Address, Env,
};

#[test]
fn test_member_creation() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let client = CollectiveContractClient::new(&env, &env.register(CollectiveContract, (&admin,)));
    //let contract = &env.register(CollectiveContract, ((&admin_add),));
    //let client = CollectiveContractClient::new(&env, &contract);
    //let contract_id = env.register(None, CollectiveContract);
    //let client = CollectiveContractClient::new(&env, &contract_id);

    
    let person = Address::generate(&env);



    let y = client.join(&person);

    // let a = client.members(&admin_add);
    // let _d = client.withdraw(&person, &5);

    // let b = client.member_paid(&person);

    // let c = client.close_member(&person, &admin_add);



    //assert!(x);
    //assert_eq!(y.address, person);
    // assert_eq!(z.balance, 20);
    // assert_eq!(a.get(0).unwrap().address, person);
    // assert_eq!(b, 15);
    // assert!(c);



}
