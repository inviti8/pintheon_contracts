use soroban_sdk::{contracttype, symbol_short, unwrap::UnwrapOptimized, Env, String, Symbol};

const METADATA_KEY: Symbol = symbol_short!("HVYMFILE");

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
#[contracttype]
pub struct FileTokenMetadata {
    pub name: String,
    pub symbol: String,
    pub ipfs_hash: String,
    pub file_type: String,
    pub gateways: String,
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
        self.env.storage().persistent().set(&METADATA_KEY, metadata);
    }

    #[inline(always)]
    pub fn get_metadata(&self) -> FileTokenMetadata {
        self.env
            .storage()
            .persistent()
            .get(&METADATA_KEY)
            .unwrap_optimized()
    }
}
