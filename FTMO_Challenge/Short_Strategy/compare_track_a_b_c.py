"""
Compare Track A, Track B, and Track C short strategy outputs.

Outputs:
- images/track_a_b_c_equity.png
- images/track_a_b_c_metrics.png
- images/track_a_b_c_ftmo.png
- reports/track_a_b_c_summary.json
- reports/track_a_b_c_summary.txt
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

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


def apply_risk_multiplier(trades_df: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    if trades_df.empty:
        return trades_df
    out = trades_df.copy()
    out["pnl"] = out["pnl"].astype(float) * float(multiplier)
    return out


def summarize_trades(trades_df: pd.DataFrame, initial_capital: float = 10000.0) -> Dict:
    if trades_df.empty:
        return {
            "oos_sharpe_daily_annualized": 0.0,
            "oos_return_pct": 0.0,
            "oos_max_drawdown_pct": 0.0,
            "mc_profitability_probability_pct": 0.0,
            "oos_trades": 0,
        }

    temp = trades_df.copy().sort_values("exit_ts")
    pnl = temp["pnl"].astype(float)
    equity = initial_capital + pnl.cumsum()
    peak = equity.cummax()
    dd_pct = np.where(peak > 0, ((peak - equity) / peak) * 100.0, 0.0)

    daily = temp.copy()
    daily["date"] = pd.to_datetime(daily["exit_ts"]).dt.date
    daily_pnl = daily.groupby("date", as_index=False)["pnl"].sum().sort_values("date")
    daily_eq = initial_capital + daily_pnl["pnl"].cumsum()
    daily_ret = daily_eq.pct_change().dropna()
    if daily_ret.empty or float(daily_ret.std()) == 0.0:
        sharpe = 0.0
    else:
        sharpe = float((daily_ret.mean() / daily_ret.std()) * np.sqrt(252.0))

    return {
        "oos_sharpe_daily_annualized": sharpe,
        "oos_return_pct": float(((equity.iloc[-1] / initial_capital) - 1.0) * 100.0),
        "oos_max_drawdown_pct": float(np.max(dd_pct)) if len(dd_pct) > 0 else 0.0,
        "mc_profitability_probability_pct": 0.0,
        "oos_trades": int(len(temp)),
    }


def evaluate_ftmo_rules(trades_df: pd.DataFrame, target_profit_pct: float = 10.0, max_total_dd_pct: float = 10.0, max_daily_dd_pct: float = 3.0, initial_capital: float = 10000.0):
    if trades_df.empty:
        return {"pass": False, "passed_in_days": None, "failure_reason": "No trades"}

    temp = trades_df.copy().sort_values("exit_ts")
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"], errors="coerce")
    temp = temp.dropna(subset=["exit_ts", "pnl"])
    if temp.empty:
        return {"pass": False, "passed_in_days": None, "failure_reason": "No valid timestamps/PnL"}

    target = initial_capital * (1.0 + target_profit_pct / 100.0)
    floor_total = initial_capital * (1.0 - max_total_dd_pct / 100.0)

    start_date = temp["exit_ts"].iloc[0].date()
    equity = initial_capital
    day = None
    day_start = equity

    for _, row in temp.iterrows():
        d = pd.to_datetime(row["exit_ts"]).date()
        if day is None or d != day:
            day = d
            day_start = equity

        equity += float(row["pnl"])
        if equity < floor_total:
            return {"pass": False, "passed_in_days": None, "failure_reason": "Total drawdown breach"}
        if equity < day_start * (1.0 - max_daily_dd_pct / 100.0):
            return {"pass": False, "passed_in_days": None, "failure_reason": "Daily drawdown breach"}
        if equity >= target:
            return {"pass": True, "passed_in_days": int((d - start_date).days + 1), "failure_reason": None}

    return {"pass": False, "passed_in_days": None, "failure_reason": "Target not reached"}


def ftmo_monte_carlo_probability(trades_df: pd.DataFrame, n_paths: int = 2000, seed: int = 42, target_profit_pct: float = 10.0, max_total_dd_pct: float = 10.0, max_daily_dd_pct: float = 3.0, initial_capital: float = 10000.0):
    if trades_df.empty:
        return {"paths": n_paths, "pass_probability_pct": 0.0, "median_days_to_pass": None, "p10_days_to_pass": None, "p90_days_to_pass": None}

    temp = trades_df.copy().sort_values("exit_ts")
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"], errors="coerce")
    temp = temp.dropna(subset=["exit_ts", "pnl"]).reset_index(drop=True)
    if temp.empty:
        return {"paths": n_paths, "pass_probability_pct": 0.0, "median_days_to_pass": None, "p10_days_to_pass": None, "p90_days_to_pass": None}

    target = initial_capital * (1.0 + target_profit_pct / 100.0)
    floor_total = initial_capital * (1.0 - max_total_dd_pct / 100.0)
    dates = temp["exit_ts"].dt.date.to_list()
    pnls = temp["pnl"].astype(float).to_numpy()
    start_date = dates[0]

    rng = np.random.default_rng(seed)
    pass_days = []

    for _ in range(n_paths):
        sample = rng.choice(pnls, size=len(pnls), replace=True)
        equity = initial_capital
        day = None
        day_start = equity
        passed = False

        for i, pnl in enumerate(sample):
            d = dates[i]
            if day is None or d != day:
                day = d
                day_start = equity
            equity += float(pnl)

            if equity < floor_total:
                break
            if equity < day_start * (1.0 - max_daily_dd_pct / 100.0):
                break
            if equity >= target:
                pass_days.append((d - start_date).days + 1)
                passed = True
                break

        if not passed:
            continue

    prob = (len(pass_days) / n_paths) * 100.0 if n_paths > 0 else 0.0
    if pass_days:
        return {
            "paths": n_paths,
            "pass_probability_pct": float(prob),
            "median_days_to_pass": int(np.median(pass_days)),
            "p10_days_to_pass": int(np.percentile(pass_days, 10)),
            "p90_days_to_pass": int(np.percentile(pass_days, 90)),
        }
    return {"paths": n_paths, "pass_probability_pct": float(prob), "median_days_to_pass": None, "p10_days_to_pass": None, "p90_days_to_pass": None}


def plot_equity(eq_a: pd.DataFrame, eq_b: pd.DataFrame, eq_c: pd.DataFrame, out_path: Path):
    plt.figure(figsize=(14, 6))
    if not eq_a.empty:
        plt.plot(eq_a["exit_ts"], eq_a["equity"], label="Track A", color="#0f766e", linewidth=2.0)
    if not eq_b.empty:
        plt.plot(eq_b["exit_ts"], eq_b["equity"], label="Track B ML", color="#2563eb", linewidth=2.0)
    if not eq_c.empty:
        plt.plot(eq_c["exit_ts"], eq_c["equity"], label="Track C FTMO", color="#dc2626", linewidth=2.0)
    plt.axhline(10000.0, color="#16a34a", linestyle="--", linewidth=1.2, label="Initial capital")
    plt.title("Track A/B/C - OOS Equity")
    plt.xlabel("Timestamp")
    plt.ylabel("Equity ($)")
    plt.grid(alpha=0.2)
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()


def plot_metrics(sum_a: Dict, sum_b: Dict, sum_c: Dict, out_path: Path):
    labels = ["Sharpe", "Return %", "Max DD %", "MC Profit %"]
    a = [float(sum_a.get("oos_sharpe_daily_annualized", 0.0)), float(sum_a.get("oos_return_pct", 0.0)), float(sum_a.get("oos_max_drawdown_pct", 0.0)), float(sum_a.get("mc_profitability_probability_pct", 0.0))]
    b = [float(sum_b.get("oos_sharpe_daily_annualized", 0.0)), float(sum_b.get("oos_return_pct", 0.0)), float(sum_b.get("oos_max_drawdown_pct", 0.0)), float(sum_b.get("mc_profitability_probability_pct", 0.0))]
    c = [float(sum_c.get("oos_sharpe_daily_annualized", 0.0)), float(sum_c.get("oos_return_pct", 0.0)), float(sum_c.get("oos_max_drawdown_pct", 0.0)), float(sum_c.get("mc_profitability_probability_pct", 0.0))]

    x = np.arange(len(labels))
    w = 0.26
    plt.figure(figsize=(13, 6))
    plt.bar(x - w, a, width=w, label="Track A", color="#0f766e", alpha=0.9)
    plt.bar(x, b, width=w, label="Track B ML", color="#2563eb", alpha=0.9)
    plt.bar(x + w, c, width=w, label="Track C FTMO", color="#dc2626", alpha=0.9)
    plt.xticks(x, labels)
    plt.title("Track A/B/C - Key Metrics")
    plt.ylabel("Value")
    plt.grid(axis="y", alpha=0.2)
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()


def plot_ftmo(ftmo_a: Dict, ftmo_b: Dict, ftmo_c: Dict, out_path: Path):
    labels = ["Pass Probability %", "Median Days To Pass"]
    def vals(ftmo):
        m = ftmo["monte_carlo"]
        return [float(m.get("pass_probability_pct", 0.0)), float(m.get("median_days_to_pass") or 0.0)]

    a, b, c = vals(ftmo_a), vals(ftmo_b), vals(ftmo_c)
    x = np.arange(len(labels))
    w = 0.26
    plt.figure(figsize=(13, 6))
    plt.bar(x - w, a, width=w, label="Track A", color="#0f766e", alpha=0.9)
    plt.bar(x, b, width=w, label="Track B ML", color="#2563eb", alpha=0.9)
    plt.bar(x + w, c, width=w, label="Track C FTMO", color="#dc2626", alpha=0.9)
    plt.xticks(x, labels)
    plt.title("FTMO Comparison A/B/C (Target 10%, Max Total DD 10%, Max Daily DD 3%)")
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

    a_sum = load_json(root / "Track_A_Short_EMA" / "reports" / "short_wfv_summary.json")
    b_sum = load_json(root / "Track_B_Short_ML" / "reports" / "track_b_short_ml_summary.json")
    c_sum = load_json(root / "Track_C_Short_FTMO" / "reports" / "track_c_short_ftmo_summary.json")

    # Try extended summary first (faster path), fallback to original
    c_balance_summary_path = root / "Track_C_Short_FTMO" / "reports" / "track_c_ftmo_balance_extended_summary.json"
    if not c_balance_summary_path.exists():
        c_balance_summary_path = root / "Track_C_Short_FTMO" / "reports" / "track_c_ftmo_balance_summary.json"
    c_balance_summary = load_json(c_balance_summary_path) if c_balance_summary_path.exists() else {}
    # Use fastest_with_80_pct_pass if available (from extended sweep), otherwise best_balance
    c_best_mult = float(c_balance_summary.get("fastest_with_80_pct_pass", c_balance_summary.get("best_balance", {})).get("risk_multiplier", 1.0))

    a_trades = load_trades(root / "Track_A_Short_EMA" / "reports" / "short_wfv_oos_trades.csv")
    b_trades = load_trades(root / "Track_B_Short_ML" / "reports" / "track_b_short_ml_oos_trades.csv")
    c_trades = load_trades(root / "Track_C_Short_FTMO" / "reports" / "track_c_short_ftmo_oos_trades.csv")
    c_trades = apply_risk_multiplier(c_trades, c_best_mult)

    c_scaled_metrics = summarize_trades(c_trades)
    # Keep Track C comparison aligned with best Pareto balance sweep if present.
    c_sum["oos_sharpe_daily_annualized"] = c_scaled_metrics["oos_sharpe_daily_annualized"]
    c_sum["oos_return_pct"] = c_scaled_metrics["oos_return_pct"]
    c_sum["oos_max_drawdown_pct"] = c_scaled_metrics["oos_max_drawdown_pct"]
    c_sum["oos_trades"] = c_scaled_metrics["oos_trades"]
    c_sum["track_c_applied_risk_multiplier"] = c_best_mult

    eq_png = images_dir / "track_a_b_c_equity.png"
    metrics_png = images_dir / "track_a_b_c_metrics.png"
    ftmo_png = images_dir / "track_a_b_c_ftmo.png"

    plot_equity(equity_curve(a_trades), equity_curve(b_trades), equity_curve(c_trades), eq_png)
    plot_metrics(a_sum, b_sum, c_sum, metrics_png)

    ftmo_params = {"target_profit_pct": 10.0, "max_total_dd_pct": 10.0, "max_daily_dd_pct": 3.0, "initial_capital": 10000.0}
    ftmo_a = {"realized": evaluate_ftmo_rules(a_trades, **ftmo_params), "monte_carlo": ftmo_monte_carlo_probability(a_trades, n_paths=2000, seed=42, **ftmo_params)}
    ftmo_b = {"realized": evaluate_ftmo_rules(b_trades, **ftmo_params), "monte_carlo": ftmo_monte_carlo_probability(b_trades, n_paths=2000, seed=42, **ftmo_params)}
    ftmo_c = {"realized": evaluate_ftmo_rules(c_trades, **ftmo_params), "monte_carlo": ftmo_monte_carlo_probability(c_trades, n_paths=2000, seed=42, **ftmo_params)}
    c_sum["mc_profitability_probability_pct"] = float(ftmo_c["monte_carlo"]["pass_probability_pct"])

    plot_ftmo(ftmo_a, ftmo_b, ftmo_c, ftmo_png)

    comparison = {
        "track_a": {
            "oos_sharpe_daily_annualized": a_sum.get("oos_sharpe_daily_annualized", 0.0),
            "oos_return_pct": a_sum.get("oos_return_pct", 0.0),
            "oos_max_drawdown_pct": a_sum.get("oos_max_drawdown_pct", 0.0),
            "mc_profitability_probability_pct": a_sum.get("mc_profitability_probability_pct", 0.0),
            "oos_trades": a_sum.get("oos_trades", 0),
        },
        "track_b_ml": {
            "oos_sharpe_daily_annualized": b_sum.get("oos_sharpe_daily_annualized", 0.0),
            "oos_return_pct": b_sum.get("oos_return_pct", 0.0),
            "oos_max_drawdown_pct": b_sum.get("oos_max_drawdown_pct", 0.0),
            "mc_profitability_probability_pct": b_sum.get("mc_profitability_probability_pct", 0.0),
            "oos_trades": b_sum.get("oos_trades", 0),
        },
        "track_c_ftmo": {
            "oos_sharpe_daily_annualized": c_sum.get("oos_sharpe_daily_annualized", 0.0),
            "oos_return_pct": c_sum.get("oos_return_pct", 0.0),
            "oos_max_drawdown_pct": c_sum.get("oos_max_drawdown_pct", 0.0),
            "mc_profitability_probability_pct": c_sum.get("mc_profitability_probability_pct", 0.0),
            "oos_trades": c_sum.get("oos_trades", 0),
            "applied_risk_multiplier": c_best_mult,
        },
        "ftmo_constraints": {
            "target_profit_pct": 10.0,
            "max_total_drawdown_pct": 10.0,
            "max_daily_drawdown_pct": 3.0,
            "floating_included_note": "Approximated at trade-resolution from exit-sequenced equity; intrabar ticks are not available.",
        },
        "ftmo_results": {
            "track_a": ftmo_a,
            "track_b_ml": ftmo_b,
            "track_c_ftmo": ftmo_c,
        },
    }

    sharpe_map = {
        "Track A": float(comparison["track_a"]["oos_sharpe_daily_annualized"]),
        "Track B ML": float(comparison["track_b_ml"]["oos_sharpe_daily_annualized"]),
        "Track C FTMO": float(comparison["track_c_ftmo"]["oos_sharpe_daily_annualized"]),
    }
    comparison["winner_by_sharpe"] = max(sharpe_map, key=sharpe_map.get)

    (reports_dir / "track_a_b_c_summary.json").write_text(json.dumps(comparison, indent=2))

    lines = [
        "Track A/B/C Comparison", "", f"Winner by Sharpe: {comparison['winner_by_sharpe']}", "",
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
        "Track C FTMO:",
        f"  Sharpe: {comparison['track_c_ftmo']['oos_sharpe_daily_annualized']:.3f}",
        f"  Return %: {comparison['track_c_ftmo']['oos_return_pct']:.2f}",
        f"  Max DD %: {comparison['track_c_ftmo']['oos_max_drawdown_pct']:.2f}",
        f"  MC Profitability %: {comparison['track_c_ftmo']['mc_profitability_probability_pct']:.2f}",
        f"  OOS trades: {comparison['track_c_ftmo']['oos_trades']}",
        f"  FTMO realized pass: {'YES' if comparison['ftmo_results']['track_c_ftmo']['realized']['pass'] else 'NO'}",
        f"  FTMO realized days to pass: {comparison['ftmo_results']['track_c_ftmo']['realized']['passed_in_days']}",
        f"  FTMO MC pass probability %: {comparison['ftmo_results']['track_c_ftmo']['monte_carlo']['pass_probability_pct']:.2f}",
        f"  FTMO MC median days to pass: {comparison['ftmo_results']['track_c_ftmo']['monte_carlo']['median_days_to_pass']}",
    ]
    (reports_dir / "track_a_b_c_summary.txt").write_text("\n".join(lines))

    print("Saved images:")
    print(f"- {eq_png}")
    print(f"- {metrics_png}")
    print(f"- {ftmo_png}")
    print("Saved reports:")
    print(f"- {reports_dir / 'track_a_b_c_summary.json'}")
    print(f"- {reports_dir / 'track_a_b_c_summary.txt'}")


if __name__ == "__main__":
    main()
