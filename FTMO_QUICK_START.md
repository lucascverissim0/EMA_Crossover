# FTMO Challenge Quick Reference

## Canonical FTMO Answer

Use `Track C - Time Optimized` as the current FTMO answer.

Current canonical candidate:
- EMA(12/20)
- SL 1.0%
- TP 3.0%
- Risk 0.5%
- Fold pass rate: 100%
- OOS max drawdown: 8.39%
- OOS worst daily loss: -1.02%
- Monte Carlo pass probability: 96.60%

Source:
- `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/reports/track_c_best_candidate.txt`

## Track Roles

- `Track C`: canonical FTMO decision engine
- `Track B`: robustness reference and alternate walk-forward baseline
- `Track D`: pinned non-canonical 0.54% snapshot for faster-but-riskier comparison

## Fastest Review Path

From repo root:

```bash
python FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/scripts/optimize_time_to_pass.py
python FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/scripts/create_performance_dashboard.py
python FTMO_Challenge/Long_Strategy/compare_all_strategies.py
```

For MT5 execution of the faster Track D profile, see:
- `FTMO_Challenge/Long_Strategy/MT5_Automation/README.md`
- `FTMO_Challenge/Long_Strategy/MT5_Automation/run_track_d_mt5.py`

## What To Open First

1. `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/reports/track_c_best_candidate.txt`
2. `FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/images/track_c_performance_dashboard.png`
3. `FTMO_Challenge/Long_Strategy/strategy_comparison_dashboard.png`
4. `FTMO_Challenge/Long_Strategy/Track_D_NonCanonical_054/reports/track_d_best_candidate.txt`

## What The Comparison Dashboard Now Shows

`FTMO_Challenge/Long_Strategy/strategy_comparison_dashboard.png` includes:
- Track A historical baseline
- Track B robustness reference
- Track C canonical FTMO answer
- Track D non-canonical 0.54% snapshot

Use that image to compare speed, drawdown, pass probability, and total equity across the full track set.

## Practical Interpretation

- Choose `Track C` when the question is: "What should I use as the FTMO answer?"
- Check `Track B` when you want a second robustness-oriented walk-forward reference.
- Check `Track D` when you want to compare the faster 0.54% candidate against Track C, knowing that it is non-canonical and above the clean FTMO drawdown line.

## Live-Use Sequence

1. Review canonical Track C outputs.
2. Compare Track C vs Track D in `strategy_comparison_dashboard.png`.
3. If trading for FTMO-style compliance, stay with Track C.
4. If exploring discretionary higher-risk execution, review Track D separately.
