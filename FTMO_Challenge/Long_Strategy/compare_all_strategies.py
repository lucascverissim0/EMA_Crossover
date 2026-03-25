"""
Compare all FTMO strategy tracks with a unified metric set and dashboard visual.

Tracks included:
- Track A: Capital Preservation (legacy, non walk-forward)
- Track B: Walk-Forward Robust (OOS)
- Track C: Time Optimized (OOS)
- Track D: Non-Canonical 0.54% snapshot (OOS)

Metrics reported:
- Profit factor
- Sharpe ratio (daily, annualized)
- Probability of passing challenge (Monte Carlo)
- Average days to Step 1 and Step 2 (Monte Carlo)
- Max drawdown
- Total equity
- Backtest period
- Walk-forward validation period (where applicable)

Outputs:
- FTMO_Challenge/Long_Strategy/strategy_comparison_summary.csv
- FTMO_Challenge/Long_Strategy/strategy_comparison_summary.json
- FTMO_Challenge/Long_Strategy/strategy_comparison_summary.txt
- FTMO_Challenge/Long_Strategy/strategy_comparison_dashboard.png
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


INITIAL_CAPITAL = 10000.0
STEP1_TARGET_PCT = 10.0
STEP2_TARGET_PCT = 15.0
MC_RUNS = 1500
MC_SEED = 42


def first_existing_path(paths: List[Path]) -> Path:
    for p in paths:
        if p.exists():
            return p
    raise FileNotFoundError("None of the expected files were found: " + ", ".join(str(p) for p in paths))


def load_track_a(repo_root: Path) -> pd.DataFrame:
    data = pd.read_csv(repo_root / "data" / "XAUUSD_1h_sample.csv")
    data["timestamp"] = pd.to_datetime(data.iloc[:, 0])

    trades = pd.read_csv(repo_root / "backtest" / "backtest_results_ml_optimized_fixed.csv")
    trades["entry_index"] = trades["entry_index"].astype(int)
    trades["exit_index"] = trades["exit_index"].astype(int)
    trades["entry_ts"] = trades["entry_index"].map(data["timestamp"])
    trades["exit_ts"] = trades["exit_index"].map(data["timestamp"])
    return trades


def load_track_b(repo_root: Path) -> pd.DataFrame:
    trades_path = first_existing_path(
        [
            repo_root
            / "FTMO_Challenge"
            / "Track_B_WalkForward_Robust"
            / "reports"
            / "wfv_extended_oos_trades.csv",
            repo_root
            / "FTMO_Challenge"
            / "Track_B_WalkForward_Robust"
            / "reports"
            / "wfv_best_candidate_oos_trades.csv",
        ]
    )
    trades = pd.read_csv(trades_path)
    trades["entry_ts"] = pd.to_datetime(trades["entry_ts"])
    trades["exit_ts"] = pd.to_datetime(trades["exit_ts"])
    return trades


def load_track_c(repo_root: Path) -> pd.DataFrame:
    trades_path = first_existing_path(
        [
            # Prefer the optimized fixed-param candidate (primary Track C output).
            repo_root
            / "FTMO_Challenge"
            / "Track_C_Time_Optimized"
            / "reports"
            / "track_c_best_candidate_oos_trades.csv",
            # Fallback: extended WFV (separate analysis, different param set).
            repo_root
            / "FTMO_Challenge"
            / "Track_C_Time_Optimized"
            / "reports"
            / "wfv_extended_oos_trades.csv",
        ]
    )
    trades = pd.read_csv(trades_path)
    trades["entry_ts"] = pd.to_datetime(trades["entry_ts"])
    trades["exit_ts"] = pd.to_datetime(trades["exit_ts"])
    return trades


def load_track_d(repo_root: Path) -> pd.DataFrame:
    trades = pd.read_csv(
        repo_root
        / "FTMO_Challenge"
        / "Track_D_NonCanonical_054"
        / "reports"
        / "track_d_best_candidate_oos_trades.csv"
    )
    trades["entry_ts"] = pd.to_datetime(trades["entry_ts"])
    trades["exit_ts"] = pd.to_datetime(trades["exit_ts"])
    return trades


def build_daily_activity(trades: pd.DataFrame) -> pd.DataFrame:
    daily = trades.copy()
    daily["date"] = pd.to_datetime(daily["exit_ts"]).dt.date
    out = (
        daily.groupby("date", as_index=False)
        .agg(
            trades=("pnl", "size"),
            total_pnl=("pnl", "sum"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )
    out["daily_return_pct_on_initial"] = (out["total_pnl"] / INITIAL_CAPITAL) * 100.0
    return out


def annualized_sharpe_from_daily(daily_activity: pd.DataFrame) -> float:
    if daily_activity.empty:
        return 0.0

    equity = INITIAL_CAPITAL + daily_activity["total_pnl"].cumsum()
    returns = equity.pct_change().dropna()
    if returns.empty or returns.std() == 0:
        return 0.0
    return float((returns.mean() / returns.std()) * np.sqrt(252))


def max_drawdown_from_trade_sequence(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    equity = INITIAL_CAPITAL + trades["pnl"].cumsum()
    running_peak = equity.cummax()
    dd = ((running_peak - equity) / running_peak) * 100.0
    return float(dd.max())


def trades_per_day_estimate(daily_activity: pd.DataFrame) -> float:
    if daily_activity.empty:
        return 1.0
    return float(daily_activity["trades"].mean())


def monte_carlo_challenge_stats(
    trades: pd.DataFrame,
    trades_per_day: float,
    runs: int = MC_RUNS,
    step1_target_pct: float = STEP1_TARGET_PCT,
    step2_target_pct: float = STEP2_TARGET_PCT,
) -> Dict:
    if trades.empty:
        return {
            "pass_probability_pct": 0.0,
            "step1_avg_days": None,
            "step2_avg_days": None,
            "step1_avg_trades": None,
            "step2_avg_trades": None,
        }

    pnls = trades["pnl"].to_numpy(dtype=float)
    n = len(pnls)
    step1_equity = INITIAL_CAPITAL * (1.0 + step1_target_pct / 100.0)
    step2_equity = INITIAL_CAPITAL * (1.0 + step2_target_pct / 100.0)

    tpd = max(trades_per_day, 1e-9)

    pass_count = 0
    step1_hits: List[float] = []
    step2_hits: List[float] = []

    for _ in range(runs):
        sim = np.random.permutation(pnls)
        eq = INITIAL_CAPITAL
        peak = INITIAL_CAPITAL
        max_dd = 0.0

        # Approximate FTMO daily loss from simulated trade order using average trade frequency.
        day_pnl: Dict[int, float] = {}
        worst_daily_loss_pct = 0.0

        step1_idx = None
        step2_idx = None

        for i, p in enumerate(sim, start=1):
            eq += p
            peak = max(peak, eq)
            dd = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

            day_idx = int((i - 1) // tpd)
            day_pnl[day_idx] = day_pnl.get(day_idx, 0.0) + float(p)
            day_loss_pct = (day_pnl[day_idx] / INITIAL_CAPITAL) * 100.0
            if day_loss_pct < worst_daily_loss_pct:
                worst_daily_loss_pct = day_loss_pct

            if step1_idx is None and eq >= step1_equity:
                step1_idx = i
            if step2_idx is None and eq >= step2_equity:
                step2_idx = i

        if step1_idx is not None:
            step1_hits.append(float(step1_idx))
        if step2_idx is not None:
            step2_hits.append(float(step2_idx))

        challenge_pass = (
            step1_idx is not None
            and step2_idx is not None
            and max_dd <= 10.0
            and worst_daily_loss_pct >= -5.0
        )
        if challenge_pass:
            pass_count += 1

    step1_avg_trades = float(np.mean(step1_hits)) if step1_hits else None
    step2_avg_trades = float(np.mean(step2_hits)) if step2_hits else None

    return {
        "pass_probability_pct": float((pass_count / runs) * 100.0),
        "step1_avg_days": (step1_avg_trades / tpd) if step1_avg_trades is not None else None,
        "step2_avg_days": (step2_avg_trades / tpd) if step2_avg_trades is not None else None,
        "step1_avg_trades": step1_avg_trades,
        "step2_avg_trades": step2_avg_trades,
    }


def profit_factor_from_trades(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    wins = trades[trades["pnl"] > 0]["pnl"]
    losses = trades[trades["pnl"] < 0]["pnl"]
    gross_win = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
    return (gross_win / gross_loss) if gross_loss > 0 else 0.0


def wfv_period(repo_root: Path) -> Tuple[str | None, str | None]:
    fold_candidates = [
        repo_root
        / "FTMO_Challenge"
        / "Track_B_WalkForward_Robust"
        / "reports"
        / "wfv_extended_fold_results.csv",
        repo_root
        / "FTMO_Challenge"
        / "Track_B_WalkForward_Robust"
        / "reports"
        / "wfv_fold_results.csv",
    ]
    fold_file = None
    for candidate in fold_candidates:
        if candidate.exists():
            fold_file = candidate
            break

    if fold_file is None:
        return None, None

    folds = pd.read_csv(fold_file)
    if folds.empty:
        return None, None

    start = pd.to_datetime(folds["test_start"]).min()
    end = pd.to_datetime(folds["test_end"]).max()
    return str(start), str(end)


def compute_strategy_row(
    name: str,
    trades: pd.DataFrame,
    validation_method: str,
    wfv_start: str | None,
    wfv_end: str | None,
) -> Dict:
    trades = trades.copy().sort_values("exit_ts").reset_index(drop=True)
    daily = build_daily_activity(trades)

    total_pnl = float(trades["pnl"].sum()) if not trades.empty else 0.0
    total_equity = INITIAL_CAPITAL + total_pnl

    row = {
        "strategy": name,
        "validation_method": validation_method,
        "period_start": str(pd.to_datetime(trades["entry_ts"]).min()) if not trades.empty else None,
        "period_end": str(pd.to_datetime(trades["exit_ts"]).max()) if not trades.empty else None,
        "wfv_period_start": wfv_start,
        "wfv_period_end": wfv_end,
        "total_trades": int(len(trades)),
        "trading_days": int(len(daily)),
        "profit_factor": float(profit_factor_from_trades(trades)),
        "sharpe_ratio_daily": float(annualized_sharpe_from_daily(daily)),
        "max_drawdown_pct": float(max_drawdown_from_trade_sequence(trades)),
        "total_pnl": total_pnl,
        "total_equity": float(total_equity),
        "return_pct_on_initial": float((total_pnl / INITIAL_CAPITAL) * 100.0),
    }

    tpd = trades_per_day_estimate(daily)
    mc = monte_carlo_challenge_stats(trades, trades_per_day=tpd, runs=MC_RUNS)
    row["trades_per_day_estimate"] = float(tpd)
    row["challenge_pass_probability_pct"] = float(mc["pass_probability_pct"])
    row["step1_avg_days"] = mc["step1_avg_days"]
    row["step2_avg_days"] = mc["step2_avg_days"]
    row["step1_avg_trades"] = mc["step1_avg_trades"]
    row["step2_avg_trades"] = mc["step2_avg_trades"]

    return row


def fmt_num(v, nd=2, suffix="") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{v:.{nd}f}{suffix}"


def fmt_text(v) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float) and np.isnan(v):
        return "N/A"
    if isinstance(v, str) and v.strip().lower() in {"nan", "none", ""}:
        return "N/A"
    return str(v)


def build_text_report(rows: pd.DataFrame) -> str:
    lines: List[str] = []
    lines.append("STRATEGY COMPARISON SUMMARY")
    lines.append("=" * 88)
    lines.append("Metrics include Monte Carlo challenge pass probability with FTMO constraints.")
    lines.append("")

    for _, r in rows.iterrows():
        lines.append(str(r["strategy"]))
        lines.append("-" * 88)
        lines.append(f"Validation method: {fmt_text(r['validation_method'])}")
        lines.append(f"Backtest period: {fmt_text(r['period_start'])} -> {fmt_text(r['period_end'])}")
        lines.append(f"Walk-forward period: {fmt_text(r['wfv_period_start'])} -> {fmt_text(r['wfv_period_end'])}")
        lines.append(f"Profit factor: {fmt_num(r['profit_factor'])}")
        lines.append(f"Sharpe ratio (daily annualized): {fmt_num(r['sharpe_ratio_daily'])}")
        lines.append(f"Challenge pass probability: {fmt_num(r['challenge_pass_probability_pct'], suffix='%')}")
        lines.append(f"Step 1 avg time: {fmt_num(r['step1_avg_days'])} days ({fmt_num(r['step1_avg_trades'])} trades)")
        lines.append(f"Step 2 avg time: {fmt_num(r['step2_avg_days'])} days ({fmt_num(r['step2_avg_trades'])} trades)")
        lines.append(f"Max drawdown: {fmt_num(r['max_drawdown_pct'], suffix='%')}")
        lines.append(f"Total equity: ${fmt_num(r['total_equity'])}")
        lines.append(f"Total trades: {int(r['total_trades'])}")
        lines.append("")

    return "\n".join(lines)


def create_dashboard(rows: pd.DataFrame, out_path: Path) -> None:
    names = rows["strategy"].tolist()
    x = np.arange(len(rows))
    palette = ["#1f77b4", "#2ca02c", "#ff7f0e", "#dc2626", "#7c3aed", "#0f766e"]
    bar_colors = palette[: len(rows)]

    metrics = [
        ("profit_factor", "Profit Factor", ""),
        ("sharpe_ratio_daily", "Sharpe Ratio", ""),
        ("challenge_pass_probability_pct", "Pass Probability", "%"),
        ("step1_avg_days", "Step 1 Days", "d"),
        ("step2_avg_days", "Step 2 Days", "d"),
        ("max_drawdown_pct", "Max Drawdown", "%"),
        ("total_equity", "Total Equity", "$"),
    ]

    fig, axes = plt.subplots(4, 2, figsize=(18, 16))
    axes_flat = axes.flatten()

    for i, (col, title, suffix) in enumerate(metrics):
        ax = axes_flat[i]
        vals = rows[col].astype(float).to_numpy()
        ax.bar(x, vals, color=bar_colors, alpha=0.9)
        ax.set_title(title)
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=12, ha="right")

        for xi, yi in zip(x, vals):
            if np.isnan(yi):
                label = "N/A"
            elif suffix == "$":
                label = f"${yi:,.0f}"
            elif suffix == "%":
                label = f"{yi:.1f}%"
            elif suffix == "d":
                label = f"{yi:.1f}d"
            else:
                label = f"{yi:.2f}"
            y_text = yi if not np.isnan(yi) else 0.0
            ax.text(xi, y_text, f" {label}", va="bottom", ha="left", fontsize=9)

        ax.grid(axis="y", alpha=0.25)

    # Final panel: periods and validation metadata as a table.
    ax_table = axes_flat[7]
    ax_table.axis("off")

    table_df = rows[
        [
            "strategy",
            "validation_method",
            "period_start",
            "period_end",
            "wfv_period_start",
            "wfv_period_end",
        ]
    ].copy()

    table_df.columns = [
        "Strategy",
        "Method",
        "Backtest Start",
        "Backtest End",
        "WFV Start",
        "WFV End",
    ]

    table = ax_table.table(
        cellText=table_df.values,
        colLabels=table_df.columns,
        loc="center",
        cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1.0, 1.4)
    ax_table.set_title("Backtest and Walk-Forward Validation Periods")

    fig.suptitle("FTMO Strategy Comparison Dashboard", fontsize=16, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main() -> None:
    np.random.seed(MC_SEED)

    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "FTMO_Challenge"

    track_a = load_track_a(repo_root)
    track_b = load_track_b(repo_root)
    track_c = load_track_c(repo_root)
    track_d = load_track_d(repo_root)

    wfv_start, wfv_end = wfv_period(repo_root)

    rows = [
        compute_strategy_row(
            "Track A - Capital Preservation",
            track_a,
            validation_method="Historical backtest (non-WFV)",
            wfv_start=None,
            wfv_end=None,
        ),
        compute_strategy_row(
            "Track B - Walk-Forward Robust",
            track_b,
            validation_method="Walk-forward OOS",
            wfv_start=wfv_start,
            wfv_end=wfv_end,
        ),
        compute_strategy_row(
            "Track C - Time Optimized",
            track_c,
            validation_method="Walk-forward OOS",
            wfv_start=wfv_start,
            wfv_end=wfv_end,
        ),
        compute_strategy_row(
            "Track D - Non-Canonical 0.54%",
            track_d,
            validation_method="Walk-forward OOS (pinned non-canonical snapshot)",
            wfv_start=wfv_start,
            wfv_end=wfv_end,
        ),
    ]

    summary = pd.DataFrame(rows)

    csv_path = out_dir / "strategy_comparison_summary.csv"
    json_path = out_dir / "strategy_comparison_summary.json"
    txt_path = out_dir / "strategy_comparison_summary.txt"
    png_path = out_dir / "strategy_comparison_dashboard.png"

    summary.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2))
    txt_path.write_text(build_text_report(summary))
    create_dashboard(summary, out_path=png_path)

    print(f"Saved: {csv_path}")
    print(f"Saved: {json_path}")
    print(f"Saved: {txt_path}")
    print(f"Saved: {png_path}")


if __name__ == "__main__":
    main()
