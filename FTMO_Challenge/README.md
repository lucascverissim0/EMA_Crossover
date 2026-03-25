# FTMO Challenge Workspace

This folder is organized as a long/short research workspace.

## Strategy Containers

1. `Long_Strategy`
- Organizational container for long-only assets.
- Long tracks and long reporting scripts now live in this folder.

2. `Short_Strategy`
- Root for short-side research tracks.
- Includes `Track_A_Short_EMA` as the first short exploration track.

## Existing Long Track Names (inside `Long_Strategy`)

1. `Track_A_Capital_Preservation`
- Legacy conservative workflow and earlier FTMO analysis assets.
- Useful for historical comparison.
- Not the primary decision engine.

2. `Track_B_WalkForward_Robust`
- Robustness reference workflow.
- Uses walk-forward validation only (no post-hoc trade filtering).
- Optimizes for pass probability under FTMO constraints.

3. `Track_C_Time_Optimized`
- Canonical FTMO answer.
- Time-to-pass optimization under robustness constraints.
- Enforces Monte Carlo pass probability >= 95%.
- Optimizes average time (trades/days) to pass Step 1 and Step 2.

4. `Track_D_NonCanonical_054`
- Pinned snapshot of the current 0.54% Track C candidate.
- Non-canonical by design.
- Intended for discretionary review of the faster, higher-risk candidate without overwriting Track C.

## Recommended Workflow (Track C)

Run from repo root:

```bash
python FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/scripts/optimize_time_to_pass.py
python FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/scripts/create_performance_dashboard.py
python FTMO_Challenge/Long_Strategy/compare_all_strategies.py
```

## Short Workflow (Track A)

Run from repo root:

```bash
python FTMO_Challenge/Short_Strategy/Track_A_Short_EMA/scripts/optimize_short_ema_track_a.py
python FTMO_Challenge/Short_Strategy/Track_A_Short_EMA/scripts/walk_forward_short_ema.py
```

The first command runs broad short EMA ranking with visuals.
The second command runs walk-forward validation (default 5y train + 2y test per fold) plus Monte Carlo plausibility checks.

Review outputs:

- Reports:
  - `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/reports/track_c_best_candidate.txt`
  - `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/reports/track_c_best_candidate.json`
  - `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/reports/track_c_candidate_rankings.csv`
- Images:
  - `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/images/track_c_performance_dashboard.png`
  - `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/images/track_c_probable_path.png`
  - `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/images/track_c_trade_activity.png`
  - `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/images/track_c_monte_carlo.png`

Track C also contains `wfv_extended_*` files from the separate `walk_forward_extended_1y_2y.py` validator. Treat those as extended stress-test outputs, not as the same artifact family as `track_c_best_candidate.*`.

Track D outputs:

- Reports:
  - `FTMO_Challenge/Long_Strategy/Track_D_NonCanonical_054/reports/track_d_best_candidate.txt`
  - `FTMO_Challenge/Long_Strategy/Track_D_NonCanonical_054/reports/track_d_best_candidate.json`
  - `FTMO_Challenge/Long_Strategy/Track_D_NonCanonical_054/reports/track_d_best_candidate_oos_trades.csv`
- Images:
  - `FTMO_Challenge/Long_Strategy/Track_D_NonCanonical_054/images/track_d_probable_path.png`
  - `FTMO_Challenge/Long_Strategy/Track_D_NonCanonical_054/images/track_d_trade_activity.png`
  - `FTMO_Challenge/Long_Strategy/Track_D_NonCanonical_054/images/track_d_monte_carlo.png`
  - `FTMO_Challenge/Long_Strategy/Track_D_NonCanonical_054/images/track_d_performance_dashboard.png`

Comparison outputs:

- `FTMO_Challenge/Long_Strategy/strategy_comparison_dashboard.png`
- `FTMO_Challenge/Long_Strategy/strategy_comparison_summary.txt`
- `FTMO_Challenge/Long_Strategy/strategy_comparison_summary.json`

MT5 automation:

- `FTMO_Challenge/Long_Strategy/MT5_Automation/README.md`
- `FTMO_Challenge/Long_Strategy/MT5_Automation/config.example.json`
- `FTMO_Challenge/Long_Strategy/MT5_Automation/run_track_d_mt5.py`

## Current FTMO Answer (Track C)

From `Track_C_Time_Optimized/reports/track_c_best_candidate.txt`:
- EMA(12/20)
- SL 1.0%
- TP 3.0%
- Risk 0.5%
- Fold pass rate: 100%
- OOS max drawdown: 8.39%
- OOS worst daily loss: -1.02%
- Monte Carlo pass probability: 96.60%

## How To Use The Tracks

- Use `Track C` as the canonical FTMO decision engine.
- Use `Track B` as a robustness reference and alternate walk-forward baseline.
- Use `Track D` only to compare the faster non-canonical 0.54% snapshot against canonical Track C in the shared comparison dashboard.

## MT5 Challenge Automation

If you intend to execute the faster Track D profile on an FTMO challenge through MT5, start in dry-run mode with the runner in `FTMO_Challenge/Long_Strategy/MT5_Automation/` and only enable live order sending after validating symbol mapping, lot sizing, and FTMO guardrail handling.
