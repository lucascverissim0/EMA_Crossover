"""
Comprehensive Trading Strategy Analysis
Calculates advanced metrics: risk of ruin, holding time, drawdown, trade frequency, and more
"""

import pandas as pd
import numpy as np
from datetime import datetime
import json

def calculate_holding_time(trades_df):
    """Calculate average holding time in hours and days"""
    trades_df['holding_indices'] = trades_df['exit_index'] - trades_df['entry_index']
    # Assuming 1-hour candles
    holding_hours = trades_df['holding_indices'].mean()
    holding_days = holding_hours / 24
    return holding_hours, holding_days

def calculate_max_drawdown(equity_curve):
    """Calculate maximum drawdown percentage"""
    cumulative_returns = equity_curve.values
    running_max = np.maximum.accumulate(cumulative_returns)
    drawdown = (cumulative_returns - running_max) / running_max
    max_drawdown_pct = np.min(drawdown) * 100
    return max_drawdown_pct, drawdown

def calculate_risk_of_ruin(trades_df, initial_capital=10000):
    """
    Calculate risk of ruin using Ralph Vince's formula
    Risk of Ruin = (1 - f) ^ N when win_rate = loss_rate = 50%
    More advanced: considers win rates and win/loss ratios
    """
    if len(trades_df) == 0:
        return 0
    
    # Calculate trading statistics
    total_trades = len(trades_df)
    wins = (trades_df['pnl'] > 0).sum()
    losses = (trades_df['pnl'] < 0).sum()
    
    if losses == 0:
        return 0  # No risk if no losses
    
    win_rate = wins / total_trades if total_trades > 0 else 0
    
    # Calculate average win and loss
    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if wins > 0 else 0
    avg_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].mean()) if losses > 0 else 0
    
    if avg_loss == 0:
        return 0
    
    # Profit factor (total wins / total losses)
    total_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    total_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())
    
    if total_loss == 0:
        return 0
    
    profit_factor = total_profit / total_loss if total_loss > 0 else 0
    
    # Risk of Ruin calculation (Ralph Vince's method)
    # f = (bp - q) / b, where b is the win/loss ratio, p is win rate, q is loss rate
    if avg_win > 0:
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - win_rate
        
        # Calculate f (optimal fraction of capital to risk)
        if b != 1:
            f = (b * p - q) / b
        else:
            f = p - q
        
        # Ensure f is between 0 and 1
        f = max(0, min(f, 0.99))
        
        # Risk of Ruin = (q/p)^N where N is number of trades for drawdown to zero
        # Simplified approach using Kelly Criterion derivative
        if p > q:
            # Risk of Ruin decreases with more trades when strategy is profitable
            ror = ((1 - f) / (1 + f)) ** min(total_trades, 100)
        else:
            # Strategy losing more than winning
            ror = 1.0
    else:
        ror = 1.0
    
    return max(0, min(ror, 1)) * 100

def calculate_consecutive_losses(trades_df):
    """Calculate maximum consecutive losing trades"""
    losing_trades = (trades_df['pnl'] < 0).astype(int)
    max_consecutive = 0
    current_consecutive = 0
    
    for loss in losing_trades:
        if loss == 1:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0
    
    return max_consecutive

def calculate_consecutive_wins(trades_df):
    """Calculate maximum consecutive winning trades"""
    winning_trades = (trades_df['pnl'] > 0).astype(int)
    max_consecutive = 0
    current_consecutive = 0
    
    for win in winning_trades:
        if win == 1:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0
    
    return max_consecutive

def calculate_recovery_factor(trades_df, max_dd):
    """
    Recovery Factor = Total Profit / Max Drawdown
    Higher is better (measure of profit relative to risk)
    """
    total_profit = trades_df['pnl'].sum()
    if max_dd == 0:
        return np.inf if total_profit > 0 else 0
    return total_profit / abs(max_dd)

def calculate_profit_factor(trades_df):
    """Profit Factor = Gross Profit / Gross Loss"""
    gross_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    gross_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())
    
    if gross_loss == 0:
        return np.inf if gross_profit > 0 else 0
    return gross_profit / gross_loss

def calculate_trades_per_day(trades_df, date_column):
    """Calculate average trades per day"""
    if len(trades_df) == 0:
        return 0
    
    first_date = trades_df[date_column].min().date()
    last_date = trades_df[date_column].max().date()
    days_active = (last_date - first_date).days + 1
    
    trades_per_day = len(trades_df) / days_active if days_active > 0 else 0
    return trades_per_day, days_active

