# Short Strategy Workspace

This folder hosts short-side FTMO exploration tracks.

Current structure:

- `Track_A_Short_EMA/`
  - `scripts/`
  - `reports/`
  - `images/`
- `Track_B_Short_ML/`
  - `scripts/`
  - `reports/`
  - `images/`
- `Track_C_Short_FTMO/`
  - `scripts/`
  - `reports/`
  - `images/`

Track A short starts with EMA crossover optimization ranked by Sharpe ratio with risk-aware penalties.
Track B adds ML trade filtering.
Track C applies an FTMO-first objective (pass probability and days-to-pass, with Sharpe as secondary ranking).
