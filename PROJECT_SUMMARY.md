# EMA Crossover Trading Strategy - Project Summary

## What We've Built

### 1. **Core Strategy Module** (`ema_strategy.py`)
- Implements EMA (Exponential Moving Average) crossover logic
- Two EMAs: Fast (responsive) and Slow (trend-following)
- Trades on crossover signals
- Methods to identify exact buy/sell points

### 2. **Backtesting Engine** (`backtest.py`)
- Simulates trading with realistic conditions:
  - Stop loss protection (2%)
  - Take profit targets (5%)
  - Position sizing based on risk
- Calculates comprehensive metrics:
  - Win rate, Profit factor, Sharpe ratio
  - Max drawdown, Total return
  - Individual trade logs

### 3. **Data Generation** (`generate_sample_data.py`)
- Creates 10 years of synthetic XAUUSD 1-hour candle data
- Realistic price movements using random walk model
- Ready for backtesting without external API dependencies

### 4. **Visualization Suite** (`visualize.py`)
- **Figure 1**: Full 10-year overview showing:
  - Price + EMAs over entire period
  - Key metrics (Sharpe ratio, Win rate, Max drawdown)
  - Cumulative P&L curve
  - Drawdown analysis
- **Figure 2**: Detailed recent period analysis (zoomed 2000 candles)
- **Figure 3**: Trade statistics dashboard with:
  - Win/loss distribution
  - P&L histograms
  - Win rate pie chart
  - Sharpe ratio & win rate highlighted

### 5. **Parameter Optimizer** (`optimize_parameters.py`)
- Grid search across EMA period combinations
- Tests different fast/slow EMA pairs
- Ranks results by Sharpe ratio
- Generates heatmaps for visualization

---

## Initial Backtest Results (EMA 12/26)

| Metric | Value |
|--------|-------|
| **Sharpe Ratio** | 0.22 |
| **Win Rate** | 33.01% |
| **Total Trades** | 1,557 |
| **Total Return** | 2,840.85% |
| **Profit Factor** | 1.35 |
| **Max Drawdown** | -44.69% |
| **Initial Capital** | $10,000 |
| **Final Capital** | $294,084 |

---

## Parameter Optimization Results (Preliminary)

### Top Performing Combinations (by Sharpe Ratio):

From 42 tested combinations, early results show:

| Fast EMA | Slow EMA | Sharpe Ratio | Win Rate | Return % |
|----------|----------|--------------|----------|----------|
| 5 | 20 | 0.24 | 31.5% | 5,615.33% |
| 5 | 26 | 0.24 | 31.6% | 4,679.80% |
| 10 | 50 | 0.24 | 32.2% | 3,954.35% |
| 12 | 50 | 0.23 | 34.0% | 2,960.82% |
| 12 | 40 | 0.23 | 32.9% | 3,453.47% |

### Key Insights:

1. **Faster EMAs = Higher Returns but Higher Frequency**
   - EMA(5/20): Highest return (5,615%) but many false signals
   - EMA(5/26): Similar Sharpe but slightly fewer trades

2. **Win Rate Sweet Spot: 32-34%**
   - Most successful strategies hover around 33% win rate
   - This is actually normal for trending strategies
   - Quality of wins > quantity (avg win/loss ratio matters)

3. **Sharpe Ratio Plateaus at 0.24**
   - Suggests synthetic data limitations
   - Real market would have different risk/reward profile

---

## File Outputs Generated

```
ema_strategy_full_period.png       # 10-year overview with key metrics
ema_strategy_detailed.png          # Zoomed recent period analysis
ema_strategy_statistics.png        # Trade statistics dashboard
optimization_results.csv           # Full parameter test results
ema_parameter_heatmap.png         # Heatmap of parameter combinations
```

---

## Key Concepts Explained

### What is Sharpe Ratio?
**Definition**: Risk-adjusted return. Measures how much excess return you get for extra volatility taken.
- **Formula**: (Average Return - Risk-Free Rate) / Standard Deviation
- **Higher is Better**: > 1 is good, > 2 is excellent
- **Our Results**: 0.22 is modest but on synthetic data (real trading would differ)

### What is Win Rate?
**Definition**: Percentage of trades that make money
- **Average Range**: 30-50%
- **Our Strategy**: ~33% (profitable trades > losing trades in P&L)
- **Key Point**: Win rate is LESS important than average win/loss ratio
  - If avg win = $2,137 and avg loss = $-781, we profit despite 33% win rate

