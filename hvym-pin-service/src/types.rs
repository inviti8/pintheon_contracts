use soroban_sdk::{
    contracttype, contracterror, symbol_short, Address, BytesN, Symbol, String, Vec,
};

// =============================================================================
// Constants
// =============================================================================

pub const NUM_SLOTS: u32 = 10;
pub const EPOCH_LENGTH: u32 = 12;
pub const DAY_IN_LEDGERS: u32 = 17_280;

// TTL constants
pub const INSTANCE_BUMP_AMOUNT: u32 = 7 * DAY_IN_LEDGERS;
pub const INSTANCE_LIFETIME_THRESHOLD: u32 = INSTANCE_BUMP_AMOUNT - DAY_IN_LEDGERS;
pub const PERSISTENT_BUMP_AMOUNT: u32 = 30 * DAY_IN_LEDGERS;
pub const PERSISTENT_LIFETIME_THRESHOLD: u32 = PERSISTENT_BUMP_AMOUNT - DAY_IN_LEDGERS;

// Symbol constants
pub const HVYMPIN: Symbol = symbol_short!("HVYMPIN");
pub const ADMIN_SYM: Symbol = symbol_short!("admin");

// =============================================================================
// Storage Keys
// =============================================================================

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DataKey {
    PinService,
    Admin,
    AdminList,
    Pinner(Address),
    PinnerCount,
    Slot(u32),
    Flagged(Address, Address),
    Flaggers(Address),
}

// =============================================================================
// Data Structs
// =============================================================================

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PinService {
    pub symbol: Symbol,
    pub pin_fee: u32,
    pub join_fee: u32,
    pub min_pin_qty: u32,
    pub min_offer_price: u32,
    pub pinner_stake: u32,
    pub pay_token: Address,
    pub max_cycles: u32,
    pub flag_threshold: u32,
    pub fees_collected: i128,
    pub start_ledger: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PinSlot {
    pub publisher: Address,
    pub cid_hash: BytesN<32>,
    pub offer_price: u32,
    pub pin_qty: u32,
    pub pins_remaining: u32,
    pub escrow_balance: u32,
    pub created_at: u32,
    pub claims: Vec<Address>,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Pinner {
    pub address: Address,
    pub node_id: String,
    pub multiaddr: String,
    pub min_price: u32,
    pub joined_at: u64,
    pub pins_completed: u32,
    pub flags: u32,
    pub staked: u32,
    pub active: bool,
}

// =============================================================================
// Error Enum
// =============================================================================

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum Error {
    // Authorization
    Unauthorized = 1,
    NotAdmin = 2,

    // Pinner errors
    AlreadyPinner = 10,
    NotPinner = 11,
    PinnerInactive = 12,

    // Slot errors
    NoSlotsAvailable = 20,
    SlotNotActive = 21,
    SlotExpired = 22,
    SlotNotExpired = 23,
    AlreadyClaimed = 24,
    SlotFilled = 25,
    NotSlotPublisher = 26,
    InvalidSlotId = 27,
    DuplicateCid = 28,
    AlreadyFlagged = 29,

    // Validation
    InsufficientPinQty = 40,
    PinQtyExceedsMax = 41,
    OfferPriceTooLow = 42,
    OfferOverflow = 43,
    InvalidCid = 44,
    InvalidAmount = 45,
    InvalidString = 46,

    // Payment
    InsufficientFunds = 50,
    TransferFailed = 51,

    // Admin
    CannotRemoveInitialAdmin = 60,
}

// =============================================================================
// Event Structs
// =============================================================================

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PinEvent {
    pub slot_id: u32,
    pub cid: String,
    pub filename: String,
    pub gateway: String,
    pub offer_price: u32,
    pub pin_qty: u32,
    pub publisher: Address,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnpinEvent {
    pub slot_id: u32,
    pub cid_hash: BytesN<32>,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PinnedEvent {
    pub slot_id: u32,
    pub cid_hash: BytesN<32>,
    pub pinner: Address,
    pub amount: u32,
    pub pins_remaining: u32,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct JoinPinnerEvent {
    pub pinner: Address,
    pub node_id: String,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RemovePinnerEvent {
    pub pinner: Address,
}

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdminEvent {
    pub admin: Address,
}

// =============================================================================
// Storage Kind
// =============================================================================

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Kind {
    Instance,
    Permanent,
    Temporary,
}
