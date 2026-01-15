#!/usr/bin/env python3
"""
Pintheon Contracts - Rent Estimation & Business Model Analysis

This script provides two modes of operation:
1. Full mode: Runs rent tests to get actual operation costs, then models business economics
2. Model-only mode: Skips tests, uses baseline estimates for pure fee/revenue modeling

Usage:
    python scripts/run_rent_tests.py [--model-only] [--json] [--csv] [--verbose]

Options:
    --model-only  Skip contract tests, use baseline cost estimates for modeling
    --json        Output results in JSON format
    --csv         Output results in CSV format
    --verbose     Show detailed test output (ignored in model-only mode)

Examples:
    python scripts/run_rent_tests.py --model-only --json  # Quick business modeling
    python scripts/run_rent_tests.py --json               # Full test + modeling
"""

import subprocess
import re
import json
import csv
import sys
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path

# Constants
STROOPS_PER_XLM = 10_000_000
LEDGERS_PER_DAY = 144_000  # ~6 seconds per ledger
LEDGERS_PER_MONTH = LEDGERS_PER_DAY * 30
LEDGERS_PER_YEAR = LEDGERS_PER_DAY * 365

# Fallback XLM price if API fails
FALLBACK_XLM_PRICE = 0.25

# Baseline cost estimates (stroops) - used in model-only mode
# These are conservative estimates based on typical Soroban operations
BASELINE_COSTS = {
    "join_operation": 500_000,      # Member join/registration
    "mint_operation": 100_000,      # Token/file minting
    "transfer_operation": 80_000,   # Token transfers
    "node_operation": 150_000,      # Node registration/updates
    "storage_per_member": 100,      # Monthly storage per member entry
    "storage_per_file": 150,        # Monthly storage per file entry
    "storage_per_node": 200,        # Monthly storage per node entry
}

@dataclass
class XLMPrice:
    """Current XLM price data"""
    price_usd: float
    timestamp: str
    source: str

@dataclass
class OperationMetrics:
    """Metrics for a single operation"""
    operation: str
    cpu_instructions: int
    memory_bytes: int
    estimated_stroops: int

@dataclass
class ContractMetrics:
    """Aggregated metrics for a contract"""
    contract_name: str
    operations: List[OperationMetrics] = field(default_factory=list)
    total_cpu: int = 0
    total_memory: int = 0
    total_stroops: int = 0
    test_count: int = 0

    def add_operation(self, op: OperationMetrics):
        self.operations.append(op)
        self.total_cpu += op.cpu_instructions
        self.total_memory += op.memory_bytes
        self.total_stroops += op.estimated_stroops

    def avg_cpu(self) -> float:
        return self.total_cpu / len(self.operations) if self.operations else 0

    def avg_memory(self) -> float:
        return self.total_memory / len(self.operations) if self.operations else 0

    def avg_stroops(self) -> float:
        return self.total_stroops / len(self.operations) if self.operations else 0

@dataclass
class ShardEconomics:
    """Economics for a single shard"""
    shard_name: str
    member_cap: int
    members_active: int
    files_per_month: int
    nodes: int

    # Fee structure (in XLM)
    join_fee_xlm: float
    mint_fee_xlm: float
    monthly_subscription_xlm: float

    # Costs
    monthly_cost_stroops: int
    monthly_cost_xlm: float
    monthly_cost_usd: float

    # Revenue
    monthly_revenue_xlm: float
    monthly_revenue_usd: float

    # Profit
    monthly_profit_xlm: float
    monthly_profit_usd: float
    profit_margin_pct: float

@dataclass
class NetworkProjection:
    """Network-wide projection across multiple shards"""
    scenario: str
    num_shards: int
    total_members: int
    member_cap_per_shard: int

    # Aggregate financials
    total_monthly_cost_xlm: float
    total_monthly_cost_usd: float
    total_monthly_revenue_xlm: float
    total_monthly_revenue_usd: float
    total_monthly_profit_xlm: float
    total_monthly_profit_usd: float

    # Annual projections
    yearly_revenue_usd: float
    yearly_profit_usd: float

    # Per-shard averages
    avg_profit_per_shard_usd: float

