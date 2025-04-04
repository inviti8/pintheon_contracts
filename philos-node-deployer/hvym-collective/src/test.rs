#![cfg(test)]
extern crate std;

use crate::{CollectiveContract, CollectiveContractClient};
use crate::{token};
use soroban_sdk::{
    testutils::{Address as _},
    Address, Env
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
    let collective = CollectiveContractClient::new(&env, &env.register(CollectiveContract, (&admin, 7_u32, &pay_token_client.address)));

    let person1 = Address::generate(&env);
    let person2 = Address::generate(&env);
    let person3 = Address::generate(&env);

    pay_token_admin_client.mint(&person1, &100);
    pay_token_admin_client.mint(&person2, &100);
    pay_token_admin_client.mint(&person3, &50);


    let a = collective.join(&person1);
    collective.join(&person2);

    assert_eq!(pay_token_client.balance(&admin), 0);

    assert_eq!(a.address, person1);

    assert_eq!(collective.withdraw(&admin), true);

    assert_eq!(pay_token_client.balance(&admin), 14);

    let _c = collective.join(&person3);

    assert_eq!(collective.remove(&person3), true);
    

}

#[test]
#[should_panic(expected = "not enough to cover fee")]
fn test_member_join_fail() {
    let env = Env::default();
    env.mock_all_auths();
    let admin = Address::generate(&env);
    let pay_token = create_token_contract(&env, &admin);
    let pay_token_client = pay_token.0;
    let pay_token_admin_client  = pay_token.1;
    let collective = CollectiveContractClient::new(&env, &env.register(CollectiveContract, (&admin, 7_u32, &pay_token_client.address)));

    let person1 = Address::generate(&env);

    pay_token_admin_client.mint(&person1, &5);

    collective.join(&person1);


}
