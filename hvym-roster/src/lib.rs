#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, symbol_short, Address, Env, IntoVal, 
    TryFromVal, Val, Vec, Error, Symbol, String, BytesN, token,
    token::StellarAssetClient
};

// Event types
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct JoinEvent {
    pub member: Address,
    pub name: String,
    pub canon: String,
    pub amount: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RemoveEvent {
    pub member: Address,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdminEvent {
    pub admin: Address,
}

const ID: Symbol = symbol_short!("ROSTER");
const ADMIN: Symbol = symbol_short!("admin");
const HEAVYMETA: Symbol = symbol_short!("HVYM");
const MAX_STRING_LENGTH: u32 = 100;

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Datakey {
    Member(Address),
    Roster,
    Admin,
    AdminList,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Member {
    pub address: Address,
    pub name: String,
    pub canon: String,
    pub paid: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Roster {
   pub symbol: Symbol,
   pub join_fee: u32,
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
pub struct RosterContract;

#[contractimpl]
impl RosterContract {
    
    pub fn __constructor(e: Env, admin: Address, join_fee: u32, token: Address) {
        // Initialize admin list with the initial admin
        let mut admin_list = Vec::new(&e);
        admin_list.push_back(admin.clone());
        
        // Set up the roster
        let roster = Roster {
            symbol: HEAVYMETA,
            join_fee,
            pay_token: token,
        };

        // Store all data
        e.storage().instance().set(&ADMIN, &admin);
        e.storage().persistent().set(&Datakey::Admin, &admin);
        e.storage().persistent().set(&Datakey::AdminList, &admin_list);
        e.storage().persistent().set(&Datakey::Roster, &roster);
    }

    pub fn fund_contract(e: Env, caller: Address, fund_amount: u32) -> i128 {

        caller.require_auth();

        let roster: Roster = storage_g(e.clone(), Kind::Permanent, Datakey::Roster).expect("cound not find roster");
        let client = token::Client::new(&e, &roster.pay_token);
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

    pub fn join(e: Env, caller: Address, name: String, canon: String) {
        caller.require_auth();

        // Validate input lengths
        if name.len() as u32 > MAX_STRING_LENGTH || canon.len() as u32 > MAX_STRING_LENGTH {
            panic!("name and canon must be {} characters or less", MAX_STRING_LENGTH);
        }

        // Get roster and check if member already exists
        let roster: Roster = storage_g(e.clone(), Kind::Permanent, Datakey::Roster).expect("could not find roster");
        
        if e.storage().persistent().has(&Datakey::Member(caller.clone())) {
            panic!("already part of roster");
        }

        // Transfer join fee
        let client = token::Client::new(&e, &roster.pay_token);
        let join_fee = roster.join_fee as i128;
        
        client.transfer(&caller, &e.current_contract_address(), &join_fee);

        // Create and store member
        let member = Member {
            address: caller.clone(),
            name: name.clone(),
            canon: canon.clone(),
            paid: roster.join_fee,
        };
        
        e.storage()
            .persistent()
            .set(&Datakey::Member(caller.clone()), &member);

        // Emit join event
        let event = JoinEvent {
            member: caller,
            name,
            canon,
            amount: roster.join_fee,
        };
        e.events().publish((symbol_short!("JOIN"), symbol_short!("member")), event);
    }

    pub fn withdraw(e:Env, caller: Address, recipient: Address)-> Result<bool, Error> {
        RosterContract::require_admin_auth(e.clone(), caller.clone());
        let roster: Roster = storage_g(e.clone(), Kind::Permanent, Datakey::Roster).expect("cound not find roster");
        let client = token::Client::new(&e, &roster.pay_token);
        let join_fee = roster.join_fee as i128;
        let totalfees = client.balance(&e.current_contract_address());

        if totalfees < join_fee {
            panic!("not enough collected to withdraw");
        }

        client.transfer(&e.current_contract_address(), &recipient, &totalfees);

        Ok(true)
    }

    pub fn symbol(e: Env) -> Symbol {
        let roster: Roster = storage_g(e.clone(), Kind::Permanent, Datakey::Roster).expect("cound not find roster");
        roster.symbol
    }

    pub fn join_fee(e: Env) -> i128 {
        let roster: Roster = storage_g(e.clone(), Kind::Permanent, Datakey::Roster).expect("cound not find roster");
        roster.join_fee as i128
    }

    pub fn member_paid(e: Env, caller: Address) -> u32 {
        caller.require_auth();
        e.storage().persistent().get(&Datakey::Member(caller)).unwrap_or(0)
    }

    pub fn is_member(e: Env, caller: Address) -> bool {
        let this_contract = e.current_contract_address();

        caller == this_contract || Self::is_admin(e.clone(), caller.clone()) || e.storage().persistent().has(&Datakey::Member(caller))
    }

    pub fn remove(e: Env, admin_caller: Address, member_to_remove: Address) -> bool {
        // Only allow admins to remove members
        if !Self::is_admin(e.clone(), admin_caller.clone()) {
            panic!("unauthorized: admin access required");
        }

        // If the member is an admin, use the admin removal function
        if Self::is_admin(e.clone(), member_to_remove.clone()) {
            return Self::remove_admin(e, admin_caller, member_to_remove);
        }

        // Handle regular member removal
        if !e.storage().persistent().has(&Datakey::Member(member_to_remove.clone())) {
            return false;
        }

        e.storage().persistent().remove(&Datakey::Member(member_to_remove.clone()));

        // Publish remove event
        e.events().publish((symbol_short!("REMOVE"), symbol_short!("member")), RemoveEvent {
            member: member_to_remove.clone(),
        });
        
        true
    }
    
    /// Update the canon for a member
    /// 
    /// # Arguments
    /// * `e` - The environment
    /// * `caller` - The address of the member updating their canon (must be the member themselves or an admin)
    /// * `member_address` - The address of the member whose canon is being updated
    /// * `new_canon` - The new canon string (max 100 characters)
    /// 
    /// # Returns
    /// * `bool` - True if the update was successful
    pub fn update_canon(e: Env, caller: Address, member_address: Address, new_canon: String) -> bool {
        // Input validation
        if new_canon.len() as u32 > MAX_STRING_LENGTH {
            panic!("canon must be {} characters or less", MAX_STRING_LENGTH);
        }
        
        // Only allow admins or the member themselves to update the canon
        let is_admin = Self::is_admin(e.clone(), caller.clone());
        let is_self = caller == member_address;
        
        if !is_admin && !is_self {
            panic!("unauthorized: only admins or the member themselves can update canon");
        }
        
        // Get the member data
        let mut member: Member = e.storage()
            .persistent()
            .get(&Datakey::Member(member_address.clone()))
            .unwrap_or_else(|| panic!("member not found: {:?}", member_address));
        
        // Update the canon
        member.canon = new_canon;
        
        // Save the updated member data
        e.storage()
            .persistent()
            .set(&Datakey::Member(member_address), &member);
        
        true
    }

    pub fn update_join_fee(e: Env, caller: Address, new_fee: u32) -> i128 {
        RosterContract::require_admin_auth(e.clone(), caller.clone());
        let  mut roster: Roster = storage_g(e.clone(), Kind::Permanent, Datakey::Roster).expect("cound find roster");
        roster.join_fee = new_fee;

        if !validate_negative_amount(new_fee as i128) {
            panic!("invalid amount, must be non-negative");
        }

        storage_p(e, roster, Kind::Permanent, Datakey::Roster);
        new_fee as i128
    }

    pub fn add_admin(e: Env, caller: Address, new_admin: Address) {
        RosterContract::require_admin_auth(e.clone(), caller.clone());
        
        let mut admin_list: Vec<Address> = e.storage().persistent().get(&Datakey::AdminList).unwrap();
        
        // Check if admin already exists
        if admin_list.contains(&new_admin) {
            panic!("admin already exists");
        }
        
        admin_list.push_back(new_admin.clone());
        e.storage().persistent().set(&Datakey::AdminList, &admin_list);
        
        // Emit admin added event
        let event = AdminEvent {
            admin: new_admin,
        };
        e.events().publish((symbol_short!("ADMIN_ADDED"), symbol_short!("admin")), event);
    }

    pub fn get_admin_list(e: Env) -> Vec<Address> {
        e.storage().persistent().get(&Datakey::AdminList).unwrap_or_else(|| Vec::new(&e))
    }
    
    pub fn is_admin(e: Env, address: Address) -> bool {
        let admin_list = RosterContract::get_admin_list(e);
        admin_list.contains(address)
    }
    
    pub fn remove_admin(e: Env, caller: Address, admin_to_remove: Address) -> bool {
        // Only allow admins to remove other admins
        if !Self::is_admin(e.clone(), caller.clone()) {
            panic!("unauthorized: admin access required");
        }
        
        let admin_list: Vec<Address> = e.storage().persistent().get(&Datakey::AdminList).unwrap();
        
        // Check if the admin to remove is the initial admin
        if admin_list.get(0).unwrap().clone() == admin_to_remove {
            panic!("cannot remove initial admin");
        }
        
        // Create a new admin list without the admin to remove
        let mut new_admin_list = Vec::new(&e);
        let mut admin_found = false;
        
        for admin in admin_list.iter() {
            if admin.clone() == admin_to_remove {
                admin_found = true;
            } else {
                new_admin_list.push_back(admin.clone());
            }
        }
        
        if !admin_found {
            panic!("admin not found");
        }
        
        e.storage().persistent().set(&Datakey::AdminList, &new_admin_list);
        
        // Emit admin removed event
        e.events().publish((symbol_short!("REMOVE"), symbol_short!("admin")), AdminEvent {
            admin: admin_to_remove.clone(),
        });
        
        true
    }

    fn require_admin_auth(e: Env, caller: Address) {
        if !Self::is_admin(e.clone(), caller.clone()) {
            panic!("unauthorized: admin access required");
        }
        caller.require_auth();
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

/// Validates that an amount is non-negative and within u32 range
/// 
/// # Arguments
/// * `amount` - The amount to validate
/// 
/// # Returns
/// * `bool` - True if the amount is valid (non-negative and within u32 range)
fn validate_negative_amount(amount: i128) -> bool {
    // Check if amount is negative
    if amount < 0 {
        return false;
    }
    
    // Check if amount is within u32 range
    if amount > u32::MAX as i128 {
        return false;
    }
    
    true
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