# Contract directories to test
CONTRACTS = [
    ("hvym-roster", "hvym-roster"),
    ("hvym-collective", "hvym-collective"),
    ("opus_token", "opus_token"),
    ("pintheon-ipfs-token", "pintheon-ipfs-deployer/pintheon-ipfs-token"),
    ("pintheon-node-token", "pintheon-node-deployer/pintheon-node-token"),
]

def fetch_xlm_price() -> XLMPrice:
    """Fetch current XLM price from CoinGecko API"""
    url = "https://api.coingecko.com/api/v3/simple/price?ids=stellar&vs_currencies=usd"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'PintheonRentEstimator/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            price = data['stellar']['usd']
            return XLMPrice(
                price_usd=price,
                timestamp=datetime.now().isoformat(),
                source="CoinGecko API"
            )
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
        print(f"  Warning: Could not fetch live XLM price ({e}), using fallback ${FALLBACK_XLM_PRICE}")
        return XLMPrice(
            price_usd=FALLBACK_XLM_PRICE,
            timestamp=datetime.now().isoformat(),
            source="Fallback (API unavailable)"
        )

def stroops_to_xlm(stroops: int) -> float:
    """Convert stroops to XLM"""
    return stroops / STROOPS_PER_XLM

def xlm_to_usd(xlm: float, price: XLMPrice) -> float:
    """Convert XLM to USD"""
    return xlm * price.price_usd

def stroops_to_usd(stroops: int, price: XLMPrice) -> float:
    """Convert stroops directly to USD"""
    return xlm_to_usd(stroops_to_xlm(stroops), price)

def run_rent_tests(contract_path: str, verbose: bool = False) -> str:
    """Run rent tests for a contract and capture output"""
    cmd = ["cargo", "test", "rent_test", "--", "--nocapture"]

    try:
        result = subprocess.run(
            cmd,
            cwd=contract_path,
            capture_output=True,
            text=True,
            timeout=300
        )
        output = result.stdout + result.stderr
        if verbose:
            print(output)
        return output
    except subprocess.TimeoutExpired:
        print(f"  Warning: Tests timed out for {contract_path}")
        return ""
    except Exception as e:
        print(f"  Error running tests for {contract_path}: {e}")
        return ""

def parse_test_output(output: str, contract_name: str) -> ContractMetrics:
    """Parse test output to extract metrics"""
    metrics = ContractMetrics(contract_name=contract_name)

    table_pattern = r'([a-zA-Z0-9_\.\s]+?)\s{2,}(\d+)\s+(\d+)\s+(\d+)'

    lines = output.split('\n')
    current_cpu = None
    current_mem = None

    for line in lines:
        if '=' in line or '-' * 10 in line or 'Operation' in line:
            continue

        table_match = re.search(table_pattern, line)
        if table_match:
            op_name = table_match.group(1).strip()
            cpu = int(table_match.group(2))
            mem = int(table_match.group(3))
            stroops = int(table_match.group(4))

            if op_name and not op_name.startswith('Total') and not op_name.startswith('Avg'):
                op = OperationMetrics(
                    operation=op_name,
                    cpu_instructions=cpu,
                    memory_bytes=mem,
                    estimated_stroops=stroops
                )
                metrics.add_operation(op)

        cpu_match = re.search(r'CPU Instructions:\s*(\d+)', line)
        if cpu_match:
            current_cpu = int(cpu_match.group(1))

        mem_match = re.search(r'Memory Bytes:\s*(\d+)', line)
        if mem_match:
            current_mem = int(mem_match.group(1))

        stroops_match = re.search(r'Estimated Stroops:\s*(\d+)', line)
        if stroops_match and current_cpu and current_mem:
            stroops = int(stroops_match.group(1))
            op = OperationMetrics(
                operation=f"operation_{len(metrics.operations)}",
                cpu_instructions=current_cpu,
                memory_bytes=current_mem,
                estimated_stroops=stroops
            )
            metrics.add_operation(op)
            current_cpu = None
            current_mem = None

    test_count_match = re.search(r'(\d+) passed', output)
    if test_count_match:
        metrics.test_count = int(test_count_match.group(1))

    return metrics

