#![cfg(test)]

//! Rent Estimation Tests for hvym-collective
//!
//! These tests measure storage footprint and estimate ledger rent costs
//! for various operations on the collective contract.
//!
//! Fee Structure (based on XLM price ~$0.2379):
//! - Join Fee: 210 XLM (~$50 USD) - cooperative membership
//! - Mint Fee: 0.5 XLM (~$0.12 USD) - per file published
//! - Opus Reward: 0.2 XLM (~$0.05 USD) - reward to node operators
//! - Misc Costs: ~21 XLM (~$5 USD) - platform operational expense per user

extern crate std;

use crate::{CollectiveContract, CollectiveContractClient};
use soroban_sdk::{
    token, Address, Env, String, FromVal,
    testutils::Address as _,
};
use std::println;
use std::vec::Vec;

/// Storage cost constants (approximate, based on Soroban fee structure)
const STROOPS_PER_CPU_10K: u64 = 25;
const STROOPS_PER_WRITE_KB: u64 = 11_800;

// =============================================================================
// FEE CONSTANTS (Production Values)
// =============================================================================
// XLM Price: ~$0.2379 USD (reference rate)
// 1 XLM = 10,000,000 stroops

/// Join Fee: 210 XLM (~$50 USD) - One-time cooperative membership fee
const JOIN_FEE_STROOPS: u32 = 2_100_000_000; // 210 XLM

/// Mint Fee: 0.5 XLM (~$0.12 USD) - Per file published
const MINT_FEE_STROOPS: u32 = 5_000_000; // 0.5 XLM

/// Opus Reward: 0.2 XLM (~$0.05 USD) - Reward to node operators per file
const OPUS_REWARD_STROOPS: u32 = 2_000_000; // 0.2 XLM

/// Opus Split: 10% of Opus rewards go to collective treasury (default)
/// Range: 0-30% (0 = all to publisher, 30 = max to collective)
const OPUS_SPLIT_PERCENT: u32 = 10; // 10% to collective, 90% to publisher

/// Miscellaneous Costs: 21 XLM (~$5 USD) - Platform operational expense per user
/// (website hosting, onboarding support, etc.) - tracked as expense, not collected
const MISC_COST_STROOPS: u32 = 210_000_000; // 21 XLM

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
    println!("RENT ESTIMATION REPORT - HVYM COLLECTIVE");
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
    // Mint enough to cover join fee (210 XLM = 2.1B stroops)
    mint_tokens(&pay_token_client, &admin, &user, &(JOIN_FEE_STROOPS as i128 * 2));

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, JOIN_FEE_STROOPS, MINT_FEE_STROOPS, &pay_token_addr, OPUS_REWARD_STROOPS, OPUS_SPLIT_PERCENT))
    );

    let (_, usage) = measure_operation(&env, "join", || {
        collective.join(&user);
    });

    println!("\n--- JOIN Operation Resource Usage ---");
    println!("CPU Instructions: {}", usage.cpu_instructions);
    println!("Memory Bytes: {}", usage.memory_bytes);
    println!("Estimated Stroops: {}", usage.estimated_stroops);
    println!("Join Fee: {} stroops ({} XLM / ~$50 USD)", JOIN_FEE_STROOPS, JOIN_FEE_STROOPS as f64 / 10_000_000.0);

    assert!(collective.is_member(&user));
}

