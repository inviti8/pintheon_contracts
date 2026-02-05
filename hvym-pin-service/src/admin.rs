use soroban_sdk::{symbol_short, Address, Env, Vec};

use crate::types::{AdminEvent, DataKey};

pub fn require_admin_auth(e: &Env, caller: &Address) {
    if !is_admin(e, caller) {
        panic!("unauthorized: admin access required");
    }
    caller.require_auth();
}

pub fn is_admin(e: &Env, address: &Address) -> bool {
    let admin_list: Vec<Address> = e
        .storage()
        .persistent()
        .get(&DataKey::AdminList)
        .unwrap();
    admin_list.contains(address)
}

pub fn add_admin(e: &Env, caller: &Address, new_admin: &Address) -> bool {
    require_admin_auth(e, caller);

    let mut admin_list: Vec<Address> = e
        .storage()
        .persistent()
        .get(&DataKey::AdminList)
        .unwrap();

    for admin in admin_list.iter() {
        if admin == *new_admin {
            panic!("admin already exists");
        }
    }

    admin_list.push_back(new_admin.clone());
    e.storage()
        .persistent()
        .set(&DataKey::AdminList, &admin_list);

    let event = AdminEvent {
        admin: new_admin.clone(),
    };
    e.events()
        .publish((symbol_short!("ADD"), symbol_short!("admin")), event);

    true
}

pub fn remove_admin(e: &Env, caller: &Address, admin_to_remove: &Address) -> bool {
    require_admin_auth(e, caller);

    let admin_list: Vec<Address> = e
        .storage()
        .persistent()
        .get(&DataKey::AdminList)
        .unwrap();

    if admin_list.get(0).unwrap() == *admin_to_remove {
        panic!("cannot remove initial admin");
    }

    let mut new_admin_list = Vec::new(e);
    let mut admin_found = false;

    for admin in admin_list.iter() {
        if admin == *admin_to_remove {
            admin_found = true;
        } else {
            new_admin_list.push_back(admin);
        }
    }

    if !admin_found {
        panic!("admin not found");
    }

    e.storage()
        .persistent()
        .set(&DataKey::AdminList, &new_admin_list);

    let event = AdminEvent {
        admin: admin_to_remove.clone(),
    };
    e.events()
        .publish((symbol_short!("REMOVE"), symbol_short!("admin")), event);

    true
}

pub fn get_admin_list(e: &Env) -> Vec<Address> {
    e.storage()
        .persistent()
        .get(&DataKey::AdminList)
        .unwrap_or_else(|| Vec::new(e))
}