def calculate_shard_economics(
    shard_name: str,
    member_cap: int,
    members_active: int,
    files_per_month: int,
    nodes: int,
    join_fee_xlm: float,
    mint_fee_xlm: float,
    monthly_sub_xlm: float,
    avg_join_stroops: int,
    avg_mint_stroops: int,
    avg_node_stroops: int,
    xlm_price: XLMPrice,
    new_members_per_month: int = 0
) -> ShardEconomics:
    """Calculate economics for a single shard"""

    # Storage rent estimates (stroops/month)
    storage_rent_per_member = 100
    storage_rent_per_file = 150
    storage_rent_per_node = 200

    # Monthly costs (transaction + storage)
    tx_cost_stroops = (
        new_members_per_month * avg_join_stroops +
        files_per_month * avg_mint_stroops +
        nodes * avg_node_stroops  # node maintenance/updates
    )

    storage_cost_stroops = (
        members_active * storage_rent_per_member +
        (files_per_month * 12) * storage_rent_per_file +  # cumulative files (rough estimate)
        nodes * storage_rent_per_node
    )

    total_cost_stroops = tx_cost_stroops + storage_cost_stroops
    total_cost_xlm = stroops_to_xlm(total_cost_stroops)
    total_cost_usd = xlm_to_usd(total_cost_xlm, xlm_price)

    # Monthly revenue
    join_revenue = new_members_per_month * join_fee_xlm
    mint_revenue = files_per_month * mint_fee_xlm
    subscription_revenue = members_active * monthly_sub_xlm

    total_revenue_xlm = join_revenue + mint_revenue + subscription_revenue
    total_revenue_usd = xlm_to_usd(total_revenue_xlm, xlm_price)

    # Profit
    profit_xlm = total_revenue_xlm - total_cost_xlm
    profit_usd = total_revenue_usd - total_cost_usd
    profit_margin = (profit_xlm / total_revenue_xlm * 100) if total_revenue_xlm > 0 else 0

    return ShardEconomics(
        shard_name=shard_name,
        member_cap=member_cap,
        members_active=members_active,
        files_per_month=files_per_month,
        nodes=nodes,
        join_fee_xlm=join_fee_xlm,
        mint_fee_xlm=mint_fee_xlm,
        monthly_subscription_xlm=monthly_sub_xlm,
        monthly_cost_stroops=total_cost_stroops,
        monthly_cost_xlm=total_cost_xlm,
        monthly_cost_usd=total_cost_usd,
        monthly_revenue_xlm=total_revenue_xlm,
        monthly_revenue_usd=total_revenue_usd,
        monthly_profit_xlm=profit_xlm,
        monthly_profit_usd=profit_usd,
        profit_margin_pct=profit_margin
    )

