# GitHub Workflows for Soroban Contract Validation

This directory contains the GitHub Actions workflow for building and releasing Soroban contracts for validation on stellar.expert.

## Workflow File

### `custom-release.yml` (Recommended)
**Use this for all releases**

- ✅ Handles contract dependencies correctly
- ✅ Builds `hvym-collective` with all dependencies available
- ✅ Creates releases for all contracts
- ✅ Works with `contractimport!` statements

**When to use:** Always use this for production and testing releases

## Dependency Issue

The `hvym-collective` contract imports other contracts using `contractimport!`:

```rust
mod pintheon_node_token {
    soroban_sdk::contractimport!(
        file = "../pintheon-node-deployer/pintheon-node-token/target/wasm32-unknown-unknown/release/pintheon_node_token.optimized.wasm"
    );
}
```

This means:
1. Other contracts must be built first
2. WASM files must exist in the expected paths
3. The standard stellar-expert workflow can't handle this

## Solution: Custom Workflow

The `custom-release.yml` workflow:

1. **Builds dependencies first:**
   - `opus_token`
   - `pintheon_node_token` 
   - `pintheon_ipfs_token`

2. **Uploads dependency artifacts** to GitHub Actions

3. **Downloads artifacts** in the hvym-collective job

4. **Copies WASM files** to the expected paths

5. **Builds hvym-collective** with all dependencies available

6. **Creates releases** for all contracts
7. **Submits validation data** to StellarExpert API

## Usage

### Automatic Release
```bash
git tag v1.0.0
git push origin v1.0.0
```

### Manual Release
1. Go to GitHub Actions
2. Select "Custom Build and Release Soroban Contracts"
3. Click "Run workflow"
4. Enter release name
5. Click "Run workflow"

## Validation on stellar.expert

After deployment, contracts are automatically validated on stellar.expert because:
- The workflow submits binary hash, repository name, and commit SHA to StellarExpert's validation API
- Contracts are built from GitHub releases with matching hashes
- Source code is available for display 