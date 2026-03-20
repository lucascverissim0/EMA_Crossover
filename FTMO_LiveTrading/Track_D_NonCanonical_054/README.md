# Track D - Non-Canonical 0.54% Snapshot

This track freezes the current 0.54% risk Track C candidate into a separate, non-canonical workflow for discretionary trading review.

## Purpose
- Preserve the current fast-to-pass Track C candidate without overwriting Track C's canonical output family.
- Generate Track D-specific reports and visuals from the pinned trade sequence.
- Keep the higher-risk discretionary candidate isolated from the canonical Track C workflow.

## Source
- Source track: `Track_C_Time_Optimized`
- Source artifact: `reports/track_c_best_candidate.*`
- Expected fixed parameters: EMA(12/20), SL 0.5%, TP 3.0%, Risk 0.54%

## Status
- `canonical`: no
- Intended use: discretionary review / own-capital evaluation
- FTMO interpretation: not the canonical Track C decision engine and not the recommended path for strict FTMO compliance

## Outputs
- `reports/track_d_best_candidate.json`
- `reports/track_d_best_candidate.txt`
- `reports/track_d_best_candidate_oos_trades.csv`
- `reports/track_d_daily_activity.csv`
- `reports/track_d_source_candidate_rankings.csv`
- `images/track_d_probable_path.png`
- `images/track_d_trade_activity.png`
- `images/track_d_monte_carlo.png`
- `images/track_d_performance_dashboard.png`

## Run
From repo root:

```bash
python FTMO_Challenge/Track_D_NonCanonical_054/scripts/build_track_d_snapshot.py
```

## Notes
- Track D is a pinned snapshot of a selected Track C candidate, not a separate optimizer.
- If Track C is rerun later with a different canonical candidate, Track D remains a separate snapshot until regenerated explicitly.