def calculate_network_projections(
    all_metrics: Dict[str, ContractMetrics],
    xlm_price: XLMPrice
) -> Tuple[List[ShardEconomics], List[NetworkProjection]]:
    """Calculate shard economics and network-wide projections"""

    # Get average costs from metrics
    collective_metrics = all_metrics.get('hvym-collective', ContractMetrics('hvym-collective'))
    ipfs_token_metrics = all_metrics.get('pintheon-ipfs-token', ContractMetrics('pintheon-ipfs-token'))
    node_token_metrics = all_metrics.get('pintheon-node-token', ContractMetrics('pintheon-node-token'))

    # Average operation costs (stroops)
    avg_join_stroops = int(collective_metrics.avg_stroops()) if collective_metrics.operations else 500000
    avg_mint_stroops = int(ipfs_token_metrics.avg_stroops()) if ipfs_token_metrics.operations else 100000
    avg_node_stroops = int(node_token_metrics.avg_stroops()) if node_token_metrics.operations else 150000

    # Fee structure (in XLM) - configurable business parameters
    JOIN_FEE_XLM = 10.0        # One-time join fee
    MINT_FEE_XLM = 0.5         # Per-file mint fee
    MONTHLY_SUB_XLM = 1.0      # Monthly subscription per member

    # Shard configurations
    MEMBER_CAP = 100  # Members per shard before spawning new shard

    shard_examples = []
    network_projections = []

    # Example shard at different fill levels
    shard_configs = [
        ("New Shard (25%)", 25, 10, 50, 1, 5),      # 25 members, 10 new/mo, 50 files, 1 node
        ("Growing Shard (50%)", 50, 8, 150, 2, 8),   # 50 members, 8 new/mo, 150 files, 2 nodes
        ("Mature Shard (75%)", 75, 5, 300, 3, 5),    # 75 members, 5 new/mo, 300 files, 3 nodes
        ("Full Shard (100%)", 100, 2, 500, 5, 2),    # 100 members, 2 new/mo (replacements), 500 files
    ]

    for name, members, new_per_mo, files, nodes, _ in shard_configs:
        shard = calculate_shard_economics(
            shard_name=name,
            member_cap=MEMBER_CAP,
            members_active=members,
            files_per_month=files,
            nodes=nodes,
            join_fee_xlm=JOIN_FEE_XLM,
            mint_fee_xlm=MINT_FEE_XLM,
            monthly_sub_xlm=MONTHLY_SUB_XLM,
            avg_join_stroops=avg_join_stroops,
            avg_mint_stroops=avg_mint_stroops,
            avg_node_stroops=avg_node_stroops,
            xlm_price=xlm_price,
            new_members_per_month=new_per_mo
        )
        shard_examples.append(shard)

    # Network-wide projections (multiple shards)
    network_scenarios = [
        ("Seed Phase", 5, 250),           # 5 shards, ~250 total members
        ("Growth Phase", 25, 1_875),      # 25 shards, ~1,875 members (75% avg fill)
        ("Scale Phase", 100, 7_500),      # 100 shards, 7,500 members
        ("Network Phase", 500, 37_500),   # 500 shards, 37,500 members
        ("Mass Adoption", 10_000, 750_000),  # 10K shards, 750K members
    ]

    # Use "Growing Shard" as average shard profile for projections
    avg_shard = shard_examples[1]  # 50% fill rate

    for scenario_name, num_shards, total_members in network_scenarios:
        members_per_shard = total_members // num_shards

        # Scale the average shard economics
        total_cost_xlm = avg_shard.monthly_cost_xlm * num_shards
        total_cost_usd = xlm_to_usd(total_cost_xlm, xlm_price)
        total_revenue_xlm = avg_shard.monthly_revenue_xlm * num_shards
        total_revenue_usd = xlm_to_usd(total_revenue_xlm, xlm_price)
        total_profit_xlm = total_revenue_xlm - total_cost_xlm
        total_profit_usd = total_revenue_usd - total_cost_usd

        projection = NetworkProjection(
            scenario=scenario_name,
            num_shards=num_shards,
            total_members=total_members,
            member_cap_per_shard=MEMBER_CAP,
            total_monthly_cost_xlm=total_cost_xlm,
            total_monthly_cost_usd=total_cost_usd,
            total_monthly_revenue_xlm=total_revenue_xlm,
            total_monthly_revenue_usd=total_revenue_usd,
            total_monthly_profit_xlm=total_profit_xlm,
            total_monthly_profit_usd=total_profit_usd,
            yearly_revenue_usd=total_revenue_usd * 12,
            yearly_profit_usd=total_profit_usd * 12,
            avg_profit_per_shard_usd=total_profit_usd / num_shards if num_shards > 0 else 0
        )
        network_projections.append(projection)

    return shard_examples, network_projections

