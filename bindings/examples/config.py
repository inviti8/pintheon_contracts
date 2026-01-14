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
    "hvym_collective": "CAKLTGOWQAXCZ3ASA3XWA5ECQDO6CKENEZVCUXZ66LETR7EIDWJUWKCX",
    "hvym_roster": "CDY6NVMRND4QOFYQ7DWPZN4PRUESSHYWO7HL572I3JWS7J5WGQNR6JDX",
    "opus_token": "CAKWTI6AY6LPSSBZOOSHMA2DHP7SUHE7N2M7PAUGOFIN5HRHW5CGRIMW",
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
