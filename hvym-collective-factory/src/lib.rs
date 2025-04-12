#![no_std]

/// This example demonstrates the 'factory' pattern for programmatically
/// deploying the contracts via `env.deployer()`.
use soroban_sdk::{contract, contractimpl, symbol_short, Address, BytesN, Bytes, Env, Symbol, Val, Vec, IntoVal, String, FromVal};

#[contract]
pub struct CollectiveFactory;

const ADMIN: Symbol = symbol_short!("admin");
const JOIN_FEE: u32 = 3_u32;
const MINT_FEE: u32 = 3_u32;
const OPUS_REWARD: u32 = 3_u32;
const MAINNET: bool = false;

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
        let str_addr = String::from_str(&env, &"CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC");
        let staddr = Address::to_string(&admin);
        // let xlm: Address = Address::from_string(&str_addr);
        // let mut ran = [0u8; 32];
        // env.prng().fill(&mut ran);
        
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

    fn address_to_bytesN(env: &Env, address: Address) -> BytesN<32> {
        Self::string_to_bytesN(env, Address::to_string(&address))
    }
    
    fn string_to_bytesN(env: &Env, string: String) -> BytesN<32> {
        BytesN::from_val(env, &string.to_val())
    }

    fn native_asset_contract_address(e: &Env, mainnet: bool) -> Address {
        let mut str_addr = String::from_str(&e, &"CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC");
        if mainnet {
            str_addr = String::from_str(&e, &"CAS3J7GYLGXMF6TDJBBYYSE3HQ6BBSMLNUQ34T6TZMYMW2EVH34XOWMA");
        }
        
        let native_asset_address = Address::from_string(&str_addr);
        native_asset_address
    }
}

mod test;
