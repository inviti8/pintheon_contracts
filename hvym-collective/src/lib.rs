#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, symbol_short, Address, Env, IntoVal, 
    TryFromVal, Val, Vec, Error, Symbol, String, BytesN, FromVal, Bytes, token
};

const ADMIN: Symbol = symbol_short!("admin");
const HEAVYMETA: Symbol = symbol_short!("HVYM");
const OPUS: Symbol = symbol_short!("OPUS");

const JOIN: Symbol = symbol_short!("JOIN");
const REMOVE: Symbol = symbol_short!("REMOVE");

mod philos_node_token {
    soroban_sdk::contractimport!(
        file = "../philos-node-deployer/philos-node-token/target/wasm32-unknown-unknown/release/philos_node_token.optimized.wasm"
    );
}

mod philos_ipfs_token {
    soroban_sdk::contractimport!(
        file = "../philos-ipfs-deployer/philos-ipfs-token/target/wasm32-unknown-unknown/release/philos_ipfs_token.optimized.wasm"
    );
}

mod opus_token {
    soroban_sdk::contractimport!(
        file = "../opus_token/target/wasm32-unknown-unknown/release/opus_token.optimized.wasm"
    );
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Datakey {
    Member(Address),
    Collective,
    Admin,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Member {
    pub address: Address,
    pub paid: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Collective {
   pub symbol: Symbol,
   pub join_fee: u32,
   pub mint_fee: u32,
   pub pay_token: Address,
   pub opus_reward: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Kind {
    Instance,
    Permanent,
    Temporary,
}

#[contract]
pub struct CollectiveContract;

#[contractimpl]
impl CollectiveContract{
    
    pub fn __constructor(e: Env, admin: Address, join_fee: u32, mint_fee: u32, token: Address, reward: u32) {
        e.storage().instance().set(&ADMIN, &admin);

        let collective = Collective {
            symbol: HEAVYMETA,
            join_fee,
            mint_fee,
            pay_token: token,
            opus_reward: reward,
        };

        e.storage().persistent().set(&Datakey::Admin, &admin);
        e.storage().persistent().set(&Datakey::Collective, &collective);
    }

    pub fn fund_contract(e: Env, caller: Address, fund_amount: u32) -> i128 {

        caller.require_auth();

        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        let client = token::Client::new(&e, &collective.pay_token);
        let balance = client.balance(&caller);
        let amount = fund_amount as i128;

        if !validate_negative_amount(amount as i128) {
            panic!("invalid amount, must be non-negative");
        }

        if amount == 0 {
            panic!("cannot fund with zero");
        }

        if balance < amount{
            panic!("not enough to fund");
        }

        client.transfer(&caller, &e.current_contract_address(), &amount);

        amount
    }

    pub fn join(e: Env, caller: Address) {

        if e.storage().persistent().has(&Datakey::Member(caller.clone())) {
            panic!("already part of collective");
        }

        caller.require_auth();
        let collective: Collective = e.storage().persistent().get(&Datakey::Collective).unwrap();
        let client = token::Client::new(&e, &collective.pay_token);
        let balance = client.balance(&caller);
        let join_fee = collective.join_fee as i128;

        if balance < join_fee {
            panic!("not enough to cover fee");
        }

        client.transfer(&caller, &e.current_contract_address(), &join_fee);
        e.storage().persistent().set(&Datakey::Member(caller.clone()), &collective.join_fee);

        e.events().publish((JOIN, symbol_short!("member")), (caller, collective.join_fee));
    }

    pub fn withdraw(e:Env, some:Address)-> Result<bool, Error> {
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        let client = token::Client::new(&e, &collective.pay_token);
        let join_fee = collective.join_fee as i128;
        let totalfees = client.balance(&e.current_contract_address());

        if totalfees < join_fee {
            panic!("not enough collected to withdraw");
        }

        client.transfer(&e.current_contract_address(), &some, &totalfees);

        Ok(true)


    }

    pub fn symbol(e: Env) -> Symbol {
        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        collective.symbol
    }

    pub fn join_fee(e: Env) -> i128 {
        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        collective.join_fee as i128
    }

    pub fn mint_fee(e: Env) -> i128 {
        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        collective.mint_fee as i128
    }

    pub fn opus_reward(e: Env) -> i128 {
        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        collective.opus_reward as i128
    }

    pub fn member_paid(e: Env, caller: Address) -> u32 {
        caller.require_auth();
        e.storage().persistent().get(&Datakey::Member(caller)).unwrap_or(0)
    }

    pub fn opus_address(e: Env)-> Address {
        let address: Address = e.storage().instance().get::<Symbol, Address>(&OPUS).expect("network not initialized");
        address
    }

    pub fn is_member(e: Env, caller: Address) -> bool {
        let this_contract = e.current_contract_address();
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();

            caller == admin || caller == this_contract || e.storage().persistent().has(&Datakey::Member(caller))
    }

    pub fn remove(e:Env, caller: Address)-> bool{
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();

        if !e.storage().persistent().has(&Datakey::Member(caller.clone())) {
            return false;
        }

        e.storage().persistent().remove(&Datakey::Member(caller.clone()));
        e.events().publish((REMOVE, symbol_short!("member")), caller);
        true
    }

    pub fn deploy_node_token(e:Env, caller: Address, name: String, descriptor: String)-> Address{

        caller.require_auth();

        if !Self::is_member(e.clone(), caller.clone()) {
            panic!("unauthorized");
        }

        let ledger = e.ledger();
        let symbol = String::from_val(&e, &"HVYMNODE");
        let b: [u8; 32] = hash_string(&e, &name).into();
        let node_id = String::from_bytes(&e, &b);
        let established = ledger.timestamp();
        let wasm_hash = e.deployer().upload_contract_wasm(philos_node_token::WASM);
        let str_addr = Address::to_string(&caller);
        let salt = hash_string(&e, &str_addr);
        let constructor_args: Vec<Val> = (caller.clone(), 0u32, name.clone(), symbol.clone(), node_id.clone(), descriptor.clone(), established.clone()).into_val(&e);

        let contract_id = Self::deploy_contract(e.clone(), caller.clone(), wasm_hash.clone(), salt.clone(), constructor_args.clone());
        let token = philos_node_token::Client::new(&e, &contract_id);
        token.mint(&caller, &1);

        contract_id
    }

    pub fn deploy_ipfs_token(e:Env, caller: Address, name: String, ipfs_hash: String, file_type: String, gateways: String, _ipns_hash: Option<String>)-> Address{

        if Self::is_launched(e.clone()) == false {
            panic!("network not up");
        }

        caller.require_auth();

        if !Self::is_member(e.clone(), caller.clone()) {
            panic!("unauthorized");
        }
        
        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        let client = token::Client::new(&e, &collective.pay_token);
        let balance = client.balance(&caller);
        let mint_fee = collective.mint_fee as i128;

        if balance < mint_fee {
            panic!("not enough to cover fee");
        }

        client.transfer(&caller, &e.current_contract_address(), &mint_fee);

        let ledger = e.ledger();
        let symbol = String::from_val(&e, &"HVYMFILE");
        let published = ledger.timestamp();
        let wasm_hash = e.deployer().upload_contract_wasm(philos_ipfs_token::WASM);
        let salt = hash_string(&e, &ipfs_hash);
        let constructor_args: Vec<Val> = (caller.clone(), 0u32, name.clone(), symbol.clone(), ipfs_hash.clone(), file_type.clone(), published.clone(), gateways.clone(), _ipns_hash.clone()).into_val(&e);

        let contract_id = Self::deploy_contract(e.clone(), caller.clone(), wasm_hash.clone(), salt.clone(), constructor_args.clone());

        //mint opus reward to caller
        let opus_address: Address = e.storage().instance().get(&OPUS).unwrap();
        let opus_client = token::StellarAssetClient::new(&e, &opus_address);
        let reward = collective.opus_reward as i128;

        opus_client.mint(&caller, &reward);

        contract_id
    }

    pub fn launch_opus(e:Env, initial_alloc: u32)-> Address{

        if Self::is_launched(e.clone()) {
            panic!("opus already up");
        }

        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let wasm_hash = e.deployer().upload_contract_wasm(opus_token::WASM);
        let str_addr = Address::to_string(&admin);
        let salt = hash_string(&e, &str_addr);
        let this_contract = &e.current_contract_address();
        let constructor_args: Vec<Val> = (this_contract.clone(),).into_val(&e);

        let contract_id = Self::deploy_contract(e.clone(), this_contract.clone(), wasm_hash.clone(), salt.clone(), constructor_args.clone());
        let allocation = initial_alloc as i128;
        e.storage().instance().set(&OPUS, &contract_id);
        let token = opus_token::Client::new(&e, &contract_id);

        token.mint(&admin, &allocation);

        contract_id

    }

    pub fn is_launched(e: Env) -> bool {
        let launched = if e.storage().instance().get::<_, Address>(&OPUS).is_some() { true } else { false }; 

        launched
    }

    pub fn update_join_fee(e: Env, new_fee: u32) -> i128 {
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let  mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound find collective");
        collective.join_fee = new_fee;

        if !validate_negative_amount(new_fee as i128) {
            panic!("invalid amount, must be non-negative");
        }

        storage_p(e, collective, Kind::Permanent, Datakey::Collective);
        new_fee as i128
    }

    pub fn update_mint_fee(e: Env, new_fee: u32) -> i128 {
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let  mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound find collective");
        collective.join_fee = new_fee;

        if !validate_negative_amount(new_fee as i128) {
            panic!("invalid amount, must be non-negative");
        }

        storage_p(e, collective, Kind::Permanent, Datakey::Collective);
        new_fee as i128
    }

    pub fn update_opus_reward(e: Env, new_reward: u32) -> i128 {
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let  mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound find collective");
        collective.opus_reward = new_reward;

        if !validate_negative_amount(new_reward as i128) {
            panic!("invalid amount, must be non-negative");
        }

        storage_p(e, collective, Kind::Permanent, Datakey::Collective);
        new_reward as i128
    }

    fn deploy_contract(
        e: Env,
        caller: Address,
        wasm_hash: BytesN<32>,
        salt: BytesN<32>,
        constructor_args: Vec<Val>,
    ) -> Address {
        
        if !Self::is_member(e.clone(), caller.clone()) {
            panic!("unauthorized");
        }

        let deployed_address = e
            .deployer()
            .with_address(e.current_contract_address(), salt)
            .deploy_v2(wasm_hash, constructor_args);

        deployed_address
    }

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

fn validate_negative_amount(amount: i128)-> bool {
    let amt: u32 = amount as u32;
    amt ==0 || (amt & 0xffffffff) > 0
}

fn storage_g<T: IntoVal<Env, Val> + TryFromVal<Env, Val>>(
    env: Env,
    kind: Kind,
    key: Datakey,
) -> Option<T> {
    let done: Option<T> = match kind {
        Kind::Instance => env.storage().instance().get(&key),

        Kind::Permanent => env.storage().persistent().get(&key),

        Kind::Temporary => env.storage().temporary().get(&key),
    };

    done
}

fn storage_p<T: IntoVal<Env, Val>>(env: Env, value: T, kind: Kind, key: Datakey) -> bool {
    let done: bool = match kind {
        Kind::Instance => {
            env.storage().instance().set(&key, &value);
            true
        }

        Kind::Permanent => {
            env.storage().persistent().set(&key, &value);
            true
        }

        Kind::Temporary => {
            env.storage().temporary().set(&key, &value);
            true
        }
    };

    done
}



mod test;
