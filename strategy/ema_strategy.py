"""
EMA (Exponential Moving Average) Crossover Strategy Implementation
"""

import pandas as pd
import numpy as np

class EMAStrategy:
    """
    EMA Crossover Trading Strategy
    
    Signals:
    - BUY: Fast EMA crosses above Slow EMA
    - SELL: Fast EMA crosses below Slow EMA
    """
    
    def __init__(self, fast_period=12, slow_period=26, signal_period=9):
        """
        Initialize EMA strategy parameters
        
        Parameters:
        - fast_period: Period for fast EMA (default: 12)
        - slow_period: Period for slow EMA (default: 26)
        - signal_period: Period for signal line (optional, for MACD variant)
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
    
    def calculate_ema(self, data, period):
        """Calculate Exponential Moving Average"""
        return data.ewm(span=period, adjust=False).mean()
    
    def generate_signals(self, df):
        """
        Generate trading signals based on EMA crossover
        
        Parameters:
        - df: DataFrame with 'Close' price column
        
        Returns:
        - DataFrame with additional columns: fast_ema, slow_ema, signal, position
        """
        
        # Make a copy to avoid modifying original
        result = df.copy()
        
        # Calculate EMAs
        result['fast_ema'] = self.calculate_ema(result['Close'], self.fast_period)
        result['slow_ema'] = self.calculate_ema(result['Close'], self.slow_period)
        
        # Generate signals: 1 for long, 0 for no position
        result['signal'] = 0
        signal_values = np.where(
            result['fast_ema'].iloc[self.slow_period:].values > result['slow_ema'].iloc[self.slow_period:].values,
            1,
            0
        )
        result.iloc[self.slow_period:, result.columns.get_loc('signal')] = signal_values
        
        # Generate positions: 1 for long, -1 for short (not used in simple version)
        result['position'] = result['signal'].diff()
        
        return result
    
    def identify_crossovers(self, df):
        """
        Identify exact crossover points
        
        Parameters:
        - df: DataFrame with fast_ema and slow_ema columns
        
        Returns:
        - Lists of buy and sell crossover indices
        """
        
        buy_signals = []
        sell_signals = []
        
        for i in range(1, len(df)):
            # Buy signal: fast EMA crosses above slow EMA
            if (df['fast_ema'].iloc[i-1] <= df['slow_ema'].iloc[i-1] and 
                df['fast_ema'].iloc[i] > df['slow_ema'].iloc[i]):
                buy_signals.append(i)
            
            # Sell signal: fast EMA crosses below slow EMA
            if (df['fast_ema'].iloc[i-1] >= df['slow_ema'].iloc[i-1] and 
                df['fast_ema'].iloc[i] < df['slow_ema'].iloc[i]):
                sell_signals.append(i)
        
        return buy_signals, sell_signals
    
    def get_strategy_parameters(self):
        """Return strategy parameters as dict"""
        return {
            'fast_ema': self.fast_period,
            'slow_ema': self.slow_period,
            'signal_period': self.signal_period
        }

if __name__ == "__main__":
    # Test the strategy
    print("EMA Crossover Strategy Module")
    print("=" * 50)
    
    # Load sample data
    df = pd.read_csv('data/XAUUSD_1h_sample.csv', index_col=0, parse_dates=True)
    
    # Initialize strategy
    strategy = EMAStrategy(fast_period=12, slow_period=26)
    
    # Generate signals
    result = strategy.generate_signals(df)
    
    print(f"\nStrategy Parameters:")
    print(strategy.get_strategy_parameters())
    
    print(f"\nData shape: {result.shape}")
    print(f"\nFirst 20 rows with indicators:")
    print(result[['Close', 'fast_ema', 'slow_ema', 'signal']].head(30))
    
    # Find crossovers
    buy_signals, sell_signals = strategy.identify_crossovers(result)
    print(f"\nBuy signals: {len(buy_signals)}")
    print(f"Sell signals: {len(sell_signals)}")
    
    if buy_signals:
        print(f"First 5 buy signals at indices: {buy_signals[:5]}")
    if sell_signals:
        print(f"First 5 sell signals at indices: {sell_signals[:5]}")
