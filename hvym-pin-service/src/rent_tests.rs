#![cfg(test)]

extern crate std;
extern crate alloc;

use crate::{PinServiceContract, PinServiceContractClient};
use crate::types::EPOCH_LENGTH;
use soroban_sdk::{
    token, Address, Env, String, FromVal,
    testutils::{Address as _, Ledger},
};
use std::println;
use std::vec::Vec;

const STROOPS_PER_CPU_10K: u64 = 25;
const STROOPS_PER_WRITE_KB: u64 = 11_800;

const PIN_FEE: u32 = 100;
const JOIN_FEE: u32 = 50;
const MIN_PIN_QTY: u32 = 3;
const MIN_OFFER_PRICE: u32 = 10;
const PINNER_STAKE: u32 = 10_000;
const MAX_CYCLES: u32 = 60;
const FLAG_THRESHOLD: u32 = 3;

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

fn print_usage_report(usages: &[ResourceUsage]) {
    println!("\n{}", "=".repeat(80));
    println!("RENT ESTIMATION REPORT - HVYM PIN SERVICE");
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

fn setup_rent_env<'a>() -> (
    Env,
    PinServiceContractClient<'a>,
    Address,
    token::Client<'a>,
    Address,
) {
    let env = Env::default();
    env.mock_all_auths();

    let admin = Address::generate(&env);
    let (pay_token_client, pay_token_addr) = create_token_contract(&env, &admin);

    let client = PinServiceContractClient::new(
        &env,
        &env.register(
            PinServiceContract,
            (
                &admin,
                PIN_FEE,
                JOIN_FEE,
                MIN_PIN_QTY,
                MIN_OFFER_PRICE,
                PINNER_STAKE,
                &pay_token_addr,
                MAX_CYCLES,
                FLAG_THRESHOLD,
            ),
        ),
    );

    (env, client, admin, pay_token_client, pay_token_addr)
}

