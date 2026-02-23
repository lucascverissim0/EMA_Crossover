"""
Equity Curve Visualization for ML-Optimized Strategy
Plots cumulative profits over time, broken down by year
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

def visualize_equity_curve():
    """
    Load backtest results and create equity curve visualization over years
    """
    
    print("Loading data...")
    
    # Load backtest results
    trades_df = pd.read_csv('backtest_results_ml_optimized_fixed.csv')
    
    # Load price data to get dates
    price_df = pd.read_csv('data/XAUUSD_1h_sample.csv', index_col=0, parse_dates=True)
    
    print(f"Total trades: {len(trades_df)}")
    print(f"Price data range: {price_df.index[0]} to {price_df.index[-1]}")
    
    # Create a list of all candle indices with their dates
    date_map = {}
    for idx, date in enumerate(price_df.index):
        date_map[idx] = date
    
    # Map exit_index to dates for tracking when each trade closes
    trades_df['exit_date'] = trades_df['exit_index'].map(date_map)
    
    # Calculate cumulative P&L
    trades_df['cumulative_pnl'] = trades_df['pnl'].cumsum()
    
    # Extract year from exit_date
    trades_df['year'] = trades_df['exit_date'].dt.year
    
    # Sort by exit_index to ensure chronological order
    trades_df = trades_df.sort_values('exit_index').reset_index(drop=True)
    
    # Create figure with multiple subplots
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('ML-Optimized EMA Strategy - Equity Curve Analysis', fontsize=16, fontweight='bold')
    
    # ===== Plot 1: Full Equity Curve =====
    ax1 = axes[0, 0]
    ax1.plot(trades_df.index, trades_df['cumulative_pnl'], linewidth=2, color='#2ecc71', label='Cumulative P&L')
    ax1.fill_between(trades_df.index, 0, trades_df['cumulative_pnl'], alpha=0.3, color='#2ecc71')
    ax1.axhline(y=0, color='red', linestyle='--', alpha=0.5, linewidth=1)
    ax1.set_xlabel('Trade Number', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Cumulative P&L ($)', fontsize=11, fontweight='bold')
    ax1.set_title('Cumulative Profit & Loss Over All Trades', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    # ===== Plot 2: Equity Curve over Time =====
    ax2 = axes[0, 1]
    ax2.plot(trades_df['exit_date'], trades_df['cumulative_pnl'], linewidth=2, color='#3498db', label='Cumulative P&L')
    ax2.fill_between(trades_df['exit_date'], 0, trades_df['cumulative_pnl'], alpha=0.3, color='#3498db')
    ax2.axhline(y=0, color='red', linestyle='--', alpha=0.5, linewidth=1)
    ax2.set_xlabel('Date', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Cumulative P&L ($)', fontsize=11, fontweight='bold')
    ax2.set_title('Equity Curve Over Time', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=12))  # Every 12 months
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    # ===== Plot 3: Annual Performance =====
    ax3 = axes[1, 0]
    
    # Calculate yearly profits
    yearly_stats = []
    for year in sorted(trades_df['year'].unique()):
        year_trades = trades_df[trades_df['year'] == year]
        yearly_pnl = year_trades['pnl'].sum()
        yearly_trades = len(year_trades)
        yearly_stats.append({
            'year': year,
            'pnl': yearly_pnl,
            'trades': yearly_trades
        })
    
    yearly_df = pd.DataFrame(yearly_stats)
    colors = ['#2ecc71' if x > 0 else '#e74c3c' for x in yearly_df['pnl']]
    bars = ax3.bar(yearly_df['year'].astype(str), yearly_df['pnl'], color=colors, alpha=0.7, edgecolor='black', linewidth=1.5)
    
    # Add value labels on bars
    for bar, val in zip(bars, yearly_df['pnl']):
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'${val:,.0f}',
                ha='center', va='bottom' if height > 0 else 'top', fontweight='bold', fontsize=9)
    
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax3.set_xlabel('Year', fontsize=11, fontweight='bold')
    ax3.set_ylabel('Annual P&L ($)', fontsize=11, fontweight='bold')
    ax3.set_title('Annual Profit & Loss', fontsize=12, fontweight='bold')
    ax3.grid(True, alpha=0.3, axis='y')
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    # ===== Plot 4: Cumulative Return Percentage & Trade Count =====
    ax4 = axes[1, 1]
    
    # Calculate cumulative return percentage
    initial_capital = 10000  # Assume $10k starting capital
    trades_df['balance'] = initial_capital + trades_df['cumulative_pnl']
    trades_df['return_pct'] = (trades_df['cumulative_pnl'] / initial_capital) * 100
    
    ax4_twin = ax4.twinx()
    
    # Plot return percentage
    line1 = ax4.plot(trades_df['exit_date'], trades_df['return_pct'], linewidth=2.5, color='#9b59b6', label='Cumulative Return %', marker='o', markersize=2, markevery=100)
    ax4.fill_between(trades_df['exit_date'], 0, trades_df['return_pct'], alpha=0.2, color='#9b59b6')
    
    # Plot cumulative trade count
    trades_df['trade_count'] = range(1, len(trades_df) + 1)
    line2 = ax4_twin.plot(trades_df['exit_date'], trades_df['trade_count'], linewidth=2.5, color='#f39c12', label='Cumulative Trades', linestyle='--')
    
    ax4.set_xlabel('Date', fontsize=11, fontweight='bold')
    ax4.set_ylabel('Cumulative Return (%)', fontsize=11, fontweight='bold', color='#9b59b6')
    ax4_twin.set_ylabel('Cumulative Trade Count', fontsize=11, fontweight='bold', color='#f39c12')
    ax4.set_title('Return % & Trade Activity Over Time', fontsize=12, fontweight='bold')
    ax4.grid(True, alpha=0.3)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax4.xaxis.set_major_locator(mdates.MonthLocator(interval=12))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45, ha='right')
    ax4.tick_params(axis='y', labelcolor='#9b59b6')
    ax4_twin.tick_params(axis='y', labelcolor='#f39c12')
    
    # Add legends
    lines1, labels1 = ax4.get_legend_handles_labels()
    lines2, labels2 = ax4_twin.get_legend_handles_labels()
    ax4.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    plt.tight_layout()
    
    # Save figure
    output_file = 'equity_curve_visualization.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\n✓ Equity curve visualization saved to: {output_file}")
    
    # Print summary statistics
    print("\n" + "="*60)
    print("ML-OPTIMIZED STRATEGY - EQUITY CURVE SUMMARY")
    print("="*60)
    print(f"Total Trades: {len(trades_df)}")
    print(f"Total P&L: ${trades_df['pnl'].sum():,.2f}")
    print(f"Final Cumulative P&L: ${trades_df['cumulative_pnl'].iloc[-1]:,.2f}")
    print(f"Return on $10k: {trades_df['return_pct'].iloc[-1]:.2f}%")
    print(f"Date Range: {trades_df['exit_date'].min().date()} to {trades_df['exit_date'].max().date()}")
    print(f"Years Covered: {sorted(trades_df['year'].unique())}")
    print("\nAnnual Performance:")
    print("-" * 60)
    for _, row in yearly_df.iterrows():
        print(f"  {int(row['year'])}: ${row['pnl']:>12,.2f} ({int(row['trades']):>4} trades)")
    print("="*60)
    
    # Show plot
    plt.show()

if __name__ == "__main__":
    visualize_equity_curve()
