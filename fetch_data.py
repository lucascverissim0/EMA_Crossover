"""
Fetch historical XAUUSD (Gold) data in 1-hour candles for at least 10 years.
Data source: yfinance
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
SYMBOL = "GC=F"  # Gold Futures (daily data available)
# Alternative: XAUUSD from different sources
START_DATE = (datetime.now() - timedelta(days=365*10)).strftime('%Y-%m-%d')
END_DATE = datetime.now().strftime('%Y-%m-%d')
INTERVAL = "1h"  # 1-hour candles
OUTPUT_DIR = Path("data")

def fetch_gold_data():
    """
    Fetch historical gold data for 10+ years in 1-hour intervals.
    
    Note: yfinance has limitations for 1-hour data beyond ~2-3 years.
    For production trading, consider using:
    - MetaTrader 5 API
    - Interactive Brokers API
    - Oanda API
    - Other forex/CFD broker APIs
    """
    
    print(f"Fetching {SYMBOL} data from {START_DATE} to {END_DATE}...")
    print(f"Interval: {INTERVAL}")
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    try:
        # Fetch data
        data = yf.download(
            SYMBOL,
            start=START_DATE,
            end=END_DATE,
            interval=INTERVAL,
            progress=True
        )
        
        # Display info
        print(f"\n✓ Successfully fetched {len(data)} candles")
        print(f"Date range: {data.index.min()} to {data.index.max()}")
        print(f"\nFirst few rows:")
        print(data.head())
        print(f"\nData info:")
        print(data.info())
        
        # Save to CSV
        output_file = OUTPUT_DIR / f"{SYMBOL.replace('=F', '')}_1h_data.csv"
        data.to_csv(output_file)
        print(f"\n✓ Data saved to: {output_file}")
        
        return data
        
    except Exception as e:
        print(f"✗ Error fetching data: {e}")
        print("\nNote: yfinance may have limitations for 1-hour historical data.")
        print("Consider using alternative data sources:")
        print("- MetaTrader 5: pip install MetaTrader5")
        print("- OANDA API: pip install v20")
        print("- Interactive Brokers: pip install ib_insync")
        return None

if __name__ == "__main__":
    data = fetch_gold_data()
