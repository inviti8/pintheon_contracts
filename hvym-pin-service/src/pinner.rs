use soroban_sdk::{symbol_short, Address, Env, String, Vec, token};

use crate::types::{
    DataKey, JoinPinnerEvent, PinService, Pinner, RemovePinnerEvent,
};
use crate::storage::{storage_has, storage_remove};
use crate::admin::require_admin_auth;

pub fn join_as_pinner(
    env: &Env,
    caller: &Address,
    node_id: String,
    multiaddr: String,
    min_price: u32,
    config: &mut PinService,
    token_client: &token::Client,
) -> Pinner {
    caller.require_auth();

    let key = DataKey::Pinner(caller.clone());
    if storage_has(env, &key) {
        panic!("already pinner");
    }

    // Transfer join_fee + pinner_stake
    let total = config.join_fee as i128 + config.pinner_stake as i128;
    token_client.transfer(caller, &env.current_contract_address(), &total);

    // Track join_fee in fees_collected
    config.fees_collected += config.join_fee as i128;

    let pinner = Pinner {
        address: caller.clone(),
        node_id: node_id.clone(),
        multiaddr,
        min_price,
        joined_at: env.ledger().timestamp(),
        pins_completed: 0,
        flags: 0,
        staked: config.pinner_stake,
        active: true,
    };

    env.storage().persistent().set(&key, &pinner);

    // Increment pinner count
    let count: u32 = env
        .storage()
        .persistent()
        .get(&DataKey::PinnerCount)
        .unwrap_or(0);
    env.storage()
        .persistent()
        .set(&DataKey::PinnerCount, &(count + 1));

    // Emit JOIN event
    let event = JoinPinnerEvent {
        pinner: caller.clone(),
        node_id,
    };
    env.events()
        .publish((symbol_short!("JOIN"), symbol_short!("pinner")), event);

    pinner
}

pub fn update_pinner(
    env: &Env,
    caller: &Address,
    node_id: Option<String>,
    multiaddr: Option<String>,
    min_price: Option<u32>,
    active: Option<bool>,
) -> Pinner {
    caller.require_auth();

    let key = DataKey::Pinner(caller.clone());
    if !storage_has(env, &key) {
        panic!("not pinner");
    }

    let mut pinner: Pinner = env.storage().persistent().get(&key).unwrap();

    if let Some(nid) = node_id {
        pinner.node_id = nid;
    }
    if let Some(ma) = multiaddr {
        pinner.multiaddr = ma;
    }
    if let Some(mp) = min_price {
        pinner.min_price = mp;
    }
    if let Some(a) = active {
        pinner.active = a;
    }

    env.storage().persistent().set(&key, &pinner);
    pinner
}

pub fn leave_as_pinner(
    env: &Env,
    caller: &Address,
    _config: &PinService,
    token_client: &token::Client,
) -> u32 {
    caller.require_auth();

    let key = DataKey::Pinner(caller.clone());
    if !storage_has(env, &key) {
        panic!("not pinner");
    }

    let pinner: Pinner = env.storage().persistent().get(&key).unwrap();
    let refund = pinner.staked;

    // Return stake if active (not deactivated by flags)
    if pinner.active && refund > 0 {
        token_client.transfer(
            &env.current_contract_address(),
            caller,
            &(refund as i128),
        );
    }

    // Remove pinner storage
    storage_remove(env, &key);

    // Decrement pinner count
    let count: u32 = env
        .storage()
        .persistent()
        .get(&DataKey::PinnerCount)
        .unwrap_or(1);
    if count > 0 {
        env.storage()
            .persistent()
            .set(&DataKey::PinnerCount, &(count - 1));
    }

    // Emit REMOVE event
    let event = RemovePinnerEvent {
        pinner: caller.clone(),
    };
    env.events()
        .publish((symbol_short!("REMOVE"), symbol_short!("pinner")), event);

    if pinner.active { refund } else { 0 }
}

