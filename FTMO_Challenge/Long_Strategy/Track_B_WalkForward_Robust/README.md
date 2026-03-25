# Track B - Walk-Forward Robust (Reference)

This is the robustness-oriented walk-forward reference track.

## Why This Track
- No look-ahead bias.
- Parameters are selected on training windows only.
- Performance is evaluated on unseen out-of-sample windows.
- Monte Carlo is computed from OOS trades.
- Useful as a benchmark against canonical Track C.

## Folder Layout
- `scripts/`: walk-forward engine and candidate selector.
- `images/`: OOS equity and Monte Carlo visuals.
- `reports/`: fold results, summaries, ranked candidates, best-candidate metrics.

## Core Scripts
1. `scripts/walk_forward_ftmo.py`
- Runs rolling walk-forward optimization and OOS validation.
- Produces fold-by-fold results and OOS-level summary.

2. `scripts/wfv_pass_probability_search.py`
- Searches fixed parameter sets and ranks by:
  1) Monte Carlo pass probability,
  2) fold pass rate,
  3) OOS return.

## Current Best Candidate
From `reports/wfv_best_candidate.txt`:
- EMA(12/20)
- SL 1.0%
- TP 3.0%
- Risk 0.5%
- Fold pass rate: 100%
- OOS max drawdown: 8.39%
- OOS worst daily loss: -1.02%
- Monte Carlo pass probability: 96.60%

## Role In The Current FTMO Setup
- Track C is the canonical FTMO answer.
- Track B remains valuable as a robustness baseline and alternate walk-forward reference.

## Typical Commands
Run from repo root:

```bash
python FTMO_Challenge/Long_Strategy/Track_B_WalkForward_Robust/scripts/walk_forward_ftmo.py
python FTMO_Challenge/Long_Strategy/Track_B_WalkForward_Robust/scripts/wfv_pass_probability_search.py
```

## What To Review First
1. `reports/wfv_best_candidate.txt`
2. `reports/wfv_candidate_rankings.csv`
3. `images/wfv_best_candidate_monte_carlo.png`
4. `images/wfv_best_candidate_oos_equity.png`
