"""
Configuration for Pintheon contract examples.

Update these values with your deployed contract addresses.
"""

# Network configuration
NETWORK = "testnet"
RPC_URL = "https://soroban-testnet.stellar.org"
NETWORK_PASSPHRASE = "Test SDF Network ; September 2015"

# Deployed contract addresses (update these with your actual contract IDs)
# These are example addresses - replace with your deployed contracts
CONTRACTS = {
    "hvym_collective": "CDIBEBWJZ3WSMDOPCVMWEKLUJRVBVU2GJSWGYWU6IKJLFKZPP37YSGFG",
    "hvym_roster": "CDKCP2OMO3NJM2JS33EXPJVQS4YT2TAIA5WC4JTO4P6KHNXN6AYKPWKH",
    "opus_token": "CB2TEJFS5FQK66VZEAQXJQPEAOXZNBSYJ5WYH7Q65XHDOPLOEAQRZRXH",
}

# XLM token contract on testnet (native asset wrapper)
XLM_TOKEN = "CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC"

# Conversion helpers
STROOPS_PER_XLM = 10_000_000


def xlm_to_stroops(xlm: float) -> int:
    """Convert XLM to stroops (1 XLM = 10,000,000 stroops)."""
    return int(xlm * STROOPS_PER_XLM)


def stroops_to_xlm(stroops: int) -> float:
    """Convert stroops to XLM."""
    return stroops / STROOPS_PER_XLM
