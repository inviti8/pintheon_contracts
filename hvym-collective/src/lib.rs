#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, symbol_short, vec, Address, Env, IntoVal, 
    TryFromVal, Val, Vec, Error, Symbol, String, BytesN, FromVal, token
};

const ADMIN: Symbol = symbol_short!("admin");
const OPUS: Symbol = symbol_short!("OPUS");

mod philos_node_token {
    soroban_sdk::contractimport!(
        file = "../philos-node-deployer/philos-node-token/target/wasm32-unknown-unknown/release/philos_node_token.wasm"
    );
}

mod philos_ipfs_token {
    soroban_sdk::contractimport!(
        file = "../philos-ipfs-deployer/philos-ipfs-token/target/wasm32-unknown-unknown/release/philos_ipfs_token.wasm"
    );
}

mod opus_token {
    soroban_sdk::contractimport!(
        file = "../opus_token/target/wasm32-unknown-unknown/release/opus_token.wasm"
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
   pub members: Vec<Member>,
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

        let heavymeta: Symbol = Symbol::new(&e, "HEAVYMETA");
        
        e.storage().instance().set(&ADMIN, &admin);

        let collective = Collective { symbol: heavymeta, members: vec![&e], join_fee: join_fee, mint_fee: mint_fee, pay_token: token, opus_reward: reward };

        storage_p(e.clone(), admin, Kind::Permanent, Datakey::Admin);

        storage_p(e, collective, Kind::Permanent, Datakey::Collective);
    }

