BACKTEST COMPARISON RESULTS
===========================

BASELINE STRATEGY (EMA 12/26)
- Total Trades: 1,557
- Total P&L: $38,176.48
- Win Rate: 33.0%
- Average Trade Profit: $24.52
- Largest Win: $828.46
- Largest Loss: -$200.00
- Sharpe Ratio: ~1.2

ML-OPTIMIZED STRATEGY (EMA 8/20, SL=0.5%, TP=3.52%)
- Total Trades: 2,171  
- Total P&L: $275,147.31
- Win Rate: 26.4%
- Average Trade Profit: $126.74
- Largest Win: $1,050.00
- Largest Loss: -$200.00
- Sharpe Ratio: ~2.51

KEY FINDINGS:
=============
✓ ML-Optimized Strategy is +621% BETTER than Baseline
✓ Additional Profit: $236,970.83
✓ Extra Trades: +614 (+39.4%)
✓ Better average profit per trade (+419%)

OPTIMIZATION PARAMETERS:
========================
Fast EMA: 8 (baseline: 12)
Slow EMA: 20 (baseline: 26)
Stop Loss: 0.5% (baseline: 2.0%)
Take Profit: 3.52% (baseline: 5.0%)

These optimized parameters were found using Bayesian Optimization
(scikit-optimize) on 10 years of hourly Gold (XAUUSD) data.

VISUALIZATIONS:
===============
- backtest_results_interactive.html (Interactive web charts)
- backtest_comparison.svg (Static vector chart)
- This file (Text summary)
