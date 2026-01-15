#![cfg(test)]

//! Rent Estimation Tests for pintheon-node-token
//!
//! These tests measure storage footprint and estimate ledger rent costs
//! for the Node token contract operations.

extern crate std;

use crate::{contract::Token, TokenClient};
use soroban_sdk::{Address, Env, String, FromVal, testutils::Address as _};
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
    let ledger = e.ledger();
    let name = String::from_val(e, &"Test Node Token");
    let symbol = String::from_val(e, &"NODE");
    let node_id = String::from_val(e, &"NODE_ID_HASH_12345678901234567890");
    let descriptor = String::from_val(e, &"A test node for the Pintheon network");
    let established = ledger.timestamp();

    let token_contract = e.register(
        Token,
        (
            admin,
            name,
            symbol,
            node_id,
            descriptor,
            established
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
    println!("RENT ESTIMATION REPORT - PINTHEON NODE TOKEN");
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

    // Node-specific metadata
    let (_, usage) = measure_operation(&env, "node_id", || {
        token.node_id();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "descriptor", || {
        token.descriptor();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "established", || {
        token.established();
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

    let (_, usage) = measure_operation(&env, "2. read_node_id", || {
        token.node_id();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "3. read_descriptor", || {
        token.descriptor();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "4. read_established", || {
        token.established();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "5. transfer_to_user2", || {
        token.transfer(&user1, &user2, &1);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "6. balance_check", || {
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
    println!("\n--- STORAGE ENTRY SIZE ESTIMATES - PINTHEON NODE TOKEN ---");
    println!("Based on Soroban storage structure:");
    println!();

    println!("Node Token Metadata (Instance Storage):");
    println!("  - Name string: ~50 bytes");
    println!("  - Symbol string: ~10 bytes");
    println!("  - Decimals (u32): 4 bytes");
    println!("  - Node ID (hash): ~64 bytes");
    println!("  - Descriptor: ~100 bytes");
    println!("  - Established (u64): 8 bytes");
    println!("  - Admin Address: ~32 bytes");
    println!("  - Total instance: ~270 bytes");
    println!();

    println!("Per Balance Entry (Persistent):");
    println!("  - Address key: ~32 bytes");
    println!("  - Balance (i128): 16 bytes");
    println!("  - Total per holder: ~50 bytes");
    println!();

    println!("Rent Cost Estimates (approximate):");
    println!("  - Instance storage (~270B): ~27 stroops per 1M ledgers");
    println!("  - For 100 node tokens: ~2700 stroops per 1M ledgers");
    println!("  - Monthly rent (100 tokens): ~12,000 stroops (~0.0012 XLM)");
}
