"""
Sample data generator for backtesting EMA crossover strategy.
Generates realistic XAUUSD 1-hour data for testing purposes.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

def generate_sample_xauusd_data(days=365*10, hourly=True):
    """
    Generate realistic synthetic XAUUSD data for backtesting.
    
    Parameters:
    - days: Number of days to generate
    - hourly: If True, generate 1-hour candles; if False, daily
    """
    
    print(f"Generating {days} days of synthetic XAUUSD data...")
    
    # Parameters
    np.random.seed(42)
    interval = 1  # 1-hour candles
    
    if hourly:
        num_candles = days * 24  # 24 hours per day
        freq = 'h'
    else:
        num_candles = days
        freq = 'D'
    
    # Start date
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Generate time index
    dates = pd.date_range(start=start_date, periods=num_candles, freq=freq)
    
    # Generate price data
    # Start price around 2000 USD per troy ounce
    open_price = 2000
    
    # Generate realistic price movements
    returns = np.random.normal(0.0001, 0.005, num_candles)  # Small drift, volatility
    close_prices = open_price * np.exp(np.cumsum(returns))
    
    # Generate OHLC data
    data = []
    for i, date in enumerate(dates):
        close = close_prices[i]
        
        # Open slightly different from previous close
        open_p = close_prices[i-1] if i > 0 else open_price
        
        # High and Low around the price
        high = max(open_p, close) * (1 + np.abs(np.random.normal(0, 0.002)))
        low = min(open_p, close) * (1 - np.abs(np.random.normal(0, 0.002)))
        
        volume = np.random.randint(1000, 100000)
        
        data.append({
            'Open': open_p,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': volume
        })
    
    df = pd.DataFrame(data, index=dates)
    
    print(f"✓ Generated {len(df)} candles")
    print(f"Date range: {df.index.min()} to {df.index.max()}")
    print(f"\nFirst few rows:")
    print(df.head(10))
    print(f"\nLast few rows:")
    print(df.tail(10))
    print(f"\nPrice range: ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")
    
    # Save to CSV
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)
    
    if hourly:
        output_file = output_dir / "XAUUSD_1h_sample.csv"
    else:
        output_file = output_dir / "XAUUSD_daily_sample.csv"
    
    df.to_csv(output_file)
    print(f"\n✓ Data saved to: {output_file}")
    
    return df

if __name__ == "__main__":
    # Generate 10 years of hourly data
    data = generate_sample_xauusd_data(days=365*10, hourly=True)
