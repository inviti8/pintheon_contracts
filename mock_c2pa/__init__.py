"""mock_c2pa — end-to-end mock for the hvym-cert-registry C2PA flow.

Layout:
  - canonical.py     — sorted-keys JSON payload builders; mirrors the
                        contract's `build_*_payload` byte-for-byte.
  - andromica/        — modules that drop directly into glasswing /
                        Andromica. No Stellar SDK at import time.
      - ca_generation — Ed25519 X.509 CA + leaf per C2PA.md §4.2/§4.3.
      - bundle        — produce the registration bundle the user pastes.
  - portal_mock/      — stub of the Heavymeta Portal's mint helper.
      - mint_token    — signs canonical payloads with a member keypair.
  - register.py      — Soroban submission (scval-based, no bindings needed).
  - keystore.py      — gitignored persistence of mock keypairs.
  - run_mock_flow.py — CLI orchestrator: dry-run or testnet mode.

See README.md.
"""
