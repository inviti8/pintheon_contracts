#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, vec, Address, Env, IntoVal, 
    TryFromVal, Val, Vec,
};

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
    pub paid: i128,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Collective {
   pub members: Vec<Member>,
   pub fee: i128,
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

pub trait CollectiveContractTrait {
    fn init(e: Env, admin: Address) -> bool;
    fn create_member(e: Env, person: Address, amount: i128) -> Member;
    fn members(env: Env, person: Address) -> Vec<Member>;
    fn member_paid(e: Env, person: Address) -> i128;
    fn close_member(e:Env, person: Address, admin: Address)-> bool;
    fn join(env:Env, person: Address, amount: i128)-> Member;
    fn withdraw(env:Env, person: Address, amount: i128)-> Member;
}

#[contractimpl]
impl CollectiveContractTrait for CollectiveContract {
    fn init(e: Env, admin: Address, fee: i128) -> bool {
        assert!(!e.storage().persistent().has(&Datakey::Admin));

        let collective = Collective { members: vec![&e], fee: &fee };

        storage_p(e.clone(), admin, Kind::Permanent, Datakey::Admin);

        storage_p(e, collective, Kind::Permanent, Datakey::Collective)
    }

    fn create_member(e: Env, person: Address) -> Member {
        person.require_auth();
        let member = Member {
            address: person.clone(),
            paid: 0,
        };

        let mut collective: Collective =
            storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound not find collective");
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


    fn join(e:Env, person: Address, fee: i128)-> Member{
        person.require_auth();

        let  mut collective: Collective = storage_g(e.clone(), Kind::Permanent, Datakey::Collective).expect("cound find collective");
        pay_fee_to_contract(&e, &person, &collective.fee);

        let mut members:Vec<Member> = collective.members;
        
        let index:usize = members.clone().iter().position(|x| x.address == person).expect("Coundnt get position");
        let mut member:Member = storage_g(e.clone(), Kind::Permanent, Datakey::Member(person.clone())).expect("Member Error");
        member.paid = fee;
         
        members.remove(index as u32);
        members.push_back(member.clone());

        collective.members = members;

        storage_p(e.clone(), collective, Kind::Permanent, Datakey::Collective);
        storage_p(e, member.clone(),Kind::Permanent, Datakey::Member(person));

        member


    }



    fn withdraw(e:Env, admin: Address, some:Addres)-> Result<bool, Error> {
        admin.require_auth();
        let admin_data: Address = env.clone().storage().instance().get(&DataKey::Admin).unwrap();
        let client = token::Client::new(&env, &admin_data);
        let totalfees: i128 = client.balance(&get_native_asset_address(&env));

        collect_fees_from_contract(&e, &some, &totalfees);

        Ok(true)


    }

    fn members(e: Env, person: Address) -> Vec<Member> {
        assert_eq!(get_admin(e.clone()), person);
        let collective: Collective =
            storage_g(e, Kind::Permanent, Datakey::Collective).expect("cound not find collective");
        collective.members
    }

    fn member_paid(e: Env, person: Address) -> i128 {
        person.require_auth();
        let member: Member = e
            .storage()
            .persistent()
            .get(&Datakey::Member(person))
            .unwrap();
        member.paid
    }


    fn close_member(e:Env, person: Address, admin: Address)-> bool{
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

fn get_admin(env: Env) -> Address {
    storage_g(env, Kind::Permanent, Datakey::Admin).unwrap()
}

fn get_native_asset_address(env: &Env) -> Address {
    let string_adr: String = String::from_str(
        &env,
        "CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC",
    );
    Address::from_string(&string_adr)
}

fn pay_fee_to_contract(env: &Env, person: &Address, price: i128) {
    let admin_data: Address = env.storage().instance().get(&DataKey::Admin).unwrap();
    let client = token::Client::new(env, &admin_data);
    client.transfer(person, &env.current_contract_address(), &price);
}

fn collect_fees_from_contract(env: &Env, to: &Address, amount: &i128) {
    let admin_data: Address = env.storage().instance().get(&DataKey::Admin).unwrap();
    let client = token::Client::new(env, &admin_data);
    client.transfer(&env.current_contract_address(), to, amount);
}

mod test;
