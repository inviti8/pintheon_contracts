#![cfg(test)]

//! Rent Estimation Tests for opus_token
//!
//! These tests measure storage footprint and estimate ledger rent costs
//! for the OPUS token contract operations.

extern crate std;

use crate::{contract::Token, TokenClient};
use soroban_sdk::{Address, Env, testutils::Address as _};
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
    let token_contract = e.register(Token, (admin,));
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
    println!("RENT ESTIMATION REPORT - OPUS TOKEN");
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
        token.mint(&user, &1000);
    });

    println!("\n--- MINT Operation Resource Usage ---");
    println!("CPU Instructions: {}", usage.cpu_instructions);
    println!("Memory Bytes: {}", usage.memory_bytes);
    println!("Estimated Stroops: {}", usage.estimated_stroops);

    assert_eq!(token.balance(&user), 1000);
}

#[test]
fn test_rent_estimation_transfer_operation() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let token = create_token(&env, &admin);

    token.mint(&user1, &1000);

    let (_, usage) = measure_operation(&env, "transfer", || {
        token.transfer(&user1, &user2, &500);
    });

    println!("\n--- TRANSFER Operation Resource Usage ---");
    println!("CPU Instructions: {}", usage.cpu_instructions);
    println!("Memory Bytes: {}", usage.memory_bytes);
    println!("Estimated Stroops: {}", usage.estimated_stroops);

    assert_eq!(token.balance(&user1), 500);
    assert_eq!(token.balance(&user2), 500);
}

#[test]
fn test_rent_estimation_read_operations() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let token = create_token(&env, &admin);

    token.mint(&user, &1000);

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

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_approve_allowance() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let token = create_token(&env, &admin);

    token.mint(&user1, &1000);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "approve", || {
        token.approve(&user1, &user2, &500, &1000);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "allowance", || {
        token.allowance(&user1, &user2);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "transfer_from", || {
        token.transfer_from(&user2, &user1, &user2, &200);
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

    token.mint(&user1, &1000);
    token.approve(&user1, &user2, &500, &1000);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "burn", || {
        token.burn(&user1, &200);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "burn_from", || {
        token.burn_from(&user2, &user1, &100);
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
fn test_rent_estimation_scaling_balances() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let token = create_token(&env, &admin);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    for i in 0..10 {
        let user = Address::generate(&env);
        let op_name = std::format!("mint_user_{}", i);
        let (_, usage) = measure_operation(&env, &op_name, || {
            token.mint(&user, &1000);
        });
        usages.push(usage);
    }

    println!("\n--- SCALING TEST: Minting to 10 Users ---");
    print_usage_report(&usages);

    let total_cpu: u64 = usages.iter().map(|u| u.cpu_instructions).sum();
    let total_mem: u64 = usages.iter().map(|u| u.memory_bytes).sum();
    let total_stroops: u64 = usages.iter().map(|u| u.estimated_stroops).sum();

    println!("\nSummary for 10 mints:");
    println!("  Total CPU: {}", total_cpu);
    println!("  Total Memory: {} bytes", total_mem);
    println!("  Total Est. Stroops: {}", total_stroops);
    println!("  Avg CPU per mint: {}", total_cpu / 10);
    println!("  Avg Memory per mint: {} bytes", total_mem / 10);
}

#[test]
fn test_rent_estimation_full_workflow() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let user3 = Address::generate(&env);
    let token = create_token(&env, &admin);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "1. mint_to_user1", || {
        token.mint(&user1, &1000);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "2. mint_to_user2", || {
        token.mint(&user2, &500);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "3. transfer_u1_to_u2", || {
        token.transfer(&user1, &user2, &200);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "4. approve_u2_for_u3", || {
        token.approve(&user2, &user3, &300, &1000);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "5. transfer_from", || {
        token.transfer_from(&user3, &user2, &user1, &100);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "6. burn", || {
        token.burn(&user1, &50);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "7. balance_check", || {
        token.balance(&user1);
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
    println!("\n--- STORAGE ENTRY SIZE ESTIMATES - OPUS TOKEN ---");
    println!("Based on Soroban storage structure:");
    println!();

    println!("Token Metadata (Instance Storage):");
    println!("  - Name string: ~20 bytes");
    println!("  - Symbol string: ~10 bytes");
    println!("  - Decimals (u32): 4 bytes");
    println!("  - Admin Address: ~32 bytes");
    println!("  - Total instance: ~70 bytes");
    println!();

    println!("Per Balance Entry (Persistent):");
    println!("  - Address key: ~32 bytes");
    println!("  - Balance (i128): 16 bytes");
    println!("  - Total per holder: ~50 bytes");
    println!();

    println!("Per Allowance Entry (Temporary):");
    println!("  - From Address: ~32 bytes");
    println!("  - Spender Address: ~32 bytes");
    println!("  - Amount (i128): 16 bytes");
    println!("  - Expiration (u32): 4 bytes");
    println!("  - Total per allowance: ~90 bytes");
    println!();

    println!("Rent Cost Estimates (approximate):");
    println!("  - Instance storage (~70B): ~7 stroops per 1M ledgers");
    println!("  - For 1000 holders (~50KB): ~5000 stroops per 1M ledgers");
    println!("  - Monthly rent (1000 holders): ~22,000 stroops (~0.0022 XLM)");
}
