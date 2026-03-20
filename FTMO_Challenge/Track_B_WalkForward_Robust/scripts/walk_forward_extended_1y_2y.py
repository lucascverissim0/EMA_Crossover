"""
Extended Walk-Forward Validation (1yr train / 2yr test, 4 folds).

This script performs rigorous walk-forward validation with NO look-ahead bias using:
- 1 year training window
- 2 year test window (out-of-sample evaluation)
- 1 year step (rolling by 1 year each fold)
- 4 total folds = ~7 years of data required

This ensures we avoid optimizing for future data and provides robust stress-testing
over extended periods.

Outputs:
- wfv_extended_fold_results.csv        (fold-by-fold metrics)
- wfv_extended_oos_trades.csv          (all OOS trades)
- wfv_extended_summary.json/txt        (aggregate stats)
- wfv_extended_monte_carlo_*.png       (Monte Carlo simulations)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import sys

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
    df = pd.read_csv(csv_path)
    first_col = df.columns[0]
    df[first_col] = pd.to_datetime(df[first_col])
    df = df.rename(columns={first_col: "timestamp"})
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def build_signals(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    out = df.copy()
    out["fast_ema"] = out["Close"].ewm(span=fast, adjust=False).mean()
    out["slow_ema"] = out["Close"].ewm(span=slow, adjust=False).mean()
    out["signal"] = (out["fast_ema"] > out["slow_ema"]).astype(int)
    out["signal_diff"] = out["signal"].diff().fillna(0)
    return out


def run_segment_backtest(
    df: pd.DataFrame,
    params: Params,
    initial_capital: float = 10000.0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Run backtest on a segment of data."""
    data = build_signals(df, params.fast, params.slow)
    trades: List[Dict] = []
    equity_points: List[Dict] = []

    capital = initial_capital
    peak = initial_capital
    in_pos = False
    entry_price = 0.0
    entry_ts = None
    position_size = 0.0

    equity_points.append({"timestamp": data["timestamp"].iloc[0], "equity": capital, "peak": peak})

    for i in range(1, len(data)):
        row = data.iloc[i]
        price = float(row["Close"])
        ts = row["timestamp"]

        if not in_pos and row["signal_diff"] > 0:
            in_pos = True
            entry_price = price
            entry_ts = ts
            risk_dollars = capital * (params.risk_pct / 100.0)
            stop_move = entry_price * (params.stop_loss_pct / 100.0)
            if stop_move <= 0:
                continue
            position_size = risk_dollars / stop_move
            continue

        if in_pos:
            pnl_pct = ((price - entry_price) / entry_price) * 100.0
            reason = None
            exit_price = price

            if pnl_pct <= -params.stop_loss_pct:
                reason = "Stop Loss"
                exit_price = entry_price * (1.0 - params.stop_loss_pct / 100.0)
            elif pnl_pct >= params.take_profit_pct:
                reason = "Take Profit"
                exit_price = entry_price * (1.0 + params.take_profit_pct / 100.0)
            elif row["signal_diff"] < 0:
                reason = "Sell Signal"

            if reason is not None:
                pnl = position_size * (exit_price - entry_price)
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
                in_pos = False
                equity_points.append({"timestamp": ts, "equity": capital, "peak": peak})

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_points)
    return trades_df, equity_df


def compute_metrics(trades_df: pd.DataFrame, initial_capital: float = 10000.0) -> Dict:
    """Compute FTMO compliance and performance metrics."""
    if trades_df.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "worst_daily_loss_pct": 0.0,
            "profit_factor": 0.0,
            "ftmo_pass": True,
        }

    pnl = trades_df["pnl"]
    total_pnl = float(pnl.sum())
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    win_rate = float((len(wins) / len(trades_df)) * 100.0) if len(trades_df) > 0 else 0.0
    return_pct = (total_pnl / initial_capital) * 100.0

    max_drawdown_pct = float(trades_df["drawdown_pct"].max())

    temp = trades_df.copy()
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"])
    temp["date"] = temp["exit_ts"].dt.date
    daily = temp.groupby("date", as_index=False)["pnl"].sum()
    daily["daily_loss_pct"] = (daily["pnl"] / initial_capital) * 100.0
    worst_daily_loss_pct = float(daily["daily_loss_pct"].min()) if not daily.empty else 0.0

    gross_win = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 0.0

    ftmo_pass = (max_drawdown_pct <= 10.0) and (worst_daily_loss_pct >= -5.0)

    return {
        "total_trades": int(len(trades_df)),
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "return_pct": return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "worst_daily_loss_pct": worst_daily_loss_pct,
        "profit_factor": profit_factor,
        "ftmo_pass": ftmo_pass,
    }


