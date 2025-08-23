use soroban_sdk::{Env, String as SorobanString, symbol_short};

pub fn read_decimal(e: &Env) -> u32 {
    e.storage().instance().get(&symbol_short!("decimal")).unwrap()
}

pub fn read_name(e: &Env) -> SorobanString {
    e.storage().instance().get(&symbol_short!("name")).unwrap()
}

pub fn read_symbol(e: &Env) -> SorobanString {
    e.storage().instance().get(&symbol_short!("symbol")).unwrap()
}

pub fn write_metadata(e: &Env, decimal: u32, name: SorobanString, symbol: SorobanString) {
    e.storage().instance().set(&symbol_short!("decimal"), &decimal);
    e.storage().instance().set(&symbol_short!("name"), &name);
    e.storage().instance().set(&symbol_short!("symbol"), &symbol);
}
