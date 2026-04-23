# hvym-registry: Deployment & Usage Guide

Contract ID registry — the source of truth for all Pintheon/Heavymeta contract addresses across networks.

## 1. Build

```bash
# From repo root (using the build script)
python build_contracts.py --contract hvym-registry

# Or manually from the contract directory
cd hvym-registry
stellar contract build
```

The optimized WASM will be at `wasm/hvym_registry.optimized.wasm`.

## 2. Deploy

### Upload WASM

```bash
stellar contract upload \
  --wasm wasm/hvym_registry.optimized.wasm \
  --source <DEPLOYER_IDENTITY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015"
```

This returns a WASM hash (e.g. `ce191e2e...`). Use it in the next step.

### Deploy instance

The constructor takes a single argument: the initial admin address.

```bash
stellar contract deploy \
  --wasm-hash <WASM_HASH> \
  --source <DEPLOYER_IDENTITY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  --admin <ADMIN_PUBLIC_KEY>
```

This returns the registry contract ID (e.g. `CABC...XYZ`). Save it — this is the address all apps will use to look up other contract IDs.

### Mainnet deployment

Replace the RPC URL and passphrase:

```bash
--rpc-url https://stellar-soroban-public.nodies.app \
--network-passphrase "Public Global Stellar Network ; September 2015"
```

## 3. Register contract IDs

Use `set_contract_id` to register each contract. The `network` argument is an enum with two variants: `Testnet` and `Mainnet`.

### Register a testnet contract

```bash
stellar contract invoke \
  --id <REGISTRY_CONTRACT_ID> \
  --source <ADMIN_IDENTITY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  set_contract_id \
  --caller <ADMIN_PUBLIC_KEY> \
  --name opus_token \
  --network Testnet \
  --contract_id CDPEWPM3B77Q3HBPLZQTKCUND6MAR6A73IQFIAVIPGKF2U2XBEDWMENU
```

(The testnet `opus_token` ID above comes from `deployments.testnet.json` — replace with the current value before running.)

### Register a mainnet contract

```bash
stellar contract invoke \
  --id <REGISTRY_CONTRACT_ID> \
  --source <ADMIN_IDENTITY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  set_contract_id \
  --caller <ADMIN_PUBLIC_KEY> \
  --name opus_token \
  --network Mainnet \
  --contract_id CA4NA27APFFWBEAML275ZT4HD6ALUUZJGHH6W27IW6GT6DQFPZWKTIPF
```

(The mainnet `opus_token` ID above comes from `deployments.public.json` — replace with the current value before running.)

Note: The `--rpc-url` and `--network-passphrase` refer to where the *registry* is deployed, not the network being registered. You can store both testnet and mainnet contract IDs in a single registry instance.

### Register all contracts (example)

```bash
REGISTRY=<REGISTRY_CONTRACT_ID>
SOURCE=<ADMIN_IDENTITY>
CALLER=<ADMIN_PUBLIC_KEY>
RPC="https://soroban-testnet.stellar.org"
PASS="Test SDF Network ; September 2015"

# Testnet IDs (from deployments.testnet.json — always re-check before running)
stellar contract invoke --id $REGISTRY --source $SOURCE --rpc-url $RPC --network-passphrase "$PASS" \
  -- set_contract_id --caller $CALLER --name opus_token --network Testnet \
  --contract_id CDPEWPM3B77Q3HBPLZQTKCUND6MAR6A73IQFIAVIPGKF2U2XBEDWMENU

stellar contract invoke --id $REGISTRY --source $SOURCE --rpc-url $RPC --network-passphrase "$PASS" \
  -- set_contract_id --caller $CALLER --name hvym_collective --network Testnet \
  --contract_id CDPDM3XDYZSQE4ZWWK2PGFJP74IS7UH3OYPGGPO7TI2KP4JDH7E54EL7

stellar contract invoke --id $REGISTRY --source $SOURCE --rpc-url $RPC --network-passphrase "$PASS" \
  -- set_contract_id --caller $CALLER --name hvym_roster --network Testnet \
  --contract_id CBDOEYS5Z6RXRBIHJK72JPE2GIPR2HTUGIVHKVCOASKXGKL73Y4HOMVM

stellar contract invoke --id $REGISTRY --source $SOURCE --rpc-url $RPC --network-passphrase "$PASS" \
  -- set_contract_id --caller $CALLER --name hvym_pin_service --network Testnet \
  --contract_id CBWZFS3QRW67SHEX5KLY7OFOTA3V5TF6V5QIDQQ52GQT7FY5Y5OQXIWW

stellar contract invoke --id $REGISTRY --source $SOURCE --rpc-url $RPC --network-passphrase "$PASS" \
  -- set_contract_id --caller $CALLER --name hvym_pin_service_factory --network Testnet \
  --contract_id CD3OUO6BSCOQWMCPE5LFSG2F2TQSNNDZGA3EITKYSE74ZACO5OXGBQ5A
```

