"""
Track metrics comparison report for FTMO Challenge.

Compares:
- Track A: legacy ML-optimized backtest results
- Track B: walk-forward best-candidate OOS trades

Outputs:
- FTMO_Challenge/Long_Strategy/track_metrics_summary.txt
- FTMO_Challenge/Long_Strategy/track_metrics_summary.json
- FTMO_Challenge/Long_Strategy/Track_A_Capital_Preservation/reports/track_a_daily_activity.csv
- FTMO_Challenge/Long_Strategy/Track_B_WalkForward_Robust/reports/track_b_daily_activity.csv
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


INITIAL_CAPITAL = 10000.0


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
    trades = pd.read_csv(
        repo_root
        / "FTMO_Challenge"
        / "Track_B_WalkForward_Robust"
        / "reports"
        / "wfv_best_candidate_oos_trades.csv"
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
            wins=("pnl", lambda series: int((series > 0).sum())),
            losses=("pnl", lambda series: int((series < 0).sum())),
            median_trade_pnl=("pnl", "median"),
            max_win=("pnl", "max"),
            max_loss=("pnl", "min"),
        )
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


def compute_metrics(name: str, trades: pd.DataFrame) -> Dict:
    trades = trades.copy().sort_values("exit_ts").reset_index(drop=True)
    daily = build_daily_activity(trades)

    wins = trades[trades["pnl"] > 0]["pnl"]
    losses = trades[trades["pnl"] < 0]["pnl"]
    gross_win = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
    profit_factor = gross_win / gross_loss if gross_loss > 0 else 0.0

    hold_hours = (pd.to_datetime(trades["exit_ts"]) - pd.to_datetime(trades["entry_ts"])).dt.total_seconds() / 3600.0

    metrics = {
        "track": name,
        "period_start": str(pd.to_datetime(trades["entry_ts"]).min()) if not trades.empty else None,
        "period_end": str(pd.to_datetime(trades["exit_ts"]).max()) if not trades.empty else None,
        "total_trades": int(len(trades)),
        "trading_days": int(len(daily)),
        "trades_per_day_avg": float(daily["trades"].mean()) if not daily.empty else 0.0,
        "trades_per_day_median": float(daily["trades"].median()) if not daily.empty else 0.0,
        "trades_per_day_max": int(daily["trades"].max()) if not daily.empty else 0,
        "trades_per_day_min": int(daily["trades"].min()) if not daily.empty else 0,
        "total_pnl": float(trades["pnl"].sum()) if not trades.empty else 0.0,
        "return_pct_on_initial": float((trades["pnl"].sum() / INITIAL_CAPITAL) * 100.0) if not trades.empty else 0.0,
        "win_rate_pct": float(((trades["pnl"] > 0).mean() * 100.0)) if not trades.empty else 0.0,
        "profit_factor": float(profit_factor),
        "expectancy_per_trade": float(trades["pnl"].mean()) if not trades.empty else 0.0,
        "median_trade_pnl": float(trades["pnl"].median()) if not trades.empty else 0.0,
        "avg_win": float(wins.mean()) if not wins.empty else 0.0,
        "median_win": float(wins.median()) if not wins.empty else 0.0,
        "largest_win": float(wins.max()) if not wins.empty else 0.0,
        "avg_loss": float(losses.mean()) if not losses.empty else 0.0,
        "median_loss": float(losses.median()) if not losses.empty else 0.0,
        "largest_loss": float(losses.min()) if not losses.empty else 0.0,
        "payoff_ratio": float(abs(wins.mean() / losses.mean())) if (not wins.empty and not losses.empty and losses.mean() != 0) else 0.0,
        "best_day_pnl": float(daily["total_pnl"].max()) if not daily.empty else 0.0,
        "worst_day_pnl": float(daily["total_pnl"].min()) if not daily.empty else 0.0,
        "best_day_return_pct_on_initial": float(daily["daily_return_pct_on_initial"].max()) if not daily.empty else 0.0,
        "worst_day_return_pct_on_initial": float(daily["daily_return_pct_on_initial"].min()) if not daily.empty else 0.0,
        "sharpe_ratio_daily": float(annualized_sharpe_from_daily(daily)),
        "max_drawdown_pct": float(max_drawdown_from_trade_sequence(trades)),
        "avg_hold_hours": float(hold_hours.mean()) if not hold_hours.empty else 0.0,
        "median_hold_hours": float(hold_hours.median()) if not hold_hours.empty else 0.0,
        "max_hold_hours": float(hold_hours.max()) if not hold_hours.empty else 0.0,
    }
    return metrics


def format_metrics(metrics: Dict) -> str:
    lines = [
        metrics["track"],
        "=" * 72,
        f"Period: {metrics['period_start']} -> {metrics['period_end']}",
        f"Total Trades: {metrics['total_trades']}",
        f"Trading Days: {metrics['trading_days']}",
        f"Trades/Day Avg: {metrics['trades_per_day_avg']:.2f}",
        f"Trades/Day Median: {metrics['trades_per_day_median']:.2f}",
        f"Trades/Day Max: {metrics['trades_per_day_max']}",
        f"Trades/Day Min: {metrics['trades_per_day_min']}",
        f"Total P&L: ${metrics['total_pnl']:.2f}",
        f"Return on Initial Capital: {metrics['return_pct_on_initial']:.2f}%",
        f"Win Rate: {metrics['win_rate_pct']:.2f}%",
        f"Profit Factor: {metrics['profit_factor']:.2f}",
        f"Sharpe Ratio (daily, annualized): {metrics['sharpe_ratio_daily']:.2f}",
        f"Max Drawdown: {metrics['max_drawdown_pct']:.2f}%",
        f"Expectancy per Trade: ${metrics['expectancy_per_trade']:.2f}",
        f"Median Trade P&L: ${metrics['median_trade_pnl']:.2f}",
        f"Average Win: ${metrics['avg_win']:.2f}",
        f"Median Win: ${metrics['median_win']:.2f}",
        f"Largest Win: ${metrics['largest_win']:.2f}",
        f"Average Loss: ${metrics['avg_loss']:.2f}",
        f"Median Loss: ${metrics['median_loss']:.2f}",
        f"Largest Loss: ${metrics['largest_loss']:.2f}",
        f"Payoff Ratio: {metrics['payoff_ratio']:.2f}",
        f"Best Day: ${metrics['best_day_pnl']:.2f} ({metrics['best_day_return_pct_on_initial']:.2f}%)",
        f"Worst Day: ${metrics['worst_day_pnl']:.2f} ({metrics['worst_day_return_pct_on_initial']:.2f}%)",
        f"Average Hold Time: {metrics['avg_hold_hours']:.2f} hours",
        f"Median Hold Time: {metrics['median_hold_hours']:.2f} hours",
        f"Max Hold Time: {metrics['max_hold_hours']:.2f} hours",
    ]
    return "\n".join(lines)


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = repo_root / "FTMO_Challenge"

    track_a = load_track_a(repo_root)
    track_b = load_track_b(repo_root)

    track_a_daily = build_daily_activity(track_a)
    track_b_daily = build_daily_activity(track_b)

    track_a_daily_path = out_dir / "Track_A_Capital_Preservation" / "reports" / "track_a_daily_activity.csv"
    track_b_daily_path = out_dir / "Track_B_WalkForward_Robust" / "reports" / "track_b_daily_activity.csv"
    track_a_daily.to_csv(track_a_daily_path, index=False)
    track_b_daily.to_csv(track_b_daily_path, index=False)

    metrics_a = compute_metrics("Track A - Capital Preservation", track_a)
    metrics_b = compute_metrics("Track B - Walk-Forward Robust", track_b)

    summary = {
        "track_a": metrics_a,
        "track_b": metrics_b,
    }

    txt = [
        "FTMO TRACK METRICS SUMMARY",
        "=" * 72,
        "",
        format_metrics(metrics_a),
        "",
        format_metrics(metrics_b),
    ]

    txt_path = out_dir / "track_metrics_summary.txt"
    json_path = out_dir / "track_metrics_summary.json"

    txt_path.write_text("\n".join(txt))
    json_path.write_text(json.dumps(summary, indent=2))

    print(f"Saved: {txt_path}")
    print(f"Saved: {json_path}")
    print(f"Saved: {track_a_daily_path}")
    print(f"Saved: {track_b_daily_path}")


if __name__ == "__main__":
    main()
