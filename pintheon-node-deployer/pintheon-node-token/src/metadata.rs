use soroban_sdk::{Env, String};
use hvym_node_token::{nodemetadata::NodeTokenMetadata, TokenUtils};

pub trait NodeTokenInterface {
    fn node_id(env: Env) -> String;
    fn descriptor(env: Env) -> String;
    fn established(env: Env) -> u64;
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

pub fn read_node_id(e: &Env) -> String {
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().node_id
}

pub fn read_descriptor(e: &Env) -> String {
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().descriptor
}

pub fn read_established(e: &Env) -> u64{
    let util = TokenUtils::new(e);
    util.metadata().get_metadata().established
}

pub fn write_metadata(e: &Env, metadata: NodeTokenMetadata) {
    let util = TokenUtils::new(e);
    util.metadata().set_metadata(&metadata);
}