def calculate_winning_rate_breakdown(trades_df):
    """Calculate winning rates by year and month"""
    trades_df['year'] = trades_df['exit_date'].dt.year
    trades_df['month'] = trades_df['exit_date'].dt.month
    
    yearly_stats = []
    for year in sorted(trades_df['year'].unique()):
        year_trades = trades_df[trades_df['year'] == year]
        year_wins = (year_trades['pnl'] > 0).sum()
        year_total = len(year_trades)
        year_wr = (year_wins / year_total * 100) if year_total > 0 else 0
        year_pnl = year_trades['pnl'].sum()
        
        yearly_stats.append({
            'year': year,
            'total_trades': year_total,
            'wins': year_wins,
            'losses': year_total - year_wins,
            'win_rate': year_wr,
            'total_pnl': year_pnl
        })
    
    return pd.DataFrame(yearly_stats)

def analyze_strategy(backtest_results_file='backtest_results_ml_optimized_fixed.csv',
                     price_data_file='data/XAUUSD_1h_sample.csv',
                     initial_capital=10000):
    """
    Comprehensive strategy analysis
    """
    
    print("\n" + "="*80)
    print("COMPREHENSIVE TRADING STRATEGY ANALYSIS")
    print("="*80 + "\n")
    
    # Load data
    print("Loading data...")
    trades_df = pd.read_csv(backtest_results_file)
    price_df = pd.read_csv(price_data_file, index_col=0, parse_dates=True)
    
    # Map exit dates
    date_map = {}
    for idx, date in enumerate(price_df.index):
        date_map[idx] = date
    
    trades_df['exit_date'] = trades_df['exit_index'].map(date_map)
    trades_df['entry_date'] = trades_df['entry_index'].map(date_map)
    
    # Calculate equity curve
    trades_df['cumulative_pnl'] = trades_df['pnl'].cumsum()
    trades_df['balance'] = initial_capital + trades_df['cumulative_pnl']
    
    # ===== BASIC STATISTICS =====
    print("\n" + "─"*80)
    print("1. BASIC TRADING STATISTICS")
    print("─"*80)
    
    total_trades = len(trades_df)
    wins = (trades_df['pnl'] > 0).sum()
    losses = (trades_df['pnl'] < 0).sum()
    breakeven = (trades_df['pnl'] == 0).sum()
    
    print(f"Total Trades:                    {total_trades:,}")
    print(f"  ├─ Winning Trades:             {wins:,} ({wins/total_trades*100:.2f}%)")
    print(f"  ├─ Losing Trades:              {losses:,} ({losses/total_trades*100:.2f}%)")
    print(f"  └─ Breakeven Trades:           {breakeven:,} ({breakeven/total_trades*100:.2f}%)")
    
    # ===== P&L STATISTICS =====
    print("\n" + "─"*80)
    print("2. PROFIT & LOSS STATISTICS")
    print("─"*80)
    
    total_pnl = trades_df['pnl'].sum()
    gross_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    gross_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())
    
    print(f"Total P&L:                       ${total_pnl:,.2f}")
    print(f"Gross Profit:                    ${gross_profit:,.2f}")
    print(f"Gross Loss:                      ${gross_loss:,.2f}")
    print(f"Return on Initial Capital:       {(total_pnl/initial_capital)*100:.2f}%")
    print(f"Return on Final Balance:         {(total_pnl/trades_df['balance'].iloc[-1])*100:.2f}%")
    
    # ===== AVERAGE TRADE METRICS =====
    print("\n" + "─"*80)
    print("3. AVERAGE TRADE METRICS")
    print("─"*80)
    
    avg_trade_pnl = trades_df['pnl'].mean()
    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if wins > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if losses > 0 else 0
    avg_loss_abs = abs(avg_loss)
    
    print(f"Average Trade P&L:               ${avg_trade_pnl:,.2f}")
    print(f"Average Winning Trade:           ${avg_win:,.2f}")
    print(f"Average Losing Trade:            ${avg_loss:,.2f}")
    print(f"Win/Loss Ratio:                  {abs(avg_win/avg_loss_abs):.2f}x" if avg_loss_abs > 0 else "N/A")
    
    # ===== EXTREMES =====
    print("\n" + "─"*80)
    print("4. TRADE EXTREMES")
    print("─"*80)
    
    largest_win = trades_df['pnl'].max()
    largest_loss = trades_df['pnl'].min()
    largest_win_idx = trades_df[trades_df['pnl'] == largest_win].index[0]
    largest_loss_idx = trades_df[trades_df['pnl'] == largest_loss].index[0]
    
    print(f"Largest Win:                     ${largest_win:,.2f}")
    print(f"  └─ Trade #{largest_win_idx + 1} at {trades_df.loc[largest_win_idx, 'exit_date']}")
    print(f"Largest Loss:                    ${largest_loss:,.2f}")
    print(f"  └─ Trade #{largest_loss_idx + 1} at {trades_df.loc[largest_loss_idx, 'exit_date']}")
    print(f"Max Consecutive Wins:            {calculate_consecutive_wins(trades_df):,} trades")
    print(f"Max Consecutive Losses:          {calculate_consecutive_losses(trades_df):,} trades")
    
    # ===== HOLDING TIME =====
    print("\n" + "─"*80)
    print("5. HOLDING TIME & TRADE FREQUENCY")
    print("─"*80)
    
    holding_hours, holding_days = calculate_holding_time(trades_df)
    trades_per_day, total_days = calculate_trades_per_day(trades_df, 'exit_date')
    
    print(f"Average Holding Time:            {holding_hours:.1f} hours ({holding_days:.2f} days)")
    print(f"Average Trades Per Day:          {trades_per_day:.2f}")
    print(f"Trading Days Covered:            {total_days:,} days")
    
    # Exit reason breakdown
    exit_reasons = trades_df['reason'].value_counts()
    print(f"\nExit Reason Breakdown:")
    for reason, count in exit_reasons.items():
        pct = (count / total_trades) * 100
        reason_pnl = trades_df[trades_df['reason'] == reason]['pnl'].sum()
        print(f"  ├─ {reason:20s}: {count:5,} trades ({pct:5.1f}%) | P&L: ${reason_pnl:>12,.2f}")
    
    # ===== DRAWDOWN ANALYSIS =====
    print("\n" + "─"*80)
    print("6. DRAWDOWN & RISK ANALYSIS")
    print("─"*80)
    
    equity_curve = trades_df['balance'].values
    max_dd_pct, drawdown_series = calculate_max_drawdown(equity_curve)
    
    max_dd_dollars = (max_dd_pct / 100) * equity_curve[0]
    
    print(f"Maximum Drawdown:                {max_dd_pct:.2f}%")
    print(f"Maximum Drawdown (USD):          ${max_dd_dollars:,.2f}")
    print(f"Starting Capital:                ${initial_capital:,.2f}")
    print(f"Ending Capital:                  ${trades_df['balance'].iloc[-1]:,.2f}")
    
    # ===== RISK OF RUIN & RECOVERY FACTOR =====
    print("\n" + "─"*80)
    print("7. RISK METRICS")
    print("─"*80)
    
    ror = calculate_risk_of_ruin(trades_df, initial_capital)
    recovery_factor = calculate_recovery_factor(trades_df, max_dd_dollars)
    profit_factor = calculate_profit_factor(trades_df)
    
    print(f"Risk of Ruin (Ralph Vince):      {ror:.2f}%")
    print(f"Recovery Factor:                 {recovery_factor:.2f}x")
    print(f"Profit Factor:                   {profit_factor:.2f}x")
    
    print(f"\nRisk Interpretation:")
    print(f"  ├─ Risk of Ruin {ror:.2f}%: ", end="")
    if ror < 0.01:
        print("✓ EXCELLENT - Almost no chance of ruin")
    elif ror < 0.05:
        print("✓ VERY GOOD - Low risk of ruin")
    elif ror < 0.15:
        print("✓ GOOD - Manageable risk")
    elif ror < 0.30:
        print("⚠ MODERATE - Acceptable but monitor")
    else:
        print("✗ HIGH - Significant risk present")
    
    print(f"  ├─ Recovery Factor {recovery_factor:.2f}x: ", end="")
    if recovery_factor > 3:
        print("✓ EXCELLENT - Profits >> Drawdown")
    elif recovery_factor > 2:
        print("✓ VERY GOOD")
    elif recovery_factor > 1:
        print("✓ GOOD")
    else:
        print("✗ POOR - Profits < Drawdown")
    
    print(f"  └─ Profit Factor {profit_factor:.2f}x: ", end="")
    if profit_factor > 2:
        print("✓ EXCELLENT - 2x more profit than loss")
    elif profit_factor > 1.5:
        print("✓ VERY GOOD")
    elif profit_factor > 1:
        print("✓ GOOD")
    else:
        print("✗ POOR")
    
    # ===== SHARPE RATIO & RETURN METRICS =====
    print("\n" + "─"*80)
    print("8. PERFORMANCE RATIOS")
    print("─"*80)
    
    # Calculate returns
    trades_df['trade_return'] = trades_df['pnl_percent'] / 100
    returns_mean = trades_df['trade_return'].mean()
    returns_std = trades_df['trade_return'].std()
    
    # Sharpe Ratio (annualized, assuming 252 trading days, 24 hours per day = 6,048 hours)
    sharpe_ratio = (returns_mean / returns_std * np.sqrt(6048)) if returns_std > 0 else 0
    
    # Sortino Ratio (only considers downside deviation)
    downside_returns = trades_df[trades_df['trade_return'] < 0]['trade_return']
    downside_std = downside_returns.std()
    sortino_ratio = (returns_mean / downside_std * np.sqrt(6048)) if downside_std > 0 else 0
    
    # Calmar Ratio (Annual Return / Max Drawdown)
    daily_return = (trades_df['balance'].iloc[-1] - initial_capital) / initial_capital
    calmar_ratio = daily_return / abs(max_dd_pct/100) if max_dd_pct != 0 else 0
    
    print(f"Sharpe Ratio (Annualized):       {sharpe_ratio:.2f}")
    print(f"Sortino Ratio (Annualized):      {sortino_ratio:.2f}")
    print(f"Calmar Ratio:                    {calmar_ratio:.2f}")
    
    # ===== YEARLY BREAKDOWN =====
    print("\n" + "─"*80)
    print("9. YEARLY PERFORMANCE BREAKDOWN")
    print("─"*80)
    
    yearly_stats = calculate_winning_rate_breakdown(trades_df)
    
    print(f"\n{'Year':<8} {'Trades':<8} {'Wins':<8} {'Losses':<8} {'Win %':<8} {'P&L':<15}")
    print("─" * 55)
    for _, row in yearly_stats.iterrows():
        print(f"{int(row['year']):<8} {int(row['total_trades']):<8} {int(row['wins']):<8} "
              f"{int(row['losses']):<8} {row['win_rate']:>6.1f}% ${row['total_pnl']:>12,.2f}")
    
    # ===== SUMMARY RECOMMENDATIONS =====
    print("\n" + "─"*80)
    print("10. STRATEGY ADAPTATION RECOMMENDATIONS")
    print("─"*80)
    
    recommendations = []
    
    # Analysis based on metrics
    if ror < 0.05:
        recommendations.append("✓ Risk of ruin is LOW - Strategy is stable")
    elif ror > 0.15:
        recommendations.append("⚠ Risk of ruin is HIGH - Consider:")
        recommendations.append("  • Reducing position size")
        recommendations.append("  • Tightening stop loss")
        recommendations.append("  • Increasing take profit")
    
    if trades_per_day < 0.5:
        recommendations.append("• Strategy trades INFREQUENTLY - Consider if this meets your goals")
    elif trades_per_day > 5:
        recommendations.append("⚠ Strategy trades FREQUENTLY - Monitor for:")
        recommendations.append("  • Overtrading and slippage costs")
        recommendations.append("  • Market impact on large orders")
    
    if recovery_factor < 1:
        recommendations.append("✗ Recovery factor < 1 - Strategy may need optimization")
    elif recovery_factor > 2:
        recommendations.append("✓ Recovery factor is STRONG - Profits significantly exceed drawdown")
    
    if holding_hours < 1:
        recommendations.append("• Strategy holds positions for LESS THAN 1 HOUR on average")
    elif holding_hours > 168:  # 1 week
        recommendations.append("• Strategy holds positions for OVER 1 WEEK on average")
    
    if yearly_stats['win_rate'].std() > 10:
        recommendations.append("⚠ Win rate varies significantly by year - Check for market dependency")
    else:
        recommendations.append("✓ Win rate CONSISTENT across years - Good robustness")
    
    if profit_factor > 1.5:
        recommendations.append("✓ Profit factor is STRONG - Good risk/reward")
    
    for rec in recommendations:
        print(rec)
    
    print("\n" + "="*80 + "\n")
    
    return {
        'total_trades': total_trades,
        'win_rate': wins/total_trades*100,
        'total_pnl': total_pnl,
        'max_drawdown': max_dd_pct,
        'risk_of_ruin': ror,
        'holding_time_hours': holding_hours,
        'trades_per_day': trades_per_day,
        'sharpe_ratio': sharpe_ratio,
        'recovery_factor': recovery_factor,
        'profit_factor': profit_factor
    }

if __name__ == "__main__":
    analyze_strategy()
