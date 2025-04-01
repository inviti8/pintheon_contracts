use soroban_sdk::{contracttype, symbol_short, unwrap::UnwrapOptimized, Env, String, Symbol};

const METADATA_KEY: Symbol = symbol_short!("HVYMNODE");

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
#[contracttype]
pub struct NodeTokenMetadata {
    pub decimal: u32,
    pub name: String,
    pub symbol: String,
    pub node_id: String,
    pub descriptor: String,
    pub established: String,
}

pub struct NodeMetadata {
    env: Env,
}

impl NodeMetadata {
    pub fn new(env: &Env) -> NodeMetadata {
        NodeMetadata { env: env.clone() }
    }

    #[inline(always)]
    pub fn set_metadata(&self, metadata: &NodeTokenMetadata) {
        self.env.storage().instance().set(&METADATA_KEY, metadata);
    }

    #[inline(always)]
    pub fn get_metadata(&self) -> NodeTokenMetadata {
        self.env
            .storage()
            .instance()
            .get(&METADATA_KEY)
            .unwrap_optimized()
    }
}
