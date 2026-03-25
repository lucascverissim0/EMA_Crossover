# Next Steps: FTMO Track Operation

## Current State

The repository now has a clear FTMO answer:
- `Track C` is the canonical FTMO path.
- `Track B` is the robustness reference.
- `Track D` is the pinned 0.54% non-canonical comparison track.

Canonical Track C metrics:
- EMA(12/20), SL 1.0%, TP 3.0%, Risk 0.5%
- Fold pass rate: 100%
- OOS max drawdown: 8.39%
- Worst daily loss: -1.02%
- Monte Carlo pass probability: 96.60%

## Priority Order

### 1. Use Track C for FTMO decisions

Primary files:
- `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/reports/track_c_best_candidate.txt`
- `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/reports/track_c_best_candidate.json`
- `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/images/track_c_performance_dashboard.png`

### 2. Compare Track C and Track D visually

Open:
- `FTMO_Challenge/Long_Strategy/strategy_comparison_dashboard.png`

Use it to compare:
- pass probability
- drawdown
- total equity
- time to pass

Interpretation:
- `Track C` is slower but cleanly compliant.
- `Track D` is faster but non-canonical and above the clean FTMO drawdown line.

### 3. Keep Track B as a reference baseline

Track B remains useful when you want:
- an alternate walk-forward baseline
- a robustness cross-check against Track C
- a second view on parameter stability

### 4. Only use Track D for discretionary review

Track D is not the strict FTMO answer.
Use it only when you intentionally want to inspect the faster 0.54% snapshot separately from canonical Track C.

## Recommended Commands

From repo root:

```bash
python FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/scripts/optimize_time_to_pass.py
python FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/scripts/create_performance_dashboard.py
python FTMO_Challenge/Long_Strategy/Track_D_NonCanonical_054/scripts/build_track_d_snapshot.py
python FTMO_Challenge/Long_Strategy/compare_all_strategies.py
```

## Reference Files

1. `FTMO_Challenge/README.md`
2. `FTMO_Challenge/TRACKS_OVERVIEW.md`
3. `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/README.md`
4. `FTMO_Challenge/Long_Strategy/Track_D_NonCanonical_054/README.md`
5. `FTMO_Challenge/Long_Strategy/strategy_comparison_summary.txt`