#[test]
fn test_rent_estimation_read_operations() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &(JOIN_FEE_STROOPS as i128 * 2));

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, JOIN_FEE_STROOPS, MINT_FEE_STROOPS, &pay_token_addr, OPUS_REWARD_STROOPS, OPUS_SPLIT_PERCENT))
    );

    collective.join(&user);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "symbol", || {
        collective.symbol();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "join_fee", || {
        collective.join_fee();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "mint_fee", || {
        collective.mint_fee();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "opus_reward", || {
        collective.opus_reward();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "is_member", || {
        collective.is_member(&user);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "is_admin", || {
        collective.is_admin(&user);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "member_paid", || {
        collective.member_paid(&user);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "get_admin_list", || {
        collective.get_admin_list();
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

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, JOIN_FEE_STROOPS, MINT_FEE_STROOPS, &pay_token_addr, OPUS_REWARD_STROOPS, OPUS_SPLIT_PERCENT))
    );

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "add_admin", || {
        collective.add_admin(&admin, &new_admin);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "update_join_fee", || {
        collective.update_join_fee(&admin, &200_u32);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "update_mint_fee", || {
        collective.update_mint_fee(&admin, &20_u32);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "update_opus_reward", || {
        collective.update_opus_reward(&admin, &10_u32);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "remove_admin", || {
        collective.remove_admin(&admin, &new_admin);
    });
    usages.push(usage);

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_fund_withdraw() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let recipient = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user, &(JOIN_FEE_STROOPS as i128 * 2));

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, JOIN_FEE_STROOPS, MINT_FEE_STROOPS, &pay_token_addr, OPUS_REWARD_STROOPS, OPUS_SPLIT_PERCENT))
    );

    collective.join(&user);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "fund_contract", || {
        collective.fund_contract(&user, &500);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "withdraw", || {
        collective.withdraw(&admin, &recipient);
    });
    usages.push(usage);

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_publish_operations() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    // Need enough for join + multiple mint fees
    mint_tokens(&pay_token_client, &admin, &user, &(JOIN_FEE_STROOPS as i128 + MINT_FEE_STROOPS as i128 * 10));

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, JOIN_FEE_STROOPS, MINT_FEE_STROOPS, &pay_token_addr, OPUS_REWARD_STROOPS, OPUS_SPLIT_PERCENT))
    );

    let ipfs_hash = String::from_val(&env, &"QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG");
    let publisher = String::from_val(&env, &"publisher_key_123");
    let recipient = String::from_val(&env, &"recipient_key_456");

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "publish_file", || {
        collective.publish_file(&user, &publisher, &ipfs_hash);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "publish_encrypted_share", || {
        collective.publish_encrypted_share(&user, &publisher, &recipient, &ipfs_hash);
    });
    usages.push(usage);

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_scaling_members() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, JOIN_FEE_STROOPS, MINT_FEE_STROOPS, &pay_token_addr, OPUS_REWARD_STROOPS, OPUS_SPLIT_PERCENT))
    );

    let mut usages: Vec<ResourceUsage> = Vec::new();

    for i in 0..10 {
        let user = Address::generate(&env);
        mint_tokens(&pay_token_client, &admin, &user, &(JOIN_FEE_STROOPS as i128 * 2));

        let op_name = std::format!("join_member_{}", i);
        let (_, usage) = measure_operation(&env, &op_name, || {
            collective.join(&user);
        });
        usages.push(usage);
    }

    println!("\n--- SCALING TEST: Adding 10 Members ---");
    print_usage_report(&usages);

    let total_cpu: u64 = usages.iter().map(|u| u.cpu_instructions).sum();
    let total_mem: u64 = usages.iter().map(|u| u.memory_bytes).sum();
    let total_stroops: u64 = usages.iter().map(|u| u.estimated_stroops).sum();

    println!("\nSummary for 10 members:");
    println!("  Total CPU: {}", total_cpu);
    println!("  Total Memory: {} bytes", total_mem);
    println!("  Total Est. Stroops: {}", total_stroops);
    println!("  Avg CPU per member: {}", total_cpu / 10);
    println!("  Avg Memory per member: {} bytes", total_mem / 10);
    println!("\n  --- Revenue from 10 Members ---");
    println!("  Join Fees Collected: {} XLM (~${:.2} USD)",
        (JOIN_FEE_STROOPS as u64 * 10) as f64 / 10_000_000.0,
        (JOIN_FEE_STROOPS as f64 / 10_000_000.0) * 10.0 * 0.2379);
    println!("  Misc Costs (platform expense): {} XLM (~${:.2} USD)",
        (MISC_COST_STROOPS as u64 * 10) as f64 / 10_000_000.0,
        (MISC_COST_STROOPS as f64 / 10_000_000.0) * 10.0 * 0.2379);
}

