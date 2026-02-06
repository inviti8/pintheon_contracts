#![no_std]

use soroban_sdk::{
    contract, contractimpl, symbol_short, Address, Bytes, BytesN, Env, String, Symbol, Vec, token,
};

mod types;
mod storage;
mod admin;
mod pinner;
mod slots;

use types::{
    DataKey, Kind, PinEvent, PinService, PinSlot, PinnedEvent, Pinner, UnpinEvent,
    HVYMPIN, NUM_SLOTS,
};
use storage::{storage_g, storage_has};

#[cfg(test)]
mod test;
#[cfg(test)]
mod rent_tests;

#[contract]
pub struct PinServiceContract;

#[contractimpl]
impl PinServiceContract {
    // =========================================================================
    // Constructor
    // =========================================================================

    pub fn __constructor(
        e: Env,
        admin_addr: Address,
        pin_fee: u32,
        join_fee: u32,
        min_pin_qty: u32,
        min_offer_price: u32,
        pinner_stake: u32,
        pay_token: Address,
        max_cycles: u32,
        flag_threshold: u32,
    ) {
        if max_cycles == 0 {
            panic!("max_cycles must be > 0");
        }
        if min_pin_qty == 0 {
            panic!("min_pin_qty must be > 0");
        }

        let config = PinService {
            symbol: HVYMPIN,
            pin_fee,
            join_fee,
            min_pin_qty,
            min_offer_price,
            pinner_stake,
            pay_token,
            max_cycles,
            flag_threshold,
            fees_collected: 0,
            start_ledger: e.ledger().sequence(),
        };

        let mut admin_list = Vec::new(&e);
        admin_list.push_back(admin_addr.clone());

        e.storage()
            .persistent()
            .set(&DataKey::Admin, &admin_addr);
        e.storage()
            .persistent()
            .set(&DataKey::AdminList, &admin_list);
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);
        e.storage()
            .persistent()
            .set(&DataKey::PinnerCount, &0_u32);
    }

    // =========================================================================
    // Slot Operations
    // =========================================================================

    pub fn create_pin(
        e: Env,
        caller: Address,
        cid: String,
        filename: String,
        gateway: String,
        offer_price: u32,
        pin_qty: u32,
    ) -> u32 {
        caller.require_auth();

        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);

        // Validation
        if offer_price < config.min_offer_price {
            panic!("offer price too low");
        }
        if pin_qty < config.min_pin_qty {
            panic!("insufficient pin quantity");
        }
        if pin_qty > NUM_SLOTS {
            panic!("pin qty exceeds max");
        }

        // Overflow check
        let escrow = (offer_price as u64).checked_mul(pin_qty as u64);
        if escrow.is_none() || escrow.unwrap() > u32::MAX as u64 {
            panic!("offer overflow");
        }
        let escrow_amount = escrow.unwrap() as u32;

        // Hash CID
        let cid_bytes = cid_to_bytes(&e, &cid);
        let cid_hash: BytesN<32> = e.crypto().sha256(&cid_bytes).into();

        // Check duplicate CID
        if slots::check_duplicate_cid(&e, &cid_hash, &config) {
            panic!("duplicate cid");
        }

        // Find available slot
        let slot_id = match slots::find_available_slot(&e, &config) {
            Some(id) => id,
            None => panic!("no slots available"),
        };

        // Lazy cleanup if slot has expired entry
        if storage_has(&e, &DataKey::Slot(slot_id)) {
            slots::lazy_cleanup(&e, slot_id, &config, &token_client);
        }

        // Transfer escrow + pin_fee
        let total = escrow_amount as i128 + config.pin_fee as i128;
        token_client.transfer(&caller, &e.current_contract_address(), &total);

        // Track fees
        config.fees_collected += config.pin_fee as i128;

        // Create slot
        let slot = PinSlot {
            publisher: caller.clone(),
            cid_hash: cid_hash.clone(),
            offer_price,
            pin_qty,
            pins_remaining: pin_qty,
            escrow_balance: escrow_amount,
            created_at: e.ledger().sequence(),
            claims: Vec::new(&e),
        };

        e.storage()
            .persistent()
            .set(&DataKey::Slot(slot_id), &slot);

        // Save updated config
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);

        // Emit PIN event
        let event = PinEvent {
            slot_id,
            cid,
            filename,
            gateway,
            offer_price,
            pin_qty,
            publisher: caller,
        };
        e.events()
            .publish((symbol_short!("PIN"), symbol_short!("request")), event);

        slot_id
    }

    pub fn collect_pin(e: Env, caller: Address, slot_id: u32) -> u32 {
        caller.require_auth();

        let config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);

        // Validate slot exists
        if !storage_has(&e, &DataKey::Slot(slot_id)) {
            panic!("slot not active");
        }

        let mut slot: PinSlot = e
            .storage()
            .persistent()
            .get(&DataKey::Slot(slot_id))
            .unwrap();

        // Check not expired
        if slots::is_expired(&slot, &e, &config) {
            panic!("slot expired");
        }

        // Check caller is registered pinner
        if !storage_has(&e, &DataKey::Pinner(caller.clone())) {
            panic!("not pinner");
        }

        // Check pinner is active
        let mut pinner: Pinner = e
            .storage()
            .persistent()
            .get(&DataKey::Pinner(caller.clone()))
            .unwrap();
        if !pinner.active {
            panic!("pinner inactive");
        }

        // Check not already claimed
        if slot.claims.contains(&caller) {
            panic!("already claimed");
        }

        // Check pins remaining
        if slot.pins_remaining == 0 {
            panic!("slot filled");
        }

        // Transfer offer_price to pinner
        let amount = slot.offer_price;
        token_client.transfer(
            &e.current_contract_address(),
            &caller,
            &(amount as i128),
        );

        // Update slot
        slot.escrow_balance -= amount;
        slot.pins_remaining -= 1;
        slot.claims.push_back(caller.clone());

        // Update pinner stats
        pinner.pins_completed += 1;
        e.storage()
            .persistent()
            .set(&DataKey::Pinner(caller.clone()), &pinner);

        let cid_hash = slot.cid_hash.clone();
        let pins_remaining = slot.pins_remaining;

        // Emit PINNED event
        let pinned_event = PinnedEvent {
            slot_id,
            cid_hash: cid_hash.clone(),
            pinner: caller,
            amount,
            pins_remaining,
        };
        e.events()
            .publish((symbol_short!("PINNED"), symbol_short!("claim")), pinned_event);

        if pins_remaining == 0 {
            // Slot fully claimed - delete it
            slots::delete_slot(&e, slot_id);

            // Emit UNPIN event
            let unpin_event = UnpinEvent {
                slot_id,
                cid_hash,
            };
            e.events()
                .publish((symbol_short!("UNPIN"), symbol_short!("request")), unpin_event);
        } else {
            e.storage()
                .persistent()
                .set(&DataKey::Slot(slot_id), &slot);
        }

        amount
    }

    pub fn cancel_pin(e: Env, caller: Address, slot_id: u32) -> u32 {
        caller.require_auth();

        let config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);

        if !storage_has(&e, &DataKey::Slot(slot_id)) {
            panic!("slot not active");
        }

        let slot: PinSlot = e
            .storage()
            .persistent()
            .get(&DataKey::Slot(slot_id))
            .unwrap();

        if slot.publisher != caller {
            panic!("not slot publisher");
        }

        let refund = slot.escrow_balance;
        let cid_hash = slot.cid_hash.clone();

        // Refund remaining escrow (pin_fee NOT refunded)
        if refund > 0 {
            token_client.transfer(
                &e.current_contract_address(),
                &caller,
                &(refund as i128),
            );
        }

        // Delete slot
        slots::delete_slot(&e, slot_id);

        // Emit UNPIN event
        let event = UnpinEvent {
            slot_id,
            cid_hash,
        };
        e.events()
            .publish((symbol_short!("UNPIN"), symbol_short!("request")), event);

        refund
    }

    pub fn clear_expired_slot(e: Env, slot_id: u32) -> bool {
        let config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);

        if !storage_has(&e, &DataKey::Slot(slot_id)) {
            panic!("slot not active");
        }

        let slot: PinSlot = e
            .storage()
            .persistent()
            .get(&DataKey::Slot(slot_id))
            .unwrap();

        if !slots::is_expired(&slot, &e, &config) {
            panic!("slot not expired");
        }

        // Refund remaining escrow to publisher
        if slot.escrow_balance > 0 {
            token_client.transfer(
                &e.current_contract_address(),
                &slot.publisher,
                &(slot.escrow_balance as i128),
            );
        }

        let cid_hash = slot.cid_hash.clone();

        // Delete slot
        slots::delete_slot(&e, slot_id);

        // Emit UNPIN event
        let event = UnpinEvent {
            slot_id,
            cid_hash,
        };
        e.events()
            .publish((symbol_short!("UNPIN"), symbol_short!("request")), event);

        true
    }

    pub fn force_clear_slot(e: Env, caller: Address, slot_id: u32) -> u32 {
        admin::require_admin_auth(&e, &caller);

        let config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);

        if !storage_has(&e, &DataKey::Slot(slot_id)) {
            panic!("slot not active");
        }

        let slot: PinSlot = e
            .storage()
            .persistent()
            .get(&DataKey::Slot(slot_id))
            .unwrap();

        let refund = slot.escrow_balance;
        let cid_hash = slot.cid_hash.clone();

        // Refund remaining escrow
        if refund > 0 {
            token_client.transfer(
                &e.current_contract_address(),
                &slot.publisher,
                &(refund as i128),
            );
        }

        // Delete slot
        slots::delete_slot(&e, slot_id);

        // Emit UNPIN event
        let event = UnpinEvent {
            slot_id,
            cid_hash,
        };
        e.events()
            .publish((symbol_short!("UNPIN"), symbol_short!("request")), event);

        refund
    }

    // =========================================================================
    // View Methods
    // =========================================================================

    pub fn symbol(e: Env) -> Symbol {
        let config: PinService = storage_g(e, Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        config.symbol
    }

    pub fn pin_fee(e: Env) -> u32 {
        let config: PinService = storage_g(e, Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        config.pin_fee
    }

    pub fn join_fee(e: Env) -> u32 {
        let config: PinService = storage_g(e, Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        config.join_fee
    }

    pub fn min_pin_qty(e: Env) -> u32 {
        let config: PinService = storage_g(e, Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        config.min_pin_qty
    }

    pub fn min_offer_price(e: Env) -> u32 {
        let config: PinService = storage_g(e, Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        config.min_offer_price
    }

    pub fn max_cycles(e: Env) -> u32 {
        let config: PinService = storage_g(e, Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        config.max_cycles
    }

    pub fn flag_threshold(e: Env) -> u32 {
        let config: PinService = storage_g(e, Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        config.flag_threshold
    }

    pub fn pinner_stake_amount(e: Env) -> u32 {
        let config: PinService = storage_g(e, Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        config.pinner_stake
    }

    pub fn fees_collected(e: Env) -> i128 {
        let config: PinService = storage_g(e, Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        config.fees_collected
    }

    pub fn balance(e: Env) -> i128 {
        let config: PinService = storage_g(e.clone(), Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        let token_client = token::Client::new(&e, &config.pay_token);
        token_client.balance(&e.current_contract_address())
    }

    pub fn pay_token(e: Env) -> Address {
        let config: PinService = storage_g(e, Kind::Permanent, DataKey::PinService)
            .expect("could not find config");
        config.pay_token
    }

    pub fn get_slot(e: Env, slot_id: u32) -> PinSlot {
        e.storage()
            .persistent()
            .get(&DataKey::Slot(slot_id))
            .unwrap()
    }

    pub fn get_all_slots(e: Env) -> Vec<PinSlot> {
        let mut result = Vec::new(&e);
        for i in 0..NUM_SLOTS {
            let key = DataKey::Slot(i);
            if storage_has(&e, &key) {
                let slot: PinSlot = e.storage().persistent().get(&key).unwrap();
                result.push_back(slot);
            }
        }
        result
    }

    pub fn has_available_slots(e: Env) -> bool {
        let config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        slots::find_available_slot(&e, &config).is_some()
    }

    pub fn current_epoch(e: Env) -> u32 {
        let config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        slots::current_epoch(&e, config.start_ledger)
    }

    pub fn is_slot_expired(e: Env, slot_id: u32) -> bool {
        let config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();

        if !storage_has(&e, &DataKey::Slot(slot_id)) {
            panic!("slot not active");
        }

        let slot: PinSlot = e
            .storage()
            .persistent()
            .get(&DataKey::Slot(slot_id))
            .unwrap();
        slots::is_expired(&slot, &e, &config)
    }

    // =========================================================================
    // Admin Methods
    // =========================================================================

    pub fn add_admin(e: Env, caller: Address, new_admin: Address) -> bool {
        admin::add_admin(&e, &caller, &new_admin)
    }

    pub fn remove_admin(e: Env, caller: Address, admin_to_remove: Address) -> bool {
        admin::remove_admin(&e, &caller, &admin_to_remove)
    }

    pub fn is_admin(e: Env, address: Address) -> bool {
        admin::is_admin(&e, &address)
    }

    pub fn get_admin_list(e: Env) -> Vec<Address> {
        admin::get_admin_list(&e)
    }

    pub fn withdraw_fees(e: Env, caller: Address, recipient: Address) -> i128 {
        admin::require_admin_auth(&e, &caller);

        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);

        let amount = config.fees_collected;
        if amount <= 0 {
            panic!("no fees to withdraw");
        }

        token_client.transfer(
            &e.current_contract_address(),
            &recipient,
            &amount,
        );

        config.fees_collected = 0;
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);

        amount
    }

    pub fn update_pin_fee(e: Env, caller: Address, new_fee: u32) -> bool {
        admin::require_admin_auth(&e, &caller);
        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        config.pin_fee = new_fee;
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);
        true
    }

    pub fn update_join_fee(e: Env, caller: Address, new_fee: u32) -> bool {
        admin::require_admin_auth(&e, &caller);
        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        config.join_fee = new_fee;
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);
        true
    }

    pub fn update_min_pin_qty(e: Env, caller: Address, new_min: u32) -> bool {
        admin::require_admin_auth(&e, &caller);
        if new_min == 0 {
            panic!("min_pin_qty must be > 0");
        }
        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        config.min_pin_qty = new_min;
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);
        true
    }

    pub fn update_min_offer_price(e: Env, caller: Address, new_min: u32) -> bool {
        admin::require_admin_auth(&e, &caller);
        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        config.min_offer_price = new_min;
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);
        true
    }

    pub fn update_max_cycles(e: Env, caller: Address, new_max: u32) -> bool {
        admin::require_admin_auth(&e, &caller);
        if new_max == 0 {
            panic!("max_cycles must be > 0");
        }
        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        config.max_cycles = new_max;
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);
        true
    }

    pub fn update_flag_threshold(e: Env, caller: Address, new_threshold: u32) -> bool {
        admin::require_admin_auth(&e, &caller);
        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        config.flag_threshold = new_threshold;
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);
        true
    }

    pub fn update_pinner_stake(e: Env, caller: Address, new_stake: u32) -> bool {
        admin::require_admin_auth(&e, &caller);
        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        config.pinner_stake = new_stake;
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);
        true
    }

    pub fn fund_contract(e: Env, caller: Address, fund_amount: u32) -> i128 {
        caller.require_auth();

        let config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);
        let amount = fund_amount as i128;

        if amount == 0 {
            panic!("cannot fund with zero");
        }

        let balance = token_client.balance(&caller);
        if balance < amount {
            panic!("not enough to fund");
        }

        token_client.transfer(&caller, &e.current_contract_address(), &amount);
        amount
    }

    // =========================================================================
    // Pinner Delegation
    // =========================================================================

    pub fn join_as_pinner(
        e: Env,
        caller: Address,
        node_id: String,
        multiaddr: String,
        min_price: u32,
    ) -> Pinner {
        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);

        let result =
            pinner::join_as_pinner(&e, &caller, node_id, multiaddr, min_price, &mut config, &token_client);

        // Save updated config (fees_collected changed)
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);

        result
    }

    pub fn update_pinner(
        e: Env,
        caller: Address,
        node_id: Option<String>,
        multiaddr: Option<String>,
        min_price: Option<u32>,
        active: Option<bool>,
    ) -> Pinner {
        pinner::update_pinner(&e, &caller, node_id, multiaddr, min_price, active)
    }

    pub fn leave_as_pinner(e: Env, caller: Address) -> u32 {
        let config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);
        pinner::leave_as_pinner(&e, &caller, &config, &token_client)
    }

    pub fn remove_pinner(e: Env, admin_addr: Address, pinner_addr: Address) -> bool {
        let config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);
        pinner::remove_pinner(&e, &admin_addr, &pinner_addr, &config, &token_client)
    }

    pub fn is_pinner(e: Env, address: Address) -> bool {
        storage_has(&e, &DataKey::Pinner(address))
    }

    pub fn get_pinner(e: Env, address: Address) -> Option<Pinner> {
        e.storage()
            .persistent()
            .get(&DataKey::Pinner(address))
    }

    pub fn get_pinner_count(e: Env) -> u32 {
        e.storage()
            .persistent()
            .get(&DataKey::PinnerCount)
            .unwrap_or(0)
    }

    pub fn flag_pinner(e: Env, caller: Address, pinner_addr: Address) -> u32 {
        let mut config: PinService = e
            .storage()
            .persistent()
            .get(&DataKey::PinService)
            .unwrap();
        let token_client = token::Client::new(&e, &config.pay_token);

        let result =
            pinner::flag_pinner(&e, &caller, &pinner_addr, &mut config, &token_client);

        // Save updated config (fees_collected may have changed from remainder)
        e.storage()
            .persistent()
            .set(&DataKey::PinService, &config);

        result
    }
}

// =============================================================================
// Helpers
// =============================================================================

fn cid_to_bytes(env: &Env, cid: &String) -> Bytes {
    let len = cid.len() as usize;
    let mut buf = [0u8; 256];
    let slice = &mut buf[0..len];
    cid.copy_into_slice(slice);
    let mut b = Bytes::new(env);
    b.copy_from_slice(0, slice);
    b
}
