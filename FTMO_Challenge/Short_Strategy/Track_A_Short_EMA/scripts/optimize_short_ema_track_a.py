"""
Track A Short EMA exploration.

Goal:
- Find short-only EMA crossover configurations with strong Sharpe ratio,
  while keeping drawdown, daily loss, and return quality in mind.

Outputs:
- reports/track_a_short_rankings.csv
- reports/track_a_short_best_candidate.json
- reports/track_a_short_best_candidate.txt
- reports/track_a_short_best_trades.csv
- images/track_a_short_equity_drawdown.png
- images/track_a_short_daily_pnl.png
- images/track_a_short_score_vs_sharpe.png
- images/track_a_short_performance_dashboard.png
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


@dataclass
class Params:
    fast: int
    slow: int
    stop_loss_pct: float
    take_profit_pct: float
    risk_pct: float


def load_data(csv_path: Path) -> pd.DataFrame:
    """Load either simple OHLC CSV or yfinance-style multi-row header CSV."""
    df = pd.read_csv(csv_path)

    if "Close" not in df.columns:
        # Handle yfinance export where first two rows are ticker metadata.
        raw = pd.read_csv(csv_path, header=None)
        if len(raw) < 4:
            raise ValueError(f"Unable to parse OHLC data from: {csv_path}")

        header = raw.iloc[0].astype(str).tolist()
        values = raw.iloc[3:].copy().reset_index(drop=True)
        values.columns = header
        values = values.rename(columns={header[0]: "timestamp"})
        keep = ["timestamp", "Open", "High", "Low", "Close", "Volume"]
        keep = [c for c in keep if c in values.columns]
        out = values[keep].copy()
    else:
        first_col = df.columns[0]
        out = df.rename(columns={first_col: "timestamp"}).copy()

    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.dropna(subset=["timestamp", "Close"]).sort_values("timestamp").reset_index(drop=True)
    return out


def build_short_signals(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    out = df.copy()
    out["fast_ema"] = out["Close"].ewm(span=fast, adjust=False).mean()
    out["slow_ema"] = out["Close"].ewm(span=slow, adjust=False).mean()
    out["short_signal"] = (out["fast_ema"] < out["slow_ema"]).astype(int)
    out["signal_diff"] = out["short_signal"].diff().fillna(0)
    return out


def run_backtest(df: pd.DataFrame, params: Params, initial_capital: float) -> Tuple[pd.DataFrame, Dict[str, float]]:
    data = build_short_signals(df, params.fast, params.slow)

    trades: List[Dict[str, float]] = []
    capital = initial_capital
    peak = initial_capital

    in_short = False
    entry_price = 0.0
    entry_ts = None
    position_size = 0.0

    # Pre-extract arrays to avoid slow data.iloc[i] inside the hot loop
    closes = data["Close"].to_numpy(dtype=float)
    signal_diffs = data["signal_diff"].to_numpy(dtype=float)
    timestamps = data["timestamp"].to_numpy()

    for i in range(1, len(data)):
        price = closes[i]
        ts = timestamps[i]
        sig_diff = signal_diffs[i]

        if not in_short and sig_diff > 0:
            in_short = True
            entry_price = price
            entry_ts = ts
            risk_dollars = capital * (params.risk_pct / 100.0)
            stop_move = entry_price * (params.stop_loss_pct / 100.0)
            if stop_move <= 0:
                in_short = False
                continue
            position_size = risk_dollars / stop_move
            continue

        if in_short:
            # Short PnL% is positive when price goes down.
            pnl_pct = ((entry_price - price) / entry_price) * 100.0
            reason = None
            exit_price = price

            if pnl_pct <= -params.stop_loss_pct:
                reason = "Stop Loss"
                exit_price = entry_price * (1.0 + params.stop_loss_pct / 100.0)
            elif pnl_pct >= params.take_profit_pct:
                reason = "Take Profit"
                exit_price = entry_price * (1.0 - params.take_profit_pct / 100.0)
            elif sig_diff < 0:
                reason = "Cover Signal"

            if reason is not None:
                pnl = position_size * (entry_price - exit_price)
                capital += pnl
                peak = max(peak, capital)
                dd_pct = ((peak - capital) / peak) * 100.0 if peak > 0 else 0.0

                trades.append(
                    {
                        "entry_ts": entry_ts,
                        "exit_ts": ts,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "pnl_percent": pnl_pct,
                        "reason": reason,
                        "equity_after": capital,
                        "drawdown_pct": dd_pct,
                    }
                )
                in_short = False

    trades_df = pd.DataFrame(trades)
    metrics = compute_metrics(trades_df, initial_capital)
    return trades_df, metrics


def compute_metrics(trades_df: pd.DataFrame, initial_capital: float) -> Dict[str, float]:
    if trades_df.empty:
        return {
            "total_trades": 0.0,
            "win_rate": 0.0,
            "return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "worst_daily_loss_pct": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "trades_per_day": 0.0,
            "sharpe_daily_annualized": 0.0,
            "total_pnl": 0.0,
        }

    pnl = trades_df["pnl"].astype(float)
    total_pnl = float(pnl.sum())
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    win_rate = float((len(wins) / len(trades_df)) * 100.0)
    return_pct = (total_pnl / initial_capital) * 100.0
    max_drawdown_pct = float(trades_df["drawdown_pct"].max())

    temp = trades_df.copy()
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"])
    temp["date"] = temp["exit_ts"].dt.date

    daily = temp.groupby("date", as_index=False)["pnl"].sum().sort_values("date")
    daily["daily_loss_pct"] = (daily["pnl"] / initial_capital) * 100.0
    worst_daily_loss_pct = float(daily["daily_loss_pct"].min()) if not daily.empty else 0.0

    gross_win = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 0.0

    expectancy = float(total_pnl / len(trades_df))

    num_days = (daily["date"].max() - daily["date"].min()).days + 1 if not daily.empty else 1
    trades_per_day = float(len(trades_df) / max(num_days, 1))

    equity_daily = initial_capital + daily["pnl"].cumsum()
    daily_returns = equity_daily.pct_change().dropna()
    if daily_returns.empty or daily_returns.std() == 0:
        sharpe = 0.0
    else:
        sharpe = float((daily_returns.mean() / daily_returns.std()) * np.sqrt(252))

    return {
        "total_trades": float(len(trades_df)),
        "win_rate": win_rate,
        "return_pct": return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "worst_daily_loss_pct": worst_daily_loss_pct,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "trades_per_day": trades_per_day,
        "sharpe_daily_annualized": sharpe,
        "total_pnl": total_pnl,
    }


def score_candidate(metrics: Dict[str, float]) -> float:
    """Sharpe-first score with explicit FTMO-style risk penalties."""
    score = metrics["sharpe_daily_annualized"] * 35.0
    score += metrics["return_pct"] * 1.2
    score += min(metrics["profit_factor"], 3.0) * 4.0
    score += metrics["win_rate"] * 0.05

    if metrics["max_drawdown_pct"] > 10.0:
        score -= (metrics["max_drawdown_pct"] - 10.0) * 14.0
    if metrics["worst_daily_loss_pct"] < -5.0:
        score -= abs(metrics["worst_daily_loss_pct"] + 5.0) * 18.0
    if metrics["total_trades"] < 30:
        score -= (30.0 - metrics["total_trades"]) * 0.4

    return float(score)


def parameter_grid() -> List[Params]:
    grid: List[Params] = []

    fasts = [8, 10, 12, 14]
    slows = [20, 26, 30, 40, 50]
    sls = [0.5, 0.75, 1.0]
    tps = [1.0, 1.5, 2.0, 3.0]
    risks = [0.25, 0.5]

    for fast in fasts:
        for slow in slows:
            if fast >= slow:
                continue
            if (slow - fast) < 10:
                continue
            for sl in sls:
                for tp in tps:
                    for risk in risks:
                        grid.append(Params(fast, slow, sl, tp, risk))
    return grid


def render_visuals(track_root: Path, trades_df: pd.DataFrame, rankings_df: pd.DataFrame, best: Dict, initial_capital: float) -> None:
    images_dir = track_root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    if trades_df.empty:
        return

    temp = trades_df.copy()
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"])
    temp["date"] = temp["exit_ts"].dt.date

    equity = initial_capital + temp["pnl"].cumsum()
    peak = equity.cummax()
    drawdown = np.where(peak > 0, ((peak - equity) / peak) * 100.0, 0.0)

    # Equity + drawdown
    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax1.plot(temp["exit_ts"], equity, color="#0f766e", linewidth=2.0, label="Equity")
    ax1.plot(temp["exit_ts"], peak, color="#14b8a6", linewidth=1.3, linestyle="--", label="Peak")
    ax1.set_title("Track A Short: Equity and Drawdown")
    ax1.set_xlabel("Timestamp")
    ax1.set_ylabel("Equity ($)")
    ax1.grid(alpha=0.2)

    ax2 = ax1.twinx()
    ax2.plot(temp["exit_ts"], drawdown, color="#dc2626", linewidth=1.2, alpha=0.9, label="Drawdown %")
    ax2.set_ylabel("Drawdown (%)")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left")
    fig.tight_layout()
    fig.savefig(images_dir / "track_a_short_equity_drawdown.png", dpi=220)
    plt.close(fig)

    # Daily pnl bars
    daily = temp.groupby("date", as_index=False)["pnl"].sum().sort_values("date")
    colors = np.where(daily["pnl"] >= 0, "#0891b2", "#f97316")

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(daily["date"].astype(str), daily["pnl"], color=colors, alpha=0.85)
    ax.axhline(0.0, color="#111827", linewidth=1.0)
    ax.set_title("Track A Short: Daily PnL")
    ax.set_xlabel("Date")
    ax.set_ylabel("PnL ($)")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(images_dir / "track_a_short_daily_pnl.png", dpi=220)
    plt.close(fig)

    # Ranking scatter
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(
        rankings_df["sharpe_daily_annualized"],
        rankings_df["score"],
        c=rankings_df["max_drawdown_pct"],
        cmap="viridis_r",
        alpha=0.75,
    )
    ax.set_title("Track A Short: Score vs Sharpe (color = max DD%)")
    ax.set_xlabel("Sharpe (daily annualized)")
    ax.set_ylabel("Composite score")
    ax.grid(alpha=0.2)
    cbar = plt.colorbar(ax.collections[0], ax=ax)
    cbar.set_label("Max drawdown %")
    fig.tight_layout()
    fig.savefig(images_dir / "track_a_short_score_vs_sharpe.png", dpi=220)
    plt.close(fig)

    # One-page dashboard
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.4, 1.0], height_ratios=[1.1, 1.0])

    ax_eq = fig.add_subplot(gs[0, 0])
    ax_eq.plot(temp["exit_ts"], equity, color="#0f766e", linewidth=2.0)
    ax_eq.plot(temp["exit_ts"], peak, color="#14b8a6", linewidth=1.2, linestyle="--")
    ax_eq.set_title("Equity Path")
    ax_eq.set_ylabel("Equity ($)")
    ax_eq.grid(alpha=0.2)
    ax_eq_dd = ax_eq.twinx()
    ax_eq_dd.plot(temp["exit_ts"], drawdown, color="#dc2626", linewidth=1.0, alpha=0.8)
    ax_eq_dd.set_ylabel("Drawdown (%)")

    ax_daily = fig.add_subplot(gs[1, 0])
    ax_daily.bar(daily["date"].astype(str), daily["pnl"], color=colors, alpha=0.85)
    ax_daily.axhline(0.0, color="#111827", linewidth=1.0)
    ax_daily.set_title("Daily PnL")
    ax_daily.set_xlabel("Date")
    ax_daily.set_ylabel("PnL ($)")
    ax_daily.tick_params(axis="x", rotation=45)
    ax_daily.grid(alpha=0.2)

    ax_kpi = fig.add_subplot(gs[:, 1])
    ax_kpi.axis("off")
    lines = [
        "TRACK A SHORT SNAPSHOT",
        "",
        f"EMA: {best['fast']}/{best['slow']}",
        f"SL/TP/Risk: {best['stop_loss_pct']}% / {best['take_profit_pct']}% / {best['risk_pct']}%",
        "",
        f"Sharpe (annualized daily): {best['sharpe_daily_annualized']:.2f}",
        f"Return: {best['return_pct']:.2f}%",
        f"Max drawdown: {best['max_drawdown_pct']:.2f}%",
        f"Worst daily loss: {best['worst_daily_loss_pct']:.2f}%",
        f"Profit factor: {best['profit_factor']:.2f}",
        f"Win rate: {best['win_rate']:.2f}%",
        f"Total trades: {int(best['total_trades'])}",
        f"Trades/day: {best['trades_per_day']:.2f}",
        f"Expectancy/trade: ${best['expectancy']:.2f}",
        f"Total PnL: ${best['total_pnl']:.2f}",
        f"Composite score: {best['score']:.2f}",
        "",
        "Scoring priority:",
        "1) Sharpe ratio",
        "2) Return / quality",
        "3) FTMO-style risk limits",
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

    fig.tight_layout()
    fig.savefig(images_dir / "track_a_short_performance_dashboard.png", dpi=220)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track A short EMA optimizer")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/XAUUSD_1h_sample.csv"),
        help="Input OHLC CSV path.",
    )
    parser.add_argument("--initial-capital", type=float, default=10000.0, help="Initial capital in USD.")
    parser.add_argument("--top-n", type=int, default=20, help="Rows to print in console summary.")
    parser.add_argument(
        "--sample-size",
        type=float,
        default=0.10,
        help="Recent fraction of bars to evaluate (0-1]. Use 1.0 for full history.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    track_root = script_dir.parent
    reports_dir = track_root / "reports"
    images_dir = track_root / "images"
    reports_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    data_path = args.data
    if not data_path.is_absolute():
        data_path = Path.cwd() / data_path
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    df = load_data(data_path)

    if args.sample_size <= 0 or args.sample_size > 1:
        raise ValueError("--sample-size must be in (0, 1].")
    start_idx = int(len(df) * (1.0 - args.sample_size))
    df = df.iloc[start_idx:].copy().reset_index(drop=True)

    grid = parameter_grid()

    candidates: List[Dict] = []
    best_trades = pd.DataFrame()
    best_score = -1e18

    print(f"[Track A Short] Loaded {len(df):,} bars from {data_path} (recent {args.sample_size:.0%})")
    print(f"[Track A Short] Testing {len(grid)} parameter combinations...")

    for idx, params in enumerate(grid):
        trades_df, metrics = run_backtest(df, params, args.initial_capital)
        score = score_candidate(metrics)

        row = {
            "fast": params.fast,
            "slow": params.slow,
            "stop_loss_pct": params.stop_loss_pct,
            "take_profit_pct": params.take_profit_pct,
            "risk_pct": params.risk_pct,
            "score": score,
            **metrics,
        }
        candidates.append(row)

        if score > best_score:
            best_score = score
            best_trades = trades_df.copy()

        if (idx + 1) % max(1, len(grid) // 10) == 0:
            print(f"  progress: {idx + 1}/{len(grid)}")

    rankings = pd.DataFrame(candidates).sort_values("score", ascending=False).reset_index(drop=True)
    best = rankings.iloc[0].to_dict()

    rankings_path = reports_dir / "track_a_short_rankings.csv"
    best_json_path = reports_dir / "track_a_short_best_candidate.json"
    best_txt_path = reports_dir / "track_a_short_best_candidate.txt"
    best_trades_path = reports_dir / "track_a_short_best_trades.csv"

    rankings.to_csv(rankings_path, index=False)
    best_trades.to_csv(best_trades_path, index=False)
    best_json_path.write_text(json.dumps(best, indent=2))

    lines = [
        "Track A Short - Best Candidate",
        "",
        f"EMA: {int(best['fast'])}/{int(best['slow'])}",
        f"SL: {best['stop_loss_pct']}%",
        f"TP: {best['take_profit_pct']}%",
        f"Risk: {best['risk_pct']}%",
        "",
        f"Sharpe (daily annualized): {best['sharpe_daily_annualized']:.4f}",
        f"Return: {best['return_pct']:.2f}%",
        f"Max drawdown: {best['max_drawdown_pct']:.2f}%",
        f"Worst daily loss: {best['worst_daily_loss_pct']:.2f}%",
        f"Profit factor: {best['profit_factor']:.2f}",
        f"Win rate: {best['win_rate']:.2f}%",
        f"Trades: {int(best['total_trades'])}",
        f"Trades/day: {best['trades_per_day']:.2f}",
        f"Expectancy/trade: ${best['expectancy']:.2f}",
        f"Total PnL: ${best['total_pnl']:.2f}",
        f"Score: {best['score']:.2f}",
    ]
    best_txt_path.write_text("\n".join(lines))

    render_visuals(track_root, best_trades, rankings, best, args.initial_capital)

    print("\nTop candidates:")
    cols = [
        "fast",
        "slow",
        "stop_loss_pct",
        "take_profit_pct",
        "risk_pct",
        "sharpe_daily_annualized",
        "return_pct",
        "max_drawdown_pct",
        "worst_daily_loss_pct",
        "profit_factor",
        "score",
    ]
    print(rankings.loc[: args.top_n - 1, cols].to_string(index=True))

    print("\nSaved reports:")
    print(f"- {rankings_path}")
    print(f"- {best_json_path}")
    print(f"- {best_txt_path}")
    print(f"- {best_trades_path}")
    print("Saved images:")
    print(f"- {images_dir / 'track_a_short_equity_drawdown.png'}")
    print(f"- {images_dir / 'track_a_short_daily_pnl.png'}")
    print(f"- {images_dir / 'track_a_short_score_vs_sharpe.png'}")
    print(f"- {images_dir / 'track_a_short_performance_dashboard.png'}")


if __name__ == "__main__":
    main()
