#![cfg(test)]
extern crate std;

use crate::{CollectiveContract, CollectiveContractClient};
use crate::{token};
use soroban_sdk::{
    testutils::{Address as _, AuthorizedFunction, AuthorizedInvocation},
    Address, Env, String
};

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
fn test_member_creation() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let pay_token = create_token_contract(&env, &admin);
    let pay_token_client = pay_token.0;
    let pay_token_admin_client  = pay_token.1;
    let client = CollectiveContractClient::new(&env, &env.register(CollectiveContract, (&admin, 7_u32, pay_token_client.address)));

    let person = Address::generate(&env);

    pay_token_admin_client.mint(&person, &100);


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
