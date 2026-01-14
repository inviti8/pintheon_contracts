# Pintheon Contract Bindings - Python Examples

This folder contains examples demonstrating how to use the Python bindings
for Pintheon smart contracts on the Stellar/Soroban network.

## Prerequisites

```bash
# Install required dependencies
pip install stellar-sdk

# For async examples
pip install aiohttp
```

## Configuration

Before running the examples, update `config.py` with your deployed contract addresses:

```python
CONTRACTS = {
    "hvym_collective": "CXXXXXXX...",  # Your collective contract ID
    "hvym_roster": "CXXXXXXX...",      # Your roster contract ID
    "opus_token": "CXXXXXXX...",       # Your opus token contract ID
}
```

## Examples

### 1. Basic Queries (`01_basic_queries.py`)

Demonstrates read-only contract queries that don't require a funded account:

- Query collective info (symbol, fees, launch status)
- Check membership status
- Check admin status
- Get admin list

```bash
python 01_basic_queries.py
```

### 2. Join Collective (`02_join_collective.py`)

Shows how to join the collective by submitting a transaction:

- Check account balance
- Verify membership status
- Submit join transaction

```bash
# Set your secret key (never commit this!)
export STELLAR_SECRET_KEY=SXXXXX...

python 02_join_collective.py
```

### 3. Async Operations (`03_async_example.py`)

Demonstrates async client usage for efficient concurrent queries:

- Parallel contract queries
- Batch membership checks
- Multiple contract interactions

```bash
python 03_async_example.py
```

### 4. Publish Files (`04_publish_file.py`)

Shows how to publish files and deploy tokens:

- Publish file events
- Deploy IPFS tokens
- Deploy node tokens

```bash
export STELLAR_SECRET_KEY=SXXXXX...

python 04_publish_file.py
```

## Client Types

Each binding provides two client classes:

### Synchronous Client (`Client`)

```python
from hvym_collective.bindings import Client

client = Client(
    contract_id="CXXXXXX...",
    rpc_url="https://soroban-testnet.stellar.org"
)

# Query (simulate only)
result = client.join_fee()
result.simulate()
print(result.result())

# Transaction (sign and submit)
tx = client.join(
    caller=public_key,
    source=public_key,
    signer=keypair
)
tx.simulate()
response = tx.sign_and_submit()
```

### Async Client (`ClientAsync`)

```python
from hvym_collective.bindings import ClientAsync
import asyncio

async def main():
    client = ClientAsync(
        contract_id="CXXXXXX...",
        rpc_url="https://soroban-testnet.stellar.org"
    )

    result = await client.join_fee()
    await result.simulate()
    print(result.result())

asyncio.run(main())
```

## Common Patterns

### Simulation vs Submission

All contract calls return an `AssembledTransaction`. You can:

1. **Simulate only** (for queries):
   ```python
   result = client.some_query()
   result.simulate()
   value = result.result()
   ```

2. **Sign and submit** (for transactions):
   ```python
   tx = client.some_action(caller=address, source=address, signer=keypair)
   tx.simulate()
   response = tx.sign_and_submit()
   ```

### Working with Addresses

```python
from stellar_sdk import Address, Keypair

# From string
address = "GXXXXX..."

# From keypair
keypair = Keypair.from_secret("SXXXXX...")
public_key = keypair.public_key
```

### Converting Values

```python
# XLM to stroops (contract uses stroops)
stroops = int(xlm_amount * 10_000_000)

# Stroops to XLM
xlm = stroops / 10_000_000

# Strings to bytes (for contract parameters)
name_bytes = "My Name".encode('utf-8')
```

## Testnet Resources

- **Stellar Laboratory**: https://laboratory.stellar.org/
- **Testnet Faucet**: `stellar keys fund <key-name> --network testnet`
- **Block Explorer**: https://stellar.expert/explorer/testnet

## Troubleshooting

### "Insufficient balance"

Fund your testnet account:
```bash
stellar keys fund mykey --network testnet
```

### "Not a member"

Join the collective first using example 2.

### "Transaction failed"

Check the simulation result for errors before submitting:
```python
tx.simulate()
if tx.simulation_data.error:
    print(f"Simulation error: {tx.simulation_data.error}")
```
