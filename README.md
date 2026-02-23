# EMA Crossover Long-Only Trading Strategy

A sophisticated algorithmic trading system based on Exponential Moving Average (EMA) crossovers, backtested on 10 years of hourly Gold (XAUUSD) data with ML-optimized parameters using Bayesian optimization.

## 📊 Strategy Overview

This is a **long-only trading strategy** that trades Gold (XAUUSD) on hourly timeframes. The strategy uses two exponential moving averages to generate trading signals and includes risk management with stop-loss and take-profit levels.

### Performance Highlight
- **Total Profit:** $275,147.31 (2,751% ROI on $10k)
- **Win Rate:** 26.4%
- **Average Trade Profit:** $126.74
- **Sharpe Ratio:** 2.51
- **Total Trades:** 2,171 over 10 years
- **Backtested Period:** Feb 2016 - Feb 2026

---

## 🎯 Strategy Logic

### Entry Conditions (LONG)
The strategy enters a long position when:
1. **Fast EMA (8-period) crosses ABOVE Slow EMA (20-period)**
   - This indicates bullish momentum and trend reversal
   - Optimized parameters: Fast EMA = 8, Slow EMA = 20

### Exit Conditions
The strategy exits a position when ANY of the following occur (whichever comes first):

#### 1. **Stop Loss (SL = 0.5%)**
   - Exits when price drops 0.5% below entry price
   - Protects capital from larger losses
   - Triggered by: `current_price ≤ entry_price × (1 - 0.005)`

#### 2. **Take Profit (TP = 3.52%)**
   - Exits when price rises 3.52% above entry price
   - Locks in profits from favorable moves
   - Triggered by: `current_price ≥ entry_price × (1.0352)`

#### 3. **Sell Signal**
   - Exits when Fast EMA crosses BELOW Slow EMA
   - Indicates trend reversal or weakening momentum
   - Exit at market price

#### Exit Priority
The exits are checked in this order at each candle:
1. Stop Loss (highest priority - risk management)
2. Take Profit
3. Sell Signal (opportunistic exit)

---

## 📁 Project Structure

### Core Strategy Files
- **`ema_strategy.py`** - EMA crossover strategy implementation
  - Calculates exponential moving averages
  - Identifies buy/sell crossover points
  - Generates trading signals
  
- **`backtest.py`** - Backtesting engine
  - Simulates trading with historical data
  - Applies stop-loss, take-profit, and sell signal logic
  - Calculates performance metrics (Sharpe ratio, win rate, etc.)
  - Generates trades CSV with entry/exit details

- **`ml_optimizer.py`** - Bayesian optimization for parameter tuning
  - Uses scikit-optimize for hyperparameter search
  - Tests combinations of: Fast EMA, Slow EMA, Stop Loss %, Take Profit %
  - Optimizes for maximum Sharpe ratio
  - ML Optimized Results: EMA(8,20), SL=0.5%, TP=3.52%

### Data Management
- **`fetch_data.py`** - Downloads historical Gold price data from Yahoo Finance
- **`fetch_data_mt5.py`** - Alternative data fetching via MT5 API
- **`generate_sample_data.py`** - Creates sample data for testing

### Visualization & Analysis
- **`visualize.py`** - Creates comprehensive strategy analysis charts
- **`visualize_equity_curve.py`** - Generates equity curve visualization with annual breakdown
- **`simple_chart.py`** - Quick visualization helper
- **`create_chart.py`**, **`create_png.py`** - Image generation utilities

### Utilities
- **`optimize_parameters.py`** - Parameter optimization runner
- **`results_readme.txt`** - Summary of backtest results
- **`requirements.txt`** - Python package dependencies

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/lucascverissim0/EMA_Crossover.git
cd EMA_Crossover_LongOnly

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Backtest with Default Parameters

```bash
python backtest.py
```

This will:
- Load historical data (or fetch if not available)
- Run the backtest with default EMA(12,26) parameters
- Generate `backtest_results.csv` with all trades
- Display performance metrics

### 3. Run ML Optimization

```bash
python ml_optimizer.py
```

This will:
- Search for optimal parameters using Bayesian optimization
- Test various combinations of EMA periods, stop-loss, and take-profit levels
- Save results to `ml_optimization_results.txt`
- Generate optimized backtest results

### 4. Visualize Results

```bash
# Generate equity curve visualization
python visualize_equity_curve.py

# Generate comprehensive analysis charts
python visualize.py
```

---

## 📈 Results

### Baseline Strategy (EMA 12/26)
- Total Trades: 1,557
- Total P&L: $38,176.48
- Win Rate: 33.0%
- Sharpe Ratio: ~1.2

### ML-Optimized Strategy (EMA 8/20, SL=0.5%, TP=3.52%)
- Total Trades: 2,171
- Total P&L: $275,147.31 ✓ **+621% better**
- Win Rate: 26.4%
- Average Trade Profit: $126.74 (+419% vs baseline)
- Sharpe Ratio: ~2.51