#[test]
fn test_rent_estimation_pinner_operations() {
    let (env, client, admin, pay_token_client, _) = setup_rent_env();

    let pinner = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &pinner, &200_000);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let node_id = String::from_val(&env, &"12D3KooWtest");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");

    let (_, usage) = measure_operation(&env, "join_as_pinner", || {
        client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "is_pinner", || {
        client.is_pinner(&pinner);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "get_pinner", || {
        client.get_pinner(&pinner);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "get_pinner_count", || {
        client.get_pinner_count();
    });
    usages.push(usage);

    let new_node = String::from_val(&env, &"12D3KooWnew");
    let (_, usage) = measure_operation(&env, "update_pinner", || {
        client.update_pinner(&pinner, &Some(new_node.clone()), &None::<String>, &None::<u32>, &None::<bool>);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "leave_as_pinner", || {
        client.leave_as_pinner(&pinner);
    });
    usages.push(usage);

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_slot_operations() {
    let (env, client, admin, pay_token_client, _) = setup_rent_env();

    // Register a pinner first
    let pinner = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &pinner, &200_000);
    let node_id = String::from_val(&env, &"12D3KooWtest");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");
    client.join_as_pinner(&pinner, &node_id, &multiaddr, &5);

    let publisher = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &publisher, &1_000_000);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    let cid = String::from_val(&env, &"QmRentTest");
    let gateway = String::from_val(&env, &"https://gateway.test");
    let (slot_id, usage) = measure_operation(&env, "create_pin", || {
        client.create_pin(&publisher, &cid, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY)
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "get_slot", || {
        client.get_slot(&slot_id);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "get_all_slots", || {
        client.get_all_slots();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "has_available_slots", || {
        client.has_available_slots();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "collect_pin", || {
        client.collect_pin(&pinner, &slot_id);
    });
    usages.push(usage);

    // Create another pin for cancel test
    let cid2 = String::from_val(&env, &"QmRentTest2");
    let slot2 = client.create_pin(&publisher, &cid2, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);

    let (_, usage) = measure_operation(&env, "cancel_pin", || {
        client.cancel_pin(&publisher, &slot2);
    });
    usages.push(usage);

    // Create pin for expiration test
    let cid3 = String::from_val(&env, &"QmRentTest3");
    let slot3 = client.create_pin(&publisher, &cid3, &gateway, &MIN_OFFER_PRICE, &MIN_PIN_QTY);

    env.ledger().with_mut(|li| {
        li.sequence_number += EPOCH_LENGTH * MAX_CYCLES + 1;
    });

    let (_, usage) = measure_operation(&env, "clear_expired_slot", || {
        client.clear_expired_slot(&slot3);
    });
    usages.push(usage);

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_admin_operations() {
    let (env, client, admin, _, _) = setup_rent_env();

    let new_admin = Address::generate(&env);
    let mut usages: Vec<ResourceUsage> = Vec::new();

    let (_, usage) = measure_operation(&env, "add_admin", || {
        client.add_admin(&admin, &new_admin);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "is_admin", || {
        client.is_admin(&admin);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "get_admin_list", || {
        client.get_admin_list();
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "update_pin_fee", || {
        client.update_pin_fee(&admin, &200);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "update_join_fee", || {
        client.update_join_fee(&admin, &100);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "update_max_cycles", || {
        client.update_max_cycles(&admin, &120);
    });
    usages.push(usage);

    let (_, usage) = measure_operation(&env, "remove_admin", || {
        client.remove_admin(&admin, &new_admin);
    });
    usages.push(usage);

    print_usage_report(&usages);
}

#[test]
fn test_rent_estimation_flag_operations() {
    let (env, client, admin, pay_token_client, _) = setup_rent_env();

    let target = Address::generate(&env);
    mint_tokens(&pay_token_client, &admin, &target, &200_000);
    let node_id = String::from_val(&env, &"12D3KooWtarget");
    let multiaddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4001");
    client.join_as_pinner(&target, &node_id, &multiaddr, &5);

    let mut usages: Vec<ResourceUsage> = Vec::new();

    for i in 0..FLAG_THRESHOLD {
        let flagger = Address::generate(&env);
        mint_tokens(&pay_token_client, &admin, &flagger, &200_000);
        let fnode = String::from_val(&env, &"12D3KooWflag");
        let faddr = String::from_val(&env, &"/ip4/127.0.0.1/tcp/4002");
        client.join_as_pinner(&flagger, &fnode, &faddr, &5);

        let op_name = alloc::format!("flag_pinner_{}", i);
        let (_, usage) = measure_operation(&env, &op_name, || {
            client.flag_pinner(&flagger, &target);
        });
        usages.push(usage);
    }

    print_usage_report(&usages);
}

#[test]
fn test_storage_footprint_estimation() {
    println!("\n{}", "=".repeat(80));
    println!("STORAGE FOOTPRINT ESTIMATES - HVYM PIN SERVICE");
    println!("{}", "=".repeat(80));

    println!("\nPinService config struct:");
    println!("  - Symbol: ~10 bytes");
    println!("  - 7 x u32 fields: 28 bytes");
    println!("  - Address (pay_token): ~32 bytes");
    println!("  - i128 (fees_collected): 16 bytes");
    println!("  - Total: ~90 bytes");

    println!("\nPinSlot struct (per active slot):");
    println!("  - Address (publisher): ~32 bytes");
    println!("  - BytesN<32> (cid_hash): 32 bytes");
    println!("  - 4 x u32 fields: 16 bytes");
    println!("  - Vec<Address> claims (max 10): ~320 bytes");
    println!("  - Total per slot: ~400 bytes max");

    println!("\nPinner struct (per registered pinner):");
    println!("  - Address: ~32 bytes");
    println!("  - String (node_id): ~50 bytes");
    println!("  - String (multiaddr): ~50 bytes");
    println!("  - 4 x u32 fields: 16 bytes");
    println!("  - u64 (joined_at): 8 bytes");
    println!("  - bool (active): 1 byte");
    println!("  - Total per pinner: ~160 bytes");

    println!("\n--- TOTAL ESTIMATES ---");
    println!("Typical (5 active slots, 20 pinners):");
    println!("  Config: ~90 bytes");
    println!("  AdminList: ~100 bytes");
    println!("  Slots: 5 * 400 = 2,000 bytes");
    println!("  Pinners: 20 * 160 = 3,200 bytes");
    println!("  Total: ~5,390 bytes");
    println!("  Monthly rent: ~2,300 stroops (~0.00023 XLM)");

    println!("\nWorst case (10 full slots, 50 pinners):");
    println!("  Config: ~90 bytes");
    println!("  AdminList: ~100 bytes");
    println!("  Slots: 10 * 400 = 4,000 bytes");
    println!("  Pinners: 50 * 160 = 8,000 bytes");
    println!("  Total: ~12,190 bytes");
    println!("  Monthly rent: ~5,200 stroops (~0.00052 XLM)");
}