def print_report(
    all_metrics: Dict[str, ContractMetrics],
    shard_examples: List[ShardEconomics],
    network_projections: List[NetworkProjection],
    xlm_price: XLMPrice,
    model_only: bool = False
):
    """Print a comprehensive report"""
    print("\n" + "=" * 110)
    if model_only:
        print("PINTHEON CONTRACTS - BUSINESS MODEL ANALYSIS REPORT")
        print("=" * 110)
        print("NOTE: Using baseline cost estimates (no contract tests run)")
    else:
        print("PINTHEON CONTRACTS - RENT & REVENUE ESTIMATION REPORT")
        print("=" * 110)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"XLM Price: ${xlm_price.price_usd:.4f} USD (Source: {xlm_price.source})")
    print(f"Price Timestamp: {xlm_price.timestamp}")
    print()

    # Conversion reference
    print("-" * 110)
    print("CONVERSION REFERENCE")
    print("-" * 110)
    print(f"  1 XLM = {STROOPS_PER_XLM:,} stroops")
    print(f"  1 XLM = ${xlm_price.price_usd:.4f} USD")
    print(f"  1,000,000 stroops = {stroops_to_xlm(1_000_000):.2f} XLM = ${stroops_to_usd(1_000_000, xlm_price):.4f} USD")
    print()

    # Contract-by-contract breakdown
    print("-" * 110)
    print("CONTRACT COST ANALYSIS")
    print("-" * 110)

    total_stroops_all = 0
    total_operations = 0

    for contract_name, metrics in all_metrics.items():
        if metrics.operations:
            xlm_total = stroops_to_xlm(metrics.total_stroops)
            usd_total = xlm_to_usd(xlm_total, xlm_price)

            print(f"\n  {contract_name.upper()}")
            print(f"    Tests passed: {metrics.test_count}")
            print(f"    Operations measured: {len(metrics.operations)}")
            print(f"    Total: {metrics.total_stroops:,} stroops = {xlm_total:.4f} XLM = ${usd_total:.4f} USD")
            print(f"    Avg per op: {metrics.avg_stroops():,.0f} stroops = ${stroops_to_usd(int(metrics.avg_stroops()), xlm_price):.4f} USD")

            total_stroops_all += metrics.total_stroops
            total_operations += len(metrics.operations)

    # Shard Economics
    print("\n" + "-" * 110)
    print("SHARD ECONOMICS (Single Shard Analysis)")
    print("-" * 110)
    print(f"  Member Cap per Shard: {shard_examples[0].member_cap}")
    print(f"  Fee Structure: Join=${shard_examples[0].join_fee_xlm} XLM, Mint=${shard_examples[0].mint_fee_xlm} XLM, Sub=${shard_examples[0].monthly_subscription_xlm} XLM/mo")
    print()
    print(f"  {'Shard Stage':<22} {'Members':>8} {'Files/Mo':>10} {'Cost/Mo':>12} {'Revenue/Mo':>12} {'Profit/Mo':>12} {'Margin':>8}")
    print("  " + "-" * 104)

    for shard in shard_examples:
        print(f"  {shard.shard_name:<22} {shard.members_active:>8} {shard.files_per_month:>10} "
              f"${shard.monthly_cost_usd:>10.2f} ${shard.monthly_revenue_usd:>10.2f} "
              f"${shard.monthly_profit_usd:>10.2f} {shard.profit_margin_pct:>7.1f}%")

    # Network Projections
    print("\n" + "-" * 110)
    print("NETWORK PROJECTIONS (Multi-Shard Scaling)")
    print("-" * 110)
    print(f"  {'Scenario':<18} {'Shards':>8} {'Members':>10} {'Mo. Cost':>14} {'Mo. Revenue':>14} {'Mo. Profit':>14} {'Yr. Profit':>14}")
    print("  " + "-" * 104)

    for proj in network_projections:
        print(f"  {proj.scenario:<18} {proj.num_shards:>8,} {proj.total_members:>10,} "
              f"${proj.total_monthly_cost_usd:>12,.0f} ${proj.total_monthly_revenue_usd:>12,.0f} "
              f"${proj.total_monthly_profit_usd:>12,.0f} ${proj.yearly_profit_usd:>12,.0f}")

    # Franchise/Shard Admin Economics
    print("\n" + "-" * 110)
    print("SHARD ADMIN ECONOMICS (Franchise Model)")
    print("-" * 110)

    mature_shard = shard_examples[2]  # 75% full shard
    print(f"  Scenario: Admin running a mature shard (75% capacity, {mature_shard.members_active} members)")
    print()
    print(f"  Monthly Revenue:     ${mature_shard.monthly_revenue_usd:>10.2f} USD ({mature_shard.monthly_revenue_xlm:.2f} XLM)")
    print(f"  Monthly Costs:       ${mature_shard.monthly_cost_usd:>10.2f} USD ({mature_shard.monthly_cost_xlm:.2f} XLM)")
    print(f"  Monthly Profit:      ${mature_shard.monthly_profit_usd:>10.2f} USD ({mature_shard.monthly_profit_xlm:.2f} XLM)")
    print(f"  Annual Profit:       ${mature_shard.monthly_profit_usd * 12:>10.2f} USD")
    print(f"  Profit Margin:       {mature_shard.profit_margin_pct:.1f}%")
    print()
    print("  Incentive: Members who reach shard capacity can spawn & admin new shards,")
    print("             earning ongoing revenue from their member community.")

    # Break-even Analysis
    print("\n" + "-" * 110)
    print("BREAK-EVEN ANALYSIS")
    print("-" * 110)

    # Calculate break-even point
    new_shard = shard_examples[0]
    if new_shard.monthly_revenue_usd > 0:
        members_for_breakeven = 0
        for i in range(1, 101):
            test_revenue = (i * new_shard.monthly_subscription_xlm +
                          (i/25 * 10) * new_shard.join_fee_xlm +  # Rough new member rate
                          (i * 2) * new_shard.mint_fee_xlm)  # 2 files per member
            test_cost_xlm = stroops_to_xlm(i * 100 + i * 2 * 150)  # Rough cost estimate
            if xlm_to_usd(test_revenue, xlm_price) > xlm_to_usd(test_cost_xlm, xlm_price):
                members_for_breakeven = i
                break

        print(f"  Estimated break-even: ~{members_for_breakeven} active members per shard")
        print(f"  At {new_shard.member_cap} member cap: {(members_for_breakeven/new_shard.member_cap)*100:.0f}% capacity needed for profitability")

    print("\n" + "=" * 110)