pub fn remove_pinner(
    env: &Env,
    admin: &Address,
    pinner_addr: &Address,
    _config: &PinService,
    token_client: &token::Client,
) -> bool {
    require_admin_auth(env, admin);

    let key = DataKey::Pinner(pinner_addr.clone());
    if !storage_has(env, &key) {
        panic!("not pinner");
    }

    let pinner: Pinner = env.storage().persistent().get(&key).unwrap();

    // Admin removal returns stake (not punitive)
    if pinner.staked > 0 {
        token_client.transfer(
            &env.current_contract_address(),
            pinner_addr,
            &(pinner.staked as i128),
        );
    }

    // Remove pinner storage
    storage_remove(env, &key);

    // Decrement pinner count
    let count: u32 = env
        .storage()
        .persistent()
        .get(&DataKey::PinnerCount)
        .unwrap_or(1);
    if count > 0 {
        env.storage()
            .persistent()
            .set(&DataKey::PinnerCount, &(count - 1));
    }

    // Emit REMOVE event
    let event = RemovePinnerEvent {
        pinner: pinner_addr.clone(),
    };
    env.events()
        .publish((symbol_short!("REMOVE"), symbol_short!("pinner")), event);

    true
}

pub fn flag_pinner(
    env: &Env,
    caller: &Address,
    pinner_addr: &Address,
    config: &mut PinService,
    token_client: &token::Client,
) -> u32 {
    caller.require_auth();

    // Caller must be a registered pinner
    let caller_key = DataKey::Pinner(caller.clone());
    if !storage_has(env, &caller_key) {
        panic!("not pinner");
    }

    // Cannot flag yourself
    if caller == pinner_addr {
        panic!("cannot flag self");
    }

    // Target must be a registered pinner
    let pinner_key = DataKey::Pinner(pinner_addr.clone());
    if !storage_has(env, &pinner_key) {
        panic!("not pinner");
    }

    // Check duplicate flag
    let flag_key = DataKey::Flagged(caller.clone(), pinner_addr.clone());
    if storage_has(env, &flag_key) {
        panic!("already flagged");
    }

    // Store flag record
    env.storage().persistent().set(&flag_key, &true);

    // Add caller to flaggers vec
    let flaggers_key = DataKey::Flaggers(pinner_addr.clone());
    let mut flaggers: Vec<Address> = env
        .storage()
        .persistent()
        .get(&flaggers_key)
        .unwrap_or_else(|| Vec::new(env));
    flaggers.push_back(caller.clone());
    env.storage()
        .persistent()
        .set(&flaggers_key, &flaggers);

    // Increment flags on pinner
    let mut pinner: Pinner = env.storage().persistent().get(&pinner_key).unwrap();
    pinner.flags += 1;

    // Check threshold
    if pinner.flags >= config.flag_threshold {
        // Deactivate pinner
        pinner.active = false;

        // Distribute stake to flaggers
        let num_flaggers = flaggers.len();
        if pinner.staked > 0 && num_flaggers > 0 {
            let share = pinner.staked as i128 / num_flaggers as i128;
            let remainder = pinner.staked as i128 % num_flaggers as i128;

            for flagger in flaggers.iter() {
                if share > 0 {
                    token_client.transfer(
                        &env.current_contract_address(),
                        &flagger,
                        &share,
                    );
                }
            }

            // Remainder goes to fees_collected
            if remainder > 0 {
                config.fees_collected += remainder;
            }
        }

        pinner.staked = 0;

        // Cleanup flag storage
        for flagger in flaggers.iter() {
            let fkey = DataKey::Flagged(flagger.clone(), pinner_addr.clone());
            storage_remove(env, &fkey);
        }
        storage_remove(env, &flaggers_key);
    }

    let flags = pinner.flags;
    env.storage().persistent().set(&pinner_key, &pinner);
    flags
}
