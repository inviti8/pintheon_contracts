use soroban_sdk::{Env, IntoVal, TryFromVal, Val};

use crate::types::{DataKey, Kind};

pub fn storage_g<T: IntoVal<Env, Val> + TryFromVal<Env, Val>>(
    env: Env,
    kind: Kind,
    key: DataKey,
) -> Option<T> {
    match kind {
        Kind::Instance => env.storage().instance().get(&key),
        Kind::Permanent => env.storage().persistent().get(&key),
        Kind::Temporary => env.storage().temporary().get(&key),
    }
}

pub fn storage_p<T: IntoVal<Env, Val>>(env: Env, value: T, kind: Kind, key: DataKey) -> bool {
    match kind {
        Kind::Instance => {
            env.storage().instance().set(&key, &value);
            true
        }
        Kind::Permanent => {
            env.storage().persistent().set(&key, &value);
            true
        }
        Kind::Temporary => {
            env.storage().temporary().set(&key, &value);
            true
        }
    }
}

pub fn storage_has(env: &Env, key: &DataKey) -> bool {
    env.storage().persistent().has(key)
}

pub fn storage_remove(env: &Env, key: &DataKey) {
    env.storage().persistent().remove(key);
}
