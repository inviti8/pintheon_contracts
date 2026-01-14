#![cfg(test)]

//! Rent Estimation Tests for hvym-roster
//!
//! These tests measure storage footprint and estimate ledger rent costs
//! for various operations on the roster contract.
//!
//! Note: Measurements in native Rust tests may be underestimated compared
//! to actual WASM execution. For production estimates, use RPC simulation.

extern crate std;

use crate::{RosterContract, RosterContractClient};
use soroban_sdk::{
    token, Address, Env, String, FromVal,
    testutils::Address as _,
};
use std::println;
use std::vec::Vec;

/// Storage cost constants (approximate, based on Soroban fee structure)
/// These are rough estimates - actual costs depend on network conditions
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
        // Rough estimate based on CPU usage
        (cpu / 10_000) * STROOPS_PER_CPU_10K + (mem / 1024) * STROOPS_PER_WRITE_KB
    }
}

fn create_token_contract<'a>(
    e: &Env,
    admin: &Address,
) -> (token::Client<'a>, Address) {
    let token_address = e.register_stellar_asset_contract_v2(admin.clone()).address();
    let token = token::Client::new(e, &token_address);

    let admin_client = token::StellarAssetClient::new(e, &token_address);
    admin_client.mint(admin, &1_000_000_000_000_000_000);

    (token, token_address.clone().into())
}

fn mint_tokens(token_client: &token::Client, _from: &Address, to: &Address, amount: &i128) {
    let admin_client = token::StellarAssetClient::new(&token_client.env, &token_client.address);
    admin_client.mint(to, amount);
}

/// Measure resource usage for a closure
fn measure_operation<F, R>(env: &Env, operation_name: &str, f: F) -> (R, ResourceUsage)
where
    F: FnOnce() -> R,
{
    // Reset budget before operation
    env.cost_estimate().budget().reset_default();

    // Execute the operation
    let result = f();

    // Capture resource usage
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
    println!("RENT ESTIMATION REPORT");
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
fn test_rent_estimation_join_operation() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &10000);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 100_u32, &pay_token_addr))
    );

    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon_data");

    // Measure the join operation
    let (_, usage) = measure_operation(&env, "join", || {
        roster.join(&user, &name, &canon);
    });

    println!("\n--- JOIN Operation Resource Usage ---");
    println!("CPU Instructions: {}", usage.cpu_instructions);
    println!("Memory Bytes: {}", usage.memory_bytes);
    println!("Estimated Stroops: {}", usage.estimated_stroops);

    // Verify the operation succeeded
    assert!(roster.is_member(&user));
}

#[test]
fn test_rent_estimation_update_canon() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &10000);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 100_u32, &pay_token_addr))
    );

    // Setup: user joins first
    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"initial_canon");
    roster.join(&user, &name, &canon);

    let new_canon = String::from_val(&env, &"updated_canon_with_more_data_here");

    // Measure the update_canon operation
    let (_, usage) = measure_operation(&env, "update_canon", || {
        roster.update_canon(&user, &user, &new_canon);
    });

    println!("\n--- UPDATE_CANON Operation Resource Usage ---");
    println!("CPU Instructions: {}", usage.cpu_instructions);
    println!("Memory Bytes: {}", usage.memory_bytes);
    println!("Estimated Stroops: {}", usage.estimated_stroops);
}

