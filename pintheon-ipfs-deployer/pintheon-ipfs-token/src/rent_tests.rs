#![cfg(test)]

//! Rent Estimation Tests for pintheon-ipfs-token
//!
//! These tests measure storage footprint and estimate ledger rent costs
//! for the IPFS token contract operations.

extern crate std;

use crate::{contract::Token, TokenClient};
use soroban_sdk::{Address, Env, String as SorobanString, testutils::Address as _};
use std::println;
use std::vec::Vec;

/// Storage cost constants (approximate, based on Soroban fee structure)
const STROOPS_PER_CPU_10K: u64 = 25;
const STROOPS_PER_WRITE_KB: u64 = 11_800;

/// Helper struct to capture resource usage for an operation
#[derive(Debug, Clone)]
pub struct ResourceUsage {
    pub operation: std::string::String,
    pub cpu_instructions: u64,
    pub memory_bytes: u64,
    pub estimated_stroops: u64,
}

impl ResourceUsage {
    fn estimate_stroops(cpu: u64, mem: u64) -> u64 {
        (cpu / 10_000) * STROOPS_PER_CPU_10K + (mem / 1024) * STROOPS_PER_WRITE_KB
    }
}

fn create_token<'a>(e: &Env, admin: &Address) -> TokenClient<'a> {
    let token_contract = e.register(
        Token,
        (
            admin,
            SorobanString::from_str(e, "Test IPFS Token"),
            SorobanString::from_str(e, "IPFS"),
            SorobanString::from_str(e, "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG"),
            SorobanString::from_str(e, "image/png"),
            SorobanString::from_str(e, "https://ipfs.io/ipfs/"),
            Some(SorobanString::from_str(e, "k51qzi5uqu5dlvj2baxnqndepeb86cbk3ng7n3i46uzyxzyqj2xjonzllnv0v8")),
        ),
    );
    TokenClient::new(e, &token_contract)
}

/// Measure resource usage for a closure
fn measure_operation<F, R>(env: &Env, operation_name: &str, f: F) -> (R, ResourceUsage)
where
    F: FnOnce() -> R,
{
    env.cost_estimate().budget().reset_default();
    let result = f();
    let cpu = env.cost_estimate().budget().cpu_instruction_cost();
    let mem = env.cost_estimate().budget().memory_bytes_cost();

    let usage = ResourceUsage {
        operation: std::string::String::from(operation_name),
        cpu_instructions: cpu,
        memory_bytes: mem,
        estimated_stroops: ResourceUsage::estimate_stroops(cpu, mem),
    };

    (result, usage)
}

/// Print a summary table of resource usage
fn print_usage_report(usages: &[ResourceUsage]) {
    println!("\n{}", "=".repeat(80));
    println!("RENT ESTIMATION REPORT - PINTHEON IPFS TOKEN");
    println!("{}", "=".repeat(80));
    println!("{:<30} {:>15} {:>15} {:>15}", "Operation", "CPU Instr.", "Memory (B)", "Est. Stroops");
    println!("{}", "-".repeat(80));

    for usage in usages {
        println!(
            "{:<30} {:>15} {:>15} {:>15}",
            usage.operation,
            usage.cpu_instructions,
            usage.memory_bytes,
            usage.estimated_stroops
        );
    }
    println!("{}", "=".repeat(80));
}

#[test]
fn test_rent_estimation_mint_operation() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let token = create_token(&env, &admin);

    let (_, usage) = measure_operation(&env, "mint", || {
        token.mint(&user, &1);
    });

    println!("\n--- MINT Operation Resource Usage ---");
    println!("CPU Instructions: {}", usage.cpu_instructions);
    println!("Memory Bytes: {}", usage.memory_bytes);
    println!("Estimated Stroops: {}", usage.estimated_stroops);

    assert_eq!(token.balance(&user), 1);
}