## 4. Query contract IDs

### Get a single contract ID

```bash
stellar contract invoke \
  --id <REGISTRY_CONTRACT_ID> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  get_contract_id \
  --name opus_token \
  --network Testnet
```

Returns the contract address. Panics if not registered.

### Check if a contract is registered

```bash
stellar contract invoke \
  --id <REGISTRY_CONTRACT_ID> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  has_contract_id \
  --name opus_token \
  --network Mainnet
```

Returns `true` or `false`.

### List all contracts for a network

```bash
stellar contract invoke \
  --id <REGISTRY_CONTRACT_ID> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  get_all_contracts \
  --network Testnet
```

Returns a list of `{name, contract_id}` entries.

## 5. Update a contract ID

Use `set_contract_id` with the same name and network — it overwrites the existing entry:

```bash
stellar contract invoke \
  --id <REGISTRY_CONTRACT_ID> \
  --source <ADMIN_IDENTITY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  set_contract_id \
  --caller <ADMIN_PUBLIC_KEY> \
  --name opus_token \
  --network Testnet \
  --contract_id <NEW_CONTRACT_ID>
```

## 6. Remove a contract ID

```bash
stellar contract invoke \
  --id <REGISTRY_CONTRACT_ID> \
  --source <ADMIN_IDENTITY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  remove_contract_id \
  --caller <ADMIN_PUBLIC_KEY> \
  --name opus_token \
  --network Testnet
```

## 7. Admin management

### Add an admin

```bash
stellar contract invoke \
  --id <REGISTRY_CONTRACT_ID> \
  --source <ADMIN_IDENTITY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  add_admin \
  --caller <EXISTING_ADMIN_PUBLIC_KEY> \
  --new_admin <NEW_ADMIN_PUBLIC_KEY>
```

### Remove an admin

```bash
stellar contract invoke \
  --id <REGISTRY_CONTRACT_ID> \
  --source <ADMIN_IDENTITY> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  remove_admin \
  --caller <EXISTING_ADMIN_PUBLIC_KEY> \
  --admin_to_remove <ADMIN_PUBLIC_KEY_TO_REMOVE>
```

The initial admin (set during deployment) cannot be removed.

### List admins

```bash
stellar contract invoke \
  --id <REGISTRY_CONTRACT_ID> \
  --rpc-url https://soroban-testnet.stellar.org \
  --network-passphrase "Test SDF Network ; September 2015" \
  -- \
  get_admin_list
```

## 8. Contract names reference

Use these names when calling `set_contract_id` / `get_contract_id`:

| Name | Contract |
|------|----------|
| `opus_token` | OPUS utility token |
| `hvym_collective` | Heavymeta Collective |
| `hvym_roster` | Heavymeta Roster |
| `hvym_pin_service` | IPFS Pin Service |
| `hvym_pin_service_factory` | Pin Service Factory |
| `pintheon_ipfs_token` | Pintheon IPFS File Token |
| `pintheon_node_token` | Pintheon Node Token |
| `hvym_registry` | This registry contract |

Names are free-form strings — you can register any name. The above are the standard names matching the per-network deployments files (`deployments.testnet.json` / `deployments.public.json`).

## 9. Using from another Soroban contract

To look up a contract ID from within another Soroban contract:

```rust
use soroban_sdk::{contractimport, Address, Env, String};

// Import the registry client
mod registry {
    soroban_sdk::contractimport!(
        file = "../hvym-registry/target/wasm32v1-none/release/hvym_registry.wasm"
    );
}

fn get_opus_token(e: &Env, registry_id: &Address) -> Address {
    let client = registry::Client::new(e, registry_id);
    let name = String::from_str(e, "opus_token");
    client.get_contract_id(&name, &registry::Network::Mainnet)
}
```
