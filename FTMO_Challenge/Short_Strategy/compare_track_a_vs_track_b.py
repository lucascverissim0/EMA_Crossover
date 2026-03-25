"""
Compare Track A Short EMA vs Track B Short ML outputs on the same OOS horizon.

Inputs:
- Track A summary/trades from Track_A_Short_EMA
- Track B summary/trades from Track_B_Short_ML

Outputs:
- FTMO_Challenge/Short_Strategy/images/track_a_vs_track_b_equity.png
- FTMO_Challenge/Short_Strategy/images/track_a_vs_track_b_metrics.png
- FTMO_Challenge/Short_Strategy/reports/track_a_vs_track_b_summary.json
- FTMO_Challenge/Short_Strategy/reports/track_a_vs_track_b_summary.txt
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text())


def load_trades(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    if "exit_ts" in df.columns:
        df["exit_ts"] = pd.to_datetime(df["exit_ts"], errors="coerce")
    return df


def equity_curve(trades_df: pd.DataFrame, initial_capital: float = 10000.0) -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame(columns=["exit_ts", "equity"])
    temp = trades_df.copy().sort_values("exit_ts")
    temp["equity"] = initial_capital + temp["pnl"].astype(float).cumsum()
    return temp[["exit_ts", "equity"]].dropna()


def plot_equity(track_a_eq: pd.DataFrame, track_b_eq: pd.DataFrame, out_path: Path) -> None:
    plt.figure(figsize=(14, 6))

    if not track_a_eq.empty:
        plt.plot(track_a_eq["exit_ts"], track_a_eq["equity"], label="Track A", color="#0f766e", linewidth=2.0)
    if not track_b_eq.empty:
        plt.plot(track_b_eq["exit_ts"], track_b_eq["equity"], label="Track B ML", color="#2563eb", linewidth=2.0)

    plt.axhline(10000.0, color="#16a34a", linestyle="--", linewidth=1.2, label="Initial capital")
    plt.title("Track A vs Track B ML - OOS Equity")
    plt.xlabel("Timestamp")
    plt.ylabel("Equity ($)")
    plt.grid(alpha=0.2)
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()


def plot_metrics(track_a_summary: Dict, track_b_summary: Dict, out_path: Path) -> None:
    labels = ["Sharpe", "Return %", "Max DD %", "MC Profit %"]

    a_vals = [
        float(track_a_summary.get("oos_sharpe_daily_annualized", 0.0)),
        float(track_a_summary.get("oos_return_pct", 0.0)),
        float(track_a_summary.get("oos_max_drawdown_pct", 0.0)),
        float(track_a_summary.get("mc_profitability_probability_pct", 0.0)),
    ]
    b_vals = [
        float(track_b_summary.get("oos_sharpe_daily_annualized", 0.0)),
        float(track_b_summary.get("oos_return_pct", 0.0)),
        float(track_b_summary.get("oos_max_drawdown_pct", 0.0)),
        float(track_b_summary.get("mc_profitability_probability_pct", 0.0)),
    ]

    x = np.arange(len(labels))
    w = 0.36

    plt.figure(figsize=(12, 6))
    plt.bar(x - w / 2, a_vals, width=w, label="Track A", color="#0f766e", alpha=0.9)
    plt.bar(x + w / 2, b_vals, width=w, label="Track B ML", color="#2563eb", alpha=0.9)
    plt.xticks(x, labels)
    plt.title("Track A vs Track B ML - Key Metrics")
    plt.ylabel("Value")
    plt.grid(axis="y", alpha=0.2)
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()


def evaluate_ftmo_rules(
    trades_df: pd.DataFrame,
    target_profit_pct: float = 10.0,
    max_total_dd_pct: float = 10.0,
    max_daily_dd_pct: float = 3.0,
    initial_capital: float = 10000.0,
) -> Dict[str, float | bool | None]:
    if trades_df.empty:
        return {
            "pass": False,
            "passed_in_days": None,
            "failure_reason": "No trades",
        }

    temp = trades_df.copy().sort_values("exit_ts")
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"], errors="coerce")
    temp = temp.dropna(subset=["exit_ts", "pnl"])
    if temp.empty:
        return {
            "pass": False,
            "passed_in_days": None,
            "failure_reason": "No valid timestamps/PnL",
        }

    target_equity = initial_capital * (1.0 + target_profit_pct / 100.0)
    total_dd_floor = initial_capital * (1.0 - max_total_dd_pct / 100.0)

    start_date = temp["exit_ts"].iloc[0].date()
    equity = initial_capital
    current_day = None
    day_start_equity = equity

    for _, row in temp.iterrows():
        ts = row["exit_ts"]
        pnl = float(row["pnl"])
        trade_day = ts.date()

        if current_day is None or trade_day != current_day:
            current_day = trade_day
            day_start_equity = equity

        equity += pnl

        if equity < total_dd_floor:
            return {
                "pass": False,
                "passed_in_days": None,
                "failure_reason": "Total drawdown breach",
            }

        daily_floor = day_start_equity * (1.0 - max_daily_dd_pct / 100.0)
        if equity < daily_floor:
            return {
                "pass": False,
                "passed_in_days": None,
                "failure_reason": "Daily drawdown breach",
            }

        if equity >= target_equity:
            days = (trade_day - start_date).days + 1
            return {
                "pass": True,
                "passed_in_days": int(days),
                "failure_reason": None,
            }

    return {
        "pass": False,
        "passed_in_days": None,
        "failure_reason": "Target not reached",
    }


def ftmo_monte_carlo_probability(
    trades_df: pd.DataFrame,
    n_paths: int = 2000,
    seed: int = 42,
    target_profit_pct: float = 10.0,
    max_total_dd_pct: float = 10.0,
    max_daily_dd_pct: float = 3.0,
    initial_capital: float = 10000.0,
) -> Dict[str, float | int | None]:
    if trades_df.empty:
        return {
            "paths": n_paths,
            "pass_probability_pct": 0.0,
            "median_days_to_pass": None,
            "p10_days_to_pass": None,
            "p90_days_to_pass": None,
        }

    temp = trades_df.copy().sort_values("exit_ts")
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"], errors="coerce")
    temp = temp.dropna(subset=["exit_ts", "pnl"]).reset_index(drop=True)
    if temp.empty:
        return {
            "paths": n_paths,
            "pass_probability_pct": 0.0,
            "median_days_to_pass": None,
            "p10_days_to_pass": None,
            "p90_days_to_pass": None,
        }

    target_equity = initial_capital * (1.0 + target_profit_pct / 100.0)
    total_dd_floor = initial_capital * (1.0 - max_total_dd_pct / 100.0)
    trade_dates = temp["exit_ts"].dt.date.to_list()
    pnls = temp["pnl"].astype(float).to_numpy()

    start_date = trade_dates[0]
    rng = np.random.default_rng(seed)
    pass_days: list[int] = []

    for _ in range(n_paths):
        sampled = rng.choice(pnls, size=len(pnls), replace=True)
        equity = initial_capital
        current_day = None
        day_start_equity = equity
        passed = False

        for idx, pnl in enumerate(sampled):
            trade_day = trade_dates[idx]
            if current_day is None or trade_day != current_day:
                current_day = trade_day
                day_start_equity = equity

            equity += float(pnl)

            if equity < total_dd_floor:
                break

            daily_floor = day_start_equity * (1.0 - max_daily_dd_pct / 100.0)
            if equity < daily_floor:
                break

            if equity >= target_equity:
                pass_days.append((trade_day - start_date).days + 1)
                passed = True
                break

        if not passed:
            continue

    pass_prob = (len(pass_days) / n_paths) * 100.0 if n_paths > 0 else 0.0

    if pass_days:
        return {
            "paths": n_paths,
            "pass_probability_pct": float(pass_prob),
            "median_days_to_pass": int(np.median(pass_days)),
            "p10_days_to_pass": int(np.percentile(pass_days, 10)),
            "p90_days_to_pass": int(np.percentile(pass_days, 90)),
        }

    return {
        "paths": n_paths,
        "pass_probability_pct": float(pass_prob),
        "median_days_to_pass": None,
        "p10_days_to_pass": None,
        "p90_days_to_pass": None,
    }


def plot_ftmo_comparison(track_a_ftmo: Dict, track_b_ftmo: Dict, out_path: Path) -> None:
    labels = ["Pass Probability %", "Median Days To Pass"]
    a_days = track_a_ftmo["monte_carlo"].get("median_days_to_pass")
    b_days = track_b_ftmo["monte_carlo"].get("median_days_to_pass")

    a_vals = [
        float(track_a_ftmo["monte_carlo"].get("pass_probability_pct", 0.0)),
        float(a_days) if a_days is not None else 0.0,
    ]
    b_vals = [
        float(track_b_ftmo["monte_carlo"].get("pass_probability_pct", 0.0)),
        float(b_days) if b_days is not None else 0.0,
    ]

    x = np.arange(len(labels))
    w = 0.36

    plt.figure(figsize=(12, 6))
    plt.bar(x - w / 2, a_vals, width=w, label="Track A", color="#0f766e", alpha=0.9)
    plt.bar(x + w / 2, b_vals, width=w, label="Track B ML", color="#2563eb", alpha=0.9)
    plt.xticks(x, labels)
    plt.title("FTMO Comparison (Target 10%, Max Total DD 10%, Max Daily DD 3%)")
    plt.ylabel("Value")
    plt.grid(axis="y", alpha=0.2)
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()


def main() -> None:
    root = Path(__file__).resolve().parent
    reports_dir = root / "reports"
    images_dir = root / "images"
    reports_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    track_a_summary_path = root / "Track_A_Short_EMA" / "reports" / "short_wfv_summary.json"
    track_b_summary_path = root / "Track_B_Short_ML" / "reports" / "track_b_short_ml_summary.json"
    track_a_trades_path = root / "Track_A_Short_EMA" / "reports" / "short_wfv_oos_trades.csv"
    track_b_trades_path = root / "Track_B_Short_ML" / "reports" / "track_b_short_ml_oos_trades.csv"

    if not track_a_summary_path.exists():
        raise FileNotFoundError(f"Missing Track A summary: {track_a_summary_path}")
    if not track_b_summary_path.exists():
        raise FileNotFoundError(f"Missing Track B summary: {track_b_summary_path}")

    track_a_summary = load_json(track_a_summary_path)
    track_b_summary = load_json(track_b_summary_path)

    track_a_trades = load_trades(track_a_trades_path)
    track_b_trades = load_trades(track_b_trades_path)

    track_a_eq = equity_curve(track_a_trades)
    track_b_eq = equity_curve(track_b_trades)

    eq_png = images_dir / "track_a_vs_track_b_equity.png"
    metrics_png = images_dir / "track_a_vs_track_b_metrics.png"
    ftmo_png = images_dir / "track_a_vs_track_b_ftmo.png"

    plot_equity(track_a_eq, track_b_eq, eq_png)
    plot_metrics(track_a_summary, track_b_summary, metrics_png)

    ftmo_params = {
        "target_profit_pct": 10.0,
        "max_total_dd_pct": 10.0,
        "max_daily_dd_pct": 3.0,
        "initial_capital": 10000.0,
    }
    track_a_ftmo_realized = evaluate_ftmo_rules(track_a_trades, **ftmo_params)
    track_b_ftmo_realized = evaluate_ftmo_rules(track_b_trades, **ftmo_params)
    track_a_ftmo_mc = ftmo_monte_carlo_probability(track_a_trades, n_paths=2000, seed=42, **ftmo_params)
    track_b_ftmo_mc = ftmo_monte_carlo_probability(track_b_trades, n_paths=2000, seed=42, **ftmo_params)

    track_a_ftmo = {
        "realized": track_a_ftmo_realized,
        "monte_carlo": track_a_ftmo_mc,
    }
    track_b_ftmo = {
        "realized": track_b_ftmo_realized,
        "monte_carlo": track_b_ftmo_mc,
    }

    plot_ftmo_comparison(track_a_ftmo, track_b_ftmo, ftmo_png)

    comparison = {
        "track_a": {
            "oos_sharpe_daily_annualized": track_a_summary.get("oos_sharpe_daily_annualized", 0.0),
            "oos_return_pct": track_a_summary.get("oos_return_pct", 0.0),
            "oos_max_drawdown_pct": track_a_summary.get("oos_max_drawdown_pct", 0.0),
            "mc_profitability_probability_pct": track_a_summary.get("mc_profitability_probability_pct", 0.0),
            "oos_trades": track_a_summary.get("oos_trades", 0),
        },
        "track_b_ml": {
            "oos_sharpe_daily_annualized": track_b_summary.get("oos_sharpe_daily_annualized", 0.0),
            "oos_return_pct": track_b_summary.get("oos_return_pct", 0.0),
            "oos_max_drawdown_pct": track_b_summary.get("oos_max_drawdown_pct", 0.0),
            "mc_profitability_probability_pct": track_b_summary.get("mc_profitability_probability_pct", 0.0),
            "oos_trades": track_b_summary.get("oos_trades", 0),
        },
        "ftmo_constraints": {
            "target_profit_pct": 10.0,
            "max_total_drawdown_pct": 10.0,
            "max_daily_drawdown_pct": 3.0,
            "floating_included_note": "Approximated at trade-resolution from exit-sequenced equity; intrabar ticks are not available.",
        },
        "ftmo_results": {
            "track_a": track_a_ftmo,
            "track_b_ml": track_b_ftmo,
        },
    }

    comparison["winner_by_sharpe"] = (
        "Track B ML"
        if float(comparison["track_b_ml"]["oos_sharpe_daily_annualized"]) > float(comparison["track_a"]["oos_sharpe_daily_annualized"])
        else "Track A"
    )

    (reports_dir / "track_a_vs_track_b_summary.json").write_text(json.dumps(comparison, indent=2))

    lines = [
        "Track A vs Track B ML Comparison",
        "",
        f"Winner by Sharpe: {comparison['winner_by_sharpe']}",
        "",
        "Track A:",
        f"  Sharpe: {comparison['track_a']['oos_sharpe_daily_annualized']:.3f}",
        f"  Return %: {comparison['track_a']['oos_return_pct']:.2f}",
        f"  Max DD %: {comparison['track_a']['oos_max_drawdown_pct']:.2f}",
        f"  MC Profitability %: {comparison['track_a']['mc_profitability_probability_pct']:.2f}",
        f"  OOS trades: {comparison['track_a']['oos_trades']}",
        f"  FTMO realized pass: {'YES' if comparison['ftmo_results']['track_a']['realized']['pass'] else 'NO'}",
        f"  FTMO realized days to pass: {comparison['ftmo_results']['track_a']['realized']['passed_in_days']}",
        f"  FTMO MC pass probability %: {comparison['ftmo_results']['track_a']['monte_carlo']['pass_probability_pct']:.2f}",
        f"  FTMO MC median days to pass: {comparison['ftmo_results']['track_a']['monte_carlo']['median_days_to_pass']}",
        "",
        "Track B ML:",
        f"  Sharpe: {comparison['track_b_ml']['oos_sharpe_daily_annualized']:.3f}",
        f"  Return %: {comparison['track_b_ml']['oos_return_pct']:.2f}",
        f"  Max DD %: {comparison['track_b_ml']['oos_max_drawdown_pct']:.2f}",
        f"  MC Profitability %: {comparison['track_b_ml']['mc_profitability_probability_pct']:.2f}",
        f"  OOS trades: {comparison['track_b_ml']['oos_trades']}",
        f"  FTMO realized pass: {'YES' if comparison['ftmo_results']['track_b_ml']['realized']['pass'] else 'NO'}",
        f"  FTMO realized days to pass: {comparison['ftmo_results']['track_b_ml']['realized']['passed_in_days']}",
        f"  FTMO MC pass probability %: {comparison['ftmo_results']['track_b_ml']['monte_carlo']['pass_probability_pct']:.2f}",
        f"  FTMO MC median days to pass: {comparison['ftmo_results']['track_b_ml']['monte_carlo']['median_days_to_pass']}",
        "",
        "FTMO constraints used:",
        "  Target profit: 10%",
        "  Max total drawdown: 10%",
        "  Max daily drawdown: 3%",
        "  Floating included approximation: trade-resolution only (no intrabar ticks)",
    ]
    (reports_dir / "track_a_vs_track_b_summary.txt").write_text("\n".join(lines))

    print("Saved images:")
    print(f"- {eq_png}")
    print(f"- {metrics_png}")
    print(f"- {ftmo_png}")
    print("Saved reports:")
    print(f"- {reports_dir / 'track_a_vs_track_b_summary.json'}")
    print(f"- {reports_dir / 'track_a_vs_track_b_summary.txt'}")


if __name__ == "__main__":
    main()