#[test]
fn test_rent_estimation_read_operations() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let token = create_token(&env, &admin);

    token.mint(&user, &1);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "balance", || {
        token.balance(&user);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "name", || {
        token.name();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "symbol", || {
        token.symbol();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "decimals", || {
        token.decimals();
    });
    usages.push(usage);

    // IPFS-specific metadata
    let (_, usage) = measure_operation(&env, "ipfs_hash", || {
        token.ipfs_hash(&user);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "file_type", || {
        token.file_type(&user);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "gateways", || {
        token.gateways(&user);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "ipns_hash", || {
        token.ipns_hash(&user);
    });
    usages.push(usage);

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_transfer_operation() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let token = create_token(&env, &admin);

    token.mint(&user1, &10);

    let (_, usage) = measure_operation(&env, "transfer", || {
        token.transfer(&user1, &user2, &5);
    });

    println!("\n--- TRANSFER Operation Resource Usage ---");
    println!("CPU Instructions: {}", usage.cpu_instructions);
    println!("Memory Bytes: {}", usage.memory_bytes);
    println!("Estimated Stroops: {}", usage.estimated_stroops);
}

#[test]
fn test_rent_estimation_approve_allowance() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let token = create_token(&env, &admin);

    token.mint(&user1, &10);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "approve", || {
        token.approve(&user1, &user2, &5, &1000);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "allowance", || {
        token.allowance(&user1, &user2);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "transfer_from", || {
        token.transfer_from(&user2, &user1, &user2, &2);
    });
    usages.push(usage);

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_burn_operations() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let token = create_token(&env, &admin);

    token.mint(&user1, &10);
    token.approve(&user1, &user2, &5, &1000);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "burn", || {
        token.burn(&user1, &2);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "burn_from", || {
        token.burn_from(&user2, &user1, &1);
    });
    usages.push(usage);

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_set_file_metadata() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let token = create_token(&env, &admin);

    let new_ipfs_hash = SorobanString::from_str(&env, "QmNewHashForUpdatedContent123456789");
    let new_file_type = SorobanString::from_str(&env, "application/pdf");
    let new_gateways = SorobanString::from_str(&env, "https://new-gateway.example/");
    let new_ipns_hash = Some(SorobanString::from_str(&env, "k51newipnshash123"));

    let (_, usage) = measure_operation(&env, "set_file_metadata", || {
        token.set_file_metadata(&admin, &new_ipfs_hash, &new_file_type, &new_gateways, &new_ipns_hash);
    });

    println!("\n--- SET_FILE_METADATA Operation Resource Usage ---");
    println!("CPU Instructions: {}", usage.cpu_instructions);
    println!("Memory Bytes: {}", usage.memory_bytes);
    println!("Estimated Stroops: {}", usage.estimated_stroops);
}

#[test]
fn test_rent_estimation_admin_operations() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let token = create_token(&env, &admin);

    let (_, usage) = measure_operation(&env, "set_admin", || {
        token.set_admin(&new_admin);
    });

    println!("\n--- SET_ADMIN Operation Resource Usage ---");
    println!("CPU Instructions: {}", usage.cpu_instructions);
    println!("Memory Bytes: {}", usage.memory_bytes);
    println!("Estimated Stroops: {}", usage.estimated_stroops);
}

#[test]
fn test_rent_estimation_full_workflow() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let token = create_token(&env, &admin);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "1. mint_to_user1", || {
        token.mint(&user1, &1);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "2. read_ipfs_hash", || {
        token.ipfs_hash(&user1);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "3. read_file_type", || {
        token.file_type(&user1);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "4. transfer_to_user2", || {
        token.transfer(&user1, &user2, &1);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "5. balance_check", || {
        token.balance(&user2);
    });
    usages.push(usage);

    println!("\n--- FULL WORKFLOW COST ESTIMATE ---");
    print_usage_report(&usages);

    let total_cpu: u64 = usages.iter().map(|u| u.cpu_instructions).sum();
    let total_mem: u64 = usages.iter().map(|u| u.memory_bytes).sum();
    let total_stroops: u64 = usages.iter().map(|u| u.estimated_stroops).sum();

    println!("\nWorkflow Totals:");
    println!("  Total CPU Instructions: {}", total_cpu);
    println!("  Total Memory: {} bytes", total_mem);
    println!("  Total Estimated Stroops: {}", total_stroops);
    println!("  Estimated XLM: {:.7} XLM", total_stroops as f64 / 10_000_000.0);
}

#[test]
fn test_storage_entry_sizes() {
    println!("\n--- STORAGE ENTRY SIZE ESTIMATES - PINTHEON IPFS TOKEN ---");
    println!("Based on Soroban storage structure:");
    println!();

    println!("File Token Metadata (Instance Storage):");
    println!("  - Name string: ~50 bytes");
    println!("  - Symbol string: ~10 bytes");
    println!("  - IPFS Hash (CIDv0): ~46 bytes");
    println!("  - IPFS Hash (CIDv1): ~59 bytes");
    println!("  - File Type: ~20 bytes");
    println!("  - Gateways string: ~50 bytes");
    println!("  - IPNS Hash (optional): ~62 bytes");
    println!("  - Admin Address: ~32 bytes");
    println!("  - Total instance: ~280-330 bytes");
    println!();

    println!("Per Balance Entry (Persistent):");
    println!("  - Address key: ~32 bytes");
    println!("  - Balance (i128): 16 bytes");
    println!("  - Total per holder: ~50 bytes");
    println!();

    println!("Rent Cost Estimates (approximate):");
    println!("  - Instance storage (~300B): ~30 stroops per 1M ledgers");
    println!("  - For 100 file tokens: ~3000 stroops per 1M ledgers");
    println!("  - Monthly rent (100 tokens): ~13,000 stroops (~0.0013 XLM)");
}
