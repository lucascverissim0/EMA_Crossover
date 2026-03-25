"""
Create a Track C performance dashboard image from the current best-candidate outputs.

Output:
- FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/images/track_c_performance_dashboard.png
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


INITIAL_CAPITAL = 10000.0


def load_inputs(track_root: Path) -> tuple[pd.DataFrame, dict]:
    reports = track_root / "reports"
    trades_csv = reports / "track_c_best_candidate_oos_trades.csv"
    summary_json = reports / "track_c_best_candidate.json"

    trades = pd.read_csv(trades_csv)
    trades["entry_ts"] = pd.to_datetime(trades["entry_ts"])
    trades["exit_ts"] = pd.to_datetime(trades["exit_ts"])

    summary = json.loads(summary_json.read_text())
    return trades, summary


def compute_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "total_trades": 0,
            "total_pnl": 0.0,
            "return_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "worst_daily_loss_pct": 0.0,
            "expectancy_usd": 0.0,
            "expectancy_pct_initial": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "payoff_ratio": 0.0,
            "trades_per_day": 0.0,
            "sharpe_daily_annualized": 0.0,
            "daily": pd.DataFrame(),
            "equity_curve": np.array([INITIAL_CAPITAL]),
            "peak_curve": np.array([INITIAL_CAPITAL]),
            "dd_curve": np.array([0.0]),
        }

    pnl = trades["pnl"].astype(float)
    total_trades = int(len(trades))
    total_pnl = float(pnl.sum())
    return_pct = (total_pnl / INITIAL_CAPITAL) * 100.0

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    win_rate_pct = float((len(wins) / total_trades) * 100.0)

    gross_win = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 0.0

    equity_curve = INITIAL_CAPITAL + pnl.cumsum().to_numpy(dtype=float)
    peak_curve = np.maximum.accumulate(equity_curve)
    dd_curve = np.where(peak_curve > 0, ((peak_curve - equity_curve) / peak_curve) * 100.0, 0.0)
    max_drawdown_pct = float(dd_curve.max()) if len(dd_curve) else 0.0

    daily = trades.copy()
    daily["date"] = pd.to_datetime(daily["exit_ts"]).dt.date
    daily = (
        daily.groupby("date", as_index=False)["pnl"]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["daily_loss_pct"] = (daily["pnl"] / INITIAL_CAPITAL) * 100.0
    worst_daily_loss_pct = float(daily["daily_loss_pct"].min()) if not daily.empty else 0.0

    expectancy_usd = float(total_pnl / total_trades)
    expectancy_pct_initial = (expectancy_usd / INITIAL_CAPITAL) * 100.0
    avg_win = float(wins.mean()) if not wins.empty else 0.0
    avg_loss = float(losses.mean()) if not losses.empty else 0.0
    payoff_ratio = (avg_win / abs(avg_loss)) if avg_loss < 0 else 0.0

    trades_per_day = float(
        trades.assign(date=trades["exit_ts"].dt.date)
        .groupby("date")["pnl"]
        .count()
        .mean()
    )

    equity_daily = INITIAL_CAPITAL + daily["pnl"].cumsum()
    daily_returns = equity_daily.pct_change().dropna()
    if daily_returns.empty or daily_returns.std() == 0:
        sharpe = 0.0
    else:
        sharpe = float((daily_returns.mean() / daily_returns.std()) * np.sqrt(252))

    return {
        "total_trades": total_trades,
        "total_pnl": total_pnl,
        "return_pct": return_pct,
        "win_rate_pct": win_rate_pct,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown_pct,
        "worst_daily_loss_pct": worst_daily_loss_pct,
        "expectancy_usd": expectancy_usd,
        "expectancy_pct_initial": expectancy_pct_initial,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": payoff_ratio,
        "trades_per_day": trades_per_day,
        "sharpe_daily_annualized": sharpe,
        "daily": daily,
        "equity_curve": np.insert(equity_curve, 0, INITIAL_CAPITAL),
        "peak_curve": np.insert(peak_curve, 0, INITIAL_CAPITAL),
        "dd_curve": np.insert(dd_curve, 0, 0.0),
    }


def render_dashboard(track_root: Path, trades: pd.DataFrame, summary: dict, metrics: dict) -> Path:
    out_path = track_root / "images" / "track_c_performance_dashboard.png"

    plt.figure(figsize=(16, 10))
    gs = plt.GridSpec(2, 2, height_ratios=[1.2, 1], width_ratios=[1.4, 1])

    # Equity + drawdown panel
    ax_eq = plt.subplot(gs[0, 0])
    x = np.arange(len(metrics["equity_curve"]))
    ax_eq.plot(x, metrics["equity_curve"], color="#14532d", linewidth=2.2, label="Equity")
    ax_eq.plot(x, metrics["peak_curve"], color="#84cc16", linewidth=1.4, linestyle="--", label="Running peak")
    selected = summary.get("selected", {})
    risk_pct = selected.get("risk_pct", "?")
    ax_eq.set_title(f"Track C Equity Path (Selected {risk_pct}% Risk)", fontsize=12, weight="bold")
    ax_eq.set_xlabel("Trade #")
    ax_eq.set_ylabel("Equity ($)")
    ax_eq.grid(alpha=0.2)
    ax_eq.legend(loc="upper left")

    ax_dd = ax_eq.twinx()
    ax_dd.plot(x, metrics["dd_curve"], color="#dc2626", linewidth=1.2, alpha=0.9, label="Drawdown %")
    ax_dd.set_ylabel("Drawdown (%)", color="#dc2626")
    ax_dd.tick_params(axis="y", colors="#dc2626")

    # Daily PnL panel
    ax_daily = plt.subplot(gs[1, 0])
    if not metrics["daily"].empty:
        daily_x = np.arange(len(metrics["daily"]))
        daily_pnl = metrics["daily"]["pnl"].to_numpy(dtype=float)
        colors = np.where(daily_pnl >= 0, "#0ea5e9", "#f97316")
        ax_daily.bar(daily_x, daily_pnl, color=colors, alpha=0.85)
    ax_daily.axhline(0, color="#111827", linewidth=1)
    ax_daily.set_title("Daily PnL Distribution", fontsize=12, weight="bold")
    ax_daily.set_xlabel("Trading day index")
    ax_daily.set_ylabel("PnL ($)")
    ax_daily.grid(alpha=0.2)

    # KPI panel
    ax_kpi = plt.subplot(gs[:, 1])
    ax_kpi.axis("off")

    lines = [
        "TRACK C PERFORMANCE SNAPSHOT",
        "",
        f"Params: EMA({selected.get('fast')}/{selected.get('slow')}), SL {selected.get('sl_pct')}%, TP {selected.get('tp_pct')}%, Risk {selected.get('risk_pct')}%",
        "",
        f"Sharpe (daily annualized): {metrics['sharpe_daily_annualized']:.2f}",
        f"Total trades: {metrics['total_trades']}",
        f"Trades/day: {metrics['trades_per_day']:.2f}",
        f"Expectancy/trade: ${metrics['expectancy_usd']:.2f} ({metrics['expectancy_pct_initial']:.3f}% of initial)",
        f"Win rate: {metrics['win_rate_pct']:.2f}%",
        f"Profit factor: {metrics['profit_factor']:.2f}",
        f"Payoff ratio (avg win/avg loss): {metrics['payoff_ratio']:.2f}",
        f"Total return: {metrics['return_pct']:.2f}%",
        f"Total equity: ${INITIAL_CAPITAL + metrics['total_pnl']:.2f}",
        f"Max drawdown: {metrics['max_drawdown_pct']:.2f}%",
        f"Worst daily loss: {metrics['worst_daily_loss_pct']:.2f}%",
        "",
        f"Constraint MC minimum: {summary.get('constraint_mc_pass_probability_pct', 0.0):.2f}%",
        f"MC pass probability: {summary.get('mc_pass_probability_pct', 0.0):.2f}%",
        f"MC Step 1 avg days: {summary.get('mc_step1_avg_days_to_pass', 0.0):.1f}",
        f"MC Step 2 avg days: {summary.get('mc_step2_avg_days_to_pass', 0.0):.1f}",
        "",
        "FTMO limits reference:",
        "- Max drawdown <= 10%",
        "- Max daily loss >= -5%",
    ]

    ax_kpi.text(
        0.02,
        0.98,
        "\n".join(lines),
        va="top",
        ha="left",
        fontsize=10.5,
        family="monospace",
        bbox={"boxstyle": "round,pad=0.6", "facecolor": "#f8fafc", "edgecolor": "#cbd5e1"},
    )

    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()
    return out_path


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    track_root = script_dir.parent
    trades, summary = load_inputs(track_root)
    metrics = compute_metrics(trades)
    out_path = render_dashboard(track_root, trades, summary, metrics)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
