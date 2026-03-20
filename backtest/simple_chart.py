import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

baseline = pd.read_csv('backtest_results_fixed.csv')
ml_opt = pd.read_csv('backtest_results_ml_optimized_fixed.csv')

fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 8))
fig.suptitle('Backtest Results Comparison', fontsize=12, fontweight='bold')

# P&L
pnls = [baseline['pnl'].sum(), ml_opt['pnl'].sum()]
ax1.bar(['Baseline', 'ML-Opt'], pnls, color=['blue', 'green'])
ax1.set_title('Total P&L')
ax1.set_ylabel('$')

# Equity
ax2.plot(baseline['pnl'].cumsum(), label='Baseline', alpha=0.7)
ax2.plot(ml_opt['pnl'].cumsum(), label='ML-Opt', alpha=0.7)
ax2.set_title('Cumulative P&L')
ax2.legend()

# Win rate
bw = (baseline['pnl'] > 0).sum() / len(baseline) * 100
mw = (ml_opt['pnl'] > 0).sum() / len(ml_opt) * 100
ax3.bar(['Baseline', 'ML-Opt'], [bw, mw], color=['blue', 'green'])
ax3.set_title('Win Rate %')
ax3.set_ylim(0, 40)

# Stats
ax4.axis('off')
stats = f"Baseline: {len(baseline)} trades, ${baseline['pnl'].sum():,.0f}\nML-Opt: {len(ml_opt)} trades, ${ml_opt['pnl'].sum():,.0f}"
ax4.text(0.1, 0.5, stats, fontsize=10)

plt.tight_layout()
plt.savefig('results_comparison.png', dpi=100)
print("File created successfully!")
