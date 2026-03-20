#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-all}"

run_compare() {
  python "$ROOT/FTMO_Challenge/compare_all_strategies.py"
}

run_track_d() {
  python "$ROOT/FTMO_Challenge/Track_D_NonCanonical_054/scripts/build_track_d_snapshot.py"
}

if [[ "$MODE" == "all" ]]; then
  python "$ROOT/FTMO_Challenge/Track_B_WalkForward_Robust/scripts/walk_forward_extended_1y_2y.py"
  python "$ROOT/FTMO_Challenge/Track_C_Time_Optimized/scripts/walk_forward_extended_1y_2y.py"
  run_track_d
  run_compare
elif [[ "$MODE" == "track-c" ]]; then
  python "$ROOT/FTMO_Challenge/Track_C_Time_Optimized/scripts/walk_forward_extended_1y_2y.py"
  run_compare
elif [[ "$MODE" == "track-d" ]]; then
  run_track_d
  run_compare
elif [[ "$MODE" == "track-b" ]]; then
  python "$ROOT/FTMO_Challenge/Track_B_WalkForward_Robust/scripts/walk_forward_extended_1y_2y.py"
  run_compare
elif [[ "$MODE" == "compare-only" ]]; then
  run_compare
else
  echo "Usage: $0 [all|track-c|track-d|track-b|compare-only]"
  exit 1
fi

echo "Refresh complete: $MODE"