def score_train(metrics: Dict) -> float:
    """Score training metrics for parameter selection."""
    score = metrics["return_pct"]

    if metrics["max_drawdown_pct"] > 10.0:
        score -= (metrics["max_drawdown_pct"] - 10.0) * 8.0
    if metrics["worst_daily_loss_pct"] < -5.0:
        score -= abs(metrics["worst_daily_loss_pct"] + 5.0) * 10.0

    score += min(metrics["profit_factor"], 3.0) * 5.0
    score += min(metrics["win_rate"], 60.0) * 0.1
    return score


def param_grid() -> List[Params]:
    """Generate parameter search grid with drawdown-aware risk settings."""
    grid: List[Params] = []
    fasts = [8, 10, 12]
    slows = [20, 26, 50]
    sls = [0.75, 1.0]
    tps = [3.0, 4.0, 5.0]
    risks = [0.25, 0.35, 0.5]

    for f in fasts:
        for s in slows:
            if f >= s:
                continue
            for sl in sls:
                for tp in tps:
                    for r in risks:
                        grid.append(Params(f, s, sl, tp, r))
    return grid


def run_walk_forward_extended(
    df: pd.DataFrame,
    initial_capital: float = 10000.0,
    train_bars: int = 24 * 365,         # 1 year
    test_bars: int = 24 * 365 * 2,      # 2 years
    step_bars: int = 24 * 365,          # 1 year step
    max_folds: int | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Run extended walk-forward validation.
    
    Args:
        df: DataFrame with OHLCV data
        initial_capital: Starting capital
        train_bars: Training window size (1 year = 8760 hourly bars)
        test_bars: Test window size (2 years = 17520 hourly bars)
        step_bars: Rolling step (1 year = 8760 hourly bars)
        max_folds: Maximum number of folds. When None, use all possible folds.
    
    Returns:
        (folds_df, oos_trades_df, summary_dict)
    """
    grid = param_grid()
    print(f"[WFV] Parameter grid has {len(grid)} combinations")
    print(f"[WFV] Data length: {len(df)} bars")

    required = train_bars + test_bars
    if len(df) < required:
        raise ValueError(
            f"Insufficient data for one fold: need at least {required} bars, got {len(df)}"
        )

    possible_folds = ((len(df) - required) // step_bars) + 1
    fold_limit = possible_folds if max_folds is None else min(max_folds, possible_folds)
    print(
        f"[WFV] Train: {train_bars} bars | Test: {test_bars} bars | Step: {step_bars} bars | "
        f"Folds: {fold_limit}/{possible_folds}"
    )

    fold_rows: List[Dict] = []
    oos_trades_all: List[pd.DataFrame] = []

    start = 0
    fold = 0

    while True:
        if fold >= fold_limit:
            break

        train_start = start
        train_end = train_start + train_bars
        test_end = train_end + test_bars

        if test_end > len(df):
            print(f"[WFV] Fold {fold}: Insufficient data (test_end={test_end} > len={len(df)}). Stopping.")
            break

        train_df = df.iloc[train_start:train_end].copy()
        test_df = df.iloc[train_end:test_end].copy()

        print(f"\n[WFV] Fold {fold}:")
        print(f"  Train: {train_df['timestamp'].iloc[0]} to {train_df['timestamp'].iloc[-1]}")
        print(f"  Test:  {test_df['timestamp'].iloc[0]} to {test_df['timestamp'].iloc[-1]}")

        best_score = -1e18
        best_params = None
        best_train_metrics = None

        # Optimize on training window
        for p in grid:
            train_trades, _ = run_segment_backtest(train_df, p, initial_capital)
            m = compute_metrics(train_trades, initial_capital)
            s = score_train(m)
            if s > best_score:
                best_score = s
                best_params = p
                best_train_metrics = m

        # Test on unseen test window
        test_trades, _ = run_segment_backtest(test_df, best_params, initial_capital)
        test_metrics = compute_metrics(test_trades, initial_capital)

        print(f"  Best params: EMA({best_params.fast}/{best_params.slow}), SL {best_params.stop_loss_pct}%, TP {best_params.take_profit_pct}%, Risk {best_params.risk_pct}%")
        print(f"  Train: {best_train_metrics['return_pct']:.2f}% return, {best_train_metrics['max_drawdown_pct']:.2f}% DD")
        print(f"  Test OOS: {test_metrics['return_pct']:.2f}% return, {test_metrics['max_drawdown_pct']:.2f}% DD, {test_metrics['total_trades']} trades")

        if not test_trades.empty:
            test_trades = test_trades.copy()
            test_trades["fold"] = fold
            test_trades["fast"] = best_params.fast
            test_trades["slow"] = best_params.slow
            test_trades["stop_loss_pct"] = best_params.stop_loss_pct
            test_trades["take_profit_pct"] = best_params.take_profit_pct
            test_trades["risk_pct"] = best_params.risk_pct
            oos_trades_all.append(test_trades)

        fold_rows.append(
            {
                "fold": fold,
                "train_start": str(train_df["timestamp"].iloc[0]),
                "train_end": str(train_df["timestamp"].iloc[-1]),
                "test_start": str(test_df["timestamp"].iloc[0]),
                "test_end": str(test_df["timestamp"].iloc[-1]),
                "best_fast": best_params.fast,
                "best_slow": best_params.slow,
                "best_sl_pct": best_params.stop_loss_pct,
                "best_tp_pct": best_params.take_profit_pct,
                "best_risk_pct": best_params.risk_pct,
                "train_score": best_score,
                "train_return_pct": best_train_metrics["return_pct"],
                "train_max_dd_pct": best_train_metrics["max_drawdown_pct"],
                "test_return_pct": test_metrics["return_pct"],
                "test_max_dd_pct": test_metrics["max_drawdown_pct"],
                "test_worst_daily_loss_pct": test_metrics["worst_daily_loss_pct"],
                "test_trades": test_metrics["total_trades"],
                "test_ftmo_pass": test_metrics["ftmo_pass"],
            }
        )

        fold += 1
        start += step_bars

    folds_df = pd.DataFrame(fold_rows)
    oos_trades_df = pd.concat(oos_trades_all, ignore_index=True) if oos_trades_all else pd.DataFrame()

    oos_metrics = compute_metrics(oos_trades_df, initial_capital)
    summary = {
        "total_folds": int(len(folds_df)),
        "oos_total_trades": int(oos_metrics["total_trades"]),
        "oos_total_pnl": float(oos_metrics["total_pnl"]),
        "oos_return_pct": float(oos_metrics["return_pct"]),
        "oos_max_drawdown_pct": float(oos_metrics["max_drawdown_pct"]),
        "oos_worst_daily_loss_pct": float(oos_metrics["worst_daily_loss_pct"]),
        "oos_win_rate": float(oos_metrics["win_rate"]),
        "oos_profit_factor": float(oos_metrics["profit_factor"]),
        "oos_ftmo_pass": bool(oos_metrics["ftmo_pass"]),
    }

    return folds_df, oos_trades_df, summary


def monte_carlo_simulation(trades_df: pd.DataFrame, num_sims: int = 10000) -> Tuple[np.ndarray, Dict]:
    """Run Monte Carlo analysis on trade PnL."""
    if trades_df.empty or len(trades_df) == 0:
        return np.array([]), {"pass_prob": 0.0}

    pnls = trades_df["pnl"].values
    num_trades = len(pnls)
    paths = []

    for _ in range(num_sims):
        sampled = np.random.choice(pnls, size=num_trades, replace=True)
        equity_path = 10000.0 + np.cumsum(sampled)
        paths.append(equity_path)

    paths = np.array(paths)
    final_equities = paths[:, -1]

    pass_prob = np.sum(final_equities > 10000.0) / num_sims

    return paths, {"pass_prob": float(pass_prob), "median_final": float(np.median(final_equities))}


def create_mc_plots(oos_trades_df: pd.DataFrame, output_dir: Path, track_name: str = "Track"):
    """Create Monte Carlo visualization."""
    if oos_trades_df.empty:
        print(f"[MC] No trades for {track_name} MC plots")
        return

    paths, mc_stats = monte_carlo_simulation(oos_trades_df)

    if len(paths) == 0:
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Plot sample paths
    for i in range(min(100, len(paths))):
        ax1.plot(paths[i], alpha=0.1, color="blue")
    ax1.axhline(y=10000, color="green", linestyle="--", label="Initial Capital")
    ax1.set_xlabel("Trade Number")
    ax1.set_ylabel("Equity")
    ax1.set_title(f"MC Paths ({track_name})")
    ax1.legend()
    ax1.grid()

    # Plot pass probability
    final_equities = paths[:, -1]
    ax2.hist(final_equities, bins=50, alpha=0.7, edgecolor="black")
    ax2.axvline(x=10000, color="red", linestyle="--", label="Break-even")
    ax2.set_xlabel("Final Equity")
    ax2.set_ylabel("Frequency")
    ax2.set_title(f"MC Pass Probability: {mc_stats['pass_prob']*100:.1f}%")
    ax2.legend()
    ax2.grid()

    plt.tight_layout()
    output_file = output_dir / f"wfv_extended_monte_carlo_{track_name.lower()}.png"
    plt.savefig(output_file, dpi=100, bbox_inches="tight")
    plt.close()

    print(f"[MC] Saved: {output_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        default="data/XAUUSD_1h_sample.csv",
        help="Path to OHLCV CSV data",
    )
    parser.add_argument(
        "--output-dir",
        default="FTMO_Challenge/Track_B_WalkForward_Robust/reports",
        help="Output directory for results",
    )
    parser.add_argument(
        "--track",
        default="Track_B_Extended",
        help="Track name for reporting",
    )
    parser.add_argument(
        "--max-folds",
        type=int,
        default=None,
        help="Optional cap on number of folds. Default uses all possible folds.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Extended Walk-Forward Validation (1yr/2yr, 4 folds)")
    print(f"{'='*60}")
    print(f"Data: {args.data}")
    print(f"Track: {args.track}")

    df = load_data(Path(args.data))
    print(f"Loaded {len(df)} bars from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")

    folds_df, oos_trades_df, summary = run_walk_forward_extended(
        df,
        initial_capital=10000.0,
        train_bars=24 * 365,         # 1 year
        test_bars=24 * 365 * 2,      # 2 years
        step_bars=24 * 365,          # 1 year step
        max_folds=args.max_folds,
    )

    # Save folds results
    folds_file = output_dir / "wfv_extended_fold_results.csv"
    folds_df.to_csv(folds_file, index=False)
    print(f"\n[Results] Saved: {folds_file}")

    # Save OOS trades
    trades_file = output_dir / "wfv_extended_oos_trades.csv"
    oos_trades_df.to_csv(trades_file, index=False)
    print(f"[Results] Saved: {trades_file}")

    # Save summary JSON
    summary_json = output_dir / "wfv_extended_summary.json"
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[Results] Saved: {summary_json}")

    # Results summary
    print(f"\n{'='*60}")
    print(f"EXTENDED WALK-FORWARD RESULTS ({args.track})")
    print(f"{'='*60}")
    print(f"Total Folds: {summary['total_folds']}")
    print(f"OOS Trades: {summary['oos_total_trades']}")
    print(f"OOS Return: {summary['oos_return_pct']:.2f}%")
    print(f"OOS Max Drawdown: {summary['oos_max_drawdown_pct']:.2f}%")
    print(f"OOS Worst Daily Loss: {summary['oos_worst_daily_loss_pct']:.2f}%")
    print(f"OOS Win Rate: {summary['oos_win_rate']:.1f}%")
    print(f"OOS Profit Factor: {summary['oos_profit_factor']:.2f}")
    print(f"FTMO Pass: {'✓ YES' if summary['oos_ftmo_pass'] else '✗ NO'}")
    print()

    # Monte Carlo
    create_mc_plots(oos_trades_df, output_dir, args.track)

    print(f"\n[Complete] Extended WFV analysis finished.\n")


if __name__ == "__main__":
    main()
