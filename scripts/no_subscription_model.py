#!/usr/bin/env python3
"""
Pintheon Profitability Analysis - No Subscription Model

Revenue: Join fees + Publish fees
Costs: Network rent + Opus rewards per upload
"""

XLM_PRICE = 0.2379

# Fee structure (revenue)
JOIN_FEE_XLM = 10.0
MINT_FEE_XLM = 0.5

# Shard assumptions (mature shard, 75% capacity)
members = 75
new_members_per_month = 5
files_per_month = 300

# Network costs (negligible)
network_cost_xlm = 2.88  # from previous analysis

# Test different Opus reward levels
reward_scenarios = [0.05, 0.1, 0.2, 0.3, 0.5]

print("PROFITABILITY ANALYSIS: No Subscription Model")
print("=" * 75)
print(f"Shard: {members} members, {new_members_per_month} new/month, {files_per_month} files/month")
print(f"Join Fee: {JOIN_FEE_XLM} XLM | Mint Fee: {MINT_FEE_XLM} XLM")
print()

header = f"{'Opus Reward':>12} {'Revenue':>12} {'Opus Cost':>12} {'Total Cost':>12} {'Profit':>12} {'Margin':>10}"
print(header)
print("-" * 75)

for reward in reward_scenarios:
    # Revenue
    join_revenue = new_members_per_month * JOIN_FEE_XLM
    mint_revenue = files_per_month * MINT_FEE_XLM
    total_revenue = join_revenue + mint_revenue

    # Costs
    opus_cost = files_per_month * reward
    total_cost = network_cost_xlm + opus_cost

    # Profit
    profit = total_revenue - total_cost
    margin = (profit / total_revenue * 100) if total_revenue > 0 else 0

    # Convert to USD
    revenue_usd = total_revenue * XLM_PRICE
    opus_cost_usd = opus_cost * XLM_PRICE
    total_cost_usd = total_cost * XLM_PRICE
    profit_usd = profit * XLM_PRICE

    print(f"{reward:>10.2f} XLM ${revenue_usd:>10.2f} ${opus_cost_usd:>10.2f} ${total_cost_usd:>10.2f} ${profit_usd:>10.2f} {margin:>9.1f}%")

print()

# Break-even calculation
# Revenue = Join + Mint = (5 * 10) + (300 * 0.5) = 50 + 150 = 200 XLM
# Cost = Network + (files * reward)
# Break-even: Revenue = Cost
# 200 = 2.88 + 300 * reward
# reward = (200 - 2.88) / 300
total_revenue_xlm = (new_members_per_month * JOIN_FEE_XLM) + (files_per_month * MINT_FEE_XLM)
breakeven_reward = (total_revenue_xlm - network_cost_xlm) / files_per_month

print("BREAK-EVEN ANALYSIS")
print("-" * 75)
print(f"Total Revenue: {total_revenue_xlm:.2f} XLM (${total_revenue_xlm * XLM_PRICE:.2f})")
print(f"Network Cost:  {network_cost_xlm:.2f} XLM (${network_cost_xlm * XLM_PRICE:.2f})")
print(f"Available for Opus rewards: {total_revenue_xlm - network_cost_xlm:.2f} XLM")
print()
print(f"Break-even Opus reward: {breakeven_reward:.3f} XLM/file (${breakeven_reward * XLM_PRICE:.4f})")
print()

# Network scaling
print("NETWORK SCALING (No Subscription)")
print("-" * 75)
print(f"Assuming Opus reward: 0.2 XLM/file (mid-range)")
print()

opus_reward = 0.2
scenarios = [
    ("Seed (5 shards)", 5, 250, 25, 250),
    ("Growth (25 shards)", 25, 1875, 125, 1875),
    ("Scale (100 shards)", 100, 7500, 500, 7500),
    ("Network (500 shards)", 500, 37500, 2500, 37500),
    ("Mass (10K shards)", 10000, 750000, 50000, 750000),
]

print(f"{'Phase':<22} {'Shards':>8} {'Members':>10} {'Mo Revenue':>14} {'Mo Profit':>14} {'Yr Profit':>14}")
print("-" * 85)

for name, shards, members, new_per_mo, files_per_mo in scenarios:
    revenue = (new_per_mo * JOIN_FEE_XLM) + (files_per_mo * MINT_FEE_XLM)
    cost = (shards * network_cost_xlm) + (files_per_mo * opus_reward)
    profit = revenue - cost

    revenue_usd = revenue * XLM_PRICE
    profit_usd = profit * XLM_PRICE
    yearly_usd = profit_usd * 12

    print(f"{name:<22} {shards:>8,} {members:>10,} ${revenue_usd:>12,.0f} ${profit_usd:>12,.0f} ${yearly_usd:>12,.0f}")

print()
print("=" * 75)
print("CONCLUSION")
print("=" * 75)
print()
print("Yes, the model is profitable WITHOUT subscriptions.")
print()
print("Key constraints:")
print(f"  - Opus reward must be < {breakeven_reward:.2f} XLM/file to remain profitable")
print(f"  - At 0.2 XLM/file reward, margin is ~69%")
print(f"  - At 0.1 XLM/file reward, margin is ~84%")
print()
print("The mint fee (0.5 XLM) effectively funds Opus rewards (0.1-0.3 XLM)")
print("with the remainder as platform revenue.")