def export_json(
    all_metrics: Dict[str, ContractMetrics],
    shard_examples: List[ShardEconomics],
    network_projections: List[NetworkProjection],
    xlm_price: XLMPrice,
    filepath: str,
    model_only: bool = False
):
    """Export results to JSON"""
    data = {
        "generated": datetime.now().isoformat(),
        "mode": "model-only (baseline estimates)" if model_only else "full (test-derived)",
        "xlm_price": {
            "price_usd": xlm_price.price_usd,
            "timestamp": xlm_price.timestamp,
            "source": xlm_price.source
        },
        "contracts": {},
        "shard_examples": [],
        "network_projections": []
    }

    for name, metrics in all_metrics.items():
        xlm_total = stroops_to_xlm(metrics.total_stroops)
        data["contracts"][name] = {
            "test_count": metrics.test_count,
            "total_cpu": metrics.total_cpu,
            "total_memory": metrics.total_memory,
            "total_stroops": metrics.total_stroops,
            "total_xlm": xlm_total,
            "total_usd": xlm_to_usd(xlm_total, xlm_price),
            "operations": [asdict(op) for op in metrics.operations]
        }

    data["shard_examples"] = [asdict(s) for s in shard_examples]
    data["network_projections"] = [asdict(p) for p in network_projections]

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Results exported to {filepath}")