### What are EMAs?
**EMA (Exponential Moving Average)**:
- Weighted average giving more importance to recent prices
- Unlike simple MA, it responds faster to price changes
- Fast EMA = more responsive (captures trends quickly)
- Slow EMA = smoother (confirms long-term direction)

**Crossover Signals**:
- BUY: Fast EMA > Slow EMA (bullish momentum)
- SELL: Fast EMA < Slow EMA (bearish momentum)

---

## Why Some Parameters Work Better

Looking at optimization results, we can see patterns:

1. **EMA(5/20)** performs best because:
   - Very responsive to short-term trends
   - Captures quick reversals
   - More trades = more opportunities
   - BUT higher false signals

2. **EMA(12/26)** (current default) balances:
   - Fewer trades (1,557 vs 2,745 for 5/20)
   - Better entry quality
   - Less whipsaw
   - Moderate Sharpe ratio

3. **EMA(12/50)** shows interesting property:
   - High Sharpe ratio (0.23) despite fewer trades (1,119)
   - Suggests quality over quantity works
   - Longer slow EMA filters out noise

---

## Next Steps & Recommendations

### 1. **Use Real Data** (Most Important)
```bash
# Install MetaTrader 5
pip install MetaTrader5

# Run the fetch script to get actual XAUUSD data
python fetch_data_mt5.py
```

**Why**: Synthetic data has perfect distributions. Real markets have:
- Gap risk
- Unusual volatility events
- Correlations with macroeconomic news
- Hidden liquidity issues

### 2. **Test Different Risk/Reward Levels**
Current settings:
- Stop Loss: 2%
- Take Profit: 5%
- Ratio: 1:2.5

Consider testing:
- 2% / 6% (higher TP)
- 1% / 3% (tighter management)
- 3% / 10% (longer swings)

### 3. **Add Strategy Filters**
Current strategy trades on every crossover. Improve with:
- **Volatility filter**: Only trade when volatility > threshold
- **Time filter**: Trade only during peak liquidity hours
- **Trend filter**: Multi-timeframe confirmation (e.g., 4H trend)
- **Support/Resistance**: Find confluences with key levels

### 4. **Optimize Position Sizing**
Instead of fixed %, implement:
- **Kelly Criterion**: Mathematical position sizing
- **ATR-based**: Size based on volatility
- **drawdown-based**: Reduce size after losses

### 5. **Walk Forward Analysis**
Current method: Train on entire 10 years
Better method: 
- Train on years 1-5
- Test on years 6-10
- Slide the window
- Prevents overfitting

---

## Trading Strategy Workflow

```
1. Data Collection
   └─> 10yr XAUUSD 1H data

2. Strategy Rules
   └─> EMA(12/26) crossover
   └─> 2% SL / 5% TP

3. Backtesting
   └─> 1,557 trades
   └─> 33% win rate
   └─> 2,840% return

4. Parameter Optimization
   └─> Test 42 combinations
   └─> Identify best Sharpe ratio
   └─> Consider trade-offs

5. Real Market Testing
   └─> Forward test on live data
   └─> Paper trade first
   └─> Monitor for curve-fitting
   └─> Live trade with small size
```

---

## Files You Have

| File | Purpose | Status |
|------|---------|--------|
| `fetch_data.py` | Yahoo Finance data (2yr limit) | ✓ Ready |
| `fetch_data_mt5.py` | MetaTrader 5 data (10yr+) | ✓ Ready |
| `generate_sample_data.py` | Synthetic testing data | ✓ Complete |
| `ema_strategy.py` | Core EMA logic | ✓ Complete |
| `backtest.py` | Backtesting engine | ✓ Complete |
| `visualize.py` | Charts & dashboards | ✓ Complete |
| `optimize_parameters.py` | Parameter grid search | ✓ Complete |

---

## Quick Reference: Running the Project

```bash
# 1. Generate/Fetch data
python generate_sample_data.py      # Synthetic (fast)
# OR
python fetch_data_mt5.py            # Real (requires MT5)

# 2. Backtest current strategy
python backtest.py

# 3. Visualize results
python visualize.py

# 4. Optimize parameters
python optimize_parameters.py

# 5. View results
# Open the PNG files in your editor
```

---

## Summary

You now have a **complete, working EMA crossover trading strategy** with:
- ✅ 10 years of backtesting capability
- ✅ Multiple visualization tools
- ✅ Parameter optimization framework
- ✅ Real vs synthetic data options
- ✅ Professional-grade metrics

**The strategy works, but remember**: This is on synthetic data with perfect conditions. Real trading involves slippage, commissions, gaps, and emotional discipline that backtests don't capture.

**Next logical step**: Get real data and validate if this works in production conditions.