### Annual Breakdown
```
2016: $18,256.70  (188 trades)
2017: $38,943.37  (217 trades) ← Best year
2018: $20,235.03  (205 trades)
2019: $29,196.16  (228 trades)
2020: $20,675.78  (216 trades)
2021: $35,977.66  (204 trades)
2022: $24,757.02  (215 trades)
2023: $25,256.29  (225 trades)
2024: $31,113.94  (207 trades)
2025: $28,446.09  (234 trades)
2026: $2,289.25   (32 trades - partial year)
```

---

## ⚙️ Configuration

### Strategy Parameters (Optimized)
```python
fast_ema = 8           # Fast EMA period
slow_ema = 20          # Slow EMA period
stop_loss = 0.5        # Stop loss percentage
take_profit = 3.52     # Take profit percentage
```

### Backtest Settings
```python
initial_capital = 10000    # Starting capital in USD
risk_percent = 2           # Risk per trade as % of capital
timeframe = "1h"           # 1-hour candles
```

---

## 📊 Output Files

- **`backtest_results.csv`** - Trades from baseline strategy (EMA 12/26)
- **`backtest_results_ml_optimized_fixed.csv`** - Trades from optimized strategy
- **`equity_curve_visualization.png`** - Equity curve charts with annual breakdown
- **`backtest_results_interactive.html`** - Interactive web-based charts

Each CSV contains:
- Entry index, entry price
- Exit index, exit price
- Profit/Loss in USD and percentage
- Exit reason (Stop Loss, Take Profit, or Sell Signal)

---

## 🔍 How to Interpret the Data

### Sample Trade Entry
```
entry_index: 2
entry_price: 2010.69
exit_index: 15
exit_price: 2000.64
pnl: -200.00
pnl_percent: -0.57%
reason: Stop Loss
```

This trade:
1. Entered when Fast EMA crossed above Slow EMA around candle 2
2. Entry price was 2010.69
3. Price fell quickly, hitting the 0.5% stop loss at 2000.64
4. Loss of $200 was taken at candle 15 (risk management working)

---

## 🛠️ Development

### Dependencies
- Python 3.8+
- pandas, numpy - Data manipulation
- yfinance - Data fetching
- scikit-optimize - Bayesian optimization
- matplotlib - Visualization

### File Dependencies Chain
```
backtest.py
    ├─ ema_strategy.py
    ├─ fetch_data.py (data loading)
    └─ generates: backtest_results.csv

ml_optimizer.py
    ├─ backtest.py
    ├─ ema_strategy.py
    └─ generates: backtest_results_ml_optimized_fixed.csv

visualize_equity_curve.py
    └─ backtest_results_ml_optimized_fixed.csv
    └─ generates: equity_curve_visualization.png
```

---

## 📝 Key Insights

1. **Parameter Optimization Matters:**
   - ML optimization improved returns by 621%
   - Tighter stop loss (0.5% vs 2%) reduced losses
   - Optimized take profit (3.52% vs 5%) captured more trades

2. **Consistency Over Years:**
   - Strategy profitable every year (2016-2025)
   - Annual profits range from $18k-$39k
   - Demonstrates robustness across market conditions

3. **Trade-Off Analysis:**
   - Lower take profit increased trade frequency (+614 trades)
   - Lower win rate (26.4% vs 33%) but higher avg profit per trade
   - Better risk-adjusted returns (Sharpe: 2.51 vs 1.2)

4. **Risk Management:**
   - Stop loss prevented catastrophic losses
   - Consistent position sizing based on risk
   - Maximum loss per trade limited by stop loss

---

## 📚 Further Reading

- [EMA Crossover Strategy Concepts](https://www.investopedia.com/terms/e/ema.asp)
- [Bayesian Optimization](https://scikit-optimize.github.io/)
- [Backtesting Best Practices](https://www.investopedia.com/terms/b/backtesting.asp)

---

## ⚠️ Disclaimer

This project is for educational and research purposes only. Past backtest performance does not guarantee future results. Always conduct thorough research and risk assessment before live trading. Real-world variables like slippage, commissions, and liquidity are not fully accounted for in the backtest model.

---

## 📞 Contact & Contributions

For questions or contributions, please open an issue or pull request on GitHub.

**Repository:** https://github.com/lucascverissim0/EMA_Crossover

---

**Last Updated:** February 23, 2026  
**Strategy Status:** ✅ Backtested & Optimized  
**Data Coverage:** 10 Years (Feb 2016 - Feb 2026)
- See `requirements_advanced.txt` for setup

## Next Steps

1. Fetch 10-year XAUUSD 1H data using MetaTrader 5
2. Implement basic EMA crossover strategy
3. Build backtesting engine
4. Optimize parameters using grid search
5. Forward test with real market data
6. Implement risk management and position sizing

## Disclaimer

This is an educational project. Past performance does not guarantee future results. Always test thoroughly and use proper risk management when trading real money.