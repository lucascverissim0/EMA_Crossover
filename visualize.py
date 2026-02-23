"""
Visualization of EMA Crossover Strategy Results
Generate plots for analysis with key metrics (Sharpe Ratio, Win Rate)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from ema_strategy import EMAStrategy

def plot_strategy_analysis(data_file='data/XAUUSD_1h_sample.csv', 
                          trades_file='backtest_results.csv',
                          sample_size=2000):
    """
    Create comprehensive strategy visualization
    
    Parameters:
    - data_file: Path to OHLCV data CSV
    - trades_file: Path to trades results CSV  
    - sample_size: Number of recent candles to plot (for clarity)
    """
    
    print("Creating visualizations...")
    
    # Load data
    df = pd.read_csv(data_file, index_col=0, parse_dates=True)
    trades = pd.read_csv(trades_file)
    
    # Calculate key metrics for display
    trades['cumsum_pnl'] = trades['pnl'].cumsum()
    
    win_rate = (sum(trades['pnl'] > 0) / len(trades) * 100) if len(trades) > 0 else 0
    total_pnl = trades['pnl'].sum()
    returns = df['Close'].pct_change().dropna()
    sharpe_ratio = (returns.mean() / returns.std() * np.sqrt(252*24)) if returns.std() > 0 else 0  # Hourly data
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min() * 100
    
    # Initialize strategy
    strategy = EMAStrategy(fast_period=12, slow_period=26)
    df = strategy.generate_signals(df)
    
    # Get recent data for detailed plot
    df_recent = df.tail(sample_size)
    
    # ===== FIGURE 1: Full 10-Year Overview with Key Metrics =====
    fig_overview = plt.figure(figsize=(16, 10))
    gs = fig_overview.add_gridspec(3, 2, height_ratios=[1, 1, 1.5], hspace=0.35, wspace=0.25)
    
    # Top row: Key Metrics (Large)
    ax_metrics = fig_overview.add_subplot(gs[0, :])
    ax_metrics.axis('off')
    
    # Create metrics text box
    metrics_text = f"""
    EMA CROSSOVER STRATEGY - 10 YEAR BACKTEST SUMMARY
    
    Sharpe Ratio: {sharpe_ratio:.2f}                Win Rate: {win_rate:.1f}%                Total P&L: ${total_pnl:,.0f}                Max Drawdown: {max_drawdown:.1f}%
    
    Strategy: EMA({strategy.fast_period}/{strategy.slow_period}) | Period: {df.index[0].date()} to {df.index[-1].date()} | Data Points: {len(df):,}
    """
    
    ax_metrics.text(0.5, 0.5, metrics_text, transform=ax_metrics.transAxes,
                   fontsize=12, verticalalignment='center', horizontalalignment='center',
                   bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.3),
                   fontfamily='monospace', fontweight='bold')
    
    # Middle row: Full 10-year price chart
    ax_full = fig_overview.add_subplot(gs[1, :])
    ax_full.plot(df.index, df['Close'], label='Close Price', linewidth=0.8, alpha=0.8, color='black')
    ax_full.plot(df.index, df['fast_ema'], label=f'EMA {strategy.fast_period}', 
                linewidth=0.8, color='orange', alpha=0.6)
    ax_full.plot(df.index, df['slow_ema'], label=f'EMA {strategy.slow_period}', 
                linewidth=0.8, color='red', alpha=0.6)
    
    # Add background color for buy/sell regions
    in_position = df['signal'] == 1
    ax_full.fill_between(df.index, df['Close'].min(), df['Close'].max(), 
                         where=in_position, alpha=0.1, color='green', label='Long Signal Active')
    
    ax_full.set_title('Full 10-Year Price Action with EMA Indicators', fontsize=12, fontweight='bold')
    ax_full.set_ylabel('Price ($)', fontsize=10)
    ax_full.legend(loc='upper left', fontsize=9)
    ax_full.grid(True, alpha=0.2)
    
    # Bottom left: Equity curve
    ax_equity = fig_overview.add_subplot(gs[2, 0])
    if not trades.empty:
        trades_sorted = trades.sort_values('exit_index')
        ax_equity.plot(range(len(trades_sorted)), trades_sorted['cumsum_pnl'], 
                      linewidth=2, color='blue', label='Equity Curve')
        ax_equity.fill_between(range(len(trades_sorted)), trades_sorted['cumsum_pnl'], alpha=0.2, color='blue')
        ax_equity.axhline(y=0, color='red', linestyle='--', linewidth=1)
    ax_equity.set_title('Cumulative P&L Over All Trades', fontsize=11, fontweight='bold')
    ax_equity.set_ylabel('Cumulative P&L ($)', fontsize=10)
    ax_equity.set_xlabel('Trade Number', fontsize=10)
    ax_equity.grid(True, alpha=0.3)
    
    # Bottom right: Drawdown chart
    ax_dd = fig_overview.add_subplot(gs[2, 1])
    drawdown_series = (cumulative - running_max) / running_max * 100
    ax_dd.fill_between(range(len(drawdown_series)), drawdown_series, alpha=0.3, color='red')
    ax_dd.plot(drawdown_series, color='darkred', linewidth=1)
    ax_dd.set_title('Drawdown Over Time', fontsize=11, fontweight='bold')
    ax_dd.set_ylabel('Drawdown (%)', fontsize=10)
    ax_dd.set_xlabel('Hourly Candles', fontsize=10)
    ax_dd.grid(True, alpha=0.3)
    
    plt.suptitle('EMA Crossover Strategy - Full Period Analysis', fontsize=14, fontweight='bold', y=0.995)
    output_file = 'ema_strategy_full_period.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"✓ Full period plot saved to: {output_file}")
    
    # ===== FIGURE 2: Detailed Recent Period Analysis =====
    fig, axes = plt.subplots(3, 1, figsize=(16, 12))
    
    # Plot 1: Price with EMAs and Signals (Zoomed Recent)
    ax1 = axes[0]
    ax1.plot(df_recent.index, df_recent['Close'], label='Close Price', linewidth=1.5, alpha=0.8, color='black')
    ax1.plot(df_recent.index, df_recent['fast_ema'], label=f'EMA {strategy.fast_period}', 
             linewidth=1.2, color='orange', alpha=0.8)
    ax1.plot(df_recent.index, df_recent['slow_ema'], label=f'EMA {strategy.slow_period}', 
             linewidth=1.2, color='red', alpha=0.8)
    
    # Mark buy and sell signals in recent data
    buy_signals, sell_signals = strategy.identify_crossovers(df_recent)
    
    if buy_signals:
        buy_prices = [df_recent['Close'].iloc[i] for i in buy_signals]
        buy_times = [df_recent.index[i] for i in buy_signals]
        ax1.scatter(buy_times, buy_prices, color='green', marker='^', 
                   s=100, label='Buy Signal', zorder=5)
    
    if sell_signals:
        sell_prices = [df_recent['Close'].iloc[i] for i in sell_signals]
        sell_times = [df_recent.index[i] for i in sell_signals]
        ax1.scatter(sell_times, sell_prices, color='red', marker='v', 
                   s=100, label='Sell Signal', zorder=5)
    
    ax1.set_title('EMA Crossover Strategy - Recent Period Zoom (Last 2000 Candles)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Price ($)', fontsize=10)
    ax1.legend(loc='best', fontsize=9)
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: EMA Difference (Momentum)
    ax2 = axes[1]
    ema_diff = df_recent['fast_ema'] - df_recent['slow_ema']
    colors = ['green' if x > 0 else 'red' for x in ema_diff]
    ax2.bar(df_recent.index, ema_diff, color=colors, alpha=0.6, width=0.02)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax2.set_title('EMA Momentum - Trend Strength (Fast EMA - Slow EMA)', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Difference ($)', fontsize=10)
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Trade results
    ax3 = axes[2]
    if not trades.empty:
        trades_sorted = trades.sort_values('exit_index')
        ax3.plot(range(len(trades_sorted)), trades_sorted['cumsum_pnl'], label='Cumulative P&L', 
                linewidth=2, color='blue', alpha=0.8)
        ax3.fill_between(range(len(trades_sorted)), trades_sorted['cumsum_pnl'], alpha=0.2, color='blue')
        
        # Mark wins and losses
        wins_idx = trades_sorted[trades_sorted['pnl'] > 0].index
        losses_idx = trades_sorted[trades_sorted['pnl'] < 0].index
        
        if not trades_sorted.loc[wins_idx].empty:
            ax3.scatter(wins_idx, trades_sorted.loc[wins_idx, 'cumsum_pnl'], color='green', s=30, 
                       label='Winning Trade', zorder=5, alpha=0.7)
        if not trades_sorted.loc[losses_idx].empty:
            ax3.scatter(losses_idx, trades_sorted.loc[losses_idx, 'cumsum_pnl'], color='red', s=30, 
                       label='Losing Trade', zorder=5, alpha=0.7)
    
    ax3.axhline(y=0, color='black', linestyle='--', linewidth=1)
    ax3.set_title('Cumulative P&L Over Time (Zoomed Period)', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Cumulative P&L ($)', fontsize=10)
    ax3.set_xlabel('Trade Number', fontsize=10)
    ax3.legend(loc='best', fontsize=9)
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    output_file2 = 'ema_strategy_detailed.png'
    plt.savefig(output_file2, dpi=150, bbox_inches='tight')
    print(f"✓ Detailed plot saved to: {output_file2}")
    
    # ===== FIGURE 3: Trade Statistics =====
    fig2, axes2 = plt.subplots(2, 3, figsize=(16, 8))
    
    # Win/Loss distribution
    ax = axes2[0, 0]
    wins = sum(trades['pnl'] > 0)
    losses = sum(trades['pnl'] < 0)
    ax.bar(['Wins', 'Losses'], [wins, losses], color=['green', 'red'], alpha=0.7)
    ax.set_title('Trade Outcomes', fontsize=11, fontweight='bold')
    ax.set_ylabel('Number of Trades', fontsize=10)
    for i, v in enumerate([wins, losses]):
        ax.text(i, v + 5, str(v), ha='center', fontweight='bold')
    
    # Win/Loss P&L comparison
    ax = axes2[0, 1]
    win_pnl = trades[trades['pnl'] > 0]['pnl'].sum()
    loss_pnl = trades[trades['pnl'] < 0]['pnl'].sum()
    ax.bar(['Total Wins', 'Total Losses'], [win_pnl, loss_pnl], color=['green', 'red'], alpha=0.7)
    ax.set_title('Total P&L by Outcome', fontsize=11, fontweight='bold')
    ax.set_ylabel('P&L ($)', fontsize=10)
    
    # Sharpe Ratio display
    ax = axes2[0, 2]
    ax.axis('off')
    sharpe_text = f"Sharpe Ratio\n{sharpe_ratio:.2f}"
    ax.text(0.5, 0.5, sharpe_text, transform=ax.transAxes,
           fontsize=14, verticalalignment='center', horizontalalignment='center',
           bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.5),
           fontweight='bold')
    
    # P&L per trade distribution
    ax = axes2[1, 0]
    ax.hist(trades['pnl'], bins=50, color='steelblue', alpha=0.7, edgecolor='black')
    ax.axvline(x=0, color='red', linestyle='--', linewidth=2)
    ax.set_title('P&L Distribution', fontsize=11, fontweight='bold')
    ax.set_xlabel('P&L per Trade ($)', fontsize=10)
    ax.set_ylabel('Frequency', fontsize=10)
    
    # Win rate pie chart
    ax = axes2[1, 1]
    sizes = [wins, losses]
    labels = [f'Wins\n{wins/len(trades)*100:.1f}%', f'Losses\n{losses/len(trades)*100:.1f}%']
    colors_pie = ['green', 'red']
    wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors_pie, autopct='%1.1f%%', startangle=90)
    for wedge in wedges:
        wedge.set_alpha(0.7)
    ax.set_title('Win Rate', fontsize=11, fontweight='bold')
    
    # Win rate text display
    ax = axes2[1, 2]
    ax.axis('off')
    wr_text = f"Win Rate\n{win_rate:.1f}%"
    ax.text(0.5, 0.5, wr_text, transform=ax.transAxes,
           fontsize=14, verticalalignment='center', horizontalalignment='center',
           bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.5),
           fontweight='bold')
    
    plt.tight_layout()
    
    # Save statistics figure
    output_file3 = 'ema_strategy_statistics.png'
    plt.savefig(output_file3, dpi=150, bbox_inches='tight')
    print(f"✓ Statistics plot saved to: {output_file3}")
    
    return df, trades

if __name__ == "__main__":
    try:
        df, trades = plot_strategy_analysis()
        print("\nVisualization complete!")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Run 'python backtest.py' first to generate results")
