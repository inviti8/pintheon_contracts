#![no_std]

mod admin;
mod allowance;
mod balance;
mod contract;
mod metadata;
mod storage_types;
mod test;

pub use crate::contract::{Token, TokenClient};
pub use soroban_sdk::Address;
