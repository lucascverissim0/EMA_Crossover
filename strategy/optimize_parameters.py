"""
Parameter Optimization: Test different EMA period combinations
Grid search across multiple EMA configurations
"""

import pandas as pd
import numpy as np
from ema_strategy import EMAStrategy
from backtest import Backtest
from pathlib import Path
import json

class ParameterOptimizer:
    """Test multiple EMA parameter combinations and rank them"""
    
    def __init__(self, data_file, initial_capital=10000, risk_percent=2):
        """
        Initialize optimizer
        
        Parameters:
        - data_file: Path to OHLCV CSV data
        - initial_capital: Starting capital
        - risk_percent: Risk per trade
        """
        self.data = pd.read_csv(data_file, index_col=0, parse_dates=True)
        self.initial_capital = initial_capital
        self.risk_percent = risk_percent
        self.results = []
    
    def optimize(self, fast_periods, slow_periods, stop_loss_percent=2, take_profit_percent=5):
        """
        Perform grid search over parameter combinations
        
        Parameters:
        - fast_periods: List of fast EMA periods to test
        - slow_periods: List of slow EMA periods to test
        - stop_loss_percent: Stop loss level (%)
        - take_profit_percent: Take profit level (%)
        
        Returns:
        - DataFrame with results sorted by Sharpe ratio
        """
        
        total_combinations = len(fast_periods) * len(slow_periods)
        current = 0
        
        print(f"\n{'='*80}")
        print(f"PARAMETER OPTIMIZATION - Testing {total_combinations} combinations")
        print(f"{'='*80}\n")
        
        for fast in fast_periods:
            for slow in slow_periods:
                current += 1
                
                # Skip if fast >= slow
                if fast >= slow:
                    continue
                
                print(f"[{current}/{total_combinations}] Testing EMA({fast}/{slow})...", end='', flush=True)
                
                try:
                    # Create strategy and run backtest
                    strategy = EMAStrategy(fast_period=fast, slow_period=slow)
                    backtest = Backtest(self.data, strategy, self.initial_capital, self.risk_percent)
                    metrics = backtest.run(stop_loss_percent, take_profit_percent)
                    
                    if metrics is not None:
                        metrics['fast_ema'] = fast
                        metrics['slow_ema'] = slow
                        self.results.append(metrics)
                        
                        print(f" ✓ SR: {metrics['sharpe_ratio']:6.2f} | WR: {metrics['win_rate_%']:5.1f}% | "
                              f"Return: {metrics['total_return_%']:8.2f}%")
                    else:
                        print(f" ✗ No trades")
                
                except Exception as e:
                    print(f" ✗ Error: {str(e)[:30]}")
        
        # Convert to DataFrame and sort by Sharpe ratio
        results_df = pd.DataFrame(self.results)
        results_df = results_df.sort_values('sharpe_ratio', ascending=False)
        
        return results_df
    
    def print_top_results(self, results_df, top_n=10):
        """Print top N results"""
        
        print(f"\n{'='*80}")
        print(f"TOP {top_n} PARAMETER COMBINATIONS (Ranked by Sharpe Ratio)")
        print(f"{'='*80}\n")
        
        display_cols = ['fast_ema', 'slow_ema', 'sharpe_ratio', 'win_rate_%', 
                       'total_return_%', 'profit_factor', 'max_drawdown_%']
        
        top_results = results_df.head(top_n)[display_cols]
        print(top_results.to_string(index=False))
        
        print(f"\n{'='*80}")
    
    def plot_optimization_results(self, results_df, output_file='optimization_heatmap.png'):
        """Create heatmap visualization of optimization results"""
        
        try:
            import matplotlib.pyplot as plt
            
            # Get unique periods
            fast_periods = sorted(results_df['fast_ema'].unique())
            slow_periods = sorted(results_df['slow_ema'].unique())
            
            # Create matrix for heatmap
            sharpe_matrix = np.full((len(slow_periods), len(fast_periods)), np.nan)
            return_matrix = np.full((len(slow_periods), len(fast_periods)), np.nan)
            wr_matrix = np.full((len(slow_periods), len(fast_periods)), np.nan)
            
            for idx, row in results_df.iterrows():
                fast_idx = fast_periods.index(row['fast_ema'])
                slow_idx = slow_periods.index(row['slow_ema'])
                
                sharpe_matrix[slow_idx, fast_idx] = row['sharpe_ratio']
                return_matrix[slow_idx, fast_idx] = row['total_return_%']
                wr_matrix[slow_idx, fast_idx] = row['win_rate_%']
            
            # Create heatmaps
            fig, axes = plt.subplots(1, 3, figsize=(18, 5))
            
            # Sharpe ratio heatmap
            im1 = axes[0].imshow(sharpe_matrix, cmap='RdYlGn', aspect='auto')
            axes[0].set_xticks(range(len(fast_periods)))
            axes[0].set_yticks(range(len(slow_periods)))
            axes[0].set_xticklabels(fast_periods)
            axes[0].set_yticklabels(slow_periods)
            axes[0].set_xlabel('Fast EMA Period', fontsize=10, fontweight='bold')
            axes[0].set_ylabel('Slow EMA Period', fontsize=10, fontweight='bold')
            axes[0].set_title('Sharpe Ratio Heatmap', fontsize=11, fontweight='bold')
            plt.colorbar(im1, ax=axes[0])
            
            # Total return heatmap
            im2 = axes[1].imshow(return_matrix, cmap='RdYlGn', aspect='auto')
            axes[1].set_xticks(range(len(fast_periods)))
            axes[1].set_yticks(range(len(slow_periods)))
            axes[1].set_xticklabels(fast_periods)
            axes[1].set_yticklabels(slow_periods)
            axes[1].set_xlabel('Fast EMA Period', fontsize=10, fontweight='bold')
            axes[1].set_ylabel('Slow EMA Period', fontsize=10, fontweight='bold')
            axes[1].set_title('Total Return % Heatmap', fontsize=11, fontweight='bold')
            plt.colorbar(im2, ax=axes[1])
            
            # Win rate heatmap
            im3 = axes[2].imshow(wr_matrix, cmap='RdYlGn', aspect='auto', vmin=0, vmax=100)
            axes[2].set_xticks(range(len(fast_periods)))
            axes[2].set_yticks(range(len(slow_periods)))
            axes[2].set_xticklabels(fast_periods)
            axes[2].set_yticklabels(slow_periods)
            axes[2].set_xlabel('Fast EMA Period', fontsize=10, fontweight='bold')
            axes[2].set_ylabel('Slow EMA Period', fontsize=10, fontweight='bold')
            axes[2].set_title('Win Rate % Heatmap', fontsize=11, fontweight='bold')
            plt.colorbar(im3, ax=axes[2])
            
            plt.tight_layout()
            plt.savefig(output_file, dpi=150, bbox_inches='tight')
            print(f"\n✓ Heatmap saved to: {output_file}")
            
        except ImportError:
            print("\nNote: Matplotlib not available for heatmap visualization")
    
    def save_results_csv(self, results_df, output_file='optimization_results.csv'):
        """Save optimization results to CSV"""
        results_df.to_csv(output_file, index=False)
        print(f"✓ Results saved to: {output_file}")