#[test]
fn test_rent_estimation_full_workflow() {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let user1 = Address::generate(&env);
    let user2 = Address::generate(&env);
    let new_admin = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);
    mint_tokens(&pay_token_client, &admin, &user1, &(JOIN_FEE_STROOPS as i128 * 2));
    mint_tokens(&pay_token_client, &admin, &user2, &(JOIN_FEE_STROOPS as i128 * 2));

    let collective = CollectiveContractClient::new(
        &env,
        &env.register(CollectiveContract, (&admin, JOIN_FEE_STROOPS, MINT_FEE_STROOPS, &pay_token_addr, OPUS_REWARD_STROOPS, OPUS_SPLIT_PERCENT))
    );

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "1. update_join_fee", || {
        collective.update_join_fee(&admin, &50_u32);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "2. add_admin", || {
        collective.add_admin(&admin, &new_admin);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "3. user1_join", || {
        collective.join(&user1);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "4. user2_join", || {
        collective.join(&user2);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "5. fund_contract", || {
        collective.fund_contract(&user1, &200);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "6. get_admin_list", || {
        collective.get_admin_list();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "7. is_member_check", || {
        collective.is_member(&user1);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "8. member_paid", || {
        collective.member_paid(&user1);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "9. remove_member", || {
        collective.remove(&admin, &user2);
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
    println!("\n{}", "=".repeat(80));
    println!("STORAGE ENTRY SIZE ESTIMATES - HVYM COLLECTIVE");
    println!("{}", "=".repeat(80));
    println!("Based on Soroban storage structure:");
    println!();

    println!("--- PRODUCTION FEE STRUCTURE (XLM @ ~$0.2379) ---");
    println!("  Join Fee:     {} XLM (~${:.2} USD)", JOIN_FEE_STROOPS as f64 / 10_000_000.0, JOIN_FEE_STROOPS as f64 / 10_000_000.0 * 0.2379);
    println!("  Mint Fee:     {} XLM (~${:.2} USD)", MINT_FEE_STROOPS as f64 / 10_000_000.0, MINT_FEE_STROOPS as f64 / 10_000_000.0 * 0.2379);
    println!("  Opus Reward:  {} XLM (~${:.4} USD)", OPUS_REWARD_STROOPS as f64 / 10_000_000.0, OPUS_REWARD_STROOPS as f64 / 10_000_000.0 * 0.2379);
    println!("  Opus Split:   {}% to collective, {}% to publisher", OPUS_SPLIT_PERCENT, 100 - OPUS_SPLIT_PERCENT);
    println!("  Misc Costs:   {} XLM (~${:.2} USD) [platform expense]", MISC_COST_STROOPS as f64 / 10_000_000.0, MISC_COST_STROOPS as f64 / 10_000_000.0 * 0.2379);
    println!();

    println!("--- STORAGE SIZE ESTIMATES ---");
    println!();
    println!("Member Entry (estimated):");
    println!("  - Address: ~32 bytes");
    println!("  - Paid (u32): 4 bytes");
    println!("  - Total per member: ~36-50 bytes");
    println!();

    println!("Collective Struct (estimated):");
    println!("  - Symbol: ~10 bytes");
    println!("  - Join Fee (u32): 4 bytes");
    println!("  - Mint Fee (u32): 4 bytes");
    println!("  - Pay Token Address: ~32 bytes");
    println!("  - Opus Reward (u32): 4 bytes");
    println!("  - Total: ~60 bytes");
    println!();

    println!("AdminList (Vec<Address>):");
    println!("  - Base overhead: ~16 bytes");
    println!("  - Per admin: ~32 bytes");
    println!("  - 5 admins: ~176 bytes");
    println!();

    println!("--- RENT COST ESTIMATES ---");
    println!("  - Persistent storage: ~100 stroops/KB per 1M ledgers (~6.9 days)");
    println!("  - For 100 members (~5KB): ~500 stroops per 1M ledgers");
    println!("  - Monthly rent (100 members): ~2,200 stroops (~0.00022 XLM)");
    println!();

    println!("--- SHARD ECONOMICS (75 members, 5 new/month, 300 files/month) ---");
    let monthly_join_revenue = JOIN_FEE_STROOPS as f64 * 5.0 / 10_000_000.0;
    let monthly_mint_revenue = MINT_FEE_STROOPS as f64 * 300.0 / 10_000_000.0;

    // Opus split: collective gets OPUS_SPLIT_PERCENT%, publishers get the rest
    let total_opus_minted = OPUS_REWARD_STROOPS as f64 * 300.0 / 10_000_000.0;
    let collective_opus_share = total_opus_minted * (OPUS_SPLIT_PERCENT as f64 / 100.0);
    let publisher_opus_share = total_opus_minted - collective_opus_share;

    let monthly_misc_cost = MISC_COST_STROOPS as f64 * 5.0 / 10_000_000.0;
    let total_revenue = monthly_join_revenue + monthly_mint_revenue;

    // Note: Opus is minted, not spent from treasury, so it's not a direct "cost"
    // The collective EARNS its share of Opus tokens
    let total_costs = monthly_misc_cost; // Only misc costs are actual expenses

    println!("  Revenue (XLM):");
    println!("    Join fees (5 × {} XLM):  {:.2} XLM (~${:.2})",
        JOIN_FEE_STROOPS as f64 / 10_000_000.0, monthly_join_revenue, monthly_join_revenue * 0.2379);
    println!("    Mint fees (300 × {} XLM): {:.2} XLM (~${:.2})",
        MINT_FEE_STROOPS as f64 / 10_000_000.0, monthly_mint_revenue, monthly_mint_revenue * 0.2379);
    println!("    Total XLM Revenue:       {:.2} XLM (~${:.2})", total_revenue, total_revenue * 0.2379);
    println!();
    println!("  Opus Token Distribution (minted, not spent):");
    println!("    Total Opus minted:       {:.2} OPUS", total_opus_minted);
    println!("    → Publishers ({}%):       {:.2} OPUS", 100 - OPUS_SPLIT_PERCENT, publisher_opus_share);
    println!("    → Collective ({}%):       {:.2} OPUS [TREASURY GAIN]", OPUS_SPLIT_PERCENT, collective_opus_share);
    println!();
    println!("  Costs (XLM):");
    println!("    Misc costs (5 × {} XLM): {:.2} XLM (~${:.2})",
        MISC_COST_STROOPS as f64 / 10_000_000.0, monthly_misc_cost, monthly_misc_cost * 0.2379);
    println!();
    let net_xlm_profit = total_revenue - total_costs;
    println!("  NET XLM PROFIT: {:.2} XLM (~${:.2})", net_xlm_profit, net_xlm_profit * 0.2379);
    println!("  XLM Profit Margin: {:.1}%", (net_xlm_profit / total_revenue) * 100.0);
    println!();
    println!("  PLUS: Collective Treasury gains {:.2} OPUS/month", collective_opus_share);
    println!("  (If OPUS reaches $1: additional ${:.2}/month value)", collective_opus_share);
}
