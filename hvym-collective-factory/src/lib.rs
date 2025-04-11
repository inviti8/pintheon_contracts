#![no_std]

/// This example demonstrates the 'factory' pattern for programmatically
/// deploying the contracts via `env.deployer()`.
use soroban_sdk::{contract, contractimpl, symbol_short, Address, BytesN, Env, Symbol, Val, Vec, IntoVal, String};

#[contract]
pub struct CollectiveFactory;

const ADMIN: Symbol = symbol_short!("admin");
const JOIN_FEE: u32 = 30;
const MINT_FEE: u32 = 3;
const OPUS_REWARD: u32 = 300;
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

    pub fn launch(env: Env) -> Address {
        let admin: Address = env.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();

        let wasm_hash = env.deployer().upload_contract_wasm(hvym_collective::WASM);
        let xlm: Address = Self::native_asset_contract_address(&env, MAINNET);
        let mut ran = [0u8; 32];
        env.prng().fill(&mut ran);
        let salt = BytesN::from_array(&env, &ran);
        let constructor_args: Vec<Val> = (admin.clone(), &JOIN_FEE,  &MINT_FEE, xlm.clone(), &OPUS_REWARD).into_val(&env);

        let contract_id = Self::deploy(env.clone(), wasm_hash.clone(), salt.clone(), constructor_args.clone());

        contract_id
    }

    /// Deploys the contract on behalf of the `CollectiveFactory` contract.
    ///
    /// This has to be authorized by the `CollectiveFactory`s administrator.    
    fn deploy(
        env: Env,
        wasm_hash: BytesN<32>,
        salt: BytesN<32>,
        constructor_args: Vec<Val>,
    ) -> Address {

        let deployed_address = env
            .deployer()
            .with_address(env.current_contract_address(), salt)
            .deploy_v2(wasm_hash, constructor_args);

        deployed_address
    }

    fn native_asset_contract_address(e: &Env, mainnet: bool) -> Address {
        let mut str_addr = String::from_str(&e, &"CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC");
        if mainnet {
            str_addr = String::from_str(&e, &"CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC");
        }
        
        let native_asset_address = Address::from_string(&str_addr);
        native_asset_address
    }
}

mod test;
