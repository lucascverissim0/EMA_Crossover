"""
Track C - Time-to-Pass Optimizer

Goal:
- Find fixed parameter sets that pass FTMO Monte Carlo robustness constraints,
- Then optimize for speed to pass challenge phases.

Selection logic:
1) Keep only candidates with Monte Carlo pass probability >= 95%.
2) Among feasible candidates, minimize average trades to Step 2 (+15%).
3) Tie-breakers: average trades to Step 1 (+10%), Monte Carlo pass probability,
   and OOS return.

Outputs:
- reports/track_c_candidate_rankings.csv
- reports/track_c_best_candidate.json
- reports/track_c_best_candidate.txt
- reports/track_c_best_candidate_oos_trades.csv
- images/track_c_probable_path.png
- images/track_c_trade_activity.png
- images/track_c_monte_carlo.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


TRACK_C_DEFAULT_MC_CONSTRAINT_PCT = 95.0
STEP1_TARGET_PCT = 10.0
STEP2_TARGET_PCT = 15.0
INITIAL_CAPITAL = 10000.0


# Reuse Track B walk-forward utilities.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
TRACK_B_SCRIPTS = REPO_ROOT / "FTMO_Challenge" / "Track_B_WalkForward_Robust" / "scripts"
if str(TRACK_B_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TRACK_B_SCRIPTS))

from walk_forward_ftmo import (  # noqa: E402
    Params,
    compute_metrics,
    load_data,
    monte_carlo_paths,
    param_grid,
    run_segment_backtest,
)


def oos_windows(
    df: pd.DataFrame,
    train_bars: int,
    test_bars: int,
    step_bars: int,
    max_folds: int,
):
    windows = []
    start = 0
    fold = 0
    while fold < max_folds:
        train_end = start + train_bars
        test_end = train_end + test_bars
        if test_end > len(df):
            break
        windows.append((fold, train_end, test_end))
        fold += 1
        start += step_bars
    return windows


def compute_trades_per_day(trades_df: pd.DataFrame) -> float:
    if trades_df.empty or "exit_ts" not in trades_df.columns:
        return 1.0

    temp = trades_df.copy()
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"])
    temp["exit_date"] = temp["exit_ts"].dt.date
    counts = temp.groupby("exit_date")["pnl"].count()
    if counts.empty:
        return 1.0
    return float(counts.mean())


def first_hit_index(paths: np.ndarray, threshold: float) -> np.ndarray:
    if paths.size == 0:
        return np.array([], dtype=float)

    hits = np.full(paths.shape[0], np.nan, dtype=float)
    for i in range(paths.shape[0]):
        idx = np.where(paths[i] >= threshold)[0]
        if idx.size > 0:
            hits[i] = float(idx[0])
    return hits


def step_timing_stats(
    paths: np.ndarray,
    initial_capital: float,
    trades_per_day: float,
    step1_target_pct: float,
    step2_target_pct: float,
) -> dict:
    if paths.size == 0:
        return {
            "step1_pass_probability_pct": 0.0,
            "step2_pass_probability_pct": 0.0,
            "step1_avg_trades": None,
            "step2_avg_trades": None,
            "step1_avg_days": None,
            "step2_avg_days": None,
        }

    step1_equity = initial_capital * (1.0 + step1_target_pct / 100.0)
    step2_equity = initial_capital * (1.0 + step2_target_pct / 100.0)

    s1 = first_hit_index(paths, step1_equity)
    s2 = first_hit_index(paths, step2_equity)

    s1_valid = s1[~np.isnan(s1)]
    s2_valid = s2[~np.isnan(s2)]

    step1_avg_trades = float(np.mean(s1_valid)) if s1_valid.size > 0 else None
    step2_avg_trades = float(np.mean(s2_valid)) if s2_valid.size > 0 else None

    tpd = max(trades_per_day, 1e-9)

    return {
        "step1_pass_probability_pct": float((s1_valid.size / len(paths)) * 100.0),
        "step2_pass_probability_pct": float((s2_valid.size / len(paths)) * 100.0),
        "step1_avg_trades": step1_avg_trades,
        "step2_avg_trades": step2_avg_trades,
        "step1_avg_days": (step1_avg_trades / tpd) if step1_avg_trades is not None else None,
        "step2_avg_days": (step2_avg_trades / tpd) if step2_avg_trades is not None else None,
    }


def plot_trade_activity(trades_df: pd.DataFrame, out_path: Path) -> None:
    if trades_df.empty:
        return

    temp = trades_df.copy()
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"])
    temp["exit_date"] = temp["exit_ts"].dt.date

    daily = (
        temp.groupby("exit_date", as_index=False)["pnl"]
        .count()
        .rename(columns={"pnl": "trades"})
    )
    daily["cum_trades"] = daily["trades"].cumsum()

    plt.figure(figsize=(14, 6))
    ax1 = plt.gca()
    ax2 = ax1.twinx()

    x = np.arange(len(daily))
    labels = daily["exit_date"].astype(str)

    ax1.bar(x, daily["trades"], alpha=0.45, color="#1f77b4", label="Trades per day")
    ax2.plot(x, daily["cum_trades"], color="#111111", linewidth=2.2, label="Cumulative trades")

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=45, ha="right")

    total = int(len(trades_df))
    ax2.axhline(total, color="#2ca02c", linestyle="--", linewidth=1.2)
    ax2.text(0.01, 0.96, f"Total OOS trades: {total}", transform=ax2.transAxes, ha="left", va="top")

    ax1.set_title("Track C Best Candidate Trade Activity (OOS)")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Trades per day")
    ax2.set_ylabel("Cumulative trades")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left")

    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def plot_probable_path(
    paths: np.ndarray,
    out_path: Path,
    initial_capital: float,
    timing: dict,
    step1_target_pct: float,
    step2_target_pct: float,
) -> None:
    if paths.size == 0:
        return

    p10 = np.percentile(paths, 10, axis=0)
    p25 = np.percentile(paths, 25, axis=0)
    p50 = np.percentile(paths, 50, axis=0)
    p75 = np.percentile(paths, 75, axis=0)
    p90 = np.percentile(paths, 90, axis=0)

    x = np.arange(paths.shape[1])
    step1_equity = initial_capital * (1.0 + step1_target_pct / 100.0)
    step2_equity = initial_capital * (1.0 + step2_target_pct / 100.0)

    plt.figure(figsize=(14, 6))
    plt.fill_between(x, p10, p90, alpha=0.2, color="#aec7e8", label="10-90 percentile")
    plt.fill_between(x, p25, p75, alpha=0.35, color="#1f77b4", label="25-75 percentile")
    plt.plot(x, p50, linewidth=2.2, color="#111111", label="Median path")

    plt.axhline(step1_equity, linestyle="--", linewidth=1.5, color="#2ca02c", label=f"Step 1 (+{step1_target_pct:.0f}%)")
    plt.axhline(step2_equity, linestyle="--", linewidth=1.5, color="#ff7f0e", label=f"Step 2 (+{step2_target_pct:.0f}%)")

    if timing["step1_avg_trades"] is not None:
        s1x = timing["step1_avg_trades"]
        plt.axvline(s1x, color="#2ca02c", linewidth=1.2, alpha=0.9)
        plt.text(
            s1x,
            step1_equity,
            f"  Avg S1: {s1x:.1f} trades / {timing['step1_avg_days']:.1f} days",
            color="#2ca02c",
            va="bottom",
        )

    if timing["step2_avg_trades"] is not None:
        s2x = timing["step2_avg_trades"]
        plt.axvline(s2x, color="#ff7f0e", linewidth=1.2, alpha=0.9)
        plt.text(
            s2x,
            step2_equity,
            f"  Avg S2: {s2x:.1f} trades / {timing['step2_avg_days']:.1f} days",
            color="#ff7f0e",
            va="bottom",
        )

    plt.title("Track C Probable Path (Monte Carlo OOS)")
    plt.xlabel("Trade #")
    plt.ylabel("Equity ($)")
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def plot_monte_carlo(paths: np.ndarray, out_path: Path) -> None:
    if paths.size == 0:
        return

    plt.figure(figsize=(14, 6))
    to_plot = min(250, paths.shape[0])
    idx = np.random.choice(paths.shape[0], to_plot, replace=False)
    for i in idx:
        plt.plot(paths[i], alpha=0.08, linewidth=0.8, color="#2ca02c")

    plt.plot(paths.mean(axis=0), color="#111111", linewidth=2.0, label="Mean path")
    plt.title("Track C Monte Carlo Paths")
    plt.xlabel("Trade #")
    plt.ylabel("Equity ($)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def build_candidate_trades(
    df: pd.DataFrame,
    windows,
    p: Params,
    initial_capital: float,
) -> tuple[pd.DataFrame, int, int]:
    fold_passes = 0
    combined = []

    for fold, test_start, test_end in windows:
        test_df = df.iloc[test_start:test_end].copy()
        trades_df, _ = run_segment_backtest(test_df, p, initial_capital=initial_capital)
        m = compute_metrics(trades_df, initial_capital=initial_capital)
        if m["ftmo_pass"]:
            fold_passes += 1

        if not trades_df.empty:
            tdf = trades_df.copy()
            tdf["fold"] = fold
            combined.append(tdf)

    comb_df = pd.concat(combined, ignore_index=True) if combined else pd.DataFrame()
    return comb_df, fold_passes, len(windows)


def to_sortable(value):
    if value is None:
        return float("inf")
    return float(value)


def candidate_seed(p: Params, salt: int = 0) -> int:
    # Deterministic seed from parameters so ranking and final summary are consistent.
    return (
        p.fast * 1_000_003
        + p.slow * 10_007
        + int(p.stop_loss_pct * 1000) * 503
        + int(p.take_profit_pct * 1000) * 101
        + int(p.risk_pct * 1000) * 17
        + salt
    ) % (2**32 - 1)


def track_c_param_grid() -> list:
    """
    Superset of the shared param_grid, extended with fine-grained intermediate
    risk levels for the best known configuration (EMA 12/20, SL 0.5%, TP 3%).

    The standard grid only has risk in [0.5, 0.75].  At 0.5% the combined OOS
    running drawdown is ~7%, leaving ~3% headroom below the 10% FTMO limit.
    At 0.75% the per-fold drawdown blows out to ~14.6%.  Intermediate risk
    steps (0.52 – 0.65%) may thread the needle: faster pass time while keeping
    MC pass probability above the required threshold.
    """
    candidates = list(param_grid())  # full shared grid (deduplication guard below)
    seen = {(p.fast, p.slow, p.stop_loss_pct, p.take_profit_pct, p.risk_pct) for p in candidates}

    # Fine-grained risk sweep for the proven EMA(12/20) SL=0.5% TP=3% setup.
    # Also included for EMA(12/50) SL=0.5% TP=3% which had the next-best trade count.
    for fast, slow in [(12, 20), (12, 50)]:
        for risk in [0.52, 0.54, 0.55, 0.57, 0.60, 0.625, 0.65]:
            key = (fast, slow, 0.5, 3.0, risk)
            if key not in seen:
                candidates.append(Params(fast, slow, 0.5, 3.0, risk))
                seen.add(key)

    return candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Optimize Track C for time-to-pass under walk-forward OOS constraints."
    )
    parser.add_argument("--train-years", type=float, default=2.0, help="Training window in years.")
    parser.add_argument("--test-days", type=int, default=90, help="OOS test window in days per fold.")
    parser.add_argument("--step-days", type=int, default=90, help="Window shift in days per fold.")
    parser.add_argument(
        "--max-folds",
        type=int,
        default=4,
        help="Maximum OOS folds to evaluate. Increase to backtest beyond 1 year.",
    )
    parser.add_argument(
        "--mc-constraint-pct",
        type=float,
        default=TRACK_C_DEFAULT_MC_CONSTRAINT_PCT,
        help="Minimum Monte Carlo pass probability required for feasibility.",
    )
    parser.add_argument(
        "--preferred-risk-pct",
        type=float,
        default=None,
        help="If set, pick the best feasible candidate that matches this risk percentage.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    np.random.seed(42)

    mc_constraint_pct = float(args.mc_constraint_pct)
    if mc_constraint_pct <= 0 or mc_constraint_pct > 100:
        raise ValueError("--mc-constraint-pct must be in (0, 100].")

    track_root = SCRIPT_DIR.parent
    reports_dir = track_root / "reports"
    images_dir = track_root / "images"

    data_csv = REPO_ROOT / "data" / "XAUUSD_1h_sample.csv"
    df = load_data(data_csv)

    train_bars = int(24 * 365 * args.train_years)
    test_bars = int(24 * args.test_days)
    step_bars = int(24 * args.step_days)
    max_folds = args.max_folds

    if train_bars <= 0 or test_bars <= 0 or step_bars <= 0 or max_folds <= 0:
        raise ValueError("All window parameters must be positive.")

    windows = oos_windows(df, train_bars, test_bars, step_bars, max_folds)
    if not windows:
        raise RuntimeError("No OOS windows generated. Reduce train/test sizes or increase data length.")
    candidates = track_c_param_grid()

    rows = []

    for p in candidates:
        comb_df, fold_passes, fold_count = build_candidate_trades(df, windows, p, initial_capital=INITIAL_CAPITAL)
        metrics = compute_metrics(comb_df, initial_capital=INITIAL_CAPITAL)
        np.random.seed(candidate_seed(p, salt=0))
        paths, mc_pass_prob = monte_carlo_paths(comb_df, initial_capital=INITIAL_CAPITAL, runs=1000)
        tpd = compute_trades_per_day(comb_df)
        timing = step_timing_stats(
            paths,
            initial_capital=INITIAL_CAPITAL,
            trades_per_day=tpd,
            step1_target_pct=STEP1_TARGET_PCT,
            step2_target_pct=STEP2_TARGET_PCT,
        )

        feasible = (
            mc_pass_prob >= mc_constraint_pct
            and timing["step1_avg_trades"] is not None
            and timing["step2_avg_trades"] is not None
        )

        rows.append(
            {
                "fast": p.fast,
                "slow": p.slow,
                "sl_pct": p.stop_loss_pct,
                "tp_pct": p.take_profit_pct,
                "risk_pct": p.risk_pct,
                "fold_passes": fold_passes,
                "fold_count": fold_count,
                "fold_pass_rate_pct": (fold_passes / fold_count) * 100.0 if fold_count else 0.0,
                "oos_trades": metrics["total_trades"],
                "oos_return_pct": metrics["return_pct"],
                "oos_max_dd_pct": metrics["max_drawdown_pct"],
                "oos_worst_daily_loss_pct": metrics["worst_daily_loss_pct"],
                "oos_profit_factor": metrics["profit_factor"],
                "mc_pass_probability_pct": mc_pass_prob,
                "trades_per_day_estimate": tpd,
                "step1_pass_probability_pct": timing["step1_pass_probability_pct"],
                "step2_pass_probability_pct": timing["step2_pass_probability_pct"],
                "step1_avg_trades": timing["step1_avg_trades"],
                "step2_avg_trades": timing["step2_avg_trades"],
                "step1_avg_days": timing["step1_avg_days"],
                "step2_avg_days": timing["step2_avg_days"],
                "feasible_constraint": feasible,
                "sort_step2_avg_trades": to_sortable(timing["step2_avg_trades"]),
                "sort_step1_avg_trades": to_sortable(timing["step1_avg_trades"]),
            }
        )

    res = pd.DataFrame(rows)
    res = res.sort_values(
        [
            "feasible_constraint",
            "sort_step2_avg_trades",
            "sort_step1_avg_trades",
            "mc_pass_probability_pct",
            "oos_return_pct",
        ],
        ascending=[False, True, True, False, False],
    ).reset_index(drop=True)

    feasible_df = res[res["feasible_constraint"] == True].copy()  # noqa: E712
    if feasible_df.empty:
        raise RuntimeError(
            f"No Track C candidate satisfies Monte Carlo pass probability >= {mc_constraint_pct:.1f}%."
        )

    if args.preferred_risk_pct is None:
        top = feasible_df.iloc[0].to_dict()
    else:
        pref = float(args.preferred_risk_pct)
        preferred_df = feasible_df[np.isclose(feasible_df["risk_pct"], pref, atol=1e-9)].copy()
        if preferred_df.empty:
            raise RuntimeError(
                f"No feasible Track C candidate found with risk_pct={pref:.6g}. "
                "Choose one of the feasible risk values in track_c_candidate_rankings.csv."
            )
        top = preferred_df.sort_values(
            [
                "sort_step2_avg_trades",
                "sort_step1_avg_trades",
                "mc_pass_probability_pct",
                "oos_return_pct",
            ],
            ascending=[True, True, False, False],
        ).iloc[0].to_dict()

    top_params = Params(
        fast=int(top["fast"]),
        slow=int(top["slow"]),
        stop_loss_pct=float(top["sl_pct"]),
        take_profit_pct=float(top["tp_pct"]),
        risk_pct=float(top["risk_pct"]),
    )

    top_trades, _, _ = build_candidate_trades(df, windows, top_params, initial_capital=INITIAL_CAPITAL)
    np.random.seed(candidate_seed(top_params, salt=0))
    top_paths, top_mc_pass_prob = monte_carlo_paths(top_trades, initial_capital=INITIAL_CAPITAL, runs=1000)

    if top_mc_pass_prob < mc_constraint_pct:
        raise RuntimeError(
            f"Selected candidate failed final MC>={mc_constraint_pct:.1f}% check. "
            "Increase runs or review candidate seeding/selection settings."
        )
    top_tpd = compute_trades_per_day(top_trades)
    top_timing = step_timing_stats(
        top_paths,
        initial_capital=INITIAL_CAPITAL,
        trades_per_day=top_tpd,
        step1_target_pct=STEP1_TARGET_PCT,
        step2_target_pct=STEP2_TARGET_PCT,
    )

    rankings_csv = reports_dir / "track_c_candidate_rankings.csv"
    best_json = reports_dir / "track_c_best_candidate.json"
    best_txt = reports_dir / "track_c_best_candidate.txt"
    trades_csv = reports_dir / "track_c_best_candidate_oos_trades.csv"

    probable_png = images_dir / "track_c_probable_path.png"
    activity_png = images_dir / "track_c_trade_activity.png"
    mc_png = images_dir / "track_c_monte_carlo.png"

    res.to_csv(rankings_csv, index=False)
    top_trades.to_csv(trades_csv, index=False)

    plot_probable_path(
        top_paths,
        out_path=probable_png,
        initial_capital=INITIAL_CAPITAL,
        timing=top_timing,
        step1_target_pct=STEP1_TARGET_PCT,
        step2_target_pct=STEP2_TARGET_PCT,
    )
    plot_trade_activity(top_trades, out_path=activity_png)
    np.random.seed(42)
    plot_monte_carlo(top_paths, out_path=mc_png)

    summary = {
        "objective": "Minimize average time to pass Step 2 with Monte Carlo pass probability constraint",
        "constraint_mc_pass_probability_pct": mc_constraint_pct,
        "window_config": {
            "train_years": float(args.train_years),
            "test_days": int(args.test_days),
            "step_days": int(args.step_days),
            "max_folds": int(args.max_folds),
            "actual_folds": int(len(windows)),
            "approx_oos_years": float((len(windows) * args.test_days) / 365.0),
        },
        "step1_target_pct": STEP1_TARGET_PCT,
        "step2_target_pct": STEP2_TARGET_PCT,
        "selected": {
            "fast": int(top["fast"]),
            "slow": int(top["slow"]),
            "sl_pct": float(top["sl_pct"]),
            "tp_pct": float(top["tp_pct"]),
            "risk_pct": float(top["risk_pct"]),
        },
        "fold_pass_rate_pct": float(top["fold_pass_rate_pct"]),
        "oos_return_pct": float(top["oos_return_pct"]),
        "oos_max_dd_pct": float(top["oos_max_dd_pct"]),
        "oos_worst_daily_loss_pct": float(top["oos_worst_daily_loss_pct"]),
        "oos_profit_factor": float(top["oos_profit_factor"]),
        "oos_trades": int(top["oos_trades"]),
        "mc_pass_probability_pct": float(top_mc_pass_prob),
        "trades_per_day_estimate": float(top_tpd),
        "mc_step1_pass_probability_pct": float(top_timing["step1_pass_probability_pct"]),
        "mc_step2_pass_probability_pct": float(top_timing["step2_pass_probability_pct"]),
        "mc_step1_avg_trades_to_pass": top_timing["step1_avg_trades"],
        "mc_step2_avg_trades_to_pass": top_timing["step2_avg_trades"],
        "mc_step1_avg_days_to_pass": top_timing["step1_avg_days"],
        "mc_step2_avg_days_to_pass": top_timing["step2_avg_days"],
    }
    best_json.write_text(json.dumps(summary, indent=2))

    lines = [
        "TRACK C - TIME TO PASS OPTIMIZATION",
        "=" * 60,
        f"Objective: {summary['objective']}",
        f"Constraint: MC pass probability >= {summary['constraint_mc_pass_probability_pct']:.1f}%",
        (
            f"Window config: train={summary['window_config']['train_years']:.2f}y, "
            f"test={summary['window_config']['test_days']}d, "
            f"step={summary['window_config']['step_days']}d, "
            f"max_folds={summary['window_config']['max_folds']}, "
            f"actual_folds={summary['window_config']['actual_folds']}, "
            f"approx OOS span={summary['window_config']['approx_oos_years']:.2f}y"
        ),
        f"Selected params: EMA({summary['selected']['fast']}/{summary['selected']['slow']}), "
        f"SL {summary['selected']['sl_pct']}%, TP {summary['selected']['tp_pct']}%, Risk {summary['selected']['risk_pct']}%",
        f"Fold pass rate: {summary['fold_pass_rate_pct']:.2f}%",
        f"OOS return: {summary['oos_return_pct']:.2f}%",
        f"OOS max drawdown: {summary['oos_max_dd_pct']:.2f}%",
        f"OOS worst daily loss: {summary['oos_worst_daily_loss_pct']:.2f}%",
        f"OOS trades: {summary['oos_trades']}",
        f"Monte Carlo pass probability: {summary['mc_pass_probability_pct']:.2f}%",
        f"Estimated trades/day: {summary['trades_per_day_estimate']:.2f}",
        f"Step 1 pass probability (+{summary['step1_target_pct']:.0f}%): {summary['mc_step1_pass_probability_pct']:.2f}%",
        (
            f"Step 1 avg time to pass: {summary['mc_step1_avg_trades_to_pass']:.1f} trades / "
            f"{summary['mc_step1_avg_days_to_pass']:.1f} days"
            if summary["mc_step1_avg_trades_to_pass"] is not None
            else "Step 1 avg time to pass: not reached in simulation"
        ),
        f"Step 2 pass probability (+{summary['step2_target_pct']:.0f}%): {summary['mc_step2_pass_probability_pct']:.2f}%",
        (
            f"Step 2 avg time to pass: {summary['mc_step2_avg_trades_to_pass']:.1f} trades / "
            f"{summary['mc_step2_avg_days_to_pass']:.1f} days"
            if summary["mc_step2_avg_trades_to_pass"] is not None
            else "Step 2 avg time to pass: not reached in simulation"
        ),
    ]
    best_txt.write_text("\n".join(lines))

    print(f"Saved: {rankings_csv}")
    print(f"Saved: {best_json}")
    print(f"Saved: {best_txt}")
    print(f"Saved: {trades_csv}")
    print(f"Saved: {probable_png}")
    print(f"Saved: {activity_png}")
    print(f"Saved: {mc_png}")
    print("---")
    print(lines[4])
    print(lines[-1])


if __name__ == "__main__":
    main()
