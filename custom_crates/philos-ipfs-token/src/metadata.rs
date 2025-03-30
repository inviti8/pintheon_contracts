use soroban_sdk::{Env, String, Vec};
use hvym_file_token::{filemetadata::FileTokenMetadata, TokenUtils};

pub trait FileTokenInterface {
    fn ipfs_hash(env: Env) -> String;
    fn file_type(env: Env) -> String;
    fn published(env: Env) -> String;
    fn gateways(env: Env) -> Vec<String>;
    fn ipns_hash(env: Env) -> Option<String>;
}

pub fn read_decimal(e: &Env) -> u32 {
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().decimal
}

pub fn read_name(e: &Env) -> String {
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().name
}

pub fn read_symbol(e: &Env) -> String {
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().symbol
}

pub fn read_ipfs_hash(e: &Env) -> String {
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().ipfs_hash
}

pub fn read_file_type(e: &Env) -> String {
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().file_type
}

pub fn read_published(e: &Env) -> String {
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().published
}

pub fn read_gateways(e: &Env) -> Vec<String> {
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().gateways
}

pub fn read_ipns_hash(e: &Env) -> Option<String> {
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().ipns_hash
}

pub fn write_metadata(e: &Env, metadata: FileTokenMetadata) {
    let util = TokenUtils::new(e);
    util.metadata().set_metadata(&metadata);
}