#[test]
fn test_rent_estimation_read_operations() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &10000);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 100_u32, &pay_token_addr))
    );

    // Setup: user joins first
    let name = String::from_val(&env, &"Alice");
    let canon = String::from_val(&env, &"alice_canon");
    roster.join(&user, &name, &canon);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    // Measure symbol()
    let (_, usage) = measure_operation(&env, "symbol", || {
        roster.symbol();
    });
    usages.push(usage);

    // Measure join_fee()
    let (_, usage) = measure_operation(&env, "join_fee", || {
        roster.join_fee();
    });
    usages.push(usage);

    // Measure is_member()
    let (_, usage) = measure_operation(&env, "is_member", || {
        roster.is_member(&user);
    });
    usages.push(usage);

    // Measure is_admin()
    let (_, usage) = measure_operation(&env, "is_admin", || {
        roster.is_admin(&user);
    });
    usages.push(usage);

    // Measure get_canon()
    let (_, usage) = measure_operation(&env, "get_canon", || {
        roster.get_canon(&user);
    });
    usages.push(usage);

    // Measure member_paid()
    let (_, usage) = measure_operation(&env, "member_paid", || {
        roster.member_paid(&user);
    });
    usages.push(usage);

    // Measure get_admin_list()
    let (_, usage) = measure_operation(&env, "get_admin_list", || {
        roster.get_admin_list();
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
    let (_, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 100_u32, &pay_token_addr))
    );

    let mut usages: Vec<ResourceUsage> = Vec::new();

    // Measure add_admin()
    let (_, usage) = measure_operation(&env, "add_admin", || {
        roster.add_admin(&admin, &new_admin);
    });
    usages.push(usage);

    // Measure update_join_fee()
    let (_, usage) = measure_operation(&env, "update_join_fee", || {
        roster.update_join_fee(&admin, &200_u32);
    });
    usages.push(usage);

    // Measure remove_admin()
    let (_, usage) = measure_operation(&env, "remove_admin", || {
        roster.remove_admin(&admin, &new_admin);
    });
    usages.push(usage);

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_scaling_members() {
    //! Tests how storage costs scale as more members are added

    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
    );

    let mut usages: Vec<ResourceUsage> = Vec::new();

    // Add members and measure cost for each
    for i in 0..10 {
        let user = Address::generate(&env);
        mint_tokens(&pay_token_client, &admin, &user, &1000);

        let name_str = std::format!("User{}", i);
        let canon_str = std::format!("canon_data_{}", i);
        let name = String::from_val(&env, &name_str.as_str());
        let canon = String::from_val(&env, &canon_str.as_str());

        let op_name = std::format!("join_member_{}", i);
        let (_, usage) = measure_operation(&env, &op_name, || {
            roster.join(&user, &name, &canon);
        });
        usages.push(usage);
    }

    println!("\n--- SCALING TEST: Adding 10 Members ---");
    print_usage_report(&usages);

    // Calculate average and total
    let total_cpu: u64 = usages.iter().map(|u| u.cpu_instructions).sum();
    let total_mem: u64 = usages.iter().map(|u| u.memory_bytes).sum();
    let total_stroops: u64 = usages.iter().map(|u| u.estimated_stroops).sum();

    println!("\nSummary for 10 members:");
    println!("  Total CPU: {}", total_cpu);
    println!("  Total Memory: {} bytes", total_mem);
    println!("  Total Est. Stroops: {}", total_stroops);
    println!("  Avg CPU per member: {}", total_cpu / 10);
    println!("  Avg Memory per member: {} bytes", total_mem / 10);
}

