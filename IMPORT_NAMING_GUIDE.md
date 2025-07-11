# Import Naming Guide for hvym-collective Contract

This guide explains how to determine the correct file names for `contractimport!` statements in the `hvym-collective` contract.

## Overview

The `hvym-collective` contract imports other contracts using `contractimport!` statements. The file names in these imports must match the actual WASM files that are built during the workflow.

## Current Setup

### Workflow Build Process
1. **Dependencies are built first** in the `build-dependencies` job
2. **Package versions are dynamically detected** from each contract's `Cargo.toml`
3. **WASM files are created with the new naming convention**: `pintheon-node-token_v0.0.6.wasm`
4. **The hvym-collective imports are automatically updated** to match the actual versions
5. **The hvym-collective imports reference these new named files**

### Import Statements in hvym-collective/src/lib.rs

**For Workflow Builds (Active - automatically updated):**
```rust
mod pintheon_node_token {
    soroban_sdk::contractimport!(
        file = "../pintheon-node-deployer/pintheon-node-token/target/wasm32v1-none/release/pintheon-node-token_v0.0.6.wasm"
    );
}

mod pintheon_ipfs_token {
    soroban_sdk::contractimport!(
        file = "../pintheon-ipfs-deployer/pintheon-ipfs-token/target/wasm32v1-none/release/pintheon-ipfs-token_v0.0.6.wasm"
    );
}

mod opus_token {
    soroban_sdk::contractimport!(
        file = "../opus_token/target/wasm32v1-none/release/opus-token_v0.0.6.wasm"
    );
}
```

**For Local Development (Commented - manual):**
```rust
//LOCAL BUILD
// mod pintheon_node_token {
//     soroban_sdk::contractimport!(
//         file = "../pintheon-node-deployer/pintheon-node-token/target/wasm32-unknown-unknown/release/pintheon_node_token.optimized.wasm"
//     );
// }
// ... etc
```

## How to Determine Import Names

### Dynamic Version Detection (Workflow)

The workflow automatically detects versions from `Cargo.toml` files:

```bash
# For each dependency contract
PACKAGE_VERSION=$(grep -m1 '^version =' Cargo.toml | cut -d '"' -f2)
WASM_FILE_NAME="${PACKAGE_NAME}_v${PACKAGE_VERSION}.wasm"
```

The workflow then automatically updates the hvym-collective imports:

```bash
# Update import statements with actual versions
sed -i "s|pintheon-node-token_v[0-9.]*\.wasm|pintheon-node-token_v${NODE_TOKEN_VERSION}.wasm|g" src/lib.rs
```

### Step 1: Check Package Names and Versions
Look at the `Cargo.toml` file for each dependency contract:

```bash
# Check package name and version
grep -E "^(name|version) = " pintheon-node-deployer/pintheon-node-token/Cargo.toml
grep -E "^(name|version) = " pintheon-ipfs-deployer/pintheon-ipfs-token/Cargo.toml
grep -E "^(name|version) = " opus_token/Cargo.toml
```

### Step 2: Determine File Names

**For Workflow Builds:**
- Use package name as-is (with hyphens) + `_v` + version + `.wasm`
- Example: `pintheon-node-token` v0.0.6 → `pintheon-node-token_v0.0.6.wasm`

**For Local Development:**
- Use package name with underscores + `.optimized.wasm`
- Example: `pintheon-node-token` → `pintheon_node_token.optimized.wasm`
- Uses `wasm32-unknown-unknown` target instead of `wasm32v1-none`

### Step 3: Update Import Paths

When you update a dependency contract's version:

1. **Check the new version** in the dependency's `Cargo.toml`
2. **Update the workflow import path** to match the new version
3. **Keep the local development imports** for easier local development

## Current Contract Versions

