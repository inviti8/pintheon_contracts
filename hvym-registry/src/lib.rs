#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, symbol_short, Address, Env, String, Vec,
};

mod test;

// ── Data types ──────────────────────────────────────────────────────────────

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Network {
    Testnet,
    Mainnet,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DataKey {
    Admin,                          // -> Address (initial admin)
    AdminList,                      // -> Vec<Address>
    ContractId(String, Network),    // (name, network) -> Address
    Registry(Network),              // network -> Vec<String> (registered names)
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ContractEntry {
    pub name: String,
    pub contract_id: Address,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RegistryEvent {
    pub name: String,
    pub network: Network,
    pub contract_id: Address,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RemoveEvent {
    pub name: String,
    pub network: Network,
}

// ── Contract ────────────────────────────────────────────────────────────────

#[contract]
pub struct RegistryContract;

#[contractimpl]
impl RegistryContract {
    // ── Constructor ─────────────────────────────────────────────────────

    pub fn __constructor(e: Env, admin: Address) {
        let mut admin_list = Vec::new(&e);
        admin_list.push_back(admin.clone());

        e.storage().persistent().set(&DataKey::Admin, &admin);
        e.storage()
            .persistent()
            .set(&DataKey::AdminList, &admin_list);
    }

    // ── Registry operations ─────────────────────────────────────────────

    /// Set or update a contract ID in the registry. Admin only.
    pub fn set_contract_id(
        e: Env,
        caller: Address,
        name: String,
        network: Network,
        contract_id: Address,
    ) {
        Self::require_admin_auth(e.clone(), caller.clone());

        let key = DataKey::ContractId(name.clone(), network.clone());
        let is_new = !e.storage().persistent().has(&key);
        e.storage().persistent().set(&key, &contract_id);

        // Track name in the registry list if new
        if is_new {
            let reg_key = DataKey::Registry(network.clone());
            let mut names: Vec<String> = e
                .storage()
                .persistent()
                .get(&reg_key)
                .unwrap_or_else(|| Vec::new(&e));
            names.push_back(name.clone());
            e.storage().persistent().set(&reg_key, &names);
        }

        e.events().publish(
            (symbol_short!("SET"), symbol_short!("contract")),
            RegistryEvent {
                name,
                network,
                contract_id,
            },
        );
    }

    /// Remove a contract ID from the registry. Admin only.
    pub fn remove_contract_id(
        e: Env,
        caller: Address,
        name: String,
        network: Network,
    ) {
        Self::require_admin_auth(e.clone(), caller.clone());

        let key = DataKey::ContractId(name.clone(), network.clone());
        if !e.storage().persistent().has(&key) {
            panic!("contract not registered");
        }
        e.storage().persistent().remove(&key);

        // Remove name from registry list
        let reg_key = DataKey::Registry(network.clone());
        if let Some(names) = e
            .storage()
            .persistent()
            .get::<_, Vec<String>>(&reg_key)
        {
            let mut updated = Vec::new(&e);
            for n in names.iter() {
                if n != name {
                    updated.push_back(n);
                }
            }
            e.storage().persistent().set(&reg_key, &updated);
        }

        e.events().publish(
            (symbol_short!("REMOVE"), symbol_short!("contract")),
            RemoveEvent { name, network },
        );
    }

    /// Get a contract ID by name and network. Panics if not found.
    pub fn get_contract_id(e: Env, name: String, network: Network) -> Address {
        let key = DataKey::ContractId(name, network);
        e.storage()
            .persistent()
            .get(&key)
            .expect("contract not registered")
    }

    /// Check if a contract ID is registered.
    pub fn has_contract_id(e: Env, name: String, network: Network) -> bool {
        let key = DataKey::ContractId(name, network);
        e.storage().persistent().has(&key)
    }

    /// Get all registered contracts for a network.
    pub fn get_all_contracts(e: Env, network: Network) -> Vec<ContractEntry> {
        let reg_key = DataKey::Registry(network.clone());
        let names: Vec<String> = e
            .storage()
            .persistent()
            .get(&reg_key)
            .unwrap_or_else(|| Vec::new(&e));

        let mut entries = Vec::new(&e);
        for name in names.iter() {
            let key = DataKey::ContractId(name.clone(), network.clone());
            if let Some(contract_id) = e.storage().persistent().get::<_, Address>(&key) {
                entries.push_back(ContractEntry {
                    name,
                    contract_id,
                });
            }
        }
        entries
    }

    // ── Admin management ────────────────────────────────────────────────

    pub fn add_admin(e: Env, caller: Address, new_admin: Address) {
        Self::require_admin_auth(e.clone(), caller.clone());

        let mut admin_list = Self::get_admin_list(e.clone());
        if admin_list.contains(&new_admin) {
            panic!("already an admin");
        }
        admin_list.push_back(new_admin.clone());
        e.storage()
            .persistent()
            .set(&DataKey::AdminList, &admin_list);

        e.events().publish(
            (symbol_short!("ADD"), symbol_short!("admin")),
            new_admin,
        );
    }

    pub fn remove_admin(e: Env, caller: Address, admin_to_remove: Address) {
        Self::require_admin_auth(e.clone(), caller.clone());

        let initial_admin: Address = e
            .storage()
            .persistent()
            .get(&DataKey::Admin)
            .expect("no initial admin");
        if admin_to_remove == initial_admin {
            panic!("cannot remove initial admin");
        }

        let admin_list = Self::get_admin_list(e.clone());
        let mut updated = Vec::new(&e);
        let mut found = false;
        for a in admin_list.iter() {
            if a == admin_to_remove {
                found = true;
            } else {
                updated.push_back(a);
            }
        }
        if !found {
            panic!("address is not an admin");
        }
        e.storage().persistent().set(&DataKey::AdminList, &updated);

        e.events().publish(
            (symbol_short!("REMOVE"), symbol_short!("admin")),
            admin_to_remove,
        );
    }

    pub fn is_admin(e: Env, address: Address) -> bool {
        let admin_list = Self::get_admin_list(e);
        admin_list.contains(&address)
    }

    pub fn get_admin_list(e: Env) -> Vec<Address> {
        e.storage()
            .persistent()
            .get(&DataKey::AdminList)
            .unwrap_or_else(|| Vec::new(&e))
    }

    // ── Internal ────────────────────────────────────────────────────────

    fn require_admin_auth(e: Env, caller: Address) {
        if !Self::is_admin(e, caller.clone()) {
            panic!("unauthorized: admin access required");
        }
        caller.require_auth();
    }
}
