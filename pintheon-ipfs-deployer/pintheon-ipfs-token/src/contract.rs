//! This contract implements an IPFS token with custom file metadata
//! that extends the standard Soroban token interface.

use soroban_sdk::{
    contract, contractevent, contractimpl, token::TokenInterface, Address, Env, MuxedAddress, String,
};
use crate::storage_types::{INSTANCE_BUMP_AMOUNT, INSTANCE_LIFETIME_THRESHOLD, DataKey, AllowanceDataKey};
use hvym_file_token::filemetadata::FileTokenMetadata;

use crate::admin::{read_administrator, write_administrator};
use crate::allowance::{read_allowance, spend_allowance, write_allowance};
use crate::storage_types::AllowanceValue;
use crate::balance::{read_balance, receive_balance, spend_balance};
use crate::metadata::{
    read_file_type, read_gateways, read_ipfs_hash, read_ipns_hash, read_name,
    read_symbol, write_metadata, FileTokenInterface,
};
use soroban_token_sdk::events;

fn check_nonnegative_amount(amount: i128) {
    if amount < 0 {
        panic!("negative amount is not allowed: {}", amount)
    }
}

#[contract]
pub struct Token;

// SetAdmin is not a standardized token event, so we just define a custom event
// for our token.
#[contractevent(data_format = "single-value")]
pub struct SetAdmin {
    #[topic]
    admin: Address,
    new_admin: Address,
}

#[contractevent]
pub struct Initialize {
    pub name: String,
    pub symbol: String,
}

#[contractimpl]
impl Token {
    /// Constructor that initializes the token contract with both standard and file metadata
    pub fn __constructor(
        e: Env,
        admin: Address,
        name: String,
        symbol: String,
        ipfs_hash: String,
        file_type: String,
        gateways: String,
        ipns_hash: Option<String>,
    ) {
        write_administrator(&e, &admin);
        
        // Create and write combined metadata
        let metadata = FileTokenMetadata {
            name: name.clone(),
            symbol: symbol.clone(),
            ipfs_hash,
            file_type,
            gateways,
            ipns_hash,
        };
        
        write_metadata(&e, metadata);
        
        // Emit initialization event
        Initialize {
            name: name.clone(),
            symbol: symbol.clone(),
        }
        .publish(&e);
    }
    
    /// Additional function to update file metadata after initialization
    pub fn set_file_metadata(
        e: Env,
        admin: Address,
        ipfs_hash: String,
        file_type: String,
        gateways: String,
        ipns_hash: Option<String>,
    ) {
        admin.require_auth();
        
        // Read existing metadata
        let name = read_name(&e);
        let symbol = read_symbol(&e);
        
        // Create and write updated metadata
        let metadata = FileTokenMetadata {
            name,
            symbol,
            ipfs_hash,
            file_type,
            gateways,
            ipns_hash,
        };
        
        write_metadata(&e, metadata);
    }

    pub fn mint(e: Env, to: Address, amount: i128) {
        check_nonnegative_amount(amount);
        let admin = read_administrator(&e);
        admin.require_auth();

        e.storage()
            .instance()
            .extend_ttl(INSTANCE_LIFETIME_THRESHOLD, INSTANCE_BUMP_AMOUNT);

        receive_balance(&e, to.clone(), amount);
        events::MintWithAmountOnly { to, amount }.publish(&e);
    }

    pub fn set_admin(e: Env, new_admin: Address) {
        let admin = read_administrator(&e);
        admin.require_auth();

        e.storage()
            .instance()
            .extend_ttl(INSTANCE_LIFETIME_THRESHOLD, INSTANCE_BUMP_AMOUNT);

        write_administrator(&e, &new_admin);
        SetAdmin { admin, new_admin }.publish(&e);
    }

    #[cfg(test)]
    pub fn get_allowance(e: Env, from: Address, spender: Address) -> Option<AllowanceValue> {
        let key = DataKey::Allowance(AllowanceDataKey { from, spender });
        let allowance = e.storage().temporary().get::<_, AllowanceValue>(&key);
        allowance
    }
}

