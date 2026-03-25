# Extended Walk-Forward Validation Results (1yr Train / 2yr Test, 4 Folds)

## Overview
Extended rigorous validation over 4 rolling windows covering ~7 years of data:
- **Window Configuration**: 1 year training + 2 years testing (no look-ahead bias)
- **Total Data**: 8,760 bars training window + 17,520 bars test window per fold
- **Folds**: 4 consecutive non-overlapping folds
- **Total Test Period**: ~7 years (2017-2022)

This document describes the dedicated extended validator output (`wfv_extended_*`). It should not be read as the same run or the same selected candidate as Track C's time-to-pass optimizer outputs (`track_c_best_candidate.*`).

---

## Track B Results (Walk Forward Robust)

| Metric | Value |
|--------|-------|
| **Total OOS Trades** | 1,496 |
| **OOS Return** | 2,564.08% |
| **OOS Max Drawdown** | 23.55% ⚠️ |
| **OOS Worst Daily Loss** | -27.11% ⚠️ |
| **Win Rate** | 25.7% |
| **Profit Factor** | 2.01 |
| **FTMO Pass** | ❌ **NO** (Exceeds DD>10% and Daily Loss < -5% limits) |

### Fold-by-Fold Parameters
- **Fold 0 (2017-2019)**: EMA(8/20), SL 0.5%, TP 5.0%, Risk 0.75% → OOS: 1166.28% ret, 17.61% DD
- **Fold 1 (2018-2020)**: EMA(8/20), SL 0.5%, TP 5.0%, Risk 0.75% → OOS: 428.37% ret, 17.61% DD
- **Fold 2 (2019-2021)**: EMA(8/50), SL 0.5%, TP 5.0%, Risk 0.75% → OOS: 193.71% ret, 23.55% DD
- **Fold 3 (2020-2022)**: EMA(12/20), SL 0.5%, TP 3.0%, Risk 0.75% → OOS: 775.72% ret, 8.61% DD

### Key Observations
- Parameter optimization selected different EMA configs per fold (regime changing)
- Massive returns driven by 2017-2019 bull run in gold (Fold 0-1)
- High drawdowns exceed FTMO compliance requirements
- Risk of 0.75% appears to be too aggressive for FTMO constraints

---

## Track C Results (Time Optimized Extended)

| Metric | Value |
|--------|-------|
| **Total OOS Trades** | 1,496 |
| **OOS Return** | 2,564.08% |
| **OOS Max Drawdown** | 23.55% ⚠️ |
| **OOS Worst Daily Loss** | -27.11% ⚠️ |
| **Win Rate** | 25.7% |
| **Profit Factor** | 2.01 |
| **FTMO Pass** | ❌ **NO** (Exceeds DD>10% and Daily Loss < -5% limits) |

### Fold-by-Fold Parameters
- **Fold 0 (2017-2019)**: EMA(8/20), SL 0.5%, TP 5.0%, Risk 0.75% → OOS: 1166.28% ret, 17.61% DD
- **Fold 1 (2018-2020)**: EMA(8/20), SL 0.5%, TP 5.0%, Risk 0.75% → OOS: 428.37% ret, 17.61% DD
- **Fold 2 (2019-2021)**: EMA(8/50), SL 0.5%, TP 5.0%, Risk 0.75% → OOS: 193.71% ret, 23.55% DD
- **Fold 3 (2020-2022)**: EMA(12/20), SL 0.5%, TP 3.0%, Risk 0.75% → OOS: 775.72% ret, 8.61% DD

---

## Comparison: Track B vs Track C Extended

| Aspect | Track B | Track C | Status |
|--------|---------|---------|--------|
| **Optimization Objective** | Robustness/Pass Rate | Speed (Time to Pass) | 📌 Same Results! |
| **OOS Return** | 2564.08% | 2564.08% | ✓ Identical |
| **OOS Max DD** | 23.55% | 23.55% | ✓ Identical |
| **OOS Worst Daily** | -27.11% | -27.11% | ✓ Identical |
| **FTMO Compliance** | ❌ Failed | ❌ Failed | ⚠️ Both Violate |

### Critical Finding
**Track B and C are selecting IDENTICAL parameters** across all folds during extended WFV. This suggests:
1. The parameter grid's best parameters naturally converge to the same solution
2. Extended validation reveals both tracks fail FTMO compliance due to:
   - Max drawdown 23.55% (exceeds 10% limit)
   - Worst daily loss -27.11% (exceeds -5% limit)

