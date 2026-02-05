#![no_std]

use soroban_sdk::{
    contract, contractimpl, symbol_short, Address, Bytes, BytesN, Env, IntoVal, Symbol, Val, Vec,
};

#[contract]
pub struct PinServiceFactory;

const ADMIN: Symbol = symbol_short!("admin");
const INSTANCES: Symbol = symbol_short!("instancs");
const DPL_COUNT: Symbol = symbol_short!("dplcount");

mod hvym_pin_service {
    soroban_sdk::contractimport!(
        file = "../hvym-pin-service/target/wasm32v1-none/release/hvym_pin_service.optimized.wasm"
    );
}

#[contractimpl]
impl PinServiceFactory {
    pub fn __constructor(env: Env, admin: Address) {
        env.storage().instance().set(&ADMIN, &admin);
        let instances: Vec<Address> = Vec::new(&env);
        env.storage().persistent().set(&INSTANCES, &instances);
        env.storage().persistent().set(&DPL_COUNT, &0_u32);
    }

    pub fn deploy(
        env: Env,
        pin_fee: u32,
        join_fee: u32,
        min_pin_qty: u32,
        min_offer_price: u32,
        pinner_stake: u32,
        pay_token: Address,
        max_cycles: u32,
        flag_threshold: u32,
    ) -> Address {
        let admin: Address = env.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();

        let wasm_hash = env
            .deployer()
            .upload_contract_wasm(hvym_pin_service::WASM);

        let count: u32 = env.storage().persistent().get(&DPL_COUNT).unwrap_or(0);
        let salt = Self::generate_salt(&env, &admin, count);

        let constructor_args: Vec<Val> = (
            &admin,
            &pin_fee,
            &join_fee,
            &min_pin_qty,
            &min_offer_price,
            &pinner_stake,
            &pay_token,
            &max_cycles,
            &flag_threshold,
        )
            .into_val(&env);

        let deployed_address = env
            .deployer()
            .with_address(env.current_contract_address(), salt)
            .deploy_v2(wasm_hash, constructor_args);

        let mut instances: Vec<Address> = env
            .storage()
            .persistent()
            .get(&INSTANCES)
            .unwrap_or(Vec::new(&env));
        instances.push_back(deployed_address.clone());
        env.storage().persistent().set(&INSTANCES, &instances);
        env.storage().persistent().set(&DPL_COUNT, &(count + 1));

        deployed_address
    }

    pub fn get_instances(env: Env) -> Vec<Address> {
        env.storage()
            .persistent()
            .get(&INSTANCES)
            .unwrap_or(Vec::new(&env))
    }

    pub fn get_instance_count(env: Env) -> u32 {
        let instances: Vec<Address> = env
            .storage()
            .persistent()
            .get(&INSTANCES)
            .unwrap_or(Vec::new(&env));
        instances.len()
    }

    pub fn get_instance_at(env: Env, index: u32) -> Address {
        let instances: Vec<Address> = env
            .storage()
            .persistent()
            .get(&INSTANCES)
            .unwrap_or(Vec::new(&env));
        instances.get(index).unwrap()
    }

    pub fn get_admin(env: Env) -> Address {
        env.storage().instance().get(&ADMIN).unwrap()
    }

    pub fn route_to_available(env: Env, max_check: u32) -> Option<Address> {
        let instances: Vec<Address> = env
            .storage()
            .persistent()
            .get(&INSTANCES)
            .unwrap_or(Vec::new(&env));

        let len = instances.len();
        let check_count = if max_check < len { max_check } else { len };

        for i in 0..check_count {
            let addr = instances.get(i).unwrap();
            let client = hvym_pin_service::Client::new(&env, &addr);
            if client.has_available_slots() {
                return Some(addr);
            }
        }

        None
    }

    fn generate_salt(env: &Env, admin: &Address, count: u32) -> BytesN<32> {
        let staddr = Address::to_string(admin);
        let len = staddr.len() as usize;
        let mut bytes = [0u8; 100];
        let slice = &mut bytes[0..len];
        staddr.copy_into_slice(slice);
        let mut b = Bytes::new(env);
        b.copy_from_slice(0, slice);

        // Append counter bytes for uniqueness
        let count_bytes = count.to_be_bytes();
        b.extend_from_slice(&count_bytes);

        env.crypto().sha256(&b).to_bytes()
    }
}

mod test;
