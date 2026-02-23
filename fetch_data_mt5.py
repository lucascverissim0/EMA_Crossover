"""
Alternative data fetcher for XAUUSD using MetaTrader 5.
This provides access to 10+ years of 1-hour candle data.

Installation: pip install MetaTrader5
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import pytz

def fetch_xauusd_mt5():
    """
    Fetch XAUUSD data from MetaTrader 5 (requires MT5 terminal running).
    
    Returns: pandas DataFrame with OHLCV data
    """
    
    # Initialize MetaTrader 5
    if not mt5.initialize():
        print("Failed to initialize MT5. Ensure MetaTrader 5 terminal is running.")
        print("Download from: https://www.metatrader5.com/en/download")
        return None
    
    # Configuration
    SYMBOL = "XAUUSD"
    TIMEFRAME = mt5.TIMEFRAME_H1  # 1-hour
    
    # Calculate dates
    end_time = datetime.now(pytz.UTC)
    start_time = end_time - timedelta(days=365*10)  # 10 years
    
    print(f"Fetching {SYMBOL} 1H data from {start_time} to {end_time}...")
    print("This may take a few minutes...")
    
    try:
        # Fetch rates
        rates = mt5.copy_rates_range(SYMBOL, TIMEFRAME, start_time, end_time)
        
        if rates is None or len(rates) == 0:
            print(f"✗ No data returned for {SYMBOL}")
            mt5.shutdown()
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'tick_volume': 'Volume'
        }, inplace=True)
        
        print(f"✓ Successfully fetched {len(df)} candles")
        print(f"Date range: {df.index.min()} to {df.index.max()}")
        print(f"\nFirst few rows:")
        print(df.head())
        
        # Save to CSV
        output_dir = Path("data")
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "XAUUSD_1h_data.csv"
        df.to_csv(output_file)
        print(f"\n✓ Data saved to: {output_file}")
        
        mt5.shutdown()
        return df
        
    except Exception as e:
        print(f"✗ Error fetching data: {e}")
        mt5.shutdown()
        return None

if __name__ == "__main__":
    data = fetch_xauusd_mt5()
