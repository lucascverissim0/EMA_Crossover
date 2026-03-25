"""
Track A Short EMA walk-forward validation with Monte Carlo robustness.

Default methodology:
- Train window: 5 years
- Test window: 2 years
- Total horizon per fold: 7 years
- Step size: 1 year

Outputs:
- reports/short_wfv_fold_results.csv
- reports/short_wfv_oos_trades.csv
- reports/short_wfv_best_config.json
- reports/short_wfv_summary.json
- reports/short_wfv_summary.txt
- images/short_wfv_oos_equity.png
- images/short_wfv_monte_carlo.png
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

    if "Close" not in df.columns:
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


def run_segment_backtest(df: pd.DataFrame, params: Params, initial_capital: float) -> pd.DataFrame:
    data = build_short_signals(df, params.fast, params.slow)

    trades: List[Dict] = []
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

    return pd.DataFrame(trades)


def compute_metrics(trades_df: pd.DataFrame, initial_capital: float) -> Dict[str, float]:
    if trades_df.empty:
        return {
            "total_trades": 0.0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "worst_daily_loss_pct": 0.0,
            "profit_factor": 0.0,
            "sharpe_daily_annualized": 0.0,
            "ftmo_pass": 1.0,
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

    equity_daily = initial_capital + daily["pnl"].cumsum()
    daily_returns = equity_daily.pct_change().dropna()
    if daily_returns.empty or daily_returns.std() == 0:
        sharpe = 0.0
    else:
        sharpe = float((daily_returns.mean() / daily_returns.std()) * np.sqrt(252))

    ftmo_pass = 1.0 if (max_drawdown_pct <= 10.0 and worst_daily_loss_pct >= -5.0) else 0.0

    return {
        "total_trades": float(len(trades_df)),
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "return_pct": return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "worst_daily_loss_pct": worst_daily_loss_pct,
        "profit_factor": profit_factor,
        "sharpe_daily_annualized": sharpe,
        "ftmo_pass": ftmo_pass,
    }


def score_train(metrics: Dict[str, float]) -> float:
    score = metrics["sharpe_daily_annualized"] * 20.0
    score += metrics["return_pct"] * 1.2
    score += min(metrics["profit_factor"], 3.0) * 5.0

    if metrics["max_drawdown_pct"] > 10.0:
        score -= (metrics["max_drawdown_pct"] - 10.0) * 15.0
    if metrics["worst_daily_loss_pct"] < -5.0:
        score -= abs(metrics["worst_daily_loss_pct"] + 5.0) * 20.0

    return float(score)


def param_grid(quick_grid: bool = False) -> List[Params]:
    grid: List[Params] = []

    if quick_grid:
        fasts = [10, 12]
        slows = [26, 30, 40]
        sls = [0.5, 0.75]
        tps = [1.5, 2.0]
        risks = [0.25, 0.5]
    else:
        fasts = [8, 10, 12, 14]
        slows = [20, 26, 30, 40, 50]
        sls = [0.5, 0.75, 1.0]
        tps = [1.0, 1.5, 2.0]
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


def monte_carlo_paths(trades_df: pd.DataFrame, initial_capital: float, n_paths: int, n_trades: int, seed: int = 42) -> np.ndarray:
    if trades_df.empty:
        return np.zeros((0, 0))

    rng = np.random.default_rng(seed)
    returns = trades_df["pnl"].to_numpy(dtype=float)
    if len(returns) == 0:
        return np.zeros((0, 0))

    paths = np.zeros((n_paths, n_trades + 1), dtype=float)
    paths[:, 0] = initial_capital

    for i in range(n_paths):
        sample = rng.choice(returns, size=n_trades, replace=True)
        paths[i, 1:] = initial_capital + np.cumsum(sample)

    return paths


def oos_windows(df: pd.DataFrame, train_bars: int, test_bars: int, step_bars: int, max_folds: int):
    windows = []
    start = 0
    fold = 0
    while fold < max_folds:
        train_end = start + train_bars
        test_end = train_end + test_bars
        if test_end > len(df):
            break
        windows.append((fold, start, train_end, test_end))
        start += step_bars
        fold += 1
    return windows


def run_walk_forward(
    df: pd.DataFrame,
    initial_capital: float,
    train_years: float,
    test_years: float,
    step_years: float,
    max_folds: int,
    quick_grid: bool,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict, Params]:
    bars_per_year = int(24 * 365)
    train_bars = int(train_years * bars_per_year)
    test_bars = int(test_years * bars_per_year)
    step_bars = int(step_years * bars_per_year)

    windows = oos_windows(df, train_bars, test_bars, step_bars, max_folds)
    if not windows:
        raise ValueError("Not enough data for requested walk-forward windows.")

    grid = param_grid(quick_grid=quick_grid)
    print(f"[Short WFV] Testing {len(grid)} parameter combinations per fold")
    fold_rows: List[Dict] = []
    oos_trades_all: List[pd.DataFrame] = []

    best_global_params = None
    best_global_score = -1e18

    for fold, train_start, train_end, test_end in windows:
        train_df = df.iloc[train_start:train_end].copy()
        test_df = df.iloc[train_end:test_end].copy()
        print(f"[Short WFV] Fold {fold + 1}/{len(windows)} | train bars={len(train_df):,} | test bars={len(test_df):,}")

        best_params = None
        best_score = -1e18
        best_train = None

        for idx, params in enumerate(grid):
            train_trades = run_segment_backtest(train_df, params, initial_capital)
            train_metrics = compute_metrics(train_trades, initial_capital)
            score = score_train(train_metrics)
            if score > best_score:
                best_score = score
                best_params = params
                best_train = train_metrics
            if (idx + 1) % max(1, len(grid) // 4) == 0:
                print(f"  progress: {idx + 1}/{len(grid)}")

        test_trades = run_segment_backtest(test_df, best_params, initial_capital)
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
                "train_sharpe": best_train["sharpe_daily_annualized"],
                "train_return_pct": best_train["return_pct"],
                "train_max_dd_pct": best_train["max_drawdown_pct"],
                "test_sharpe": test_metrics["sharpe_daily_annualized"],
                "test_return_pct": test_metrics["return_pct"],
                "test_max_dd_pct": test_metrics["max_drawdown_pct"],
                "test_ftmo_pass": int(test_metrics["ftmo_pass"]),
                "test_total_trades": int(test_metrics["total_trades"]),
            }
        )

        if best_score > best_global_score:
            best_global_score = best_score
            best_global_params = best_params

    folds_df = pd.DataFrame(fold_rows)
    oos_trades_df = pd.concat(oos_trades_all, ignore_index=True) if oos_trades_all else pd.DataFrame()
    oos_metrics = compute_metrics(oos_trades_df, initial_capital)

    summary = {
        "train_years": train_years,
        "test_years": test_years,
        "step_years": step_years,
        "horizon_years_per_fold": train_years + test_years,
        "folds": int(len(folds_df)),
        "fold_pass_rate_pct": float(folds_df["test_ftmo_pass"].mean() * 100.0),
        "selected": {
            "fast": best_global_params.fast,
            "slow": best_global_params.slow,
            "sl_pct": best_global_params.stop_loss_pct,
            "tp_pct": best_global_params.take_profit_pct,
            "risk_pct": best_global_params.risk_pct,
        },
        "oos_trades": int(oos_metrics["total_trades"]),
        "oos_sharpe_daily_annualized": float(oos_metrics["sharpe_daily_annualized"]),
        "oos_return_pct": float(oos_metrics["return_pct"]),
        "oos_max_drawdown_pct": float(oos_metrics["max_drawdown_pct"]),
        "oos_worst_daily_loss_pct": float(oos_metrics["worst_daily_loss_pct"]),
        "oos_profit_factor": float(oos_metrics["profit_factor"]),
        "oos_ftmo_pass": bool(oos_metrics["ftmo_pass"] > 0.5),
    }

    return folds_df, oos_trades_df, summary, best_global_params


def plot_oos_equity(oos_trades_df: pd.DataFrame, out_path: Path, initial_capital: float) -> None:
    if oos_trades_df.empty:
        return

    temp = oos_trades_df.copy()
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"])
    temp = temp.sort_values("exit_ts")
    equity = initial_capital + temp["pnl"].cumsum()
    peak = equity.cummax()
    dd = np.where(peak > 0, ((peak - equity) / peak) * 100.0, 0.0)

    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax1.plot(temp["exit_ts"], equity, color="#0f766e", linewidth=2.0, label="OOS equity")
    ax1.plot(temp["exit_ts"], peak, color="#14b8a6", linewidth=1.2, linestyle="--", label="Peak")
    ax1.set_title("Short WFV OOS Equity")
    ax1.set_xlabel("Timestamp")
    ax1.set_ylabel("Equity ($)")
    ax1.grid(alpha=0.2)

    ax2 = ax1.twinx()
    ax2.plot(temp["exit_ts"], dd, color="#dc2626", linewidth=1.0, alpha=0.9, label="Drawdown %")
    ax2.set_ylabel("Drawdown (%)")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left")

    fig.tight_layout()
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def plot_monte_carlo(paths: np.ndarray, out_path: Path, initial_capital: float) -> Tuple[float, float]:
    if paths.size == 0:
        return 0.0, 0.0

    final = paths[:, -1]
    pass_prob = float(np.mean(final > initial_capital) * 100.0)
    median_ret = float((np.median(final) / initial_capital - 1.0) * 100.0)

    p10 = np.percentile(paths, 10, axis=0)
    p25 = np.percentile(paths, 25, axis=0)
    p50 = np.percentile(paths, 50, axis=0)
    p75 = np.percentile(paths, 75, axis=0)
    p90 = np.percentile(paths, 90, axis=0)
    x = np.arange(paths.shape[1])

    plt.figure(figsize=(14, 6))
    plt.fill_between(x, p10, p90, alpha=0.18, color="#93c5fd", label="10-90 percentile")
    plt.fill_between(x, p25, p75, alpha=0.3, color="#3b82f6", label="25-75 percentile")
    plt.plot(x, p50, color="#111827", linewidth=2.0, label="Median")
    plt.axhline(initial_capital, linestyle="--", color="#16a34a", linewidth=1.3, label="Break-even")
    plt.title("Short WFV Monte Carlo on OOS Trade Distribution")
    plt.xlabel("Trade #")
    plt.ylabel("Equity ($)")
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()

    return pass_prob, median_ret


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Short EMA walk-forward + Monte Carlo")
    parser.add_argument("--data", type=Path, default=Path("data/XAUUSD_1h_sample.csv"), help="OHLC CSV path.")
    parser.add_argument("--initial-capital", type=float, default=10000.0, help="Initial capital.")
    parser.add_argument("--train-years", type=float, default=5.0, help="Training years per fold.")
    parser.add_argument("--test-years", type=float, default=2.0, help="Test years per fold.")
    parser.add_argument("--step-years", type=float, default=1.0, help="Step years between folds.")
    parser.add_argument("--max-folds", type=int, default=4, help="Max folds.")
    parser.add_argument("--mc-paths", type=int, default=2000, help="Monte Carlo paths.")
    parser.add_argument("--quick-grid", action="store_true", help="Use smaller parameter grid for faster exploration.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    track_root = script_dir.parent
    reports_dir = track_root / "reports"
    images_dir = track_root / "images"
    reports_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    data_path = args.data if args.data.is_absolute() else (Path.cwd() / args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    df = load_data(data_path)
    folds_df, oos_trades_df, summary, _ = run_walk_forward(
        df,
        initial_capital=args.initial_capital,
        train_years=args.train_years,
        test_years=args.test_years,
        step_years=args.step_years,
        max_folds=args.max_folds,
        quick_grid=args.quick_grid,
    )

    mc_paths = monte_carlo_paths(
        oos_trades_df,
        initial_capital=args.initial_capital,
        n_paths=args.mc_paths,
        n_trades=max(int(len(oos_trades_df)), 1),
    )
    mc_pass_prob, mc_median_ret = plot_monte_carlo(
        mc_paths,
        images_dir / "short_wfv_monte_carlo.png",
        initial_capital=args.initial_capital,
    )

    summary["quick_grid"] = bool(args.quick_grid)
    summary["mc_paths"] = int(args.mc_paths)
    summary["mc_profitability_probability_pct"] = mc_pass_prob
    summary["mc_median_return_pct"] = mc_median_ret

    folds_df.to_csv(reports_dir / "short_wfv_fold_results.csv", index=False)
    oos_trades_df.to_csv(reports_dir / "short_wfv_oos_trades.csv", index=False)
    (reports_dir / "short_wfv_best_config.json").write_text(json.dumps(summary["selected"], indent=2))
    (reports_dir / "short_wfv_summary.json").write_text(json.dumps(summary, indent=2))

    lines = [
        "Track A Short - Walk-Forward Summary",
        "",
        f"Data: {data_path}",
        f"Train/Test/Step (years): {args.train_years}/{args.test_years}/{args.step_years}",
        f"Horizon per fold: {summary['horizon_years_per_fold']} years",
        f"Folds: {summary['folds']}",
        f"Fold FTMO pass rate: {summary['fold_pass_rate_pct']:.2f}%",
        "",
        f"Selected params: EMA({summary['selected']['fast']}/{summary['selected']['slow']}), "
        f"SL {summary['selected']['sl_pct']}%, TP {summary['selected']['tp_pct']}%, Risk {summary['selected']['risk_pct']}%",
        f"OOS trades: {summary['oos_trades']}",
        f"OOS Sharpe: {summary['oos_sharpe_daily_annualized']:.3f}",
        f"OOS return: {summary['oos_return_pct']:.2f}%",
        f"OOS max drawdown: {summary['oos_max_drawdown_pct']:.2f}%",
        f"OOS worst daily loss: {summary['oos_worst_daily_loss_pct']:.2f}%",
        f"OOS profit factor: {summary['oos_profit_factor']:.2f}",
        f"OOS FTMO pass: {'YES' if summary['oos_ftmo_pass'] else 'NO'}",
        "",
        f"Monte Carlo paths: {summary['mc_paths']}",
        f"MC profitability probability: {summary['mc_profitability_probability_pct']:.2f}%",
        f"MC median return: {summary['mc_median_return_pct']:.2f}%",
    ]
    (reports_dir / "short_wfv_summary.txt").write_text("\n".join(lines))

    plot_oos_equity(
        oos_trades_df,
        images_dir / "short_wfv_oos_equity.png",
        initial_capital=args.initial_capital,
    )

    print("Saved reports:")
    print(f"- {reports_dir / 'short_wfv_fold_results.csv'}")
    print(f"- {reports_dir / 'short_wfv_oos_trades.csv'}")
    print(f"- {reports_dir / 'short_wfv_best_config.json'}")
    print(f"- {reports_dir / 'short_wfv_summary.json'}")
    print(f"- {reports_dir / 'short_wfv_summary.txt'}")
    print("Saved images:")
    print(f"- {images_dir / 'short_wfv_oos_equity.png'}")
    print(f"- {images_dir / 'short_wfv_monte_carlo.png'}")


if __name__ == "__main__":
    main()
