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
    "hvym_collective": "CAGZJMYO6GAEOYOX7QZQPINTLEDLS3OEDMVA4OCMCLFIUVGEBHUTLZTE",
    "hvym_roster": "CANS7U5DNOWFUYMULMN3ZPNRIRKSQENKZLGMWOZJMCJATD3EFVW6PUXP",
    "opus_token": "CA3WCMMNEZALGNPSYDIO4OR4BBBMHKI3732BDLLADNG5FZAV57ZBR64F",
    "hvym_pin_service": "CCNOEJLBMXBNCYRV3JJ3OP54MPE7Z65YIKBQMIXVY3TH7O65RW6UBTDY",
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