| Contract | Package Name | Version | Workflow Import | Local Import |
|----------|--------------|---------|-----------------|--------------|
| pintheon-node-token | `pintheon-node-token` | `0.0.6` | `pintheon-node-token_v0.0.6.wasm` | `pintheon_node_token.optimized.wasm` |
| pintheon-ipfs-token | `pintheon-ipfs-token` | `0.0.6` | `pintheon-ipfs-token_v0.0.6.wasm` | `pintheon_ipfs_token.optimized.wasm` |
| opus-token | `opus-token` | `0.0.6` | `opus-token_v0.0.6.wasm` | `opus_token.optimized.wasm` |

## Workflow File Naming Logic

The workflow creates files with this naming pattern:

1. **For imports** (what hvym-collective needs):
   - Use package name as-is: `pintheon-node-token`
   - Add version: `pintheon-node-token_v0.0.6.wasm`
   - This matches what gets uploaded to GitHub releases

2. **For local development**:
   - Convert package name: `pintheon-node-token` → `pintheon_node_token`
   - Add `.optimized.wasm` suffix
   - Result: `pintheon_node_token.optimized.wasm`

## When to Update Imports

Update the import statements when:

1. **Version changes** in a dependency's `Cargo.toml`
2. **Package name changes** in a dependency's `Cargo.toml`
3. **You want to use a different version** of a dependency

## Example: Updating a Contract Version

If you update `pintheon-node-token` from v0.0.6 to v0.0.7:

1. **Update the workflow import in hvym-collective/src/lib.rs:**
   ```rust
   mod pintheon_node_token {
       soroban_sdk::contractimport!(
           file = "../pintheon-node-deployer/pintheon-node-token/target/wasm32v1-none/release/pintheon-node-token_v0.0.7.wasm"
       );
   }
   ```

2. **Update the workflow build step:**
   ```yaml
   - name: Build Pintheon Node Token
     working-directory: pintheon-node-deployer/pintheon-node-token
     run: |
       stellar contract build
       stellar contract optimize --wasm target/wasm32v1-none/release/pintheon_node_token.wasm
       cp target/wasm32v1-none/release/pintheon_node_token.optimized.wasm target/wasm32v1-none/release/pintheon-node-token_v0.0.7.wasm
   ```

3. **Update the upload artifacts path:**
   ```yaml
   path: |
     pintheon-node-deployer/pintheon-node-token/target/wasm32v1-none/release/pintheon-node-token_v0.0.7.wasm
   ```

4. **Update the copy step:**
   ```yaml
   cp temp-deps/pintheon-node-deployer/pintheon-node-token/target/wasm32v1-none/release/pintheon-node-token_v0.0.7.wasm pintheon-node-deployer/pintheon-node-token/target/wasm32v1-none/release/
   ```

## Example: Adding a New Dependency

If you add a new contract `my-new-contract` with package name `my-new-contract` v0.0.1:

1. **Add to workflow build-dependencies job:**
   ```yaml
   - name: Build My New Contract
     working-directory: my-new-contract
     run: |
       stellar contract build
       stellar contract optimize --wasm target/wasm32v1-none/release/my_new_contract.wasm
       cp target/wasm32v1-none/release/my_new_contract.optimized.wasm target/wasm32v1-none/release/my-new-contract_v0.0.1.wasm
   ```

2. **Add import to hvym-collective/src/lib.rs:**
   ```rust
   mod my_new_contract {
       soroban_sdk::contractimport!(
           file = "../my-new-contract/target/wasm32v1-none/release/my-new-contract_v0.0.1.wasm"
       );
   }
   ```

3. **Add local development version:**
   ```rust
   //LOCAL BUILD
   // mod my_new_contract {
   //     soroban_sdk::contractimport!(
   //         file = "../my-new-contract/target/wasm32-unknown-unknown/release/my_new_contract.optimized.wasm"
   //     );
   // }
   ```

## Troubleshooting

### Import Not Found Error
- Check that the file exists in the expected path
- Verify the version number matches the Cargo.toml
- Ensure the workflow copied the file correctly

### Build Target Mismatch
- Workflow uses `wasm32v1-none` target
- Local development uses `wasm32-unknown-unknown` target
- Make sure both versions are available

### Version Mismatch
- Check that the version in `Cargo.toml` matches what you expect
- Update the workflow if the version changes
- Ensure the file name includes the correct version 