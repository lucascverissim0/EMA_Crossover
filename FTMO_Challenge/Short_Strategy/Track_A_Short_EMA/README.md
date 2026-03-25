# Track A - Short EMA Exploration

Objective:
- Find short-only EMA combinations with strong Sharpe ratio.
- Keep maximum drawdown, worst daily loss, and return quality in the ranking.

## Run

From repository root:

```bash
python FTMO_Challenge/Short_Strategy/Track_A_Short_EMA/scripts/optimize_short_ema_track_a.py
```

Walk-forward + Monte Carlo validation (7-year horizon per fold by default):

```bash
python FTMO_Challenge/Short_Strategy/Track_A_Short_EMA/scripts/walk_forward_short_ema.py
```

Optional input file:

```bash
python FTMO_Challenge/Short_Strategy/Track_A_Short_EMA/scripts/optimize_short_ema_track_a.py --data data/GC_1h_data.csv
python FTMO_Challenge/Short_Strategy/Track_A_Short_EMA/scripts/walk_forward_short_ema.py --data data/GC_1h_data.csv
```

## Outputs

Reports:
- `reports/track_a_short_rankings.csv`
- `reports/track_a_short_best_candidate.json`
- `reports/track_a_short_best_candidate.txt`
- `reports/track_a_short_best_trades.csv`

Images:
- `images/track_a_short_equity_drawdown.png`
- `images/track_a_short_daily_pnl.png`
- `images/track_a_short_score_vs_sharpe.png`
- `images/track_a_short_performance_dashboard.png`
