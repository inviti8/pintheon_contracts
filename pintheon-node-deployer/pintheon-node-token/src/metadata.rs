use soroban_sdk::{
    contracttype, Env, String as SorobanString, Symbol, Val, Vec,
};
use soroban_token_sdk::metadata::TokenMetadata as StandardTokenMetadata;

/// Extended metadata for node tokens
#[derive(Clone, Debug, Eq, PartialEq)]
#[contracttype]
pub struct NodeTokenMetadata {
    /// Standard token metadata
    pub token: StandardTokenMetadata,
    /// Node identifier
    pub node_id: SorobanString,
    /// Node descriptor
    pub descriptor: SorobanString,
    /// Timestamp when the node was established
    pub established: u64,
}

/// Interface for node token metadata
pub trait NodeTokenInterface {
    /// Get the node ID
    fn node_id(env: Env) -> SorobanString;
    
    /// Get the node descriptor
    fn descriptor(env: Env) -> SorobanString;
    
    /// Get the establishment timestamp
    fn established(env: Env) -> u64;
}

/// Storage key for metadata
#[derive(Clone)]
#[contracttype]
enum DataKey {
    Metadata,
}
/// Write metadata to storage
pub fn write_metadata(e: &Env, metadata: NodeTokenMetadata) {
    e.storage().persistent().set(&DataKey::Metadata, &metadata);
}

/// Read metadata from storage
fn read_metadata(e: &Env) -> NodeTokenMetadata {
    e.storage()
        .persistent()
        .get(&DataKey::Metadata)
        .unwrap_or_else(|| panic!("Metadata not initialized"))
}

// Implement the standard token metadata getters
pub fn read_decimal(e: &Env) -> u32 {
    read_metadata(e).token.decimal
}

pub fn read_name(e: &Env) -> SorobanString {
    read_metadata(e).token.name
}

pub fn read_symbol(e: &Env) -> SorobanString {
    read_metadata(e).token.symbol
}

// Implement node-specific getters
pub fn read_node_id(e: &Env) -> SorobanString {
    read_metadata(e).node_id
}

pub fn read_descriptor(e: &Env) -> SorobanString {
    read_metadata(e).descriptor
}

pub fn read_established(e: &Env) -> u64 {
    read_metadata(e).established
}
