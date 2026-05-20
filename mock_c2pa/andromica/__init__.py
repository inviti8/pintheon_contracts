"""mock_c2pa.andromica — modules portable to glasswing / Andromica.

These modules have no Stellar SDK dependency at import time. They take and
return primitive types (bytes, str, datetime) so they drop into any host
that knows how to do Soroban contract submission separately.

What's here:
  - `ca_generation`: build a spec-compliant Ed25519 self-signed X.509 CA
    cert per C2PA.md §4.2. Generates the keypair, builds the cert, exposes
    the SHA-256 DER fingerprint that the contract stores.
  - `bundle`: produce the human-pasteable registration bundle the user
    takes from the app to the Portal.
  - `leaf`: issue per-publish member leaf certs (ephemeral; never persisted).

What's NOT here (deliberately):
  - The Portal-side `mint_app_ca_registration_token`. Andromica receives
    the token; the Portal mints it. See `mock_c2pa.portal_mock` for the
    mock of that.
  - The on-chain submission itself. See `mock_c2pa.register`.
"""
