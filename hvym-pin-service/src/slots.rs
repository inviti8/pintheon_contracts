use soroban_sdk::{symbol_short, Env, token};

use crate::types::{DataKey, PinService, PinSlot, UnpinEvent, EPOCH_LENGTH, NUM_SLOTS};
use crate::storage::{storage_has, storage_remove};

pub fn current_epoch(env: &Env, start_ledger: u32) -> u32 {
    (env.ledger().sequence() - start_ledger) / EPOCH_LENGTH
}

pub fn slot_created_epoch(slot: &PinSlot, start_ledger: u32) -> u32 {
    (slot.created_at - start_ledger) / EPOCH_LENGTH
}

pub fn is_expired(slot: &PinSlot, env: &Env, config: &PinService) -> bool {
    current_epoch(env, config.start_ledger) - slot_created_epoch(slot, config.start_ledger)
        >= config.max_cycles
}

pub fn find_available_slot(env: &Env, config: &PinService) -> Option<u32> {
    for i in 0..NUM_SLOTS {
        let key = DataKey::Slot(i);
        if !storage_has(env, &key) {
            return Some(i);
        }
        // Check if slot is expired
        let slot: PinSlot = env.storage().persistent().get(&key).unwrap();
        if is_expired(&slot, env, config) {
            return Some(i);
        }
    }
    None
}

pub fn lazy_cleanup(env: &Env, slot_id: u32, config: &PinService, token_client: &token::Client) {
    let key = DataKey::Slot(slot_id);
    if !storage_has(env, &key) {
        return;
    }

    let slot: PinSlot = env.storage().persistent().get(&key).unwrap();
    if !is_expired(&slot, env, config) {
        return;
    }

    // Refund remaining escrow to publisher
    if slot.escrow_balance > 0 {
        token_client.transfer(
            &env.current_contract_address(),
            &slot.publisher,
            &(slot.escrow_balance as i128),
        );
    }

    let cid_hash = slot.cid_hash.clone();

    // Delete slot entry
    storage_remove(env, &key);

    // Emit UNPIN event
    let event = UnpinEvent {
        slot_id,
        cid_hash,
    };
    env.events()
        .publish((symbol_short!("UNPIN"), symbol_short!("request")), event);
}

pub fn check_duplicate_cid(env: &Env, cid_hash: &soroban_sdk::BytesN<32>, config: &PinService) -> bool {
    for i in 0..NUM_SLOTS {
        let key = DataKey::Slot(i);
        if storage_has(env, &key) {
            let slot: PinSlot = env.storage().persistent().get(&key).unwrap();
            if !is_expired(&slot, env, config) && slot.cid_hash == *cid_hash {
                return true;
            }
        }
    }
    false
}

pub fn delete_slot(env: &Env, slot_id: u32) {
    storage_remove(env, &DataKey::Slot(slot_id));
}
