#![no_std]

/// This example demonstrates the 'factory' pattern for programmatically
/// deploying the contracts via `env.deployer()`.
use soroban_sdk::{contract, contractimpl, symbol_short, Address, BytesN, Bytes, Env, Symbol, Val, Vec, IntoVal, String};

#[contract]
pub struct CollectiveFactory;

const ADMIN: Symbol = symbol_short!("admin");

mod hvym_collective {
    soroban_sdk::contractimport!(
        file = "../hvym-collective/target/wasm32-unknown-unknown/release/hvym_collective.optimized.wasm"
    );
}

#[contractimpl]
impl CollectiveFactory {
    /// Construct the deployer with a provided administrator.
    pub fn __constructor(env: Env, admin: Address) {
        env.storage().instance().set(&ADMIN, &admin);
    }

    pub fn deploy(env: Env, join_fee: u32, pay_token: Address, mint_fee: u32, reward: u32) -> Address {
        let admin: Address = env.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();

        let wasm_hash = env.deployer().upload_contract_wasm(hvym_collective::WASM);
        let staddr = Address::to_string(&admin);
        
        let salt = Self::hash_string(&env, &staddr);
        let constructor_args: Vec<Val> = (&admin, &join_fee,  &mint_fee, &pay_token, &reward).into_val(&env);

        let deployed_address = env
            .deployer()
            .with_address(env.current_contract_address(), salt)
            .deploy_v2(wasm_hash, constructor_args);

        deployed_address

    }

    fn hash_string(env: &Env, s: &String) -> BytesN<32> {
        let len = s.len() as usize;
        let mut bytes = [0u8; 100];
        let bytes = &mut bytes[0..len];
        s.copy_into_slice(bytes);
        let mut b = Bytes::new(env);
        b.copy_from_slice(0, bytes);
        env.crypto().sha256(&b).to_bytes()
    }

}

mod test;
