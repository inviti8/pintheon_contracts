"""
Configuration for Pintheon contract examples.

Update these values with your deployed contract addresses.
"""

# Network configuration
NETWORK = "testnet"
RPC_URL = "https://soroban-testnet.stellar.org"
NETWORK_PASSPHRASE = "Test SDF Network ; September 2015"

# Deployed contract addresses (update these with your actual contract IDs as needed)
# These are deployed contracts from the deployments.json file, as of alpha v0.08
CONTRACTS = {
    "hvym_collective": "CADANB5AR5GDFF4YWWETWA4KSRM3Y2ZLJPQJFNSBORSTZRVOZXMHJWBT",
    "hvym_roster": "CANK5NWUYO3PXWLTNYHE4F775CZXTJXCGPMV2STEZYDTSDBNPJH4NO33",
    "opus_token": "CCZ4GP3CAFGF4DSBKI3YQCGMEHPPYL4OALXW4MHQXYQY47O22SWHI4NN",
    "hvym_pin_service": "CDRBV6AEZ6UBMHHHVHRLAZW4IKFRGU7RWZ5DVFLWJAPHAQJZCXILEVKS",
    "hvym_pin_service_factory": "CB4QL4BBC7IRGWYK7V6SMW6DPYW2DTTLB6BC2YC5L4Z2CKLEREDTUR4Q",
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
