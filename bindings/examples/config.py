"""
Configuration for Pintheon contract examples.

Update these values with your deployed contract addresses.
"""

# Network configuration
NETWORK = "testnet"
RPC_URL = "https://soroban-testnet.stellar.org"
NETWORK_PASSPHRASE = "Test SDF Network ; September 2015"

# Deployed contract addresses (update these with your actual contract IDs as needed)
# These are deployed contracts from the deployments.json file, as of
CONTRACTS = {
    "hvym_collective": "CDHSOV4IKQB3YZTA6HW26RN7VS6UVZRZZCNWDQVCSQPKYKBMATRJSQ5R",
    "hvym_roster": "CDWX72R3Z7CAKWWBNKVNDLSUH5WZOC4CR7OOFJQANO2IX37S3IE4JRRO",
    "opus_token": "CA3SLEQ65R3DAYT5GPFB6SXAHTR5NS5VAEZSEMMIYNXWMTLBT7NX2RHX",
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
