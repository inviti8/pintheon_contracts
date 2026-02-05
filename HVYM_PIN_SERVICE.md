# HVYM_PIN_SERVICE Contract Specification

## Overview

`hvym-pin-service` is a Soroban smart contract that facilitates decentralized IPFS pinning within the Heavymeta ecosystem. It enables Pintheon nodes (self-sovereign IPFS gateways) to request pins for their content and incentivizes a network of pinning daemons to provide redundant storage.

**Project Context:**
- Part of the Heavymeta ecosystem (https://heavymeta.art)
- Works alongside `/pintheon` and `/metavinci` repositories
- Follows patterns established in `hvym-collective` and `hvym-roster`

---

## Core Concepts

### The Problem
IPFS nodes are only effective for file distribution when multiple nodes pin a particular file. Content with insufficient pinning nodes becomes unreliable and may become unavailable when nodes go offline.

### The Solution
Create a decentralized marketplace where:
1. **Pintheon nodes** (content publishers) pay for pins
2. **Pinning daemons** (Kubo nodes + listener software) earn by pinning content
3. **hvym-pin-service** escrows payments and coordinates the marketplace

---

## Architecture: Modeless Slot Pool

### Design Philosophy

The contract uses a **fixed pool of 10 reusable slots**, each holding at most one active pin request. This design optimizes for:

- **Predictable rent**: Fixed storage footprint regardless of usage volume
- **No garbage accumulation**: Slots are recycled, never appended
- **Minimal on-chain data**: Events carry rich metadata (CID strings, gateway URLs); the contract stores only what's needed for payment logic
- **No modal restrictions**: Publishers and pinners can operate at any time without waiting for phase windows

### Slot Lifecycle

```
┌──────────────┐  create_pin  ┌──────────┐  all pins   ┌──────────────┐
│  NO ENTRY    │─────────────▶│  ACTIVE  │── claimed ──▶│ ENTRY DELETED│
│ (available)  │              │ (stored) │             │ (available)  │
└──────────────┘              └──────────┘             └──────────────┘
                                 │    │
                     cancel_pin  │    │  max_cycles
                                 │    │  exceeded
                                 ▼    ▼
                             ┌──────────────┐  lazy    ┌──────────────┐
                             │   EXPIRED    │─ refund ─▶│ ENTRY DELETED│
                             │   (stale)    │          │ (available)  │
                             └──────────────┘          └──────────────┘

Slot available = !storage.has(DataKey::Slot(i))
Expiration is computed, not stored:
  is_expired = (current_epoch - created_epoch) >= max_cycles
```

### Epoch-Based Expiration

Epochs divide time into fixed intervals measured in ledger sequences. Slot expiration is **computed** from the ledger, never explicitly stored or decremented:

```rust
const DAY_IN_LEDGERS: u32 = 17_280;  // ~5 seconds per ledger
const EPOCH_LENGTH: u32 = 12;        // ~1 minute per epoch (tuned via testnet)

fn current_epoch(env: &Env, start_ledger: u32) -> u32 {
    (env.ledger().sequence() - start_ledger) / EPOCH_LENGTH
}

fn slot_created_epoch(slot: &PinSlot, start_ledger: u32) -> u32 {
    (slot.created_at - start_ledger) / EPOCH_LENGTH
}

fn is_expired(slot: &PinSlot, env: &Env, config: &PinService) -> bool {
    current_epoch(env, config.start_ledger) - slot_created_epoch(slot, config.start_ledger) >= config.max_cycles
}
```

### Lazy Cleanup

Expired slots are not proactively cleaned. Instead, they are refunded and freed **lazily** when:
- A publisher calls `create_pin()` and the only available slot index has an expired entry
- A pinner calls `collect_pin()` on an expired slot (returns error)
- Anyone calls `clear_expired_slot(slot_id)` explicitly

The lazy refund transfers remaining escrow back to the original publisher and **deletes the slot's storage entry**, making the index available again.

---

## Data Structures

### Storage Keys

```rust
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DataKey {
    // Configuration
    PinService,                    // Stores PinService config struct
    Admin,                         // Initial admin address (protected from removal)
    AdminList,                     // Vec<Address> of all admins

    // Pinner Registry
    Pinner(Address),               // Stores Pinner struct for registered daemons
    PinnerCount,                   // u32 count of registered pinners

    // Slot Pool (fixed size, 0..NUM_SLOTS-1)
    Slot(u32),                     // Stores PinSlot struct (only exists when active)

    // CID Hunter Flags
    Flagged(Address, Address),     // (publisher, pinner) -> bool (prevents duplicate flags)
    Flaggers(Address),             // pinner -> Vec<Address> (who flagged, for bounty distribution)
}
```

### Configuration Struct

```rust
const NUM_SLOTS: u32 = 10;
const EPOCH_LENGTH: u32 = 12;     // Ledgers per epoch (~1 minute). Tuned via testnet simulation.

#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PinService {
    pub symbol: Symbol,            // Contract identifier (e.g., "HVYMPIN")
    pub pin_fee: u32,              // Platform fee in stroops per PIN request (non-refundable)
    pub join_fee: u32,             // Fee for pinners to register (anti-spam)
    pub min_pin_qty: u32,          // Minimum pins per request (default: 3)
    pub min_offer_price: u32,      // Minimum offer_price per pin (must exceed collect_pin tx cost)
    pub pinner_stake: u32,         // Required XLM stake for pinners (returned on voluntary leave, forfeited on flag threshold)
    pub pay_token: Address,        // Payment token (XLM native)
    pub max_cycles: u32,           // Epochs before a slot expires (global, same for all)
    pub flag_threshold: u32,       // Flags before pinner is auto-deactivated (e.g., 5)
    pub fees_collected: i128,      // Accumulated platform fees (tracked separately from escrow)
    pub start_ledger: u32,         // Ledger when contract was initialized
}
```

### Pin Slot Struct

The core on-chain data structure. Only stores fields needed for payment logic and claim verification. Rich metadata (CID string, gateway URL) is emitted in events only.

**Slots are not stored when empty.** A slot index with no storage entry is considered available. When a slot is filled (all pins claimed) or freed (cancelled/expired), its storage entry is deleted.

```rust
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PinSlot {
    pub publisher: Address,        // Who owns this request (for refunds)
    pub cid_hash: BytesN<32>,      // SHA256 hash of CID (for verification)
    pub offer_price: u32,          // Stroops per pin
    pub pin_qty: u32,              // Total pins requested
    pub pins_remaining: u32,       // How many left to claim
    pub escrow_balance: u32,       // Funds held for pinners
    pub created_at: u32,           // Ledger sequence when created (for expiration calc)
    pub claims: Vec<Address>,      // Who has claimed (bounded by pin_qty, max 10)
}
```

**Slot availability**: `!storage.has(DataKey::Slot(i))` means the slot is available.
**Storage footprint per active slot**: ~44 bytes base + (up to 10 x 32 bytes for claims) = ~364 bytes max
**Only active slots cost rent.** Empty slots consume zero storage.

### Pinner Registry Struct

```rust
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Pinner {
    pub address: Address,          // Stellar address of the pinner
    pub node_id: String,           // IPFS peer ID (e.g., "12D3KooW...")
    pub multiaddr: String,         // IPFS multiaddress for connectivity
    pub min_price: u32,            // Minimum price in stroops willing to accept
    pub joined_at: u64,            // Ledger timestamp when joined
    pub pins_completed: u32,       // Total pins completed (reputation)
    pub flags: u32,                // Accumulated dispute flags (CID Hunter)
    pub staked: u32,               // XLM stake held (forfeited to bounty hunters on deactivation)
    pub active: bool,              // Whether currently accepting pins (auto-deactivated at flag_threshold)
}
```

---

## Events

Events carry the rich metadata that is NOT stored in the contract. Off-chain systems (pinning daemons, UIs) rely on events for discovery.

### PIN Event
Emitted when a publisher creates a pin request. Contains the full CID and gateway URL that pinners need.

```rust
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PinEvent {
    pub slot_id: u32,              // Which slot this request occupies
    pub cid: String,               // Full IPFS CID (NOT stored on-chain)
    pub gateway: String,           // Public URL of Pintheon node (NOT stored on-chain)
    pub offer_price: u32,          // Amount in stroops per pin
    pub pin_qty: u32,              // Number of pins available
    pub publisher: Address,        // Who created the request
}

// Emission:
e.events().publish(
    (symbol_short!("PIN"), symbol_short!("request")),
    PinEvent { slot_id, cid, gateway, offer_price, pin_qty, publisher }
);
```

### UNPIN Event
Emitted when a slot is freed for any reason (cancelled, expired, or filled).

```rust
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnpinEvent {
    pub slot_id: u32,              // Which slot was freed
    pub cid_hash: BytesN<32>,      // Hash of CID (for correlation)
}

// Emission:
e.events().publish(
    (symbol_short!("UNPIN"), symbol_short!("request")),
    UnpinEvent { slot_id, cid_hash }
);
```

### PINNED Event
Emitted when a pinner collects payment. Recorded to the ledger as the public record of pin claims (not stored in contract beyond the inline `claims` vec).

```rust
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PinnedEvent {
    pub slot_id: u32,              // Which slot
    pub cid_hash: BytesN<32>,      // Hash of CID
    pub pinner: Address,           // Who claimed
    pub amount: u32,               // Amount paid in stroops
    pub pins_remaining: u32,       // How many left after this claim
}

// Emission:
e.events().publish(
    (symbol_short!("PINNED"), symbol_short!("claim")),
    PinnedEvent { slot_id, cid_hash, pinner, amount, pins_remaining }
);
```

### JOIN / REMOVE Events (pinner registry)

```rust
#[contracttype]
pub struct JoinPinnerEvent {
    pub pinner: Address,
    pub node_id: String,
}

#[contracttype]
pub struct RemovePinnerEvent {
    pub pinner: Address,
}

// Emission:
e.events().publish((symbol_short!("JOIN"), symbol_short!("pinner")), event);
e.events().publish((symbol_short!("REMOVE"), symbol_short!("pinner")), event);
```

---

## Contract Interface

### Constructor

```rust
/// Initialize the pin service contract
/// No slots are stored at init - they are created on demand
///
/// # Arguments
/// * `admin` - Initial admin address (protected from removal)
/// * `pin_fee` - Platform fee in stroops per PIN request (non-refundable)
/// * `join_fee` - Fee for pinners to register
/// * `min_pin_qty` - Minimum pins per request (recommend: 3)
/// * `min_offer_price` - Minimum offer_price per pin in stroops
/// * `pay_token` - Payment token address (XLM)
/// * `max_cycles` - Number of epochs before slot expires
/// * `flag_threshold` - Number of flags before pinner is auto-deactivated
/// * `pinner_stake` - Required XLM stake for pinners (refundable on voluntary leave)
fn __constructor(
    e: Env,
    admin: Address,
    pin_fee: u32,
    join_fee: u32,
    min_pin_qty: u32,
    min_offer_price: u32,
    pinner_stake: u32,
    pay_token: Address,
    max_cycles: u32,
    flag_threshold: u32,
);
```

### Pinner Registration Methods

```rust
/// Register as a pinning daemon
/// Requires payment of join_fee (non-refundable) + pinner_stake (refundable on voluntary leave)
fn join_as_pinner(
    e: Env,
    caller: Address,
    node_id: String,
    multiaddr: String,
    min_price: u32,
) -> Result<Pinner, Error>;

/// Update pinner configuration
fn update_pinner(
    e: Env,
    caller: Address,
    node_id: Option<String>,
    multiaddr: Option<String>,
    min_price: Option<u32>,
    active: Option<bool>,
) -> Result<Pinner, Error>;

/// Remove self from pinner registry
/// Returns pinner_stake to caller (only if not deactivated by flags)
fn leave_as_pinner(e: Env, caller: Address) -> Result<u32, Error>;  // Returns stake refund

/// Admin: Remove a pinner (e.g., for operational reasons)
/// Returns pinner_stake to the removed pinner (admin removal is not punitive)
fn remove_pinner(e: Env, admin: Address, pinner: Address) -> Result<bool, Error>;

/// Check if address is registered pinner
fn is_pinner(e: Env, address: Address) -> bool;

/// Get pinner details
fn get_pinner(e: Env, address: Address) -> Option<Pinner>;

/// Get count of registered pinners
fn get_pinner_count(e: Env) -> u32;
```

### Slot Operations

```rust
/// Create a new pin request in an available slot
/// Publisher pays (offer_price * pin_qty) + pin_fee
/// If the assigned slot is expired, lazily refunds previous occupant first
/// Emits PIN event with full CID and gateway URL
///
/// # Arguments
/// * `caller` - Publisher address (Pintheon node)
/// * `cid` - Full IPFS CID (emitted in event, hash stored on-chain)
/// * `gateway` - Public gateway URL (emitted in event only)
/// * `offer_price` - Price per pin in stroops (>= min_offer_price)
/// * `pin_qty` - Number of pins requested (>= min_pin_qty, <= 10)
///
/// Constraints:
/// - offer_price >= min_offer_price (must exceed pinner's collect_pin tx cost)
/// - offer_price * pin_qty must not overflow u32
/// - One unique CID per slot (rejects if CID already has an active slot)
/// - A publisher may occupy multiple slots with different CIDs
fn create_pin(
    e: Env,
    caller: Address,
    cid: String,
    gateway: String,
    offer_price: u32,
    pin_qty: u32,
) -> Result<u32, Error>;  // Returns slot_id

/// Collect payment for pinning a CID (pinner daemon calls this)
/// Must be a registered pinner
/// Caller must not have already claimed this slot
/// Slot must be active and not expired
/// Transfers offer_price from escrow to pinner
/// Emits PINNED event
/// If last pin claimed: frees slot, emits UNPIN
fn collect_pin(
    e: Env,
    caller: Address,
    slot_id: u32,
) -> Result<u32, Error>;  // Returns amount paid

/// Cancel a pin request (only the publisher who created it)
/// Refunds remaining escrow (pin_fee is NOT refunded)
/// Emits UNPIN event
fn cancel_pin(
    e: Env,
    caller: Address,
    slot_id: u32,
) -> Result<u32, Error>;  // Returns refund amount

/// Clear an expired slot (anyone can call)
/// Refunds remaining escrow to original publisher
/// Emits UNPIN event
fn clear_expired_slot(
    e: Env,
    slot_id: u32,
) -> Result<bool, Error>;

/// Get a slot's current state
fn get_slot(e: Env, slot_id: u32) -> PinSlot;

/// Get all slots (for UI discovery)
fn get_all_slots(e: Env) -> Vec<PinSlot>;

/// Check if contract has available slots
fn has_available_slots(e: Env) -> bool;

/// Get the current epoch number
fn current_epoch(e: Env) -> u32;

/// Check if a specific slot is expired
fn is_slot_expired(e: Env, slot_id: u32) -> bool;
```

### Admin Methods

```rust
/// Add an admin
fn add_admin(e: Env, caller: Address, new_admin: Address) -> Result<bool, Error>;

/// Remove an admin (cannot remove initial admin)
fn remove_admin(e: Env, caller: Address, admin_to_remove: Address) -> Result<bool, Error>;

/// Check if address is admin
fn is_admin(e: Env, address: Address) -> bool;

/// Get all admins
fn get_admin_list(e: Env) -> Vec<Address>;

/// Withdraw accumulated fees to recipient
/// Can only withdraw up to fees_collected (escrow funds are protected)
fn withdraw_fees(e: Env, caller: Address, recipient: Address) -> Result<i128, Error>;

/// Update platform pin fee
fn update_pin_fee(e: Env, caller: Address, new_fee: u32) -> Result<bool, Error>;

/// Update pinner join fee
fn update_join_fee(e: Env, caller: Address, new_fee: u32) -> Result<bool, Error>;

/// Update minimum pin quantity
fn update_min_pin_qty(e: Env, caller: Address, new_min: u32) -> Result<bool, Error>;

/// Update minimum offer price
fn update_min_offer_price(e: Env, caller: Address, new_min: u32) -> Result<bool, Error>;

/// Update max cycles (global expiration for all future requests)
fn update_max_cycles(e: Env, caller: Address, new_max: u32) -> Result<bool, Error>;

/// Force-clear a slot (admin override for stuck escrow)
/// Refunds remaining escrow to original publisher and frees the slot
/// Use when funds are stuck due to inactivity and slot has not expired naturally
fn force_clear_slot(e: Env, caller: Address, slot_id: u32) -> Result<u32, Error>;  // Returns refund amount

/// Fund contract (for operational purposes)
fn fund_contract(e: Env, caller: Address, amount: u32) -> Result<i128, Error>;
```

### View Methods

```rust
fn symbol(e: Env) -> Symbol;
fn pin_fee(e: Env) -> u32;
fn join_fee(e: Env) -> u32;
fn min_pin_qty(e: Env) -> u32;
fn min_offer_price(e: Env) -> u32;
fn max_cycles(e: Env) -> u32;
fn flag_threshold(e: Env) -> u32;
fn pinner_stake(e: Env) -> u32;   // Current stake requirement for new pinners
fn fees_collected(e: Env) -> i128; // Accumulated platform fees (safe to withdraw)
fn balance(e: Env) -> i128;       // Total contract XLM balance (fees + escrow)
fn pay_token(e: Env) -> Address;
```

---

## Payment Flow

### Creating a Pin Request

```
Publisher (Pintheon Node)
    |
    |-- 1. Calls create_pin(cid, gateway, offer_price=1000, pin_qty=5)
    |
    |-- 2. Contract validates:
    |       - offer_price >= min_offer_price
    |       - offer_price * pin_qty does not overflow u32
    |       - pin_qty >= min_pin_qty and <= 10
    |       - CID not already in an active slot
    |
    |-- 3. Contract finds first available slot (no storage entry, or expired)
    |       - If expired: lazily refund previous publisher, delete entry, then reuse
    |       - If no slots available: return Error::NoSlotsAvailable
    |
    |-- 4. Contract calculates total: (1000 * 5) + pin_fee = 5000 + fee
    |
    |-- 5. XLM transferred from publisher to contract
    |       config.fees_collected += pin_fee (tracked separately)
    |
    |-- 6. Slot storage entry created:
    |       publisher, cid_hash=sha256(cid),
    |       offer_price=1000, pin_qty=5, pins_remaining=5,
    |       escrow_balance=5000, created_at=current_ledger, claims=[]
    |
    |-- 7. PIN event emitted with full CID string and gateway URL
    |
    v
Contract holds: 5000 (escrow in slot) + fee (in fees_collected)
```

### Collecting a Pin

```
Pinner Daemon
    |
    |-- 1. Listens for PIN events, filters by offer_price >= min_price
    |
    |-- 2. Pins content to local IPFS node from gateway URL
    |
    |-- 3. Calls collect_pin(slot_id=2)
    |
    |-- 4. Contract verifies:
    |       - Caller is registered pinner
    |       - Slot is active
    |       - Slot is not expired (computed from created_at + max_cycles)
    |       - Caller address not in slot.claims vec
    |       - pins_remaining > 0
    |
    |-- 5. offer_price transferred from escrow to pinner
    |       slot.escrow_balance -= offer_price
    |       slot.pins_remaining -= 1
    |       slot.claims.push_back(caller)
    |
    |-- 6. PINNED event emitted
    |
    |-- 7. If pins_remaining == 0:
    |       Slot storage entry deleted (freed for reuse)
    |       UNPIN event emitted
    |
    v
Pinner receives offer_price directly
```

### Cancellation Refund

```
Publisher
    |
    |-- 1. Calls cancel_pin(slot_id=2)
    |
    |-- 2. Contract verifies caller == slot.publisher
    |
    |-- 3. Refund = slot.escrow_balance (remaining after any claims)
    |       (pin_fee is NOT refunded)
    |
    |-- 4. XLM transferred from contract to publisher
    |
    |-- 5. Slot storage entry deleted (freed for reuse)
    |
    |-- 6. UNPIN event emitted
```

### Lazy Expiration Refund

```
Anyone (or triggered by create_pin finding expired slot)
    |
    |-- 1. Calls clear_expired_slot(slot_id) or create_pin triggers it
    |
    |-- 2. Contract computes: is current_epoch - created_epoch >= max_cycles?
    |
    |-- 3. If expired:
    |       Refund slot.escrow_balance to slot.publisher
    |       Slot storage entry deleted (freed for reuse)
    |       UNPIN event emitted
```

---

## Slot Attack Prevention

### Threat: Slot Lockup Attack
An attacker fills all 10 slots with unreasonably priced offers, taking the contract offline.

### Mitigations

1. **Non-refundable pin_fee**: Every slot costs the publisher a fee that is never returned. Occupying all 10 slots costs `pin_fee * 10` per epoch cycle. Admin can adjust `pin_fee` to make attacks expensive.

2. **max_cycles expiration**: All slots expire after a fixed number of epochs. With short epochs (~1 minute) and low `max_cycles` (e.g., 60), a slot lockup lasts at most ~1 hour before slots auto-free via lazy cleanup.

3. **Lazy cleanup**: Anyone can call `clear_expired_slot()` to free expired slots. This could be incentivized in the future with a small bounty.

4. **One unique CID per slot**: Duplicate CIDs are rejected, preventing redundant slot usage. A publisher may occupy multiple slots with different CIDs, but each slot costs `pin_fee`.

5. **Expiration guarantees**: Any request, legitimate or malicious, will expire after `max_cycles`. Slots always free up regardless of whether pinners claim them.

6. **Admin override**: Admins can adjust `pin_fee`, `max_cycles`, and `epoch_length` to adapt to attack patterns. `force_clear_slot()` available for stuck escrow.

---

## Error Types

```rust
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
```

---

## CID Hunter: Publisher-Driven Verification

### Concept

CID Hunter is the verification layer for hvym-pin-service. Rather than building a general-purpose policing network, verification is driven by the parties with the most at stake: **the publishers who paid for pins**.

Every Pintheon user who publishes content is the natural bounty hunter for their own CIDs. They paid for redundancy - they have the financial motivation to ensure they got what they paid for.

### Architecture

```
┌──────────────────────┐     ┌──────────────────────┐
│   Pintheon Node      │     │   Pinning Daemon      │
│   (isolated, serves  │     │   (IPFS network,      │
│    web traffic)      │     │    also CID Hunter)   │
│                      │     │                       │
│  create_pin() ───────┼─────┼──▶ hvym-pin-service   │
│                      │     │                       │
│                      │     │  Monitors PINNED      │
│                      │     │  events for own CIDs  │
│                      │     │                       │
│                      │     │  Bitswap want-have ──▶ Pinner A: HAVE ✓
│                      │     │  Bitswap want-have ──▶ Pinner B: DONT_HAVE ✗
│                      │     │                       │
│                      │     │  dispute_claim() ─────┼──▶ hvym-pin-service
└──────────────────────┘     └──────────────────────┘
```

**Key insight**: Pintheon nodes are completely isolated (no peering, no exposed API). But Pintheon users typically also run pinning daemons to support the network. The CID Hunter functionality runs on the user's **pinning daemon**, which is already a full IPFS node on the network.

### Verification Method: Bitswap Want-Have

The [Bitswap protocol](https://specs.ipfs.tech/bitswap-protocol/) provides native peer-to-peer content verification with **zero configuration** on the target node:

```
CID Hunter daemon                     Claimed pinner
    |                                      |
    |-- libp2p connect (via multiaddr) --->|
    |-- Bitswap WANT_HAVE(CID) ---------->|
    |<-- HAVE / DONT_HAVE ----------------|
    |                                      |
    No API exposure required.
    Standard IPFS protocol.
    Pinner's multiaddr is in the contract registry.
```

- **Every IPFS node speaks Bitswap** - no special configuration needed
- The pinner's `node_id` (peer ID) and `multiaddr` are already in their registration
- [ipfs-check](https://github.com/ipfs/ipfs-check) demonstrates this approach: Bitswap + DHT queries, no custom API

A combined verification approach:
1. **DHT provider lookup** (`ipfs routing findprovs <cid>`) - quick check if pinner is listed as provider
2. **Bitswap want-have** - definitive proof of actual data possession
3. **Optional partial retrieval** - for high-value content, retrieve a small block to confirm

**Sources:**
- [Bitswap Protocol Spec](https://specs.ipfs.tech/bitswap-protocol/)
- [ipfs-check tool](https://github.com/ipfs/ipfs-check)
- [IPFS Retrieval Check](https://check.ipfs.network/)
- [Kubo RPC API](https://docs.ipfs.tech/reference/kubo/rpc/)

### Scope: Own CIDs Only

A CID Hunter can only dispute claims for CIDs **they published**. This is enforced by verifying `caller == slot.publisher` in the contract. This ensures:

- **Natural incentive alignment** - only the payer has financial motivation
- **No griefing** - pinners can't harass each other through false disputes
- **Bounded scope** - each user polices their own content, not the whole network

### Flag Threshold System (Reputation-Based)

Fraudulent pinners expose themselves naturally because they tend to operate at scale, not for a single CID. A pinner gaming the system accumulates flags from multiple publishers whose content isn't being served. The resolution mechanism is simple: **flags accumulate, threshold triggers action**.

Flags are decoupled from slots entirely. The publisher knows who to flag from PINNED events recorded to the ledger - no slot reference needed. This avoids the problem of slot reuse clearing claims data.

```
Publisher A: flag_pinner(pinner_X)  → flags: 1
Publisher B: flag_pinner(pinner_X)  → flags: 2
Publisher C: flag_pinner(pinner_X)  → flags: 3  ← threshold hit → auto-deactivate
```

#### Storage

```rust
DataKey::Flagged(Address, Address),  // (publisher, pinner) -> bool (prevents duplicate flags)
DataKey::Flaggers(Address),          // pinner -> Vec<Address> (who flagged, for bounty payout)
```

#### Contract Interface

```rust
/// Flag a pinner for not serving content
/// Caller must be a registered pinner (publishers also run pinning daemons)
/// Each publisher can only flag a given pinner once (prevents spam)
/// If flags reach threshold:
///   - Pinner is automatically deactivated
///   - Pinner's stake is forfeited and divided equally among all flaggers
///   - Flaggers receive their share via XLM transfer
fn flag_pinner(
    e: Env,
    caller: Address,
    pinner: Address,
) -> Result<u32, Error>;  // Returns current flag count

/// Update the flag threshold
fn update_flag_threshold(e: Env, caller: Address, new_threshold: u32) -> Result<bool, Error>;

/// Update pinner stake requirement (applies to future registrations)
fn update_pinner_stake(e: Env, caller: Address, new_stake: u32) -> Result<bool, Error>;
```

#### How It Works

1. Publisher's CID Hunter daemon detects a pinner isn't serving content (Bitswap want-have returns `DONT_HAVE`)
2. Publisher calls `flag_pinner(pinner_addr)`
3. Contract verifies caller hasn't already flagged this pinner (`DataKey::Flagged(caller, pinner)`)
4. Stores flag record, adds caller to `DataKey::Flaggers(pinner)` vec, increments pinner's `flags` counter
5. If `flags >= flag_threshold`:
   - Pinner set to `active = false` (deactivated)
   - Pinner's `staked` amount divided equally among all addresses in `Flaggers` vec
   - Each flagger receives `stake / num_flaggers` via XLM transfer
   - Any remainder (from integer division) goes to `fees_collected`
   - Pinner's `staked` set to 0
6. Deactivated pinners cannot call `collect_pin()` on any slot

#### Bounty Distribution Example

```
pinner_stake = 10,000,000 stroops (1 XLM)
flag_threshold = 5

Publisher A flags → flags: 1
Publisher B flags → flags: 2
Publisher C flags → flags: 3
Publisher D flags → flags: 4
Publisher E flags → flags: 5 ← threshold hit!

Bounty per hunter: 10,000,000 / 5 = 2,000,000 stroops (0.2 XLM each)
Pinner deactivated, stake zeroed, all 5 hunters paid out.
```

#### Stake Lifecycle

```
join_as_pinner:   Pinner pays join_fee (non-refundable) + pinner_stake (held)
                  pinner.staked = pinner_stake

leave_as_pinner:  If pinner.active == true:
                    pinner_stake returned to pinner
                  If pinner.active == false (deactivated by flags):
                    Stake already distributed to bounty hunters, nothing to return

flag_threshold:   Stake forfeited → divided among flaggers
                  Flaggers vec and Flagged records cleaned up after payout

remove_pinner:    Admin removal → stake returned (not punitive)
```

#### Design Properties

- **Real economic incentive**: CID Hunters earn bounties, not just reputation
- **Decoupled from slots**: Flags reference pinners, not slots. Works regardless of slot lifecycle
- **No on-chain verification needed**: The contract doesn't verify the claim - it's a reputation signal. Parties can't realistically know each other, and bounty hunters (publishers) are anonymous
- **No arbitration needed**: The volume of flags IS the evidence
- **Self-regulating**: Legitimate pinners never accumulate flags; fraudulent ones do
- **One flag per publisher per pinner**: Prevents a single publisher from spamming
- **Admin-tunable threshold**: Start conservative (e.g., 5), adjust based on network behavior
- **Bounty payout is atomic**: Distributed in the same transaction that triggers the threshold

#### Known Limitation: Sybil Re-registration

A deactivated pinner can `leave_as_pinner()` and rejoin with a new address and peer ID, resetting their flags. The `join_fee` is the economic barrier to this cycle. A separate blacklist contract could be explored in the future, but any address-based blacklist can be circumvented by creating a new identity. This is a network-economics problem, not solvable at the contract level.

### CID Hunter Daemon Spec

The full CID Hunter daemon specification will be developed separately in the `/pintheon` repository. Key components:

- **Event listener**: Monitors PINNED events for the user's own CIDs
- **Verification scheduler**: Periodic Bitswap want-have checks against all claimed pinners
- **Dispute submitter**: Automatic dispute filing when verification fails
- **Reporting dashboard**: Status of all pins and their verification state

### Future: Filecoin PDP Integration

[Filecoin's Proof of Data Possession (PDP)](https://filecoin.io/blog/posts/introducing-proof-of-data-possession-pdp-verifiable-hot-storage-on-filecoin/) offers a path to more robust verification:

- Random sampling challenges (160 bytes per challenge, regardless of dataset size)
- Standard SHA2 hashing (no specialized hardware)
- Cryptographic proof of possession without full retrieval
- Automated daily verification challenges

PDP-style proofs could eventually replace or augment the Bitswap-based approach, providing cryptographic on-chain verification.

**Sources:**
- [Introducing PDP - Filecoin](https://filecoin.io/blog/posts/introducing-proof-of-data-possession-pdp-verifiable-hot-storage-on-filecoin/)
- [Filecoin Foundation - PDP](https://fil.org/blog/introducing-proof-of-data-possession-pdp-verifiable-hot-storage-on-filecoin)

### IPFS Garbage Collection Note

**Clarification on "minimum 3 pins" claim:**

Research indicates there is NO inherent "minimum pins" requirement in IPFS. Garbage collection behavior:
- Each IPFS node independently decides what to keep/discard
- Pinned content is protected from local garbage collection
- Content availability depends on at least ONE node pinning and being online
- The "3 pins" recommendation is a **redundancy best practice**, not a protocol requirement

**Sources:**
- [IPFS Persistence](https://docs.ipfs.tech/concepts/persistence/)
- [IPFS Garbage Collection Guide](https://blog.logrocket.com/guide-ipfs-garbage-collection/)

**Recommendation:** The `min_pin_qty` of 3 is a sensible default for redundancy, but is configurable by admin.

### Documentation Note: Peer ID Privacy

The `Pinner.node_id` field stores the IPFS peer ID, which is inherently public by IPFS design. When registered on-chain, operators should be aware that:
- Peer IDs enable DHT lookups to discover IP addresses
- Activity monitoring can associate content with specific nodes

This is expected behavior for public pinning services. Daemon documentation should advise operators to use dedicated nodes rather than personal ones. Full privacy implications to be addressed in the Pintheon daemon specification.

**Sources:**
- [IPFS Privacy & Encryption](https://docs.ipfs.tech/concepts/privacy-and-encryption/)

---

## Tests Required

### Constructor Tests

```rust
#[test]
fn test_constructor_initializes_config() { }

#[test]
fn test_constructor_sets_admin() { }

#[test]
fn test_constructor_creates_empty_slots() { }

#[test]
#[should_panic]
fn test_constructor_rejects_zero_epoch_length() { }

#[test]
#[should_panic]
fn test_constructor_rejects_zero_max_cycles() { }

#[test]
#[should_panic]
fn test_constructor_rejects_zero_min_pin_qty() { }
```

### Pinner Registration Tests

```rust
#[test]
fn test_join_as_pinner_success() { }

#[test]
fn test_join_as_pinner_transfers_fee() { }

#[test]
fn test_join_as_pinner_emits_event() { }

#[test]
#[should_panic(expected = "already pinner")]
fn test_join_as_pinner_rejects_duplicate() { }

#[test]
fn test_update_pinner_updates_fields() { }

#[test]
fn test_leave_as_pinner_removes_registration() { }

#[test]
fn test_admin_remove_pinner() { }

#[test]
#[should_panic(expected = "unauthorized")]
fn test_non_admin_cannot_remove_pinner() { }
```

### Pin Request (Slot) Tests

```rust
#[test]
fn test_create_pin_success() { }

#[test]
fn test_create_pin_transfers_correct_amount() {
    // Verify (offer_price * pin_qty) + pin_fee transferred
}

#[test]
fn test_create_pin_emits_pin_event_with_cid_and_gateway() { }

#[test]
fn test_create_pin_stores_cid_hash_not_cid_string() { }

#[test]
fn test_create_pin_assigns_first_available_slot() { }

#[test]
fn test_create_pin_reuses_expired_slot_with_refund() {
    // 1. Fill slot, advance past max_cycles
    // 2. New publisher creates pin
    // 3. Verify old publisher received refund
    // 4. Verify slot now holds new request
}

#[test]
#[should_panic(expected = "no slots available")]
fn test_create_pin_rejects_when_all_slots_full() { }

#[test]
#[should_panic(expected = "insufficient pin quantity")]
fn test_create_pin_rejects_low_qty() { }

#[test]
#[should_panic(expected = "pin qty exceeds max")]
fn test_create_pin_rejects_qty_over_10() { }

#[test]
#[should_panic(expected = "offer price too low")]
fn test_create_pin_rejects_low_offer_price() { }

#[test]
#[should_panic(expected = "offer overflow")]
fn test_create_pin_rejects_overflow() {
    // offer_price * pin_qty exceeds u32
}

#[test]
#[should_panic(expected = "duplicate cid")]
fn test_create_pin_rejects_duplicate_cid() {
    // Same CID in two different slots should fail
}

#[test]
fn test_same_publisher_multiple_slots_different_cids() {
    // One publisher occupying multiple slots with unique CIDs should succeed
}
```

### Pin Collection Tests

```rust
#[test]
fn test_collect_pin_success() { }

#[test]
fn test_collect_pin_transfers_offer_price_to_pinner() { }

#[test]
fn test_collect_pin_decrements_pins_remaining() { }

#[test]
fn test_collect_pin_adds_pinner_to_claims() { }

#[test]
fn test_collect_pin_emits_pinned_event() { }

#[test]
fn test_collect_pin_frees_slot_when_filled() {
    // Verify slot.active = false after last pin collected
}

#[test]
fn test_collect_pin_emits_unpin_when_complete() { }

#[test]
fn test_multiple_pinners_collect_same_slot() { }

#[test]
#[should_panic(expected = "not pinner")]
fn test_collect_pin_requires_registration() { }

#[test]
#[should_panic(expected = "already claimed")]
fn test_collect_pin_prevents_double_claim() { }

#[test]
#[should_panic(expected = "slot not active")]
fn test_collect_pin_rejects_inactive_slot() { }

#[test]
#[should_panic(expected = "slot expired")]
fn test_collect_pin_rejects_expired_slot() { }
```

### Cancellation Tests

```rust
#[test]
fn test_cancel_pin_refunds_remaining_escrow() { }

#[test]
fn test_cancel_pin_does_not_refund_pin_fee() { }

#[test]
fn test_cancel_pin_after_partial_fill() {
    // 1. Create request for 5 pins
    // 2. 2 pinners collect
    // 3. Publisher cancels
    // 4. Verify 3 * offer_price refunded
}

#[test]
fn test_cancel_pin_emits_unpin() { }

#[test]
fn test_cancel_pin_frees_slot() { }

#[test]
#[should_panic(expected = "not slot publisher")]
fn test_cancel_pin_only_publisher() { }

#[test]
#[should_panic(expected = "slot not active")]
fn test_cancel_rejects_inactive_slot() { }
```

### Expiration Tests

```rust
#[test]
fn test_slot_expires_after_max_cycles() {
    // Advance ledger past max_cycles * epoch_length
    // Verify is_slot_expired returns true
}

#[test]
fn test_clear_expired_slot_refunds_publisher() { }

#[test]
fn test_clear_expired_slot_emits_unpin() { }

#[test]
fn test_clear_expired_slot_frees_slot() { }

#[test]
#[should_panic(expected = "slot not expired")]
fn test_clear_expired_slot_rejects_active() { }

#[test]
fn test_epoch_computation() {
    // Verify current_epoch returns correct value at various ledger positions
}

#[test]
fn test_lazy_cleanup_on_create_pin() {
    // 1. Fill all 10 slots
    // 2. Advance past max_cycles
    // 3. New publisher calls create_pin
    // 4. Verify expired slot cleaned up and reused
}
```

### Admin Tests

```rust
#[test]
fn test_add_admin() { }

#[test]
fn test_remove_admin() { }

#[test]
#[should_panic(expected = "cannot remove initial admin")]
fn test_cannot_remove_initial_admin() { }

#[test]
fn test_withdraw_fees() { }

#[test]
fn test_update_pin_fee() { }

#[test]
fn test_update_join_fee() { }

#[test]
fn test_update_min_pin_qty() { }

#[test]
fn test_update_min_offer_price() { }

#[test]
fn test_update_max_cycles() { }

#[test]
fn test_force_clear_slot_refunds_publisher() { }

#[test]
fn test_force_clear_slot_frees_active_slot() {
    // Verify admin can clear a slot that has not yet expired
}

#[test]
#[should_panic(expected = "not admin")]
fn test_non_admin_cannot_force_clear_slot() { }

#[test]
#[should_panic(expected = "not admin")]
fn test_non_admin_cannot_update_config() { }
```

### CID Hunter Flag Tests

```rust
#[test]
fn test_flag_pinner_increments_count() { }

#[test]
fn test_flag_pinner_auto_deactivates_at_threshold() {
    // Flag pinner N times from N different publishers
    // Verify pinner.active == false after threshold reached
}

#[test]
fn test_deactivated_pinner_cannot_collect() {
    // Deactivated pinner calls collect_pin → should fail
}

#[test]
#[should_panic(expected = "already flagged")]
fn test_flag_pinner_one_flag_per_publisher_per_pinner() {
    // Same publisher flags same pinner twice → should fail
}

#[test]
fn test_flag_persists_after_slot_reuse() {
    // 1. Publisher creates pin, pinner claims, slot fills and is deleted
    // 2. Publisher flags pinner (no slot reference needed)
    // 3. Verify flag recorded
}

#[test]
fn test_flag_threshold_update() { }

#[test]
fn test_admin_can_reactivate_flagged_pinner() {
    // Admin calls update_pinner to set active=true
}
```

### Pinner Staking Tests

```rust
#[test]
fn test_join_as_pinner_collects_stake() {
    // Verify join_fee + pinner_stake transferred on registration
    // Verify pinner.staked == pinner_stake
}

#[test]
fn test_leave_as_pinner_returns_stake() {
    // Active pinner leaves voluntarily
    // Verify pinner_stake returned to pinner
}

#[test]
fn test_leave_as_pinner_no_stake_if_deactivated() {
    // Pinner deactivated by flag threshold (stake already distributed)
    // Verify leave_as_pinner returns 0 (pinner.staked == 0)
}

#[test]
fn test_flag_threshold_forfeits_stake() {
    // Flag pinner up to threshold
    // Verify pinner.staked set to 0
    // Verify pinner.active == false
}

#[test]
fn test_flag_threshold_distributes_bounty_equally() {
    // 5 flaggers, stake = 10_000_000 stroops
    // Each flagger receives 2_000_000 stroops
    // Verify all transfers
}

#[test]
fn test_flag_bounty_remainder_goes_to_fees() {
    // 3 flaggers, stake = 10_000_000 stroops
    // Each flagger receives 3_333_333 stroops
    // Remainder 1 stroop → fees_collected
}

#[test]
fn test_admin_remove_pinner_returns_stake() {
    // Admin removes active pinner
    // Verify pinner_stake returned (admin removal not punitive)
}

#[test]
fn test_update_pinner_stake_applies_to_future_only() {
    // Update pinner_stake from 1 XLM to 2 XLM
    // Existing pinner still has original stake amount
    // New pinner pays updated stake
}
```

### Integration Tests

```rust
#[test]
fn test_full_pin_lifecycle() {
    // 1. Initialize contract
    // 2. Register pinner
    // 3. Publisher creates pin request
    // 4. Pinner collects pin (repeat for pin_qty)
    // 5. Verify slot freed, events emitted, balances correct
}

#[test]
fn test_multiple_publishers_multiple_pinners() {
    // Fill multiple slots, multiple pinners collect across slots
}

#[test]
fn test_slot_reuse_after_fill() {
    // 1. Fill a slot completely
    // 2. New publisher reuses same slot
}

#[test]
fn test_slot_reuse_after_expiration() {
    // 1. Create request, don't fill
    // 2. Advance past expiration
    // 3. New publisher claims slot, verify lazy refund
}

#[test]
fn test_contract_throughput_simulation() {
    // Simulate many epochs of create/collect/expire cycles
    // Verify no state leaks or accounting errors
}

#[test]
fn test_slot_attack_scenario() {
    // 1. Attacker fills all 10 slots with high-price offers
    // 2. Advance past max_cycles
    // 3. Verify all slots can be freed
    // 4. Verify attacker paid 10 * pin_fee (non-refundable)
}
```

### Financial Tests

```rust
#[test]
fn test_fee_accounting() {
    // Verify fees_collected increments by pin_fee on each create_pin
    // Verify fees_collected is separate from escrow
}

#[test]
fn test_withdraw_fees_respects_escrow() {
    // Verify withdraw_fees only withdraws up to fees_collected
    // Verify escrow funds are untouched after withdrawal
}

#[test]
fn test_escrow_accounting() {
    // Verify escrow decrements correctly on each collect
}

#[test]
fn test_no_fund_leakage() {
    // After all slots filled or expired: sum of all payouts + fees == total deposits
}

#[test]
fn test_rent_estimation() {
    // Estimate storage costs for 10 slots + pinner registry
}
```

---

## Storage Considerations

### Storage Footprint

| Data | Count | Size | Storage Tier | Monthly Rent |
|------|-------|------|--------------|-------------|
| PinService config | 1 | ~160 bytes | Instance | Included with contract |
| AdminList | 1 | ~100 bytes | Persistent | ~43 stroops |
| PinSlot (active, 10 claims) | 0-10 | ~364 bytes each | Persistent | ~155 stroops each |
| PinSlot (empty) | - | 0 bytes | Not stored | 0 |
| Pinner registry | N | ~200 bytes each | Persistent | ~85 stroops each |
| Flag records (Flagged) | M | ~64 bytes each | Persistent | ~27 stroops each |
| Flaggers vec per pinner | K | ~32 bytes/addr + overhead | Persistent | ~varies |

**Typical (5 active slots + 20 pinners + 10 flags)**: ~5.6 KB = ~2,391 stroops/month (~0.0002 XLM)
**Worst case (10 full slots + 50 pinners + 100 flags + 20 flaggers vecs)**: ~22 KB = ~9,400 stroops/month (~0.0009 XLM)

### TTL Management

```rust
const DAY_IN_LEDGERS: u32 = 17_280;

// Contract instance and config
const INSTANCE_BUMP_AMOUNT: u32 = 7 * DAY_IN_LEDGERS;
const INSTANCE_LIFETIME_THRESHOLD: u32 = INSTANCE_BUMP_AMOUNT - DAY_IN_LEDGERS;

// Slots and pinner registry
const PERSISTENT_BUMP_AMOUNT: u32 = 30 * DAY_IN_LEDGERS;
const PERSISTENT_LIFETIME_THRESHOLD: u32 = PERSISTENT_BUMP_AMOUNT - DAY_IN_LEDGERS;
```

---

## Open Questions & Future Considerations

### Immediate Questions

1. **CID validation**: Should we validate CID format on-chain?
   - Recommendation: Basic length validation only (CIDs are variable length)

2. **Gateway URL validation**: Validate URL format?
   - Recommendation: Length limit only (100 chars, consistent with hvym-roster)

3. **Epoch tuning**: Optimal epoch_length and max_cycles values TBD through simulation

### Future Enhancements

1. **Reputation system**: Weight pinner selection by `pins_completed`
2. **Tiered pricing**: Different rates for different file sizes
3. **Subscription model**: Ongoing pinning with periodic payments
4. **Oracle integration**: Automated verification of pin status
5. **Cross-contract**: Integration with hvym-collective for member benefits
6. **Dynamic slot count**: Allow admin to adjust NUM_SLOTS
7. **Bounty for cleanup**: Small reward for calling `clear_expired_slot()`

---

## File Structure

```
hvym-pin-service/
├── Cargo.toml
├── src/
│   ├── lib.rs              # Contract implementation + constructor
│   ├── types.rs            # DataKey, PinSlot, PinService, Pinner, Error
│   ├── events.rs           # PinEvent, UnpinEvent, PinnedEvent, etc.
│   ├── storage.rs          # Storage helpers (get/set patterns)
│   ├── admin.rs            # Admin management (add/remove/auth)
│   ├── pinner.rs           # Pinner registration logic
│   ├── slots.rs            # Slot pool management + epoch computation
│   ├── test.rs             # Unit tests
│   └── integration_test.rs # Integration tests
```

---

## Dependencies

```toml
[package]
name = "hvym-pin-service"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]

[dependencies]
soroban-sdk = "23.0.1"
soroban-token-sdk = "23.0.1"

[dev-dependencies]
soroban-sdk = { version = "23.0.1", features = ["testutils"] }

[features]
testutils = ["soroban-sdk/testutils"]
```

---

## Summary

`hvym-pin-service` creates a decentralized marketplace for IPFS pinning using a **modeless, fixed-slot pool** design:

- **10 reusable slots** with on-demand storage (empty slots cost nothing)
- **Epoch-based expiration** with constant `EPOCH_LENGTH` and global `max_cycles` prevents slot lockup
- **No phase restrictions**: Publishers and pinners operate at any time
- **Events carry rich data**: CID strings and gateway URLs live in events, not storage
- **Lazy cleanup**: Expired slots are refunded and deleted when reused
- **Inline claims**: Double-claim prevention via bounded `Vec<Address>` in each slot
- **Fee/escrow separation**: `fees_collected` counter protects escrow from accidental withdrawal
- **Minimum offer_price**: Ensures pinners can profit after transaction costs

Verification is handled by **CID Hunter**, a publisher-driven reputation system:
- Publishers verify their own CIDs via Bitswap want-have from their pinning daemons
- No exposed APIs required - uses standard IPFS protocols
- Flag-based reputation: flags accumulate, threshold auto-deactivates fraudulent pinners
- Flags decoupled from slots - work regardless of slot lifecycle
- **Pinner staking**: Pinners post refundable XLM stake on registration; forfeited and distributed as bounty to flaggers on deactivation
- Future path to Filecoin PDP-style cryptographic proofs
