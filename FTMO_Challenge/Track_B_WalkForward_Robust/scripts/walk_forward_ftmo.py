"""
Walk-forward FTMO validation for EMA crossover strategy.

This script avoids look-ahead bias by:
1) Optimizing parameters on a rolling training window.
2) Testing those parameters only on the next unseen window.
3) Concatenating only out-of-sample (OOS) results.

Outputs:
- FTMO_Challenge/wfv_fold_results.csv
- FTMO_Challenge/wfv_oos_trades.csv
- FTMO_Challenge/wfv_summary.json
- FTMO_Challenge/wfv_summary.txt
- FTMO_Challenge/wfv_oos_equity.png
- FTMO_Challenge/wfv_monte_carlo_paths.png
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
    initial_capital: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
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


def compute_metrics(trades_df: pd.DataFrame, initial_capital: float) -> Dict:
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

    win_rate = float((len(wins) / len(trades_df)) * 100.0)
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
    # Encourage FTMO compliance first, then profitability and quality.
    score = metrics["return_pct"]

    if metrics["max_drawdown_pct"] > 10.0:
        score -= (metrics["max_drawdown_pct"] - 10.0) * 8.0
    if metrics["worst_daily_loss_pct"] < -5.0:
        score -= abs(metrics["worst_daily_loss_pct"] + 5.0) * 10.0

    score += min(metrics["profit_factor"], 3.0) * 5.0
    score += min(metrics["win_rate"], 60.0) * 0.1
    return score


def param_grid() -> List[Params]:
    grid: List[Params] = []
    fasts = [8, 12]
    slows = [20, 50]
    sls = [0.5, 1.0]
    tps = [3.0, 5.0]
    risks = [0.5, 0.75]

    for f in fasts:
        for s in slows:
            if f >= s:
                continue
            for sl in sls:
                for tp in tps:
                    for r in risks:
                        grid.append(Params(f, s, sl, tp, r))
    return grid


def run_walk_forward(
    df: pd.DataFrame,
    initial_capital: float = 10000.0,
    train_bars: int = 24 * 365 * 2,
    test_bars: int = 24 * 120,
    step_bars: int = 24 * 120,
    max_folds: int = 12,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    grid = param_grid()

    fold_rows: List[Dict] = []
    oos_trades_all: List[pd.DataFrame] = []

    start = 0
    fold = 0

    while True:
        if fold >= max_folds:
            break
        train_start = start
        train_end = train_start + train_bars
        test_end = train_end + test_bars

        if test_end > len(df):
            break

        train_df = df.iloc[train_start:train_end].copy()
        test_df = df.iloc[train_end:test_end].copy()

        best_score = -1e18
        best_params = None
        best_train_metrics = None

        for p in grid:
            train_trades, _ = run_segment_backtest(train_df, p, initial_capital)
            m = compute_metrics(train_trades, initial_capital)
            s = score_train(m)
            if s > best_score:
                best_score = s
                best_params = p
                best_train_metrics = m

        test_trades, _ = run_segment_backtest(test_df, best_params, initial_capital)
        test_metrics = compute_metrics(test_trades, initial_capital)

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
        "folds": int(len(folds_df)),
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


def derive_recommendations(folds_df: pd.DataFrame, summary: Dict) -> str:
    if folds_df.empty:
        return "No folds were generated. Increase data or reduce window sizes."

    lines: List[str] = []
    lines.append("WALK-FORWARD PARAMETER RECOMMENDATIONS")
    lines.append("=" * 60)
    lines.append(f"Folds evaluated: {len(folds_df)}")
    lines.append("")

    cols = ["best_fast", "best_slow", "best_sl_pct", "best_tp_pct", "best_risk_pct"]
    top_sets = (
        folds_df.groupby(cols, as_index=False)
        .agg(
            selected_count=("fold", "count"),
            avg_test_return_pct=("test_return_pct", "mean"),
            avg_test_dd_pct=("test_max_dd_pct", "mean"),
            pass_rate=("test_ftmo_pass", "mean"),
        )
        .sort_values(["selected_count", "avg_test_return_pct"], ascending=[False, False])
    )

    lines.append("Most selected parameter sets across folds:")
    for _, r in top_sets.head(5).iterrows():
        lines.append(
            f"- EMA({int(r['best_fast'])}/{int(r['best_slow'])}), "
            f"SL {r['best_sl_pct']}%, TP {r['best_tp_pct']}%, Risk {r['best_risk_pct']}% | "
            f"selected {int(r['selected_count'])} folds | "
            f"avg OOS return {r['avg_test_return_pct']:.2f}% | "
            f"avg OOS DD {r['avg_test_dd_pct']:.2f}% | "
            f"fold pass rate {(r['pass_rate'] * 100):.1f}%"
        )

    lines.append("")
    lines.append("Overall OOS summary:")
    lines.append(f"- OOS return: {summary['oos_return_pct']:.2f}%")
    lines.append(f"- OOS max drawdown: {summary['oos_max_drawdown_pct']:.2f}%")
    lines.append(f"- OOS worst daily loss: {summary['oos_worst_daily_loss_pct']:.2f}%")
    lines.append(f"- OOS FTMO pass: {'YES' if summary['oos_ftmo_pass'] else 'NO'}")
    lines.append(f"- OOS Monte Carlo pass probability: {summary['mc_oos_pass_probability_pct']:.2f}%")
    lines.append("")
    lines.append("Use the most frequent top set as your default live candidate, then continue updating by fold.")

    return "\n".join(lines)


def monte_carlo_paths(
    trades_df: pd.DataFrame,
    initial_capital: float,
    runs: int = 1000,
) -> Tuple[np.ndarray, float]:
    if trades_df.empty:
        return np.zeros((0, 0)), 0.0

    pnls = trades_df["pnl"].to_numpy(dtype=float)
    n = len(pnls)

    paths = np.zeros((runs, n + 1), dtype=float)
    paths[:, 0] = initial_capital

    pass_count = 0

    for r in range(runs):
        sim = np.random.permutation(pnls)
        eq = initial_capital
        peak = initial_capital
        max_dd = 0.0

        for i, p in enumerate(sim, start=1):
            eq += p
            peak = max(peak, eq)
            dd = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
            paths[r, i] = eq

        if max_dd <= 10.0:
            pass_count += 1

    pass_prob = (pass_count / runs) * 100.0
    return paths, pass_prob


def plot_oos_equity(trades_df: pd.DataFrame, initial_capital: float, out_path: Path) -> None:
    if trades_df.empty:
        return

    eq = [initial_capital]
    peak = [initial_capital]
    cur = initial_capital
    cur_peak = initial_capital

    for p in trades_df["pnl"].to_numpy(dtype=float):
        cur += p
        cur_peak = max(cur_peak, cur)
        eq.append(cur)
        peak.append(cur_peak)

    x = np.arange(len(eq))

    plt.figure(figsize=(14, 6))
    plt.plot(x, eq, label="OOS Equity", linewidth=2, color="#1f77b4")
    plt.plot(x, peak, label="Running Peak", linewidth=1.5, linestyle="--", color="#ff7f0e")
    plt.fill_between(x, eq, peak, alpha=0.2, color="#d62728", label="Drawdown")
    plt.title("Walk-Forward OOS Equity Curve")
    plt.xlabel("Trade #")
    plt.ylabel("Equity ($)")
    plt.legend()
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

    mean_path = paths.mean(axis=0)
    plt.plot(mean_path, color="#111111", linewidth=2.2, label="Mean Path")
    plt.title("Monte Carlo Paths (OOS Trades Only)")
    plt.xlabel("Trade #")
    plt.ylabel("Equity ($)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def write_summary_txt(summary: Dict, out_path: Path, mc_pass_prob: float) -> None:
    lines = [
        "WALK-FORWARD FTMO SUMMARY",
        "=" * 60,
        f"Folds: {summary['folds']}",
        f"OOS Trades: {summary['oos_total_trades']}",
        f"OOS Total P&L: ${summary['oos_total_pnl']:.2f}",
        f"OOS Return: {summary['oos_return_pct']:.2f}%",
        f"OOS Max Drawdown: {summary['oos_max_drawdown_pct']:.2f}%",
        f"OOS Worst Daily Loss: {summary['oos_worst_daily_loss_pct']:.2f}%",
        f"OOS Win Rate: {summary['oos_win_rate']:.2f}%",
        f"OOS Profit Factor: {summary['oos_profit_factor']:.2f}",
        f"FTMO Pass (OOS): {'YES' if summary['oos_ftmo_pass'] else 'NO'}",
        f"Monte Carlo Pass Probability (OOS trades): {mc_pass_prob:.2f}%",
    ]
    out_path.write_text("\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Track B walk-forward FTMO validation.")
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

    folds_df, oos_trades_df, summary = run_walk_forward(
        df,
        initial_capital=10000.0,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        max_folds=max_folds,
    )

    folds_path = reports_dir / "wfv_fold_results.csv"
    oos_path = reports_dir / "wfv_oos_trades.csv"
    sum_json_path = reports_dir / "wfv_summary.json"
    sum_txt_path = reports_dir / "wfv_summary.txt"
    rec_txt_path = reports_dir / "wfv_recommendations.txt"
    eq_png_path = images_dir / "wfv_oos_equity.png"
    mc_png_path = images_dir / "wfv_monte_carlo_paths.png"

    folds_df.to_csv(folds_path, index=False)
    oos_trades_df.to_csv(oos_path, index=False)

    paths, mc_pass_prob = monte_carlo_paths(oos_trades_df, initial_capital=10000.0, runs=300)
    summary["mc_oos_pass_probability_pct"] = mc_pass_prob
    summary["window_config"] = {
        "train_years": float(args.train_years),
        "test_days": int(args.test_days),
        "step_days": int(args.step_days),
        "max_folds": int(args.max_folds),
        "actual_folds": int(len(folds_df)),
        "approx_oos_years": float((len(folds_df) * args.test_days) / 365.0),
    }

    sum_json_path.write_text(json.dumps(summary, indent=2))
    write_summary_txt(summary, sum_txt_path, mc_pass_prob)
    rec_txt_path.write_text(derive_recommendations(folds_df, summary))

    plot_oos_equity(oos_trades_df, initial_capital=10000.0, out_path=eq_png_path)
    plot_monte_carlo(paths, out_path=mc_png_path)

    print("Walk-forward run completed.")
    print(f"Saved: {folds_path}")
    print(f"Saved: {oos_path}")
    print(f"Saved: {sum_json_path}")
    print(f"Saved: {sum_txt_path}")
    print(f"Saved: {rec_txt_path}")
    print(f"Saved: {eq_png_path}")
    print(f"Saved: {mc_png_path}")
    print("")
    print(f"OOS FTMO pass: {summary['oos_ftmo_pass']}")
    print(f"OOS max DD: {summary['oos_max_drawdown_pct']:.2f}%")
    print(f"OOS worst daily loss: {summary['oos_worst_daily_loss_pct']:.2f}%")
    print(f"Monte Carlo OOS pass probability: {mc_pass_prob:.2f}%")


if __name__ == "__main__":
    main()