def export_csv(
    all_metrics: Dict[str, ContractMetrics],
    shard_examples: List[ShardEconomics],
    network_projections: List[NetworkProjection],
    xlm_price: XLMPrice,
    filepath: str
):
    """Export results to CSV"""
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Header info
        writer.writerow(["Pintheon Rent & Revenue Estimation"])
        writer.writerow(["Generated", datetime.now().isoformat()])
        writer.writerow(["XLM Price USD", xlm_price.price_usd])
        writer.writerow(["Price Source", xlm_price.source])
        writer.writerow([])

        # Operations data
        writer.writerow(["CONTRACT OPERATIONS"])
        writer.writerow(["Contract", "Operation", "CPU Instructions", "Memory Bytes", "Stroops", "XLM", "USD"])
        for name, metrics in all_metrics.items():
            for op in metrics.operations:
                xlm = stroops_to_xlm(op.estimated_stroops)
                usd = xlm_to_usd(xlm, xlm_price)
                writer.writerow([name, op.operation, op.cpu_instructions, op.memory_bytes,
                               op.estimated_stroops, f"{xlm:.6f}", f"{usd:.6f}"])

        writer.writerow([])

        # Shard economics
        writer.writerow(["SHARD ECONOMICS"])
        writer.writerow(["Shard", "Members", "Files/Mo", "Cost USD", "Revenue USD", "Profit USD", "Margin %"])
        for s in shard_examples:
            writer.writerow([s.shard_name, s.members_active, s.files_per_month,
                           f"{s.monthly_cost_usd:.2f}", f"{s.monthly_revenue_usd:.2f}",
                           f"{s.monthly_profit_usd:.2f}", f"{s.profit_margin_pct:.1f}"])

        writer.writerow([])

        # Network projections
        writer.writerow(["NETWORK PROJECTIONS"])
        writer.writerow(["Scenario", "Shards", "Members", "Monthly Cost USD", "Monthly Revenue USD",
                        "Monthly Profit USD", "Yearly Profit USD"])
        for p in network_projections:
            writer.writerow([p.scenario, p.num_shards, p.total_members,
                           f"{p.total_monthly_cost_usd:.0f}", f"{p.total_monthly_revenue_usd:.0f}",
                           f"{p.total_monthly_profit_usd:.0f}", f"{p.yearly_profit_usd:.0f}"])

    print(f"Results exported to {filepath}")

