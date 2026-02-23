"""
Machine Learning Parameter Optimization for EMA Strategy
Uses Bayesian Optimization to find best parameters that maximize Sharpe Ratio
"""

import pandas as pd
import numpy as np
from ema_strategy import EMAStrategy
from backtest import Backtest
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

try:
    from skopt import gp_minimize
    from skopt.space import Integer, Real
    from skopt.utils import use_named_args
    HAS_SKOPT = True
except ImportError:
    HAS_SKOPT = False
    print("Warning: scikit-optimize not installed")
    print("Install with: pip install scikit-optimize")

class MLParameterOptimizer:
    """
    Use Bayesian Optimization to find optimal trading parameters.
    
    Benefits over grid search:
    - Tests fewer combinations (42 → 50-100 smart tests)
    - Focuses on promising regions
    - Finds global optimum, not just local
    - Much faster convergence
    """
    
    def __init__(self, data_file, metric='sharpe_ratio'):
        """
        Initialize ML optimizer
        
        Parameters:
        - data_file: Path to OHLCV data
        - metric: Metric to optimize ('sharpe_ratio', 'win_rate', 'return')
        """
        self.data = pd.read_csv(data_file, index_col=0, parse_dates=True)
        self.metric = metric
        self.best_params = None
        self.best_score = None
        self.iteration = 0
        self.max_iterations = 50
        
    def calculate_sharpe_hourly(self, returns):
        """Calculate Sharpe ratio for hourly data"""
        if returns.std() == 0:
            return -999
        return (returns.mean() / returns.std() * np.sqrt(252*24))
    
    def evaluate_parameters(self, fast_ema, slow_ema, sl_percent, tp_percent):
        """
        Evaluate a parameter combination
        
        Returns negative Sharpe (for minimization)
        """
        self.iteration += 1
        
        try:
            # Skip invalid combinations
            if fast_ema >= slow_ema:
                print(f"Iteration {self.iteration}: Invalid (fast >= slow)")
                return 999  # Bad score
            
            # Run backtest
            strategy = EMAStrategy(fast_period=fast_ema, slow_period=slow_ema)
            backtest = Backtest(self.data, strategy, initial_capital=10000, risk_percent=2)
            metrics = backtest.run(stop_loss_percent=sl_percent, take_profit_percent=tp_percent)
            
            if metrics is None:
                return 999
            
            # Get metric to optimize
            if self.metric == 'sharpe_ratio':
                score = metrics['sharpe_ratio']
            elif self.metric == 'win_rate_%':
                score = metrics['win_rate_%']
            elif self.metric == 'total_return_%':
                score = metrics['total_return_%']
            else:
                score = metrics['sharpe_ratio']
            
            # Print progress
            print(f"Iteration {self.iteration}: EMA({fast_ema}/{slow_ema}) "
                  f"SL={sl_percent}% TP={tp_percent}% → {self.metric}={score:.2f}")
            
            # Return negative for minimization (we want to maximize)
            return -score
            
        except Exception as e:
            print(f"Iteration {self.iteration}: Error - {str(e)[:50]}")
            return 999
    
    def optimize_bayesian(self):
        """
        Use Bayesian Optimization to find best parameters
        Much smarter than grid search!
        """
        
        if not HAS_SKOPT:
            print("scikit-optimize not installed. Using manual search instead.")
            return self.optimize_manual()
        
        print("\n" + "="*80)
        print("BAYESIAN OPTIMIZATION - Finding optimal parameters")
        print(f"Metric to optimize: {self.metric}")
        print(f"Max iterations: {self.max_iterations}")
        print("="*80 + "\n")
        
        # Define parameter space
        space = [
            Integer(5, 20, name='fast_ema'),       # 5-20 periods
            Integer(20, 50, name='slow_ema'),      # 20-50 periods
            Real(0.5, 3.0, name='sl_percent'),     # 0.5% - 3%
            Real(3.0, 15.0, name='tp_percent'),    # 3% - 15%
        ]
        
        # Define objective function
        @use_named_args(space)
        def objective(**params):
            return self.evaluate_parameters(
                params['fast_ema'],
                params['slow_ema'],
                params['sl_percent'],
                params['tp_percent']
            )
        
        # Run Bayesian Optimization
        result = gp_minimize(
            objective,
            space,
            n_calls=self.max_iterations,
            n_initial_points=10,  # Random exploration first
            acq_func='EI',  # Expected Improvement
            random_state=42,
            verbose=0
        )
        
        # Extract best parameters
        best = result.x
        self.best_params = {
            'fast_ema': int(best[0]),
            'slow_ema': int(best[1]),
            'sl_percent': round(best[2], 2),
            'tp_percent': round(best[3], 2)
        }
        self.best_score = -result.fun
        
        return self.best_params
    
    def optimize_manual(self):
        """Fallback: Manual extensive search"""
        
        print("\n" + "="*80)
        print("MANUAL OPTIMIZATION - Testing parameter combinations")
        print("="*80 + "\n")
        
        results = []
        
        fast_periods = [5, 8, 10, 12, 14, 15]
        slow_periods = [20, 26, 30, 35, 40, 50]
        sl_values = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        tp_values = [5, 7, 10, 12, 15]
        
        total = len(fast_periods) * len(slow_periods) * len(sl_values) * len(tp_values)
        current = 0
        
        for fast in fast_periods:
            for slow in slow_periods:
                if fast >= slow:
                    continue
                for sl in sl_values:
                    for tp in tp_values:
                        current += 1
                        score = -self.evaluate_parameters(fast, slow, sl, tp)
                        results.append({
                            'fast_ema': fast,
                            'slow_ema': slow,
                            'sl_percent': sl,
                            'tp_percent': tp,
                            'score': score
                        })
        
        results_df = pd.DataFrame(results)
        best_idx = results_df['score'].idxmax()
        best = results_df.iloc[best_idx]
        
        self.best_params = {
            'fast_ema': best['fast_ema'],
            'slow_ema': best['slow_ema'],
            'sl_percent': best['sl_percent'],
            'tp_percent': best['tp_percent']
        }
        self.best_score = best['score']
        
        return self.best_params
    
    def print_results(self):
        """Print optimization results"""
        
        if self.best_params is None:
            print("No optimization results available")
            return
        
        print("\n" + "="*80)
        print("OPTIMIZATION RESULTS")
        print("="*80)
        print(f"\n✓ Recommended Parameters:")
        print(f"  Fast EMA Period:   {self.best_params['fast_ema']}")
        print(f"  Slow EMA Period:   {self.best_params['slow_ema']}")
        print(f"  Stop Loss:         {self.best_params['sl_percent']}%")
        print(f"  Take Profit:       {self.best_params['tp_percent']}%")
        print(f"\n✓ Expected {self.metric}: {self.best_score:.2f}")
        print("\nNext steps:")
        print("1. Update backtest.py with new parameters")
        print("2. Run: python backtest.py")
        print("3. Run: python visualize.py")
        print("="*80 + "\n")
    
    def save_results(self, filename='ml_optimization_results.txt'):
        """Save optimal parameters to file"""
        
        if self.best_params is None:
            return
        
        with open(filename, 'w') as f:
            f.write("ML Optimization Results\n")
            f.write("="*50 + "\n\n")
            f.write(f"Date: {datetime.now()}\n")
            f.write(f"Metric Optimized: {self.metric}\n")
            f.write(f"Best Score: {self.best_score:.2f}\n\n")
            f.write("Recommended Parameters:\n")
            f.write(f"  fast_ema = {self.best_params['fast_ema']}\n")
            f.write(f"  slow_ema = {self.best_params['slow_ema']}\n")
            f.write(f"  stop_loss_percent = {self.best_params['sl_percent']}\n")
            f.write(f"  take_profit_percent = {self.best_params['tp_percent']}\n")
        
        print(f"✓ Results saved to: {filename}")

def main():
    """Run ML optimization"""
    
    data_file = Path('data/XAUUSD_1h_sample.csv')
    
    if not data_file.exists():
        print(f"Data file not found: {data_file}")
        print("Run 'python generate_sample_data.py' first")
        return
    
    # Create optimizer
    optimizer = MLParameterOptimizer(str(data_file), metric='sharpe_ratio')
    
    # Run optimization
    if HAS_SKOPT:
        print("✓ Using Bayesian Optimization (smarter)")
        best_params = optimizer.optimize_bayesian()
    else:
        print("✗ Using Manual Optimization (slower)")
        best_params = optimizer.optimize_manual()
    
    # Print results
    optimizer.print_results()
    
    # Save results
    optimizer.save_results()
    
    return best_params

if __name__ == "__main__":
    best = main()