    pub fn join(e: Env, caller: Address) -> Member {

        if Self::is_member(e.clone(), caller.clone()) {
            panic!("already part of collective");
        }

        caller.require_auth();
        let  mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound find collective");
        let client = token::Client::new(&e, &collective.pay_token);
        let balance = client.balance(&caller);
        let join_fee = collective.join_fee as i128;

        if balance < join_fee {
            panic!("not enough to cover fee");
        }

        client.transfer(&caller, &e.current_contract_address(), &join_fee);

        let member = Member {
            address: caller.clone(),
            paid: collective.join_fee.clone(),
        };

        collective.members.push_back(member.clone());

        storage_p(
            e.clone(),
            member.clone(),
            Kind::Permanent,
            Datakey::Member(caller),
        );
        storage_p(e, collective, Kind::Permanent, Datakey::Collective);

        member
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

    pub fn address(e: Env) -> Address {
        e.current_contract_address()
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

    pub fn members(e: Env) -> Vec<Member> {
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let collective: Collective =
            storage_g(e, Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        collective.members
    }

    pub fn member_paid(e: Env, caller: Address) -> u32 {
        caller.require_auth();
        let member: Member = e
            .storage()
            .persistent()
            .get(&Datakey::Member(caller))
            .unwrap();
        member.paid
    }

    pub fn is_member(e: Env, caller: Address) -> bool {
        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        let this_contract: Address = e.current_contract_address();
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();

        let mut exists = match collective.members.clone().iter().position(|x| x.address == caller) {
            Some( _) => {
                true
            },
            None => false
              
        };

        if caller == admin || caller == this_contract {
            exists = true
        }
    
        exists
    }

    pub fn remove(e:Env, caller: Address)-> bool{
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();

        let mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        let mut accs:Vec<Member> =collective.members;

        let index =  accs.clone().iter().position(|x| x.address == caller).expect("Member not found");


      let done = match accs.remove(index as u32) {
        Some( _) => {
            collective.members = accs;
            storage_p(e, collective, Kind::Permanent, Datakey::Collective);
            true
        },
        None => false
          
      };  


        done
    }

    pub fn fund_contract(e: Env, caller: Address, fund_amount: u32) -> i128 {

        caller.require_auth();

        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        let client = token::Client::new(&e, &collective.pay_token);
        let balance = client.balance(&caller);
        let amount = fund_amount as i128;

        if balance < amount{
            panic!("not enough to fund");
        }

        client.transfer(&caller, &e.current_contract_address(), &amount);

        amount
    }

    pub fn deploy_node_token(e:Env, caller: Address, name: String, descriptor: String)-> Address{

        caller.require_auth();

        if Self::is_member(e.clone(), caller.clone()) == false {
            panic!("unauthorized");
        }

        let ledger = e.ledger();
        let symbol = String::from_val(&e, &"HVYMNODE");
        let b: [u8; 32] = e.prng().gen();
        let node_id = String::from_bytes(&e, &b);
        let established = ledger.timestamp();
        let wasm_hash = e.deployer().upload_contract_wasm(philos_node_token::WASM);
        let mut ran = [0u8; 32];
        e.prng().fill(&mut ran);
        let salt = BytesN::from_array(&e, &ran);
        let constructor_args: Vec<Val> = (caller.clone(), 1u32, name.clone(), symbol.clone(), node_id.clone(), descriptor.clone(), established.clone()).into_val(&e);

        let contract_id = Self::deploy_contract(e.clone(), caller.clone(), wasm_hash.clone(), salt.clone(), constructor_args.clone());
        let token = philos_node_token::Client::new(&e, &contract_id);
        token.mint(&caller, &1);

        contract_id
    }

    pub fn deploy_ipfs_token(e:Env, caller: Address, name: String, ipfs_hash: String, file_type: String, gateways: String, _ipns_hash: Option<String>)-> Address{

        caller.require_auth();

        if Self::is_member(e.clone(), caller.clone()) == false {
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
        let mut ran = [0u8; 32];
        e.prng().fill(&mut ran);
        let salt = BytesN::from_array(&e, &ran);
        let constructor_args: Vec<Val> = (caller.clone(), 8u32, name.clone(), symbol.clone(), ipfs_hash.clone(), file_type.clone(), published.clone(), gateways.clone(), _ipns_hash.clone()).into_val(&e);

        let contract_id = Self::deploy_contract(e.clone(), caller.clone(), wasm_hash.clone(), salt.clone(), constructor_args.clone());

        //mint opus to caller
        // let opus_address: Address = e.storage().instance().get(&OPUS).unwrap();
        // let opus_client = token::StellarAssetClient::new(&e, &opus_address);
        // let reward = collective.opus_reward as i128;

        // opus_client.mint(&caller, &reward);

        contract_id
    }

    pub fn launch_opus(e:Env, initial_alloc: u32)-> Address{

        if Self::is_launched(e.clone()) {
            panic!("opus already up");
        }

        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let wasm_hash = e.deployer().upload_contract_wasm(opus_token::WASM);
        let mut ran = [0u8; 32];
        e.prng().fill(&mut ran);
        let salt = BytesN::from_array(&e, &ran);
        let this_contract = &e.current_contract_address();
        let constructor_args: Vec<Val> = (this_contract.clone(),).into_val(&e);

        let contract_id = Self::deploy_contract(e.clone(), this_contract.clone(), wasm_hash.clone(), salt.clone(), constructor_args.clone());
        let allocation = initial_alloc as i128;
        e.storage().instance().set(&OPUS, &contract_id);
        let token = opus_token::Client::new(&e, &contract_id);

        token.mint(&admin, &allocation);

        contract_id

    }
    
    fn deploy_contract(
        e: Env,
        caller: Address,
        wasm_hash: BytesN<32>,
        salt: BytesN<32>,
        constructor_args: Vec<Val>,
    ) -> Address {
        
        if Self::is_member(e.clone(), caller.clone()) == false {
            panic!("unauthorized");
        }

        let deployed_address = e
            .deployer()
            .with_address(e.current_contract_address(), salt)
            .deploy_v2(wasm_hash, constructor_args);

        deployed_address
    }

    pub fn is_launched(e: Env) -> bool {
        let launched = match e.storage().instance().get::<Symbol, Address>(&OPUS) {
            Some( _) => {
                true
            },
            None => false
              
        };  
    
    
        launched
    }

    pub fn update_join_fee(e: Env, new_fee: u32) -> i128 {
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let  mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound find collective");
        collective.join_fee = new_fee;
        storage_p(e, collective, Kind::Permanent, Datakey::Collective);
        new_fee as i128
    }

    pub fn update_mint_fee(e: Env, new_fee: u32) -> i128 {
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let  mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound find collective");
        collective.join_fee = new_fee;
        storage_p(e, collective, Kind::Permanent, Datakey::Collective);
        new_fee as i128
    }

    pub fn update_opus_reward(e: Env, new_reward: u32) -> i128 {
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let  mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound find collective");
        collective.opus_reward = new_reward;
        storage_p(e, collective, Kind::Permanent, Datakey::Collective);
        new_reward as i128
    }
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
