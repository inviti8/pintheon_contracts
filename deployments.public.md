# Deployments — public

Verified against the on-chain `hvym_registry` at
`CA6KQ5GYGI33VZB5IGWW7XXLLHR2MPEBWVDREU4P5ZGCSKRGHXBCRKXV`.
Run `python verify_registry.py --network public --registry-id CA6KQ5GYGI33VZB5IGWW7XXLLHR2MPEBWVDREU4P5ZGCSKRGHXBCRKXV --verify-wasm`
to reproduce.

| Contract | Contract ID | Wasm Hash |
|----------|-------------|-----------|
| pintheon_ipfs_token | `Upload only` | `416704f4bce9a1a69d10b468deb0ed98944a6d21a5341663636b085df773c8a6` |
| pintheon_node_token | `Upload only` | `3dad79585c6bef820984c18c7465454a2e1113a686e787a0b6ed1b562fb1e20e` |
| opus_token | `CAXX7JEGO2P2X6KMXCII2ISCA24L7KHU6O3O66BXRMDAJ5Y5T7GSZEK6` | `1e65df19aab602c415909ef6ab3043ffd349c21c35b97aafb3946c471d61cd39` |
| hvym_collective | `CBZPNQJUPE5E4BOHA7PYVH44B4RWEQQW4QU4BL6LHQOWZYAU5ZRNWJYL` | `42549904d3f537404746b43460a560820f80acfdabb433e33cc63bdf8238ed4b` |
| hvym_roster | `CBUS33CAIMTV7T4M4G3FTH35QBAY6VWY3K4IZTYTRPD45ZDSQMSIZ2AB` | `3f88b09753a43291da62799db81a051fda10ce97e7a091ad8ace4da17c62c284` |
| hvym_pin_service | `CCMEKYORB732TMYJJ6FR5EZM3XRWOE2U4HNGZUWBLTMXATVRZ2DQYOBZ` | `448d2c5e1921a9d3fe349b6e40b93b3ebc9cbf38d427145419e0f787cb71cd4a` |
| hvym_registry | `CA6KQ5GYGI33VZB5IGWW7XXLLHR2MPEBWVDREU4P5ZGCSKRGHXBCRKXV` | `39be8e7d49cd82d0fa79a07a05fd268c97631d0360382bb8fe6732d75513dad1` |

`hvym_pin_service_factory` WASM is uploaded to mainnet (hash `d9002069e506bb00df9c0f8e3c3634c8d695289c5dcae18ff7d8b337824fed2d`) but no factory instance contract is deployed for this release.
