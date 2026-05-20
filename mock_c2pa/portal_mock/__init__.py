"""mock_c2pa.portal_mock — stub for the heavymeta_collective Portal helper.

In production, the Heavymeta Portal mints registration tokens via the
Banker + Guardian dual-key unlock of the member's Stellar secret
(see INKTERNITY.md §3). This package replaces that with an in-memory
keypair so the mock testing flow doesn't need the Portal repo at all.

The on-the-wire token shape produced here is byte-identical to what the
real Portal will eventually emit. Andromica's `register.py` doesn't care
which side minted it.
"""