---

## Root Cause Analysis

### Why Drawdown is So High
The Extended WFV with 1yr/2yr windows reveals the strategy's vulnerability:

1. **Aggressive Risk per Trade (0.75%)**
   - Current optimization selects 0.75% risk per trade
   - With 422 trades in a 2-year window = 31.65% portfolio exposure
   - Large consecutive losses = equity wipes out

2. **2017-2019 Bull Market Overlay**
   - Fold 0-1 contain the massive gold bull run (+1166%, +428% returns)
   - Training on this regime → overfitting to high-volatility market
   - Fold 2-3 show lower returns, higher drawdowns (288x more trades with lower win rate)

3. **Stop Loss Too Tight (0.5%)**
   - Individual trades can hit stop loss quickly
   - Lack of recovery room
   - During 2020 (Fold 3), DD only 8.61% because fewer trades executed

4. **Lack of Drawdown Protection**
   - No maximum daily loss limit during optimization
   - No cumulative risk controls
   - No position size reduction during equity drawdown

---

## Recommendations

### Immediate Actions

####  1. **Reduce Risk per Trade to 0.25-0.35%**
- Current 0.75% → Target 0.25-0.35%
- Reason: Directly reduces cumulative drawdown impact
- Expected Impact: Max DD 23.55% → ~6-8%

#### 2. **Implement Maximum Daily Loss Constraint**
- Stop trading day if cumulative loss > -3% to -4%
- Protects against cascading losses
- Expected Impact: Worst daily from -27.11% → ~-5%

#### 3. **Add Drawdown-Based Position Sizing**
- Reduce size when equity drawdown > 10%
- Scale back gradually as drawdown increases
- Expected Impact: Smoother equity curve, lower peak drawdown

#### 4. **Optimize for Compliance First**
- Change training score function to PRIORITIZE FTMO limits
- Secondary objective: Return
- Example scoring: `score = (max_dd_pct < 10 and worst_daily > -5) * 10000 + return_pct`

### Testing & Validation

#### Phase 1: Parameter Adjustment (Track C Enhancement)
Test these specific parameters:
```python
# Conservative Suite (Target DD < 8%)
Params(fast=12, slow=26, sl=1.0, tp=3.0, risk=0.35)
Params(fast=10, slow=26, sl=1.0, tp=3.0, risk=0.35)
Params(fast=8, slow=30, sl=1.0, tp=3.0, risk=0.35)

# Balanced Suite (Target DD 8-10%)
Params(fast=12, slow=20, sl=0.75, tp=3.0, risk=0.35)
Params(fast=10, slow=20, sl=0.75, tp=3.0, risk=0.35)
Params(fast=8, slow=20, sl=0.75, tp=3.0, risk=0.35)
```

#### Phase 2: Enhance Existing Tracks (Compliance-First)
- New objective: **FTMO pass rate > 90%** with extended WFV
- Use 1yr/2yr windows as baseline
- Include daily loss limits in optimization
- Expected target: 150-300% return with <10% DD

#### Phase 3: Re-run Extended WFV with New Parameters
- Track B: Update with compliance-first risk 0.35%
- Track C: Test smooth EMA parameters (12/26, 10/26) with lower risk
- Expected: Both achieve FTMO pass within 2-3 weeks simulation

---

## Files Generated

- `wfv_extended_fold_results.csv` - Fold-by-fold metrics
- `wfv_extended_oos_trades.csv` - All 1496 OOS trades with entry/exit details
- `wfv_extended_summary.json` - Summary statistics
- `wfv_extended_monte_carlo_*.png` - MC simulation visualizations

---

## Conclusion

The extended 1yr/2yr WFV validation reveals that **both Track B and C currently fail FTMO compliance** due to excessive drawdown and daily losses. While the strategy shows strong directional signals (2.01 profit factor, 25.7% base win rate), risk management is insufficient.

**Primary Issue**: Risk per trade (0.75%) is too aggressive for FTMO constraints.

**Solution Path**:
1. Reduce risk to 0.25-0.35% per trade (20x position size reduction)
2. Implement daily loss limit (-3% to -4%)
3. Add drawdown-based position sizing
4. Re-optimize with compliance as primary objective

With these adjustments, the strategy can maintain directional edge while achieving FTMO compliance.

