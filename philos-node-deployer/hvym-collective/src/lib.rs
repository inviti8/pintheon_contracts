#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, symbol_short, vec, Address, Env, IntoVal, 
    TryFromVal, Val, Vec, Error, Symbol, token
};

const ADMIN: Symbol = symbol_short!("admin");


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


    pub fn remove(e:Env, person: Address)-> bool{
        let admin: Address = e.storage().instance().get(&ADMIN).unwrap();
        admin.require_auth();

        let mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not found a collective");
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
