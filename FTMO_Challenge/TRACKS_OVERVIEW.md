# FTMO Challenge Tracks Overview

This directory is organized into four named tracks:

## 1) Track_A_Capital_Preservation
- Purpose: legacy conservative analysis and historical comparison.
- Status: secondary reference.
- Subfolders:
  - `scripts/`
  - `images/`
  - `reports/`

## 2) Track_B_WalkForward_Robust
- Purpose: realistic walk-forward workflow for FTMO pass probability.
- Status: robustness reference path.
- Subfolders:
  - `scripts/`
  - `images/`
  - `reports/`

## 3) Track_C_Time_Optimized
- Purpose: optimize challenge completion speed under a strict robustness guard.
- Status: canonical FTMO answer.
- Constraint: Monte Carlo pass probability must remain >= 95%.
- Objective: minimize average trades/days to pass Step 1 (+10%) and Step 2 (+15%).
- Subfolders:
  - `scripts/`
  - `images/`
  - `reports/`

## 4) Track_D_NonCanonical_054
- Purpose: pin the faster 0.54% Track C candidate into a separate discretionary-review track.
- Constraint: none beyond the pinned source artifact; this track is intentionally non-canonical.
- Objective: preserve and visualize the non-canonical 0.54% candidate without overwriting Track C.
- Subfolders:
  - `scripts/`
  - `images/`
  - `reports/`

## Recommendation
Use Track C as the canonical FTMO answer. Use Track B as the robustness reference. Use Track D only when you want to compare the faster pinned 0.54% non-canonical snapshot against Track C in the shared comparison dashboard.
