# Track A - Capital Preservation (Legacy)

This track is the conservative, earlier FTMO preparation workflow.

## Important
- This track contains earlier analysis utilities.
- It includes post-hoc ideas that are **not** recommended for live decision-making.
- Keep this track mainly for historical comparison and exploratory reporting.

## Folder Layout
- `scripts/`: legacy validators/optimizers/visualizers.
- `images/`: generated charts from this track.
- `reports/`: generated CSV/TXT/JSON outputs.

## Typical Commands
Run from repo root:

```bash
python FTMO_Challenge/Track_A_Capital_Preservation/scripts/ftmo_validator.py
python FTMO_Challenge/Track_A_Capital_Preservation/scripts/ftmo_visualizer.py
python FTMO_Challenge/Track_A_Capital_Preservation/scripts/ftmo_optimizer.py
```

## When To Use
- Comparing against newer walk-forward results.
- Reviewing earlier assumptions and outputs.

## When Not To Use
- Final parameter selection for FTMO challenge.
- Any workflow that uses post-backtest filtering after seeing full results.
