"""
Backtesting Engine for EMA Crossover Strategy
Simulates trading with entry/exit signals and calculates performance metrics
"""

import pandas as pd
import numpy as np
from ema_strategy import EMAStrategy
from pathlib import Path

class Backtest:
    """Backtest trading strategy on historical data"""
    
    def __init__(self, data, strategy, initial_capital=10000, risk_percent=2):
        """
        Initialize backtest
        
        Parameters:
        - data: DataFrame with OHLCV data
        - strategy: EMAStrategy object
        - initial_capital: Starting capital in USD
        - risk_percent: Risk per trade as % of capital
        """
        self.data = data.copy()
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.risk_percent = risk_percent
        self.trades = []
        self.equity_curve = []
    
    def run(self, stop_loss_percent=2, take_profit_percent=5):
        """
        Run backtest with stop loss and take profit
        
        Parameters:
        - stop_loss_percent: Stop loss level (%)
        - take_profit_percent: Take profit level (%)
        """
        
        # Generate signals
        self.data = self.strategy.generate_signals(self.data)
        
        # Find crossovers
        buy_signals, sell_signals = self.strategy.identify_crossovers(self.data)
        
        print(f"Total buy signals: {len(buy_signals)}")
        print(f"Total sell signals: {len(sell_signals)}")
        
        # Simulate trades
        capital = self.initial_capital
        position_open = False
        entry_price = 0
        entry_index = 0
        equity_curve = [self.initial_capital]
        
        # Fixed position sizing: always risk same $ amount per trade
        fixed_risk_dollars = self.initial_capital * (self.risk_percent / 100)
        
        for i in range(1, len(self.data)):
            current_price = self.data['Close'].iloc[i]
            
            if not position_open and i in buy_signals:
                # Open long position
                entry_price = current_price
                entry_index = i
                position_open = True
                # Position size = fixed risk $ / price_move_at_stop_loss
                position_size = fixed_risk_dollars / (entry_price * (stop_loss_percent / 100))
                
            elif position_open:
                # Check for exit conditions
                pnl_percent = (current_price - entry_price) / entry_price * 100
                
                # Stop loss
                if pnl_percent <= -stop_loss_percent:
                    exit_price = entry_price * (1 - stop_loss_percent / 100)
                    pnl = position_size * (exit_price - entry_price)
                    capital += pnl
                    
                    self.trades.append({
                        'entry_index': entry_index,
                        'entry_price': entry_price,
                        'exit_index': i,
                        'exit_price': exit_price,
                        'pnl': pnl,
                        'pnl_percent': pnl_percent,
                        'reason': 'Stop Loss'
                    })
                    
                    position_open = False
                
                # Take profit
                elif pnl_percent >= take_profit_percent:
                    exit_price = entry_price * (1 + take_profit_percent / 100)
                    pnl = position_size * (exit_price - entry_price)
                    capital += pnl
                    
                    self.trades.append({
                        'entry_index': entry_index,
                        'entry_price': entry_price,
                        'exit_index': i,
                        'exit_price': exit_price,
                        'pnl': pnl,
                        'pnl_percent': pnl_percent,
                        'reason': 'Take Profit'
                    })
                    
                    position_open = False
                
                # Sell signal
                elif i in sell_signals:
                    exit_price = current_price
                    pnl = position_size * (exit_price - entry_price)
                    capital += pnl
                    
                    self.trades.append({
                        'entry_index': entry_index,
                        'entry_price': entry_price,
                        'exit_index': i,
                        'exit_price': exit_price,
                        'pnl': pnl,
                        'pnl_percent': pnl_percent,
                        'reason': 'Sell Signal'
                    })
                    
                    position_open = False
            
            equity_curve.append(capital)
        
        self.equity_curve = pd.Series(equity_curve, index=self.data.index[:len(equity_curve)])
        
        return self.calculate_metrics()
    
    def calculate_metrics(self):
        """Calculate performance metrics"""
        
        if not self.trades:
            print("No trades executed!")
            return None
        
        trades_df = pd.DataFrame(self.trades)
        
        # Basic metrics
        total_trades = len(trades_df)
        winning_trades = (trades_df['pnl'] > 0).sum()
        losing_trades = (trades_df['pnl'] < 0).sum()
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # P&L metrics
        total_pnl = trades_df['pnl'].sum()
        avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
        avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if losing_trades > 0 else 0
        
        profit_factor = (trades_df[trades_df['pnl'] > 0]['pnl'].sum() / 
                        abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum()) 
                        if losing_trades > 0 else float('inf'))
        
        # Return metrics
        initial_capital = self.initial_capital
        final_capital = self.equity_curve.iloc[-1]
        total_return = (final_capital - initial_capital) / initial_capital * 100
        
        # Sharpe ratio (hourly data annualization)
        # Using sqrt(252*24) because we have hourly returns
        returns = self.equity_curve.pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std() * np.sqrt(252*24)) if returns.std() > 0 else 0
        
        # Max drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min() * 100
        
        metrics = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate_%': round(win_rate, 2),
            'total_pnl_$': round(total_pnl, 2),
            'avg_win_$': round(avg_win, 2),
            'avg_loss_$': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'initial_capital_$': initial_capital,
            'final_capital_$': round(final_capital, 2),
            'total_return_%': round(total_return, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'max_drawdown_%': round(max_drawdown, 2)
        }
        
        return metrics
    
    def print_report(self):
        """Print detailed backtest report"""
        
        metrics = self.calculate_metrics()
        if metrics is None:
            return
        
        print("\n" + "="*60)
        print("BACKTEST REPORT")
        print("="*60)
        print(f"\nStrategy: EMA ({self.strategy.fast_period}/{self.strategy.slow_period})")
        print(f"Data Points: {len(self.data)}")
        print(f"Period: {self.data.index[0].date()} to {self.data.index[-1].date()}")
        
        print("\n" + "-"*60)
        print("TRADE STATISTICS")
        print("-"*60)
        print(f"Total Trades:        {metrics['total_trades']}")
        print(f"Winning Trades:      {metrics['winning_trades']}")
        print(f"Losing Trades:       {metrics['losing_trades']}")
        print(f"Win Rate:            {metrics['win_rate_%']}%")
        
        print("\n" + "-"*60)
        print("P&L METRICS")
        print("-"*60)
        print(f"Total P&L:           ${metrics['total_pnl_$']:,.2f}")
        print(f"Average Win:         ${metrics['avg_win_$']:,.2f}")
        print(f"Average Loss:        ${metrics['avg_loss_$']:,.2f}")
        print(f"Profit Factor:       {metrics['profit_factor']}")
        
        print("\n" + "-"*60)
        print("RETURN METRICS")
        print("-"*60)
        print(f"Initial Capital:     ${metrics['initial_capital_$']:,.2f}")
        print(f"Final Capital:       ${metrics['final_capital_$']:,.2f}")
        print(f"Total Return:        {metrics['total_return_%']}%")
        print(f"Sharpe Ratio:        {metrics['sharpe_ratio']}")
        print(f"Max Drawdown:        {metrics['max_drawdown_%']}%")
        
        print("\n" + "="*60)
        print("SAMPLE TRADES (First 10)")
        print("="*60)
        
        if self.trades:
            trades_df = pd.DataFrame(self.trades)
            print(trades_df[['entry_price', 'exit_price', 'pnl', 'pnl_percent', 'reason']].head(10).to_string())
        
        print("\n")
    
    def save_results(self, filename='backtest_results.csv'):
        """Save trades to CSV"""
        if self.trades:
            trades_df = pd.DataFrame(self.trades)
            trades_df.to_csv(filename, index=False)
            print(f"Results saved to {filename}")

def main():
    """Run backtest"""
    
    # Load data
    data_file = Path('data/XAUUSD_1h_sample.csv')
    
    if not data_file.exists():
        print(f"Data file not found: {data_file}")
        print("Run 'python generate_sample_data.py' first")
        return
    
    print("Loading data...")
    df = pd.read_csv(data_file, index_col=0, parse_dates=True)
    print(f"Loaded {len(df)} candles")
    
    # Initialize strategy
    strategy = EMAStrategy(fast_period=12, slow_period=26)
    
    # Run backtest
    print("\nRunning backtest...")
    backtest = Backtest(df, strategy, initial_capital=10000, risk_percent=2)
    backtest.run(stop_loss_percent=2, take_profit_percent=5)
    
    # Print report
    backtest.print_report()
    
    # Save results
    backtest.save_results('backtest_results.csv')

if __name__ == "__main__":
    main()
