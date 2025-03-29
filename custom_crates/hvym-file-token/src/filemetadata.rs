use soroban_sdk::{contracttype, symbol_short, unwrap::UnwrapOptimized, Env, String, Symbol, Vec};

const METADATA_KEY: Symbol = symbol_short!("HVYMFILE");

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
#[contracttype]
pub struct FileTokenMetadata {
    pub decimal: u32,
    pub name: String,
    pub symbol: String,
    pub ipfs_hash: String,
    pub file_type: String,
    pub published: String,
    pub gateways: Vec<String>,
    pub ipns_hash: Option<String>,
}

pub struct FileMetadata {
    env: Env,
}

impl FileMetadata {
    pub fn new(env: &Env) -> FileMetadata {
        FileMetadata { env: env.clone() }
    }

    #[inline(always)]
    pub fn set_metadata(&self, metadata: &FileTokenMetadata) {
        self.env.storage().instance().set(&METADATA_KEY, metadata);
    }

    #[inline(always)]
    pub fn get_metadata(&self) -> FileTokenMetadata {
        self.env
            .storage()
            .instance()
            .get(&METADATA_KEY)
            .unwrap_optimized()
    }
}
