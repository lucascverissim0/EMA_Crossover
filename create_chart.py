#!/usr/bin/env python3
"""
Create comparison chart from existing backtest results
"""
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import os
import sys

print("Loading data...")
baseline = pd.read_csv('backtest_results_fixed.csv')
ml_opt = pd.read_csv('backtest_results_ml_optimized_fixed.csv')

print(f"Baseline: {len(baseline)} trades, P&L: ${baseline['pnl'].sum():,.0f}")
print(f"ML-Opt: {len(ml_opt)} trades, P&L: ${ml_opt['pnl'].sum():,.0f}")

# Create figure
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('Backtest Results: Baseline vs ML-Optimized (Corrected Position Sizing)', 
             fontsize=14, fontweight='bold')

# Plot 1: P&L Bar Chart
ax = axes[0, 0]
strategies = ['Baseline\nEMA 12/26', 'ML-Optimized\nEMA 8/20']
pnls = [baseline['pnl'].sum(), ml_opt['pnl'].sum()]
colors = ['steelblue', 'darkgreen']
bars = ax.bar(strategies, pnls, color=colors, alpha=0.7, edgecolor='black', linewidth=2)
ax.set_ylabel('Total P&L ($)', fontweight='bold')
ax.set_title('Total Profit & Loss', fontweight='bold')
ax.grid(True, alpha=0.3, axis='y')
for bar in bars:
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2., height,
            f'${height:,.0f}', ha='center', va='bottom', fontweight='bold')

# Plot 2: Equity Curves
ax = axes[0, 1]
baseline_cumsum = baseline['pnl'].cumsum()
ml_cumsum = ml_opt['pnl'].cumsum()
ax.plot(baseline_cumsum.values, linewidth=2, color='steelblue', label='Baseline', alpha=0.8)
ax.plot(ml_cumsum.values, linewidth=2, color='darkgreen', label='ML-Optimized', alpha=0.8)
ax.set_ylabel('Cumulative P&L ($)', fontweight='bold')
ax.set_xlabel('Trade #', fontweight='bold')
ax.set_title('Equity Curve', fontweight='bold')
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)

# Plot 3: Win Rate
ax = axes[1, 0]
baseline_wins = (baseline['pnl'] > 0).sum()
baseline_wr = (baseline_wins / len(baseline) * 100)
ml_wins = (ml_opt['pnl'] > 0).sum()
ml_wr = (ml_wins / len(ml_opt) * 100)
wrs = [baseline_wr, ml_wr]
bars = ax.bar(strategies, wrs, color=colors, alpha=0.7, edgecolor='black', linewidth=2)
ax.set_ylabel('Win Rate (%)', fontweight='bold')
ax.set_title('Win Rate Comparison', fontweight='bold')
ax.set_ylim(0, 40)
ax.grid(True, alpha=0.3, axis='y')
for bar in bars:
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2., height,
            f'{height:.1f}%', ha='center', va='bottom', fontweight='bold')

# Plot 4: Summary Stats
ax = axes[1, 1]
ax.axis('off')

summary_text = f"""BASELINE (EMA 12/26)
SL: 2.0% | TP: 5.0%
━━━━━━━━━━━━━━━━
Trades: {len(baseline):,}
P&L: ${baseline['pnl'].sum():,.0f}
Avg Trade: ${baseline['pnl'].mean():.2f}
Win Rate: {baseline_wr:.1f}%
Max Win: ${baseline['pnl'].max():.0f}
Max Loss: ${baseline['pnl'].min():.0f}

ML-OPTIMIZED (EMA 8/20)
SL: 0.5% | TP: 3.52%
━━━━━━━━━━━━━━━━
Trades: {len(ml_opt):,}
P&L: ${ml_opt['pnl'].sum():,.0f}
Avg Trade: ${ml_opt['pnl'].mean():.2f}
Win Rate: {ml_wr:.1f}%
Max Win: ${ml_opt['pnl'].max():.0f}
Max Loss: ${ml_opt['pnl'].min():.0f}

IMPROVEMENT: +{((ml_opt['pnl'].sum()/baseline['pnl'].sum())-1)*100:.1f}%"""

ax.text(0.05, 0.95, summary_text, transform=ax.transAxes,
        fontsize=9.5, verticalalignment='top', fontfamily='monospace',
        bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

# Save
output_file = 'results_comparison.png'
plt.savefig(output_file, dpi=150, bbox_inches='tight')
print(f"✓ Saved: {output_file}")

# Verify
if os.path.exists(output_file):
    size = os.path.getsize(output_file)
    print(f"✓ File size: {size:,} bytes")
    print(f"✓ File saved successfully!")
else:
    print(f"✗ File not found!")
    sys.exit(1)

plt.close()
