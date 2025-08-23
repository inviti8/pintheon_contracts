use soroban_sdk::{Address, Env, log};

pub(crate) struct Events;

impl Events {
    pub fn new(_env: &Env) -> Self {
        Self
    }

    pub fn mint(&self, admin: Address, to: Address, amount: i128) {
        let env = admin.env();
        env.events().publish(("mint", admin, to), amount);
    }

    pub fn burn(&self, from: Address, amount: i128) {
        let env = from.env();
        env.events().publish(("burn", from), amount);
    }

    pub fn transfer(&self, from: Address, to: Address, amount: i128) {
        let env = from.env();
        env.events().publish(("transfer", from, to), amount);
    }

    pub fn approve(&self, from: Address, spender: Address, amount: i128, expiration_ledger: u32) {
        let env = from.env();
        env.events().publish(("approve", from, spender), (amount, expiration_ledger));
    }

    pub fn set_admin(&self, admin: Address, new_admin: Address) {
        let env = admin.env();
        env.events().publish(("set_admin", admin), new_admin);
    }
}