def main():
    """Run parameter optimization"""
    
    # Check for data file
    data_file = Path('data/XAUUSD_1h_sample.csv')
    if not data_file.exists():
        print(f"Data file not found: {data_file}")
        print("Run 'python generate_sample_data.py' first")
        return
    
    # Initialize optimizer
    optimizer = ParameterOptimizer(str(data_file), initial_capital=10000, risk_percent=2)
    
    # Test parameters
    # Testing a reasonable range of EMA periods
    fast_periods = [5, 8, 10, 12, 14, 15, 20]
    slow_periods = [20, 26, 30, 35, 40, 50]
    
    # Run optimization
    results = optimizer.optimize(fast_periods, slow_periods, 
                                stop_loss_percent=2, 
                                take_profit_percent=5)
    
    # Print results
    optimizer.print_top_results(results, top_n=15)
    
    # Save results
    optimizer.save_results_csv(results, 'optimization_results.csv')
    
    # Plot heatmap
    optimizer.plot_optimization_results(results, 'ema_parameter_heatmap.png')
    
    # Summary statistics
    print(f"\nOPTIMIZATION SUMMARY")
    print(f"{'='*80}")
    print(f"Total parameter combinations tested: {len(results)}")
    print(f"Best Sharpe Ratio: {results['sharpe_ratio'].max():.2f}")
    print(f"Average Sharpe Ratio: {results['sharpe_ratio'].mean():.2f}")
    print(f"Best Win Rate: {results['win_rate_%'].max():.2f}%")
    print(f"Best Return: {results['total_return_%'].max():.2f}%")
    print(f"\nRecommended EMA periods:")
    
    best = results.iloc[0]
    print(f"  Fast EMA: {int(best['fast_ema'])}")
    print(f"  Slow EMA: {int(best['slow_ema'])}")
    print(f"  Expected Sharpe Ratio: {best['sharpe_ratio']:.2f}")
    print(f"  Expected Win Rate: {best['win_rate_%']:.2f}%")

if __name__ == "__main__":
    main()
