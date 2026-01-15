#![no_std]

// Core modules
mod admin;
mod allowance;
mod balance;
mod metadata;
mod storage_types;

// Re-export the token interface
pub use soroban_sdk::token::Interface as TokenInterface;

// Re-export the node token interface
pub use metadata::NodeTokenInterface;

// The main token contract
mod contract;
pub use contract::Token;

mod test;
mod rent_tests;
