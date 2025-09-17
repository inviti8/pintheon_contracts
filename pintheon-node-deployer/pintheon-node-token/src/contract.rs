//! This is the main entry point for the Pintheon Node Token contract.
//! It implements the standard Soroban token interface with custom metadata.

use soroban_sdk::{contract, contractimpl, Address, Env, String as SorobanString};

// Import our token implementation
use crate::token::{Token, TokenClient};

#[contract]
pub struct Contract;

#[contractimpl]
impl Contract {
    // Delegate all token functionality to the Token implementation
    
    pub fn initialize(
        e: Env,
        admin: Address,
        decimal: u32,
        name: SorobanString,
        symbol: SorobanString,
        node_id: SorobanString,
        descriptor: SorobanString,
        established: u64,
    ) {
        Token::initialize(e, admin, decimal, name, symbol, node_id, descriptor, established);
    }
    
    pub fn mint(e: Env, to: Address, amount: i128) {
        Token::mint(e, to, amount);
    }
    
    pub fn set_admin(e: Env, new_admin: Address) {
        Token::set_admin(e, new_admin);
    }
    
    // Standard token methods
    pub fn allowance(e: Env, from: Address, spender: Address) -> i128 {
        Token::allowance(e, from, spender)
    }
    
    pub fn approve(e: Env, from: Address, spender: Address, amount: i128, expiration_ledger: u32) {
        Token::approve(e, from, spender, amount, expiration_ledger);
    }
    
    pub fn balance(e: Env, id: Address) -> i128 {
        Token::balance(e, id)
    }
    
    pub fn transfer(e: Env, from: Address, to: Address, amount: i128) {
        Token::transfer(e, from, to, amount);
    }
    
    pub fn transfer_from(e: Env, spender: Address, from: Address, to: Address, amount: i128) {
        Token::transfer_from(e, spender, from, to, amount);
    }
    
    pub fn burn(e: Env, from: Address, amount: i128) {
        Token::burn(e, from, amount);
    }
    
    pub fn burn_from(e: Env, spender: Address, from: Address, amount: i128) {
        Token::burn_from(e, spender, from, amount);
    }
    
    pub fn decimals(e: Env) -> u32 {
        Token::decimals(e)
    }
    
    pub fn name(e: Env) -> SorobanString {
        Token::name(e)
    }
    
    pub fn symbol(e: Env) -> SorobanString {
        Token::symbol(e)
    }
    
    // Node-specific methods
    pub fn node_id(e: Env) -> SorobanString {
        crate::metadata::read_node_id(&e)
    }
    
    pub fn descriptor(e: Env) -> SorobanString {
        crate::metadata::read_descriptor(&e)
    }
    
    pub fn established(e: Env) -> u64 {
        crate::metadata::read_established(&e)
    }
}

// Client implementation for easier testing
pub struct ContractClient<'a> {
    env: &'a Env,
    contract_id: Address,
}

impl<'a> ContractClient<'a> {
    pub fn new(env: &'a Env, contract_id: &Address) -> Self {
        Self {
            env,
            contract_id: contract_id.clone(),
        }
    }
    
    pub fn token(&self) -> TokenClient {
        TokenClient::new(self.env, &self.contract_id)
    }
    
    // Add any contract-specific client methods here
}