#[contractimpl]
impl FileTokenInterface for Token {
    fn ipfs_hash(e: Env, _caller: Address) -> String {
        read_ipfs_hash(&e)
    }

    fn file_type(e: Env, _caller: Address) -> String {
        read_file_type(&e)
    }

    fn gateways(e: Env, _caller: Address) -> String {
        read_gateways(&e)
    }

    fn ipns_hash(e: Env, _caller: Address) -> Option<String> {
        read_ipns_hash(&e)
    }
}

#[contractimpl]
impl TokenInterface for Token {
    fn allowance(e: Env, from: Address, spender: Address) -> i128 {
        e.storage()
            .instance()
            .extend_ttl(INSTANCE_LIFETIME_THRESHOLD, INSTANCE_BUMP_AMOUNT);
        read_allowance(&e, from, spender).amount
    }

    fn approve(e: Env, from: Address, spender: Address, amount: i128, expiration_ledger: u32) {
        from.require_auth();
        check_nonnegative_amount(amount);

        e.storage()
            .instance()
            .extend_ttl(INSTANCE_LIFETIME_THRESHOLD, INSTANCE_BUMP_AMOUNT);

        write_allowance(&e, from.clone(), spender.clone(), amount, expiration_ledger);
        
        events::Approve {
            from,
            spender,
            amount,
            expiration_ledger,
        }.publish(&e);
    }

    fn balance(e: Env, id: Address) -> i128 {
        e.storage()
            .instance()
            .extend_ttl(INSTANCE_LIFETIME_THRESHOLD, INSTANCE_BUMP_AMOUNT);
        read_balance(&e, id)
    }

    fn transfer(e: Env, from: Address, to_muxed: MuxedAddress, amount: i128) {
        from.require_auth();
        check_nonnegative_amount(amount);

        e.storage()
            .instance()
            .extend_ttl(INSTANCE_LIFETIME_THRESHOLD, INSTANCE_BUMP_AMOUNT);

        spend_balance(&e, from.clone(), amount);
        let to: Address = to_muxed.address();
        receive_balance(&e, to.clone(), amount);
        
        events::Transfer {
            from,
            to,
            to_muxed_id: to_muxed.id(),
            amount,
        }.publish(&e);
    }

    fn transfer_from(e: Env, spender: Address, from: Address, to: Address, amount: i128) {
        spender.require_auth();

        check_nonnegative_amount(amount);

        e.storage()
            .instance()
            .extend_ttl(INSTANCE_LIFETIME_THRESHOLD, INSTANCE_BUMP_AMOUNT);

        spend_allowance(&e, from.clone(), spender, amount);
        spend_balance(&e, from.clone(), amount);
        receive_balance(&e, to.clone(), amount);
        
        events::Transfer {
            from,
            to,
            // `transfer_from` does not support muxed destination
            to_muxed_id: None,
            amount,
        }.publish(&e);
    }

    fn burn(e: Env, from: Address, amount: i128) {
        from.require_auth();

        check_nonnegative_amount(amount);

        e.storage()
            .instance()
            .extend_ttl(INSTANCE_LIFETIME_THRESHOLD, INSTANCE_BUMP_AMOUNT);

        spend_balance(&e, from.clone(), amount);
        events::Burn { from, amount }.publish(&e);
    }

    fn burn_from(e: Env, spender: Address, from: Address, amount: i128) {
        spender.require_auth();

        check_nonnegative_amount(amount);

        e.storage()
            .instance()
            .extend_ttl(INSTANCE_LIFETIME_THRESHOLD, INSTANCE_BUMP_AMOUNT);

        spend_allowance(&e, from.clone(), spender, amount);
        spend_balance(&e, from.clone(), amount);
        events::Burn { from, amount }.publish(&e);
    }

    fn decimals(_e: Env) -> u32 {
        0
    }

    fn name(e: Env) -> String {
        read_name(&e)
    }

    fn symbol(e: Env) -> String {
        read_symbol(&e)
    }
}
