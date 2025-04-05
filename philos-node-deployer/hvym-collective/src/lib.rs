#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, symbol_short, vec, Address, Env, IntoVal, 
    TryFromVal, Val, Vec, Error, Symbol, String, Bytes, BytesN, FromVal, token
};

const ADMIN: Symbol = symbol_short!("admin");

mod philos_node_token {
    soroban_sdk::contractimport!(
        file = "../philos-node-token/target/wasm32-unknown-unknown/release/philos_node_token.wasm"
    );
}

mod philos_ipfs_token {
    soroban_sdk::contractimport!(
        file = "../../philos-ipfs-deployer/philos-ipfs-token/target/wasm32-unknown-unknown/release/philos_ipfs_token.wasm"
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
   pub members: Vec<Member>,
   pub fee: u32,
   pub pay_token: Address,
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
    
    pub fn __constructor(e: Env, admin: Address, fee: u32, token: Address) {
        e.storage().instance().set(&ADMIN, &admin);

        let collective = Collective { members: vec![&e], fee: fee, pay_token: token };

        storage_p(e.clone(), admin, Kind::Permanent, Datakey::Admin);

        storage_p(e, collective, Kind::Permanent, Datakey::Collective);
    }

    pub fn join(e: Env, person: Address) -> Member {

        if Self::is_member(e.clone(), person.clone()) {
            panic!("already part of collective");
        }

        person.require_auth();
        let  mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound find collective");
        let client = token::Client::new(&e, &collective.pay_token);
        let balance = client.balance(&person);
        let fee = collective.fee as i128;

        if balance < fee {
            panic!("not enough to cover fee");
        }

        client.transfer(&person, &e.current_contract_address(), &fee);

        let member = Member {
            address: person.clone(),
            paid: collective.fee.clone(),
        };

        collective.members.push_back(member.clone());

        storage_p(
            e.clone(),
            member.clone(),
            Kind::Permanent,
            Datakey::Member(person),
        );
        storage_p(e, collective, Kind::Permanent, Datakey::Collective);

        member
    }

    pub fn withdraw(e:Env, some:Address)-> Result<bool, Error> {
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        let client = token::Client::new(&e, &collective.pay_token);
        let fee = collective.fee as i128;
        let totalfees = client.balance(&e.current_contract_address());

        if totalfees < fee {
            panic!("not enough collected to withdraw");
        }

        client.transfer(&e.current_contract_address(), &some, &totalfees);

        Ok(true)


    }

    pub fn members(e: Env) -> Vec<Member> {
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();
        let collective: Collective =
            storage_g(e, Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        collective.members
    }

    pub fn member_paid(e: Env, person: Address) -> u32 {
        person.require_auth();
        let member: Member = e
            .storage()
            .persistent()
            .get(&Datakey::Member(person))
            .unwrap();
        member.paid
    }

    pub fn is_member(e: Env, person: Address) -> bool {
        let collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");

        let exists = match collective.members.clone().iter().position(|x| x.address == person) {
            Some( _) => {
                true
            },
            None => false
              
        };  
    
    
        exists
    }

    pub fn remove(e:Env, person: Address)-> bool{
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();

        let mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        let mut accs:Vec<Member> =collective.members;

        let index =  accs.clone().iter().position(|x| x.address == person).expect("Member not found");


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

    pub fn deploy_node_token(e:Env, person: Address, name: String, descriptor: String)-> Address{

        person.require_auth();

        if Self::is_member(e.clone(), person.clone()) == false {
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
        let constructor_args: Vec<Val> = (person.clone(), 1u32, name.clone(), symbol.clone(), node_id.clone(), descriptor.clone(), established.clone()).into_val(&e);

        let contract_id = Self::deploy_contract(e.clone(), person.clone(), wasm_hash.clone(), salt.clone(), constructor_args.clone());

        contract_id
    }

    pub fn deploy_ipfs_token(e:Env, person: Address, name: String, ipfs_hash: String, file_type: String, gateways: String, _ipns_hash: Option<String>)-> Address{

        person.require_auth();

        if Self::is_member(e.clone(), person.clone()) == false {
            panic!("unauthorized");
        }

        let ledger = e.ledger();
        let symbol = String::from_val(&e, &"HVYMFILE");
        let published = ledger.timestamp();
        let wasm_hash = e.deployer().upload_contract_wasm(philos_ipfs_token::WASM);
        let mut ran = [0u8; 32];
        e.prng().fill(&mut ran);
        let salt = BytesN::from_array(&e, &ran);
        let constructor_args: Vec<Val> = (person.clone(), 8u32, name.clone(), symbol.clone(), ipfs_hash.clone(), file_type.clone(), published.clone(), gateways.clone(), _ipns_hash.clone()).into_val(&e);

        let contract_id = Self::deploy_contract(e.clone(), person.clone(), wasm_hash.clone(), salt.clone(), constructor_args.clone());

        contract_id
    }

    fn deploy_contract(
        e: Env,
        person: Address,
        wasm_hash: BytesN<32>,
        salt: BytesN<32>,
        constructor_args: Vec<Val>,
    ) -> Address {
        
        if Self::is_member(e.clone(), person.clone()) == false {
            panic!("unauthorized");
        }

        let deployed_address = e
            .deployer()
            .with_address(e.current_contract_address(), salt)
            .deploy_v2(wasm_hash, constructor_args);

        deployed_address
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
