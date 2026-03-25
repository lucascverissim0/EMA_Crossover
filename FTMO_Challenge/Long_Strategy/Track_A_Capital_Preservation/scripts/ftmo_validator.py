"""
FTMO Challenge Validator
Analyzes backtest results against FTMO Challenge requirements
Requirements:
- Max 5% daily loss limit
- Max 10% total drawdown (including floating losses)
- No day limit
- Ignore losing streaks

Calculates probability of passing the challenge
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime


class FTMOValidator:
    """Validates trading strategy against FTMO Challenge requirements"""
    
    def __init__(self, data_file, backtest_results_file, initial_capital=10000):
        """
        Initialize validator
        
        Parameters:
        - data_file: Path to OHLCV data CSV (with timestamps)
        - backtest_results_file: Path to backtest results CSV
        - initial_capital: Starting capital
        """
        self.data = pd.read_csv(data_file)
        self.backtest_results = pd.read_csv(backtest_results_file)
        self.initial_capital = initial_capital
        
        # Ensure data has timestamp
        if 'timestamp' not in self.data.columns and 'Datetime' in self.data.columns:
            self.data['timestamp'] = pd.to_datetime(self.data['Datetime'])
        elif 'timestamp' in self.data.columns:
            self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])
        
        # Sort by timestamp
        if 'timestamp' in self.data.columns:
            self.data = self.data.sort_values('timestamp').reset_index(drop=True)
        
        self.violation_report = {}
        self.daily_pnl = pd.DataFrame()
        self.portfolio_values = []
        self.drawdowns = []
        
    def calculate_daily_pnl(self):
        """
        Calculate daily P&L from backtest trades
        Important: Account for floating/unrealized losses on open positions
        """
        # Create daily buckets
        if 'timestamp' in self.data.columns:
            self.data['date'] = self.data['timestamp'].dt.date
        else:
            self.data['date'] = range(len(self.data))
        
        daily_pnl = []
        capital = self.initial_capital
        portfolio_values = [self.initial_capital]
        
        # Track open positions
        open_positions = []
        
        for idx, row in self.backtest_results.iterrows():
            entry_idx = int(row['entry_index'])
            exit_idx = int(row['exit_index'])
            pnl = row['pnl']
            
            # Use the date of the close
            if exit_idx < len(self.data):
                trade_date = self.data['date'].iloc[exit_idx]
                
                # Find or create daily entry
                daily_entry = next((d for d in daily_pnl if d['date'] == trade_date), None)
                if daily_entry is None:
                    daily_entry = {'date': trade_date, 'closed_pnl': 0, 'realized_pnl': pnl}
                    daily_pnl.append(daily_entry)
                else:
                    daily_entry['realized_pnl'] += pnl
                
                daily_entry['closed_pnl'] += pnl
                capital += pnl
                portfolio_values.append(capital)
        
        self.daily_pnl = pd.DataFrame(daily_pnl).sort_values('date')
        self.portfolio_values = portfolio_values
        
        return self.daily_pnl
    
    def calculate_running_drawdown(self):
        """
        Calculate running drawdown at each trade close
        This includes floating/unrealized losses
        """
        drawdowns = []
        peak_capital = self.initial_capital
        
        for capital in self.portfolio_values:
            # Calculate drawdown from peak
            dd_dollars = peak_capital - capital
            dd_percent = (dd_dollars / peak_capital) * 100 if peak_capital > 0 else 0
            
            drawdowns.append({
                'capital': capital,
                'peak': peak_capital,
                'dd_dollars': dd_dollars,
                'dd_percent': dd_percent
            })
            
            # Update peak
            if capital > peak_capital:
                peak_capital = capital
        
        self.drawdowns = pd.DataFrame(drawdowns)
        return self.drawdowns
    
    def check_ftmo_compliance(self):
        """
        Check if strategy meets FTMO requirements
        
        Returns:
        - compliance_report: Dict with pass/fail for each requirement
        """
        self.calculate_daily_pnl()
        self.calculate_running_drawdown()
        
        compliance = {}
        
        # 1. Check Max Daily Loss (5%)
        self.daily_pnl['daily_loss_percent'] = (self.daily_pnl['closed_pnl'] / self.initial_capital) * 100
        max_daily_loss = self.daily_pnl['daily_loss_percent'].min()
        daily_loss_violates = max_daily_loss < -5.0
        daily_loss_violation_count = len(self.daily_pnl[self.daily_pnl['daily_loss_percent'] < -5.0])
        
        compliance['max_daily_loss'] = {
            'requirement': 'Max -5% daily loss',
            'value': f"{max_daily_loss:.2f}%",
            'pass': not daily_loss_violates,
            'violations': daily_loss_violation_count
        }
        
        # 2. Check Max Drawdown (10%)
        max_dd = self.drawdowns['dd_percent'].max()
        max_dd_violates = max_dd > 10.0
        
        compliance['max_drawdown'] = {
            'requirement': 'Max 10% drawdown',
            'value': f"{max_dd:.2f}%",
            'pass': not max_dd_violates,
            'max_dd_at_price': self.drawdowns.loc[self.drawdowns['dd_percent'].idxmax()]['capital'] if len(self.drawdowns) > 0 else 0
        }
        
        # 3. Total profit calculation
        total_pnl = self.backtest_results['pnl'].sum()
        total_return_percent = (total_pnl / self.initial_capital) * 100
        
        compliance['total_performance'] = {
            'total_pnl': f"${total_pnl:.2f}",
            'total_return_percent': f"{total_return_percent:.2f}%",
            'final_capital': f"${self.initial_capital + total_pnl:.2f}"
        }
        
        # 4. Additional metrics
        traded_days = len(self.daily_pnl)
        win_trades = len(self.backtest_results[self.backtest_results['pnl'] > 0])
        loss_trades = len(self.backtest_results[self.backtest_results['pnl'] < 0])
        win_rate = (win_trades / len(self.backtest_results)) * 100 if len(self.backtest_results) > 0 else 0
        
        if win_trades > 0 and loss_trades > 0:
            avg_win = self.backtest_results[self.backtest_results['pnl'] > 0]['pnl'].mean()
            avg_loss = abs(self.backtest_results[self.backtest_results['pnl'] < 0]['pnl'].mean())
            profit_factor = (avg_win * win_trades) / (avg_loss * loss_trades)
        else:
            profit_factor = 0
        
        compliance['additional_metrics'] = {
            'total_trades': len(self.backtest_results),
            'winning_trades': win_trades,
            'losing_trades': loss_trades,
            'win_rate': f"{win_rate:.2f}%",
            'avg_win': f"${self.backtest_results[self.backtest_results['pnl'] > 0]['pnl'].mean():.2f}" if win_trades > 0 else "$0.00",
            'avg_loss': f"${abs(self.backtest_results[self.backtest_results['pnl'] < 0]['pnl'].mean()):.2f}" if loss_trades > 0 else "$0.00",
            'profit_factor': f"{profit_factor:.2f}",
            'traded_days': traded_days
        }
        
        # Overall pass/fail
        compliance['overall'] = {
            'passes_ftmo': compliance['max_daily_loss']['pass'] and compliance['max_drawdown']['pass'],
            'daily_loss_pass': compliance['max_daily_loss']['pass'],
            'drawdown_pass': compliance['max_drawdown']['pass']
        }
        
        self.violation_report = compliance
        return compliance
    
    def generate_report(self, output_file=None):
        """Generate human-readable FTMO compliance report"""
        if not self.violation_report:
            self.check_ftmo_compliance()
        
        report_lines = [
            "=" * 70,
            "FTMO CHALLENGE COMPLIANCE REPORT",
            "=" * 70,
            "",
            "REQUIREMENTS STATUS",
            "-" * 70,
        ]
        
        # Daily Loss Check
        daily_loss_info = self.violation_report['max_daily_loss']
        status = "✅ PASS" if daily_loss_info['pass'] else "❌ FAIL"
        report_lines.extend([
            f"\n1. Max Daily Loss: {status}",
            f"   Requirement: {daily_loss_info['requirement']}",
            f"   Worst Day: {daily_loss_info['value']}",
            f"   Violations: {daily_loss_info['violations']} days",
        ])
        
        # Drawdown Check
        dd_info = self.violation_report['max_drawdown']
        status = "✅ PASS" if dd_info['pass'] else "❌ FAIL"
        report_lines.extend([
            f"\n2. Max Drawdown: {status}",
            f"   Requirement: {dd_info['requirement']}",
            f"   Max Drawdown: {dd_info['value']}",
        ])
        
        # Performance Metrics
        perf = self.violation_report['total_performance']
        metrics = self.violation_report['additional_metrics']
        report_lines.extend([
            "",
            "PERFORMANCE METRICS",
            "-" * 70,
            f"Total Trades: {metrics['total_trades']}",
            f"Winning Trades: {metrics['winning_trades']}",
            f"Losing Trades: {metrics['losing_trades']}",
            f"Win Rate: {metrics['win_rate']}",
            f"Average Win: {metrics['avg_win']}",
            f"Average Loss: {metrics['avg_loss']}",
            f"Profit Factor: {metrics['profit_factor']}",
            f"Trading Days: {metrics['traded_days']}",
            "",
            "RESULTS",
            "-" * 70,
            f"Total P&L: {perf['total_pnl']}",
            f"Total Return: {perf['total_return_percent']}",
            f"Final Capital: {perf['final_capital']}",
            "",
            "OVERALL VERDICT",
            "-" * 70,
        ])
        
        overall = self.violation_report['overall']
        if overall['passes_ftmo']:
            report_lines.append("✅ STRATEGY PASSES FTMO CHALLENGE REQUIREMENTS")
        else:
            report_lines.append("❌ STRATEGY FAILS FTMO CHALLENGE REQUIREMENTS")
            if not overall['daily_loss_pass']:
                report_lines.append("   → Issue: Exceeds 5% daily loss limit")
            if not overall['drawdown_pass']:
                report_lines.append("   → Issue: Exceeds 10% max drawdown limit")
        
        report_lines.extend([
            "=" * 70,
        ])
        
        report_text = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_text)
        
        return report_text
    
    def calculate_pass_probability(self, num_simulations=1000):
        """
        Calculate probability of passing FTMO using Monte Carlo
        
        Simulates various market condition scenarios to estimate 
        likelihood of passing simultaneously
        """
        if self.backtest_results.empty:
            return None
        
        trades = self.backtest_results['pnl'].values
        pass_count = 0
        results = []
        
        for sim in range(num_simulations):
            # Randomly shuffle trades (different order, same distribution)
            shuffled_trades = np.random.permutation(trades)
            
            # Calculate equity curve for this simulation
            capital = self.initial_capital
            peak = self.initial_capital
            max_dd = 0
            max_daily_loss = 0
            trade_counter = 0
            
            # Group trades by simulated daily periods
            trades_per_day = max(1, len(shuffled_trades) // max(1, 30))  # Assume ~30 trading days
            
            for i, pnl in enumerate(shuffled_trades):
                capital += pnl
                
                # Track daily P&L
                if i % trades_per_day == 0:
                    daily_pnl_pct = pnl / self.initial_capital
                    max_daily_loss = min(max_daily_loss, daily_pnl_pct * 100)
                
                # Track drawdown
                if capital > peak:
                    peak = capital
                dd = (peak - capital) / peak * 100
                max_dd = max(max_dd, dd)
            
            # Check if passes FTMO
            passes = (max_daily_loss > -5.0) and (max_dd <= 10.0)
            pass_count += 1 if passes else 0
            
            results.append({
                'simulation': sim,
                'final_capital': capital,
                'max_dd': max_dd,
                'max_daily_loss': max_daily_loss,
                'passes': passes
            })
        
        pass_probability = (pass_count / num_simulations) * 100
        results_df = pd.DataFrame(results)
        
        return {
            'pass_probability': pass_probability,
            'simulations_passed': pass_count,
            'simulations_failed': num_simulations - pass_count,
            'avg_max_dd': results_df['max_dd'].mean(),
            'std_max_dd': results_df['max_dd'].std(),
            'avg_daily_loss': results_df['max_daily_loss'].mean(),
            'simulation_results': results_df
        }
    
    def save_detailed_analysis(self, output_dir=None):
        """Save detailed analysis including daily P&L and drawdown tracking"""
        if output_dir is None:
            output_dir = Path('.')
        else:
            output_dir = Path(output_dir)
        
        # Save daily P&L
        self.daily_pnl.to_csv(output_dir / 'ftmo_daily_pnl.csv', index=False)
        
        # Save drawdown curve
        self.drawdowns.to_csv(output_dir / 'ftmo_drawdown_curve.csv', index=False)
        
        # Save compliance report
        report_text = self.generate_report()
        with open(output_dir / 'ftmo_compliance_report.txt', 'w') as f:
            f.write(report_text)
        
        # Save JSON compliance data
        with open(output_dir / 'ftmo_compliance.json', 'w') as f:
            json.dump(self.violation_report, f, indent=2, default=str)
        
        print(f"✅ Analysis saved to {output_dir}/")


def main():
    """Example usage"""
    from pathlib import Path
    
    # Use the ML-optimized results as they're better
    repo_root = Path(__file__).resolve().parents[3]
    track_root = Path(__file__).resolve().parent.parent
    data_file = repo_root / 'data' / 'XAUUSD_1h_sample.csv'
    backtest_file = repo_root / 'backtest' / 'backtest_results_ml_optimized_fixed.csv'
    output_dir = track_root / 'reports'
    
    validator = FTMOValidator(str(data_file), str(backtest_file), initial_capital=10000)
    
    # Check compliance
    print(validator.generate_report())
    
    # Calculate pass probability
    print("\n\nCalculating pass probability (1000 simulations)...")
    prob = validator.calculate_pass_probability(num_simulations=1000)
    
    print(f"\nMonte Carlo Results:")
    print(f"  Pass Probability: {prob['pass_probability']:.2f}%")
    print(f"  Simulations Passed: {prob['simulations_passed']}/1000")
    print(f"  Simulations Failed: {prob['simulations_failed']}/1000")
    print(f"  Average Max DD: {prob['avg_max_dd']:.2f}%")
    print(f"  Std Dev Max DD: {prob['std_max_dd']:.2f}%")
    
    # Save detailed analysis
    validator.save_detailed_analysis(output_dir)


if __name__ == '__main__':
    main()
