"""
FTMO Challenge Visualizations
Creates comprehensive charts for FTMO compliance analysis
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

plt.style.use('seaborn-v0_8-darkgrid')


class FTMOVisualizer:
    """Creates visualizations for FTMO analysis"""
    
    def __init__(self, base_dir=None):
        """Initialize visualizer"""
        if base_dir is None:
            base_dir = Path(__file__).parent
        else:
            base_dir = Path(base_dir)
        
        self.base_dir = base_dir
        self.daily_pnl = None
        self.drawdown_curve = None
        self.compliance = None
        
        # Load data
        self._load_data()
    
    def _load_data(self):
        """Load required data files"""
        daily_pnl_file = self.base_dir / 'ftmo_daily_pnl.csv'
        dd_file = self.base_dir / 'ftmo_drawdown_curve.csv'
        compliance_file = self.base_dir / 'ftmo_compliance.json'
        
        if daily_pnl_file.exists():
            self.daily_pnl = pd.read_csv(daily_pnl_file)
        
        if dd_file.exists():
            self.drawdown_curve = pd.read_csv(dd_file)
        
        if compliance_file.exists():
            with open(compliance_file) as f:
                self.compliance = json.load(f)
    
    def plot_daily_pnl(self, output_file=None):
        """Plot daily P&L as bar chart"""
        if self.daily_pnl is None or len(self.daily_pnl) == 0:
            print("⚠️  No daily P&L data available")
            return
        
        df = self.daily_pnl.copy()
        
        # Create figure
        fig, ax = plt.subplots(figsize=(14, 6))
        
        # Create bar chart - color green for profits, red for losses
        colors = ['green' if x >= 0 else 'red' for x in df['closed_pnl']]
        ax.bar(range(len(df)), df['closed_pnl'], color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)
        
        # Add zero line
        ax.axhline(y=0, color='black', linestyle='-', linewidth=1)
        
        # Labels and title
        ax.set_xlabel('Trading Day', fontsize=11, fontweight='bold')
        ax.set_ylabel('Daily P&L ($)', fontsize=11, fontweight='bold')
        ax.set_title('Daily Profit & Loss (FTMO Challenge Analysis)', fontsize=13, fontweight='bold')
        
        # Format y-axis with $ signs
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Add statistics box
        total_pnl = df['closed_pnl'].sum()
        avg_pnl = df['closed_pnl'].mean()
        max_daily = df['closed_pnl'].max()
        min_daily = df['closed_pnl'].min()
        
        stats_text = f"Total P&L: ${total_pnl:,.0f}\nAvg Daily: ${avg_pnl:,.0f}\nBest Day: ${max_daily:,.0f}\nWorst Day: ${min_daily:,.0f}"
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=10,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                family='monospace')
        
        plt.tight_layout()
        
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            print(f"✅ Saved daily P&L chart to {output_file}")
        
        return fig
    
    def plot_drawdown_curve(self, output_file=None):
        """Plot drawdown curve with limit line"""
        if self.drawdown_curve is None or len(self.drawdown_curve) == 0:
            print("⚠️  No drawdown data available")
            return
        
        df = self.drawdown_curve.copy()
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        
        # Plot 1: Equity curve and peak
        ax1.plot(range(len(df)), df['capital'], linewidth=2, label='Account Equity', color='green', alpha=0.8)
        ax1.plot(range(len(df)), df['peak'], linewidth=1, label='Peak Equity', color='blue', linestyle='--', alpha=0.6)
        ax1.fill_between(range(len(df)), df['capital'], df['peak'], alpha=0.2, color='red')
        
        ax1.set_xlabel('Trade #', fontsize=11, fontweight='bold')
        ax1.set_ylabel('Account Value ($)', fontsize=11, fontweight='bold')
        ax1.set_title('Equity Curve with Peak (Floating Loss)', fontsize=13, fontweight='bold')
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        ax1.legend(loc='best', fontsize=10)
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Drawdown percentage
        ax2.fill_between(range(len(df)), 0, df['dd_percent'], alpha=0.3, color='red', label='Drawdown %')
        ax2.plot(range(len(df)), df['dd_percent'], linewidth=2, color='red')
        ax2.axhline(y=10, color='orange', linestyle='--', linewidth=2, label='FTMO Limit (10%)')
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        # Highlight violations
        violations = df[df['dd_percent'] > 10]
        if len(violations) > 0:
            ax2.scatter(violations.index, violations['dd_percent'], color='red', s=50, zorder=5, 
                       label=f'Violations ({len(violations)})')
        
        ax2.set_xlabel('Trade #', fontsize=11, fontweight='bold')
        ax2.set_ylabel('Drawdown (%)', fontsize=11, fontweight='bold')
        ax2.set_title('Maximum Drawdown Over Time', fontsize=13, fontweight='bold')
        ax2.legend(loc='best', fontsize=10)
        ax2.grid(True, alpha=0.3)
        
        # Add statistics
        max_dd = df['dd_percent'].max()
        avg_dd = df['dd_percent'].mean()
        final_dd = df['dd_percent'].iloc[-1] if len(df) > 0 else 0
        
        stats_text = f"Max DD: {max_dd:.2f}%\nAvg DD: {avg_dd:.2f}%\nFinal DD: {final_dd:.2f}%"
        ax2.text(0.02, 0.98, stats_text, transform=ax2.transAxes, fontsize=10,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                family='monospace')
        
        plt.tight_layout()
        
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            print(f"✅ Saved drawdown curve to {output_file}")
        
        return fig
    
    def plot_monte_carlo_simulation(self, num_simulations=1000, output_file=None):
        """Plot Monte Carlo simulation paths"""
        from ftmo_validator import FTMOValidator
        
        repo_root = Path(__file__).resolve().parents[3]
        data_file = repo_root / 'data' / 'XAUUSD_1h_sample.csv'
        backtest_file = repo_root / 'backtest' / 'backtest_results_ml_optimized_fixed.csv'
        
        validator = FTMOValidator(str(data_file), str(backtest_file))
        
        print(f"Running {num_simulations} Monte Carlo simulations...")
        
        trades = pd.read_csv(backtest_file)['pnl'].values
        initial_capital = 10000
        
        # Run simulations
        simulations = []
        pass_count = 0
        
        for sim in range(num_simulations):
            shuffled_trades = np.random.permutation(trades)
            
            capital = initial_capital
            peak = initial_capital
            max_dd = 0
            equity_curve = [initial_capital]
            
            for pnl in shuffled_trades:
                capital += pnl
                if capital > peak:
                    peak = capital
                dd = (peak - capital) / peak * 100
                max_dd = max(max_dd, dd)
                equity_curve.append(capital)
            
            passes = max_dd <= 10.0
            pass_count += 1 if passes else 0
            simulations.append({
                'equity_curve': equity_curve,
                'max_dd': max_dd,
                'passes': passes,
                'final_capital': capital
            })
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        # Plot 1: All simulation paths
        for i, sim in enumerate(simulations):
            color = 'green' if sim['passes'] else 'red'
            alpha = 0.1 if sim['passes'] else 0.05
            ax1.plot(sim['equity_curve'], color=color, alpha=alpha, linewidth=0.5)
        
        # Add average
        avg_curve = np.mean([sim['equity_curve'] for sim in simulations], axis=0)
        ax1.plot(avg_curve, color='blue', linewidth=2.5, label='Average Path', zorder=10)
        
        ax1.axhline(y=initial_capital, color='black', linestyle='--', linewidth=1, alpha=0.5)
        ax1.set_xlabel('Trade #', fontsize=11, fontweight='bold')
        ax1.set_ylabel('Account Value ($)', fontsize=11, fontweight='bold')
        ax1.set_title(f'Monte Carlo Simulation Paths ({num_simulations} scenarios)', fontsize=13, fontweight='bold')
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Legend
        pass_patch = mpatches.Patch(color='green', alpha=0.3, label=f'Pass FTMO ({pass_count})')
        fail_patch = mpatches.Patch(color='red', alpha=0.1, label=f'Fail FTMO ({num_simulations - pass_count})')
        ax1.legend(handles=[pass_patch, fail_patch, plt.Line2D([0], [0], color='blue', linewidth=2.5)], 
                  loc='best', fontsize=10)
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Distribution of outcomes
        max_dds = [sim['max_dd'] for sim in simulations]
        final_capitals = [sim['final_capital'] for sim in simulations]
        
        ax2_twin = ax2.twinx()
        
        # Histogram of max drawdowns
        n, bins, patches = ax2.hist(max_dds, bins=30, alpha=0.6, color='purple', edgecolor='black')
        ax2.axvline(x=10, color='orange', linestyle='--', linewidth=2.5, label='FTMO Limit (10%)')
        ax2.set_xlabel('Max Drawdown (%)', fontsize=11, fontweight='bold')
        ax2.set_ylabel('Frequency', fontsize=11, fontweight='bold', color='purple')
        ax2.tick_params(axis='y', labelcolor='purple')
        
        # Color the bars
        for i, patch in enumerate(patches):
            if bins[i] > 10:
                patch.set_facecolor('red')
            else:
                patch.set_facecolor('green')
        
        # Add statistics
        pass_prob = (pass_count / num_simulations) * 100
        avg_dd = np.mean(max_dds)
        median_dd = np.median(max_dds)
        std_dd = np.std(max_dds)
        
        stats_text = (f"Pass Probability: {pass_prob:.1f}%\n"
                     f"Avg Max DD: {avg_dd:.2f}%\n"
                     f"Median Max DD: {median_dd:.2f}%\n"
                     f"Std Dev: {std_dd:.2f}%")
        ax2.text(0.98, 0.97, stats_text, transform=ax2.transAxes, fontsize=10,
                verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7),
                family='monospace')
        
        # Final capital stats on right axis
        if len(set(final_capitals)) > 1:  # Only plot if values vary
            try:
                ax2_twin.hist(final_capitals, bins=min(30, len(set(final_capitals))), alpha=0.2, color='blue', edgecolor='none')
            except:
                pass  # Skip if histogram can't be created
        ax2_twin.set_ylabel('Distribution', fontsize=11, fontweight='bold', color='blue')
        ax2_twin.tick_params(axis='y', labelcolor='blue')
        
        ax2.legend(loc='upper left', fontsize=10)
        ax2.grid(True, alpha=0.3)
        ax2.set_title('Drawdown Distribution & Pass Probability', fontsize=13, fontweight='bold')
        
        plt.tight_layout()
        
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            print(f"✅ Saved Monte Carlo chart to {output_file}")
        
        return fig, pass_prob
    
    def create_dashboard(self, output_file=None):
        """Create comprehensive dashboard"""
        fig = plt.figure(figsize=(16, 12))
        gs = GridSpec(3, 2, figure=fig, hspace=0.35, wspace=0.3)
        
        # 1. Daily P&L
        if self.daily_pnl is not None:
            ax1 = fig.add_subplot(gs[0, :])
            df = self.daily_pnl
            colors = ['green' if x >= 0 else 'red' for x in df['closed_pnl']]
            ax1.bar(range(len(df)), df['closed_pnl'], color=colors, alpha=0.7, edgecolor='black', linewidth=0.3)
            ax1.axhline(y=0, color='black', linestyle='-', linewidth=1)
            ax1.set_ylabel('Daily P&L ($)', fontsize=10, fontweight='bold')
            ax1.set_title('Daily Profit & Loss', fontsize=12, fontweight='bold')
            ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x/1000:.0f}K'))
            ax1.grid(True, alpha=0.3, axis='y')
        
        # 2. Drawdown curve
        if self.drawdown_curve is not None:
            ax2 = fig.add_subplot(gs[1, 0])
            df = self.drawdown_curve
            ax2.fill_between(range(len(df)), 0, df['dd_percent'], alpha=0.3, color='red')
            ax2.plot(range(len(df)), df['dd_percent'], linewidth=1.5, color='red')
            ax2.axhline(y=10, color='orange', linestyle='--', linewidth=2, label='FTMO 10%')
            ax2.set_ylabel('Drawdown (%)', fontsize=10, fontweight='bold')
            ax2.set_title('Maximum Drawdown', fontsize=12, fontweight='bold')
            ax2.legend(loc='best', fontsize=9)
            ax2.grid(True, alpha=0.3)
        
        # 3. Compliance status
        ax3 = fig.add_subplot(gs[1, 1])
        ax3.axis('off')
        
        if self.compliance:
            comp = self.compliance
            status_lines = [
                "COMPLIANCE STATUS",
                "=" * 35,
                "",
            ]
            
            # Daily loss
            daily_pass = comp.get('max_daily_loss', {}).get('pass', False)
            daily_value = comp.get('max_daily_loss', {}).get('value', 'N/A')
            status_lines.append(f"Daily Loss: {'✅ PASS' if daily_pass else '❌ FAIL'}")
            status_lines.append(f"  Worst: {daily_value} (limit: -5%)")
            
            # Drawdown
            dd_pass = comp.get('max_drawdown', {}).get('pass', False)
            dd_value = comp.get('max_drawdown', {}).get('value', 'N/A')
            status_lines.append(f"Drawdown: {'✅ PASS' if dd_pass else '❌ FAIL'}")
            status_lines.append(f"  Max: {dd_value} (limit: 10%)")
            
            # Overall
            overall_pass = comp.get('overall', {}).get('passes_ftmo', False)
            status_lines.append("")
            status_lines.append("=" * 35)
            status_lines.append(f"Overall: {'✅ FTMO PASS' if overall_pass else '❌ FTMO FAIL'}")
            
            # Performance
            perf = comp.get('total_performance', {})
            status_lines.append("")
            status_lines.extend([
                "PERFORMANCE",
                "=" * 35,
                f"Total P&L: {perf.get('total_pnl', 'N/A')}",
                f"Return: {perf.get('total_return_percent', 'N/A')}",
            ])
            
            # Metrics
            metrics = comp.get('additional_metrics', {})
            status_lines.extend([
                "",
                "METRICS",
                "=" * 35,
                f"Trades: {metrics.get('total_trades', 'N/A')}",
                f"Win Rate: {metrics.get('win_rate', 'N/A')}",
                f"Profit Factor: {metrics.get('profit_factor', 'N/A')}",
            ])
            
            status_text = "\n".join(status_lines)
            ax3.text(0.05, 0.95, status_text, transform=ax3.transAxes, fontsize=9.5,
                    verticalalignment='top', family='monospace',
                    bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.3))
        
        # 4. Equity curve
        if self.drawdown_curve is not None:
            ax4 = fig.add_subplot(gs[2, 0])
            df = self.drawdown_curve
            ax4.plot(range(len(df)), df['capital'], linewidth=1.5, color='green', label='Account Value')
            ax4.plot(range(len(df)), df['peak'], linewidth=1, color='blue', linestyle='--', alpha=0.6, label='Peak')
            ax4.fill_between(range(len(df)), df['capital'], df['peak'], alpha=0.2, color='red')
            ax4.set_ylabel('Account Value ($)', fontsize=10, fontweight='bold')
            ax4.set_xlabel('Trade #', fontsize=10, fontweight='bold')
            ax4.set_title('Equity Curve', fontsize=12, fontweight='bold')
            ax4.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x/1000:.0f}K'))
            ax4.legend(loc='best', fontsize=9)
            ax4.grid(True, alpha=0.3)
        
        # 5. Recommendations
        ax5 = fig.add_subplot(gs[2, 1])
        ax5.axis('off')
        
        recommendations = [
            "RECOMMENDATIONS",
            "=" * 35,
            "",
            "OPTION 1 (Fastest):",
            "• 50% position size",
            "• Est. DD: 6.51%",
            "• Est. P&L: $137k",
            "• Implementation: 5 min",
            "",
            "OPTION 2 (Best):",
            "• Filter worst 20%",
            "• Est. DD: 6%",
            "• Est. P&L: $361k ⭐",
            "• Implementation: Medium",
            "",
            "OPTION 3 (Deep):",
            "• Tight params",
            "• Est. DD: 8%",
            "• Est. P&L: $100k",
            "• Implementation: High",
        ]
        
        rec_text = "\n".join(recommendations)
        ax5.text(0.05, 0.95, rec_text, transform=ax5.transAxes, fontsize=9,
                verticalalignment='top', family='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.3))
        
        fig.suptitle('FTMO Challenge - Comprehensive Analysis Dashboard', 
                    fontsize=14, fontweight='bold', y=0.995)
        
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            print(f"✅ Saved dashboard to {output_file}")
        
        return fig
    
    def save_all_visualizations(self):
        """Generate and save all visualizations"""
        output_dir = self.base_dir.parent / 'images'
        
        print("\n" + "=" * 70)
        print("GENERATING FTMO VISUALIZATIONS")
        print("=" * 70)
        
        # 1. Daily P&L
        self.plot_daily_pnl(output_dir / 'ftmo_daily_pnl.png')
        
        # 2. Drawdown curve
        self.plot_drawdown_curve(output_dir / 'ftmo_drawdown_curve.png')
        
        # 3. Monte Carlo
        self.plot_monte_carlo_simulation(num_simulations=1000, 
                                        output_file=output_dir / 'ftmo_monte_carlo.png')
        
        # 4. Dashboard
        self.create_dashboard(output_dir / 'ftmo_dashboard.png')
        
        print("\n✅ All visualizations generated!")


def main():
    """Main entry point"""
    track_root = Path(__file__).resolve().parent.parent
    reports_dir = track_root / 'reports'
    
    visualizer = FTMOVisualizer(reports_dir)
    visualizer.save_all_visualizations()
    
    print(f"\nGenerated files in {track_root / 'images'}:")
    print("  ✓ ftmo_daily_pnl.png")
    print("  ✓ ftmo_drawdown_curve.png")
    print("  ✓ ftmo_monte_carlo.png")
    print("  ✓ ftmo_dashboard.png")


if __name__ == '__main__':
    main()
