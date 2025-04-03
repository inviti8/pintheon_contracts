#![cfg(test)]

use super::*;
use soroban_sdk::{ Env,String};

#[test]
fn test_member_creation() {
    let env = Env::default();
    env.mock_all_auths();
    let contract_id = env.register_contract(None, CollectiveContract);
    let client = CollectiveContractClient::new(&env, &contract_id);

    let str = String::from_str(&env, "GA7KOUZLPX7T45WLNYY6KFZZGJYMNI4H5J5TN3HHSVGL5BFQ4YCTQ4QR");
    let admin_add = Address::from_string(&str);

    let pstr = String::from_str(&env, "GCIWZIHX75NU4PSIZAWPHMSBLXS4QEA5ECB2YRUV54AABDKBSMLEN4II");
    let person = Address::from_string(&pstr);



    let x = client.init(&admin_add, &3);

    let y = client.create_member(&person);

    // let z = client.join(&person, &10);

    // let a = client.members(&admin_add);
    // let _d = client.withdraw(&person, &5);

    // let b = client.member_paid(&person);

    // let c = client.close_member(&person, &admin_add);



    // assert!(x);
    // assert_eq!(y.address, person);
    // assert_eq!(z.balance, 20);
    // assert_eq!(a.get(0).unwrap().address, person);
    // assert_eq!(b, 15);
    // assert!(c);



}