def create_baseline_metrics() -> Dict[str, ContractMetrics]:
    """Create baseline metrics using estimated costs (no tests required)"""
    metrics = {}

    # Collective contract baseline
    collective = ContractMetrics(contract_name="hvym-collective")
    collective.add_operation(OperationMetrics("join", 40_000_000, 1_000_000, BASELINE_COSTS["join_operation"]))
    collective.add_operation(OperationMetrics("fund", 30_000_000, 800_000, BASELINE_COSTS["transfer_operation"]))
    collective.add_operation(OperationMetrics("withdraw", 30_000_000, 800_000, BASELINE_COSTS["transfer_operation"]))
    collective.add_operation(OperationMetrics("publish_file", 35_000_000, 900_000, BASELINE_COSTS["mint_operation"]))
    collective.test_count = 4
    metrics["hvym-collective"] = collective

    # IPFS token baseline
    ipfs_token = ContractMetrics(contract_name="pintheon-ipfs-token")
    ipfs_token.add_operation(OperationMetrics("mint", 35_000_000, 900_000, BASELINE_COSTS["mint_operation"]))
    ipfs_token.add_operation(OperationMetrics("transfer", 25_000_000, 700_000, BASELINE_COSTS["transfer_operation"]))
    ipfs_token.test_count = 2
    metrics["pintheon-ipfs-token"] = ipfs_token

    # Node token baseline
    node_token = ContractMetrics(contract_name="pintheon-node-token")
    node_token.add_operation(OperationMetrics("mint", 35_000_000, 900_000, BASELINE_COSTS["node_operation"]))
    node_token.add_operation(OperationMetrics("transfer", 25_000_000, 700_000, BASELINE_COSTS["transfer_operation"]))
    node_token.test_count = 2
    metrics["pintheon-node-token"] = node_token

    # Opus token baseline
    opus_token = ContractMetrics(contract_name="opus_token")
    opus_token.add_operation(OperationMetrics("mint", 35_000_000, 900_000, BASELINE_COSTS["mint_operation"]))
    opus_token.add_operation(OperationMetrics("transfer", 25_000_000, 700_000, BASELINE_COSTS["transfer_operation"]))
    opus_token.test_count = 2
    metrics["opus_token"] = opus_token

    # Roster baseline
    roster = ContractMetrics(contract_name="hvym-roster")
    roster.add_operation(OperationMetrics("add_member", 40_000_000, 1_000_000, BASELINE_COSTS["join_operation"]))
    roster.add_operation(OperationMetrics("get_member", 20_000_000, 500_000, 50_000))
    roster.test_count = 2
    metrics["hvym-roster"] = roster

    return metrics

def main():
    """Main entry point"""
    verbose = "--verbose" in sys.argv
    output_json = "--json" in sys.argv
    output_csv = "--csv" in sys.argv
    model_only = "--model-only" in sys.argv

    script_dir = Path(__file__).parent.absolute()
    project_root = script_dir.parent

    print("=" * 80)
    if model_only:
        print("PINTHEON CONTRACTS - BUSINESS MODEL ANALYSIS (Model-Only Mode)")
    else:
        print("PINTHEON CONTRACTS - RENT & REVENUE ESTIMATION")
    print("=" * 80)
    print(f"Project root: {project_root}")
    if model_only:
        print("Mode: Model-only (using baseline cost estimates, no tests run)")
    print()

    # Fetch current XLM price
    print("Fetching current XLM price...")
    xlm_price = fetch_xlm_price()
    print(f"  XLM Price: ${xlm_price.price_usd:.4f} USD ({xlm_price.source})")
    print()

    all_metrics: Dict[str, ContractMetrics] = {}

    if model_only:
        # Use baseline estimates instead of running tests
        print("Using baseline cost estimates for modeling...")
        all_metrics = create_baseline_metrics()
        print(f"  Loaded {len(all_metrics)} contract baseline profiles")
    else:
        # Run actual tests
        for contract_name, contract_path in CONTRACTS:
            full_path = project_root / contract_path
            if not full_path.exists():
                print(f"Skipping {contract_name}: path not found ({full_path})")
                continue

            print(f"Running rent tests for {contract_name}...")
            output = run_rent_tests(str(full_path), verbose)
            metrics = parse_test_output(output, contract_name)
            all_metrics[contract_name] = metrics
            print(f"  Found {len(metrics.operations)} operations, {metrics.test_count} tests passed")

    # Calculate projections
    shard_examples, network_projections = calculate_network_projections(all_metrics, xlm_price)

    # Print report
    print_report(all_metrics, shard_examples, network_projections, xlm_price, model_only)

    # Export if requested
    if output_json:
        export_json(all_metrics, shard_examples, network_projections, xlm_price,
                   str(project_root / "rent_estimation_results.json"), model_only)

    if output_csv:
        export_csv(all_metrics, shard_examples, network_projections, xlm_price,
                  str(project_root / "rent_estimation_results.csv"))

    return 0

if __name__ == "__main__":
    sys.exit(main())