#[test]
fn test_rent_estimation_canon_size_impact() {
    //! Tests how canon string size affects storage costs

    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    // Test with different canon sizes
    let canon_sizes = [10, 25, 50, 75, 100]; // MAX_STRING_LENGTH is 100

    for size in canon_sizes {
        let user = Address::generate(&env);
        mint_tokens(&pay_token_client, &admin, &user, &1000);

        let roster = RosterContractClient::new(
            &env,
            &env.register(RosterContract, (&admin, 10_u32, &pay_token_addr))
        );

        let name = String::from_val(&env, &"User");
        let canon_str: std::string::String = "x".repeat(size);
        let canon = String::from_val(&env, &canon_str.as_str());

        let op_name = std::format!("join_canon_{}_chars", size);
        let (_, usage) = measure_operation(&env, &op_name, || {
            roster.join(&user, &name, &canon);
        });
        usages.push(usage);
    }

    println!("\n--- CANON SIZE IMPACT TEST ---");
    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_full_workflow() {
    //! Tests a complete workflow and provides total cost estimate

    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user1, &10000);
    mint_tokens(&pay_token_client, &admin, &user2, &10000);

    let roster = RosterContractClient::new(
        &env,
        &env.register(RosterContract, (&admin, 100_u32, &pay_token_addr))
    );

    let mut usages: Vec<ResourceUsage> = Vec::new();

    // 1. Admin updates join fee
    let (_, usage) = measure_operation(&env, "1. update_join_fee", || {
        roster.update_join_fee(&admin, &50_u32);
    });
    usages.push(usage);

    // 2. Add another admin
    let (_, usage) = measure_operation(&env, "2. add_admin", || {
        roster.add_admin(&admin, &new_admin);
    });
    usages.push(usage);

    // 3. User1 joins
    let name1 = String::from_val(&env, &"Alice");
    let canon1 = String::from_val(&env, &"alice_canon");
    let (_, usage) = measure_operation(&env, "3. user1_join", || {
        roster.join(&user1, &name1, &canon1);
    });
    usages.push(usage);

    // 4. User2 joins
    let name2 = String::from_val(&env, &"Bob");
    let canon2 = String::from_val(&env, &"bob_canon");
    let (_, usage) = measure_operation(&env, "4. user2_join", || {
        roster.join(&user2, &name2, &canon2);
    });
    usages.push(usage);

    // 5. User1 updates their canon
    let new_canon = String::from_val(&env, &"alice_updated_canon");
    let (_, usage) = measure_operation(&env, "5. update_canon", || {
        roster.update_canon(&user1, &user1, &new_canon);
    });
    usages.push(usage);

    // 6. Query operations
    let (_, usage) = measure_operation(&env, "6. get_admin_list", || {
        roster.get_admin_list();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "7. is_member_check", || {
        roster.is_member(&user1);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "8. get_canon", || {
        roster.get_canon(&user1);
    });
    usages.push(usage);

    // 9. Admin removes user2
    let (_, usage) = measure_operation(&env, "9. remove_member", || {
        roster.remove(&admin, &user2);
    });
    usages.push(usage);

    println!("\n--- FULL WORKFLOW COST ESTIMATE ---");
    print_usage_report(&usages);

    // Calculate totals
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
    //! Estimates the size of different storage entries

    println!("\n--- STORAGE ENTRY SIZE ESTIMATES ---");
    println!("Based on Soroban storage structure:");
    println!();

    // Estimate Member struct size
    // Address: ~32 bytes
    // String (name, max 100): ~100 bytes + overhead
    // String (canon, max 100): ~100 bytes + overhead
    // u32 (paid): 4 bytes
    // Total Member: ~256-300 bytes estimated

    println!("Member Struct (estimated):");
    println!("  - Address: ~32 bytes");
    println!("  - Name (max 100 chars): ~100 bytes + overhead");
    println!("  - Canon (max 100 chars): ~100 bytes + overhead");
    println!("  - Paid (u32): 4 bytes");
    println!("  - Total per member: ~250-300 bytes");
    println!();

    // Roster struct size
    // Symbol: ~10 bytes
    // u32: 4 bytes
    // Address: ~32 bytes
    println!("Roster Struct (estimated):");
    println!("  - Symbol: ~10 bytes");
    println!("  - Join Fee (u32): 4 bytes");
    println!("  - Pay Token Address: ~32 bytes");
    println!("  - Total: ~50 bytes");
    println!();

    // AdminList - Vec<Address>
    println!("AdminList (Vec<Address>):");
    println!("  - Base overhead: ~16 bytes");
    println!("  - Per admin: ~32 bytes");
    println!("  - 5 admins: ~176 bytes");
    println!();

    // Rent cost estimate per ledger (rough)
    // Persistent storage: ~100 stroops per KB per 1M ledgers (~6.9 days)
    println!("Rent Cost Estimates (approximate):");
    println!("  - Persistent storage: ~100 stroops/KB per 1M ledgers (~6.9 days)");
    println!("  - For 100 members (~30KB): ~3000 stroops per 1M ledgers");
    println!("  - Monthly rent (100 members): ~13,000 stroops (~0.0013 XLM)");
}
