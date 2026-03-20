"""
Search for the most FTMO-robust fixed parameter set on walk-forward OOS windows.

Method:
- Use the same rolling windows as walk_forward_ftmo.py.
- For each candidate parameter set, evaluate only on OOS test windows.
- Rank by Monte Carlo pass probability first, then fold pass rate, then OOS return.

This is a robustness screen to pick the highest pass-probability live candidate.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from walk_forward_ftmo import (
    Params,
    compute_metrics,
    load_data,
    monte_carlo_paths,
    param_grid,
    run_segment_backtest,
)


def compute_trades_per_day(trades_df: pd.DataFrame) -> float:
    if trades_df.empty or "exit_ts" not in trades_df.columns:
        return 1.0

    temp = trades_df.copy()
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"])
    temp["exit_date"] = temp["exit_ts"].dt.date
    daily_counts = temp.groupby("exit_date")["pnl"].count()

    if daily_counts.empty:
        return 1.0
    return float(daily_counts.mean())


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
    step1_target_pct: float = 10.0,
    step2_target_pct: float = 15.0,
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

    s1_hits = first_hit_index(paths, step1_equity)
    s2_hits = first_hit_index(paths, step2_equity)

    s1_valid = s1_hits[~np.isnan(s1_hits)]
    s2_valid = s2_hits[~np.isnan(s2_hits)]

    step1_avg_trades = float(np.mean(s1_valid)) if s1_valid.size > 0 else None
    step2_avg_trades = float(np.mean(s2_valid)) if s2_valid.size > 0 else None

    trades_per_day = max(trades_per_day, 1e-9)

    return {
        "step1_pass_probability_pct": float((s1_valid.size / len(paths)) * 100.0),
        "step2_pass_probability_pct": float((s2_valid.size / len(paths)) * 100.0),
        "step1_avg_trades": step1_avg_trades,
        "step2_avg_trades": step2_avg_trades,
        "step1_avg_days": (step1_avg_trades / trades_per_day) if step1_avg_trades is not None else None,
        "step2_avg_days": (step2_avg_trades / trades_per_day) if step2_avg_trades is not None else None,
    }


def plot_total_trades_visual(trades_df: pd.DataFrame, out_path: Path) -> None:
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

    ax1.bar(daily["exit_date"].astype(str), daily["trades"], alpha=0.45, color="#1f77b4", label="Trades per day")
    ax2.plot(daily["exit_date"].astype(str), daily["cum_trades"], color="#111111", linewidth=2.2, label="Cumulative trades")

    total = int(len(trades_df))
    ax2.axhline(total, color="#2ca02c", linestyle="--", linewidth=1.2)
    ax2.text(0.01, 0.96, f"Total OOS trades: {total}", transform=ax2.transAxes, ha="left", va="top")

    ax1.set_title("Best Candidate Trade Activity (OOS)")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Trades per day")
    ax2.set_ylabel("Cumulative trades")
    ax1.tick_params(axis="x", rotation=45)

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
    step1_target_pct: float = 10.0,
    step2_target_pct: float = 15.0,
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

    plt.axhline(step1_equity, linestyle="--", linewidth=1.5, color="#2ca02c", label=f"Step 1 target (+{step1_target_pct:.0f}%)")
    plt.axhline(step2_equity, linestyle="--", linewidth=1.5, color="#ff7f0e", label=f"Step 2 target (+{step2_target_pct:.0f}%)")

    if timing["step1_avg_trades"] is not None:
        s1x = timing["step1_avg_trades"]
        plt.axvline(s1x, color="#2ca02c", linewidth=1.2, alpha=0.9)
        plt.text(
            s1x,
            step1_equity,
            f"  Avg Step 1: {s1x:.1f} trades / {timing['step1_avg_days']:.1f} days",
            color="#2ca02c",
            va="bottom",
        )

    if timing["step2_avg_trades"] is not None:
        s2x = timing["step2_avg_trades"]
        plt.axvline(s2x, color="#ff7f0e", linewidth=1.2, alpha=0.9)
        plt.text(
            s2x,
            step2_equity,
            f"  Avg Step 2: {s2x:.1f} trades / {timing['step2_avg_days']:.1f} days",
            color="#ff7f0e",
            va="bottom",
        )

    plt.title("Best Candidate Probable Path (Monte Carlo OOS)")
    plt.xlabel("Trade #")
    plt.ylabel("Equity ($)")
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def oos_windows(df: pd.DataFrame, train_bars: int, test_bars: int, step_bars: int, max_folds: int):
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find Track B best fixed parameters on walk-forward OOS windows."
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    track_root = Path(__file__).resolve().parent.parent
    reports_dir = track_root / "reports"
    images_dir = track_root / "images"

    data_csv = repo_root / "data" / "XAUUSD_1h_sample.csv"
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
    candidates = param_grid()

    rows = []

    for p in candidates:
        fold_passes = 0
        combined = []

        for fold, test_start, test_end in windows:
            test_df = df.iloc[test_start:test_end].copy()
            trades_df, _ = run_segment_backtest(test_df, p, initial_capital=10000.0)
            m = compute_metrics(trades_df, initial_capital=10000.0)
            if m["ftmo_pass"]:
                fold_passes += 1
            if not trades_df.empty:
                t = trades_df.copy()
                t["fold"] = fold
                combined.append(t)

        comb_df = pd.concat(combined, ignore_index=True) if combined else pd.DataFrame()
        comb_metrics = compute_metrics(comb_df, initial_capital=10000.0)

        _, mc_pass_prob = monte_carlo_paths(comb_df, initial_capital=10000.0, runs=200)

        rows.append(
            {
                "fast": p.fast,
                "slow": p.slow,
                "sl_pct": p.stop_loss_pct,
                "tp_pct": p.take_profit_pct,
                "risk_pct": p.risk_pct,
                "fold_passes": fold_passes,
                "fold_count": len(windows),
                "fold_pass_rate_pct": (fold_passes / len(windows)) * 100.0 if windows else 0.0,
                "mc_pass_probability_pct": mc_pass_prob,
                "oos_return_pct": comb_metrics["return_pct"],
                "oos_max_dd_pct": comb_metrics["max_drawdown_pct"],
                "oos_worst_daily_loss_pct": comb_metrics["worst_daily_loss_pct"],
                "oos_profit_factor": comb_metrics["profit_factor"],
                "oos_trades": comb_metrics["total_trades"],
            }
        )

    res = pd.DataFrame(rows)
    res = res.sort_values(
        ["mc_pass_probability_pct", "fold_pass_rate_pct", "oos_return_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    top = res.iloc[0].to_dict()

    # Monte Carlo on top candidate OOS combined trades
    top_params = Params(
        fast=int(top["fast"]),
        slow=int(top["slow"]),
        stop_loss_pct=float(top["sl_pct"]),
        take_profit_pct=float(top["tp_pct"]),
        risk_pct=float(top["risk_pct"]),
    )

    combined_top = []
    for fold, test_start, test_end in windows:
        test_df = df.iloc[test_start:test_end].copy()
        tdf, _ = run_segment_backtest(test_df, top_params, initial_capital=10000.0)
        if not tdf.empty:
            tdf = tdf.copy()
            tdf["fold"] = fold
            combined_top.append(tdf)
    top_trades = pd.concat(combined_top, ignore_index=True) if combined_top else pd.DataFrame()

    _, mc_pass_prob = monte_carlo_paths(top_trades, initial_capital=10000.0, runs=1000)

    # Save best-candidate OOS trades for inspection.
    top_trades_path = reports_dir / "wfv_best_candidate_oos_trades.csv"
    top_trades.to_csv(top_trades_path, index=False)

    # Save Monte Carlo paths chart for the best candidate.
    paths, _ = monte_carlo_paths(top_trades, initial_capital=10000.0, runs=1000)
    mc_png = images_dir / "wfv_best_candidate_monte_carlo.png"
    if paths.size > 0:
        plt.figure(figsize=(14, 6))
        to_plot = min(250, paths.shape[0])
        idx = np.random.choice(paths.shape[0], to_plot, replace=False)
        for i in idx:
            plt.plot(paths[i], alpha=0.08, linewidth=0.8, color="#1f77b4")
        plt.plot(paths.mean(axis=0), color="#111111", linewidth=2.0, label="Mean path")
        plt.title("Best Candidate Monte Carlo Paths")
        plt.xlabel("Trade #")
        plt.ylabel("Equity ($)")
        plt.legend()
        plt.tight_layout()
        plt.savefig(mc_png, dpi=200)
        plt.close()

    trades_per_day = compute_trades_per_day(top_trades)
    timing = step_timing_stats(
        paths,
        initial_capital=10000.0,
        trades_per_day=trades_per_day,
        step1_target_pct=10.0,
        step2_target_pct=15.0,
    )

    probable_path_png = images_dir / "wfv_best_candidate_probable_path.png"
    plot_probable_path(
        paths,
        out_path=probable_path_png,
        initial_capital=10000.0,
        timing=timing,
        step1_target_pct=10.0,
        step2_target_pct=15.0,
    )

    trade_activity_png = images_dir / "wfv_best_candidate_trade_activity.png"
    plot_total_trades_visual(top_trades, trade_activity_png)

    # Save OOS equity chart for the best candidate.
    eq_png = images_dir / "wfv_best_candidate_oos_equity.png"
    if not top_trades.empty:
        eq = [10000.0]
        cur = 10000.0
        for p in top_trades["pnl"].to_numpy(dtype=float):
            cur += p
            eq.append(cur)
        plt.figure(figsize=(14, 6))
        plt.plot(eq, linewidth=2.0, color="#2ca02c")
        plt.title("Best Candidate OOS Equity")
        plt.xlabel("Trade #")
        plt.ylabel("Equity ($)")
        plt.tight_layout()
        plt.savefig(eq_png, dpi=200)
        plt.close()

    summary = {
        "selected": {
            "fast": int(top["fast"]),
            "slow": int(top["slow"]),
            "sl_pct": float(top["sl_pct"]),
            "tp_pct": float(top["tp_pct"]),
            "risk_pct": float(top["risk_pct"]),
        },
        "selection_basis": "Max Monte Carlo pass probability, then fold pass rate, then OOS return",
        "fold_pass_rate_pct": float(top["fold_pass_rate_pct"]),
        "oos_return_pct": float(top["oos_return_pct"]),
        "oos_max_dd_pct": float(top["oos_max_dd_pct"]),
        "oos_worst_daily_loss_pct": float(top["oos_worst_daily_loss_pct"]),
        "oos_profit_factor": float(top["oos_profit_factor"]),
        "oos_trades": int(top["oos_trades"]),
        "mc_pass_probability_pct": float(mc_pass_prob),
        "step1_target_pct": 10.0,
        "step2_target_pct": 15.0,
        "trades_per_day_estimate": float(trades_per_day),
        "mc_step1_pass_probability_pct": float(timing["step1_pass_probability_pct"]),
        "mc_step2_pass_probability_pct": float(timing["step2_pass_probability_pct"]),
        "mc_step1_avg_trades_to_pass": timing["step1_avg_trades"],
        "mc_step2_avg_trades_to_pass": timing["step2_avg_trades"],
        "mc_step1_avg_days_to_pass": timing["step1_avg_days"],
        "mc_step2_avg_days_to_pass": timing["step2_avg_days"],
        "window_config": {
            "train_years": float(args.train_years),
            "test_days": int(args.test_days),
            "step_days": int(args.step_days),
            "max_folds": int(args.max_folds),
            "actual_folds": int(len(windows)),
            "approx_oos_years": float((len(windows) * args.test_days) / 365.0),
        },
    }

    res_path = reports_dir / "wfv_candidate_rankings.csv"
    sum_json = reports_dir / "wfv_best_candidate.json"
    sum_txt = reports_dir / "wfv_best_candidate.txt"

    res.to_csv(res_path, index=False)
    sum_json.write_text(json.dumps(summary, indent=2))

    lines = [
        "WALK-FORWARD BEST CANDIDATE",
        "=" * 60,
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
        f"OOS profit factor: {summary['oos_profit_factor']:.2f}",
        f"OOS trades: {summary['oos_trades']}",
        f"Monte Carlo pass probability: {summary['mc_pass_probability_pct']:.2f}%",
        f"Estimated trades/day: {summary['trades_per_day_estimate']:.2f}",
        f"Step 1 pass probability (+{summary['step1_target_pct']:.0f}%): {summary['mc_step1_pass_probability_pct']:.2f}%",
        f"Step 1 avg time to pass: {summary['mc_step1_avg_trades_to_pass']:.1f} trades / {summary['mc_step1_avg_days_to_pass']:.1f} days"
        if summary["mc_step1_avg_trades_to_pass"] is not None
        else "Step 1 avg time to pass: not reached in simulation",
        f"Step 2 pass probability (+{summary['step2_target_pct']:.0f}%): {summary['mc_step2_pass_probability_pct']:.2f}%",
        f"Step 2 avg time to pass: {summary['mc_step2_avg_trades_to_pass']:.1f} trades / {summary['mc_step2_avg_days_to_pass']:.1f} days"
        if summary["mc_step2_avg_trades_to_pass"] is not None
        else "Step 2 avg time to pass: not reached in simulation",
    ]
    sum_txt.write_text("\n".join(lines))

    print(f"Saved: {res_path}")
    print(f"Saved: {sum_json}")
    print(f"Saved: {sum_txt}")
    print(f"Saved: {top_trades_path}")
    print(f"Saved: {mc_png}")
    print(f"Saved: {eq_png}")
    print(f"Saved: {probable_path_png}")
    print(f"Saved: {trade_activity_png}")
    print("---")
    print("Top selection:")
    print(lines[2])
    print(lines[3])


if __name__ == "__main__":
    main()
