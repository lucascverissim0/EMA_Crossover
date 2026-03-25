"""
Track B Short: Walk-forward EMA with ML trade filtering.

Method:
1) Generate short EMA candidate trades.
2) Build entry-time features for each candidate.
3) Train Gradient Boosting classifier on each fold's train window.
4) Keep only trades with predicted win probability >= threshold.
5) Evaluate OOS performance and Monte Carlo robustness.

Outputs:
- reports/track_b_short_ml_fold_results.csv
- reports/track_b_short_ml_oos_trades.csv
- reports/track_b_short_ml_oos_candidates.csv
- reports/track_b_short_ml_summary.json
- reports/track_b_short_ml_summary.txt
- reports/track_b_short_ml_feature_importance.csv
- images/track_b_short_ml_oos_equity.png
- images/track_b_short_ml_monte_carlo.png
- images/track_b_short_ml_feature_importance.png
- images/track_b_short_ml_probability_quality.png
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
from sklearn.ensemble import GradientBoostingClassifier


@dataclass
class Params:
    fast: int
    slow: int
    stop_loss_pct: float
    take_profit_pct: float
    risk_pct: float


FEATURE_COLUMNS = [
    "atr14_pct",
    "rsi14",
    "ema_spread_pct",
    "zscore20",
    "ret_1",
    "ret_6",
    "bar_range_pct",
    "volume_ratio",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]


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
    if "Volume" not in out.columns:
        out["Volume"] = 1.0
    return out


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    close = out["Close"].astype(float)
    high = out["High"].astype(float) if "High" in out.columns else close
    low = out["Low"].astype(float) if "Low" in out.columns else close

    prev_close = close.shift(1)
    tr_components = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    )
    tr = tr_components.max(axis=1)
    atr14 = tr.rolling(14).mean()
    out["atr14_pct"] = (atr14 / close) * 100.0

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out["rsi14"] = 100.0 - (100.0 / (1.0 + rs))

    ema20 = close.ewm(span=20, adjust=False).mean()
    std20 = close.rolling(20).std()
    out["zscore20"] = (close - ema20) / std20.replace(0.0, np.nan)

    out["ret_1"] = close.pct_change(1) * 100.0
    out["ret_6"] = close.pct_change(6) * 100.0
    out["bar_range_pct"] = ((high - low) / close.replace(0.0, np.nan)) * 100.0
    out["volume_ratio"] = out["Volume"] / out["Volume"].rolling(20).mean().replace(0.0, np.nan)

    hour = out["timestamp"].dt.hour.astype(float)
    dow = out["timestamp"].dt.dayofweek.astype(float)
    out["hour_sin"] = np.sin(2.0 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2.0 * np.pi * hour / 24.0)
    out["dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    out["dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)

    return out


def build_short_signals(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    out = df.copy()
    out["fast_ema"] = out["Close"].ewm(span=fast, adjust=False).mean()
    out["slow_ema"] = out["Close"].ewm(span=slow, adjust=False).mean()
    out["ema_spread_pct"] = ((out["fast_ema"] - out["slow_ema"]) / out["Close"]) * 100.0
    out["short_signal"] = (out["fast_ema"] < out["slow_ema"]).astype(int)
    out["signal_diff"] = out["short_signal"].diff().fillna(0.0)
    return out


def generate_trade_candidates(df: pd.DataFrame, params: Params) -> pd.DataFrame:
    data = build_short_signals(df, params.fast, params.slow)

    closes = data["Close"].to_numpy(dtype=float)
    signal_diffs = data["signal_diff"].to_numpy(dtype=float)
    timestamps = data["timestamp"].to_numpy()

    feature_matrix = data[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).to_numpy(dtype=float)

    candidates: List[Dict[str, float]] = []
    in_short = False
    entry_price = 0.0
    entry_ts = None
    entry_idx = -1

    for i in range(1, len(data)):
        price = closes[i]
        ts = timestamps[i]
        sig_diff = signal_diffs[i]

        if not in_short and sig_diff > 0:
            in_short = True
            entry_price = price
            entry_ts = ts
            entry_idx = i
            continue

        if in_short:
            move_pct = ((entry_price - price) / entry_price) * 100.0
            reason = None
            exit_price = price
            realized_move_pct = move_pct

            if move_pct <= -params.stop_loss_pct:
                reason = "Stop Loss"
                exit_price = entry_price * (1.0 + params.stop_loss_pct / 100.0)
                realized_move_pct = -params.stop_loss_pct
            elif move_pct >= params.take_profit_pct:
                reason = "Take Profit"
                exit_price = entry_price * (1.0 - params.take_profit_pct / 100.0)
                realized_move_pct = params.take_profit_pct
            elif sig_diff < 0:
                reason = "Cover Signal"

            if reason is not None:
                feats = feature_matrix[entry_idx]
                if not np.isnan(feats).any() and np.isfinite(feats).all():
                    row = {
                        "entry_ts": entry_ts,
                        "exit_ts": ts,
                        "entry_price": float(entry_price),
                        "exit_price": float(exit_price),
                        "move_pct": float(realized_move_pct),
                        "reason": reason,
                        "is_win": int(realized_move_pct > 0.0),
                    }
                    for j, col in enumerate(FEATURE_COLUMNS):
                        row[col] = float(feats[j])
                    candidates.append(row)
                in_short = False

    if not candidates:
        return pd.DataFrame()

    out = pd.DataFrame(candidates)
    out["entry_ts"] = pd.to_datetime(out["entry_ts"])
    out["exit_ts"] = pd.to_datetime(out["exit_ts"])
    out = out.sort_values("exit_ts").reset_index(drop=True)
    return out


def simulate_filtered_trades(
    candidates_df: pd.DataFrame,
    params: Params,
    initial_capital: float,
    threshold: float,
    proba_col: str = "win_proba",
) -> pd.DataFrame:
    if candidates_df.empty:
        return pd.DataFrame()

    temp = candidates_df.sort_values("exit_ts").copy()
    if proba_col not in temp.columns:
        temp[proba_col] = 1.0

    accepted = temp[temp[proba_col] >= threshold].copy()
    if accepted.empty:
        return pd.DataFrame()

    trades: List[Dict[str, float]] = []
    capital = initial_capital
    peak = initial_capital

    for _, row in accepted.iterrows():
        risk_dollars = capital * (params.risk_pct / 100.0)
        pnl = risk_dollars * (float(row["move_pct"]) / params.stop_loss_pct)
        capital += pnl
        peak = max(peak, capital)
        dd_pct = ((peak - capital) / peak) * 100.0 if peak > 0 else 0.0

        trades.append(
            {
                "entry_ts": row["entry_ts"],
                "exit_ts": row["exit_ts"],
                "entry_price": float(row["entry_price"]),
                "exit_price": float(row["exit_price"]),
                "move_pct": float(row["move_pct"]),
                "pnl": float(pnl),
                "reason": row["reason"],
                "equity_after": float(capital),
                "drawdown_pct": float(dd_pct),
                "win_proba": float(row[proba_col]),
            }
        )

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
        sharpe = float((daily_returns.mean() / daily_returns.std()) * np.sqrt(252.0))

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
    # Sharpe-first objective with light quality constraints.
    score = metrics["sharpe_daily_annualized"] * 35.0
    score += metrics["return_pct"] * 0.6
    score += min(metrics["profit_factor"], 2.5) * 3.0

    if metrics["max_drawdown_pct"] > 10.0:
        score -= (metrics["max_drawdown_pct"] - 10.0) * 15.0
    if metrics["worst_daily_loss_pct"] < -5.0:
        score -= abs(metrics["worst_daily_loss_pct"] + 5.0) * 20.0

    # Penalty for too few trades to avoid over-filtering into noisy Sharpe.
    if metrics["total_trades"] < 20:
        score -= (20.0 - metrics["total_trades"]) * 1.5

    return float(score)


def param_grid(quick_grid: bool = True) -> List[Params]:
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


def fit_filter_and_threshold(
    candidates_df: pd.DataFrame,
    params: Params,
    initial_capital: float,
) -> Tuple[GradientBoostingClassifier | None, float, float, str]:
    if len(candidates_df) < 80:
        baseline = simulate_filtered_trades(
            candidates_df,
            params=params,
            initial_capital=initial_capital,
            threshold=0.0,
        )
        return None, 0.0, score_train(compute_metrics(baseline, initial_capital)), "no_filter"

    y = candidates_df["is_win"].to_numpy(dtype=int)
    if y.min() == y.max():
        baseline = simulate_filtered_trades(
            candidates_df,
            params=params,
            initial_capital=initial_capital,
            threshold=0.0,
        )
        return None, 0.0, score_train(compute_metrics(baseline, initial_capital)), "no_filter"

    X = candidates_df[FEATURE_COLUMNS].to_numpy(dtype=float)
    split = int(len(candidates_df) * 0.7)
    split = max(50, min(split, len(candidates_df) - 20))

    X_fit = X[:split]
    y_fit = y[:split]
    val = candidates_df.iloc[split:].copy()
    if len(val) < 20:
        baseline = simulate_filtered_trades(
            candidates_df,
            params=params,
            initial_capital=initial_capital,
            threshold=0.0,
        )
        return None, 0.0, score_train(compute_metrics(baseline, initial_capital)), "no_filter"

    model = GradientBoostingClassifier(
        n_estimators=180,
        learning_rate=0.05,
        max_depth=3,
        random_state=42,
    )
    model.fit(X_fit, y_fit)

    val["win_proba"] = model.predict_proba(val[FEATURE_COLUMNS].to_numpy(dtype=float))[:, 1]

    baseline_val = simulate_filtered_trades(
        val,
        params=params,
        initial_capital=initial_capital,
        threshold=0.0,
        proba_col="win_proba",
    )
    best_threshold = 0.0
    best_score = score_train(compute_metrics(baseline_val, initial_capital))
    best_mode = "no_filter"

    min_val_trades = max(30, int(len(val) * 0.15))

    for threshold in np.arange(0.3, 0.91, 0.05):
        sim_trades = simulate_filtered_trades(
            val,
            params=params,
            initial_capital=initial_capital,
            threshold=float(threshold),
            proba_col="win_proba",
        )
        if len(sim_trades) < min_val_trades:
            continue
        m = compute_metrics(sim_trades, initial_capital)
        s = score_train(m)
        if s > best_score:
            best_score = s
            best_threshold = float(threshold)
            best_mode = "ml_filter"

    # Refit on full training fold for deployment into test window.
    model.fit(X, y)
    return model, best_threshold, float(best_score), best_mode


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


def run_walk_forward_ml(
    df: pd.DataFrame,
    initial_capital: float,
    train_years: float,
    test_years: float,
    step_years: float,
    max_folds: int,
    quick_grid: bool,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict, pd.DataFrame]:
    bars_per_year = int(24 * 365)
    train_bars = int(train_years * bars_per_year)
    test_bars = int(test_years * bars_per_year)
    step_bars = int(step_years * bars_per_year)

    windows = oos_windows(df, train_bars, test_bars, step_bars, max_folds)
    if not windows:
        raise ValueError("Not enough data for requested walk-forward windows.")

    grid = param_grid(quick_grid=quick_grid)
    print(f"[Track B ML] Testing {len(grid)} parameter combinations per fold")

    fold_rows: List[Dict] = []
    all_oos_trades: List[pd.DataFrame] = []
    all_oos_candidates: List[pd.DataFrame] = []
    feature_importance_rows: List[Dict[str, float]] = []

    best_global_params: Params | None = None
    best_global_score = -1e18

    for fold, train_start, train_end, test_end in windows:
        train_df = df.iloc[train_start:train_end].copy()
        test_df = df.iloc[train_end:test_end].copy()

        print(f"[Track B ML] Fold {fold + 1}/{len(windows)} | train bars={len(train_df):,} | test bars={len(test_df):,}")

        best_params = None
        best_threshold = 0.0
        best_mode = "no_filter"
        best_model: GradientBoostingClassifier | None = None
        best_score = -1e18

        for idx, params in enumerate(grid):
            train_candidates = generate_trade_candidates(train_df, params)
            model, threshold, train_score, mode = fit_filter_and_threshold(train_candidates, params, initial_capital)

            if train_score > best_score:
                best_score = train_score
                best_params = params
                best_threshold = threshold
                best_model = model
                best_mode = mode

            if (idx + 1) % max(1, len(grid) // 4) == 0:
                print(f"  progress: {idx + 1}/{len(grid)}")

        if best_params is None:
            print("  warning: no valid setup for fold, skipping.")
            continue

        test_candidates = generate_trade_candidates(test_df, best_params)
        if not test_candidates.empty:
            test_candidates = test_candidates.copy()
            if best_model is not None and best_mode == "ml_filter":
                test_candidates["win_proba"] = best_model.predict_proba(
                    test_candidates[FEATURE_COLUMNS].to_numpy(dtype=float)
                )[:, 1]
            else:
                test_candidates["win_proba"] = 1.0
            test_candidates["fold"] = fold

            test_trades = simulate_filtered_trades(
                test_candidates,
                params=best_params,
                initial_capital=initial_capital,
                threshold=best_threshold,
                proba_col="win_proba",
            )
            if not test_trades.empty:
                test_trades["fold"] = fold
                test_trades["fast"] = best_params.fast
                test_trades["slow"] = best_params.slow
                test_trades["stop_loss_pct"] = best_params.stop_loss_pct
                test_trades["take_profit_pct"] = best_params.take_profit_pct
                test_trades["risk_pct"] = best_params.risk_pct
                test_trades["proba_threshold"] = best_threshold
                test_trades["filter_mode"] = best_mode

                all_oos_trades.append(test_trades)

            all_oos_candidates.append(test_candidates)

        test_metrics = compute_metrics(
            all_oos_trades[-1] if all_oos_trades else pd.DataFrame(),
            initial_capital=initial_capital,
        )

        accepted_count = int(test_metrics["total_trades"])
        total_candidates = int(len(test_candidates)) if "test_candidates" in locals() else 0
        accept_rate = (accepted_count / total_candidates * 100.0) if total_candidates > 0 else 0.0

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
                "filter_mode": best_mode,
                "proba_threshold": best_threshold,
                "train_ml_score": best_score,
                "test_trades": accepted_count,
                "test_candidates": total_candidates,
                "accept_rate_pct": accept_rate,
                "test_sharpe": test_metrics["sharpe_daily_annualized"],
                "test_return_pct": test_metrics["return_pct"],
                "test_max_dd_pct": test_metrics["max_drawdown_pct"],
                "test_ftmo_pass": int(test_metrics["ftmo_pass"]),
            }
        )

        if best_model is not None and hasattr(best_model, "feature_importances_"):
            for feat, imp in zip(FEATURE_COLUMNS, best_model.feature_importances_):
                feature_importance_rows.append({"fold": fold, "feature": feat, "importance": float(imp)})

        if best_score > best_global_score:
            best_global_score = best_score
            best_global_params = best_params

    folds_df = pd.DataFrame(fold_rows)
    oos_trades_df = pd.concat(all_oos_trades, ignore_index=True) if all_oos_trades else pd.DataFrame()
    oos_candidates_df = pd.concat(all_oos_candidates, ignore_index=True) if all_oos_candidates else pd.DataFrame()
    feat_imp_df = pd.DataFrame(feature_importance_rows)

    oos_metrics = compute_metrics(oos_trades_df, initial_capital)

    summary = {
        "train_years": train_years,
        "test_years": test_years,
        "step_years": step_years,
        "horizon_years_per_fold": train_years + test_years,
        "folds": int(len(folds_df)),
        "fold_pass_rate_pct": float(folds_df["test_ftmo_pass"].mean() * 100.0) if not folds_df.empty else 0.0,
        "selected": {
            "fast": best_global_params.fast if best_global_params else None,
            "slow": best_global_params.slow if best_global_params else None,
            "sl_pct": best_global_params.stop_loss_pct if best_global_params else None,
            "tp_pct": best_global_params.take_profit_pct if best_global_params else None,
            "risk_pct": best_global_params.risk_pct if best_global_params else None,
        },
        "oos_trades": int(oos_metrics["total_trades"]),
        "oos_sharpe_daily_annualized": float(oos_metrics["sharpe_daily_annualized"]),
        "oos_return_pct": float(oos_metrics["return_pct"]),
        "oos_max_drawdown_pct": float(oos_metrics["max_drawdown_pct"]),
        "oos_worst_daily_loss_pct": float(oos_metrics["worst_daily_loss_pct"]),
        "oos_profit_factor": float(oos_metrics["profit_factor"]),
        "oos_ftmo_pass": bool(oos_metrics["ftmo_pass"] > 0.5),
        "candidate_count": int(len(oos_candidates_df)),
        "accept_count": int(len(oos_trades_df)),
        "accept_rate_pct": float((len(oos_trades_df) / len(oos_candidates_df) * 100.0) if len(oos_candidates_df) > 0 else 0.0),
        "ml_filter_folds": int((folds_df["filter_mode"] == "ml_filter").sum()) if not folds_df.empty else 0,
        "no_filter_folds": int((folds_df["filter_mode"] == "no_filter").sum()) if not folds_df.empty else 0,
    }

    return folds_df, oos_trades_df, oos_candidates_df, summary, feat_imp_df


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
    ax1.set_title("Track B Short ML - OOS Equity")
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
    plt.title("Track B Short ML - Monte Carlo on OOS Trade Distribution")
    plt.xlabel("Trade #")
    plt.ylabel("Equity ($)")
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()

    return pass_prob, median_ret


def plot_feature_importance(feat_imp_df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    if feat_imp_df.empty:
        return pd.DataFrame(columns=["feature", "importance"])

    avg = feat_imp_df.groupby("feature", as_index=False)["importance"].mean()
    avg = avg.sort_values("importance", ascending=True)

    plt.figure(figsize=(10, 6))
    plt.barh(avg["feature"], avg["importance"], color="#2563eb", alpha=0.9)
    plt.title("Track B Short ML - Mean Feature Importance")
    plt.xlabel("Importance")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()

    return avg.sort_values("importance", ascending=False).reset_index(drop=True)


def plot_probability_quality(oos_candidates_df: pd.DataFrame, out_path: Path) -> None:
    if oos_candidates_df.empty or "win_proba" not in oos_candidates_df.columns:
        return

    temp = oos_candidates_df.copy()
    temp["bucket"] = pd.cut(temp["win_proba"], bins=np.linspace(0.0, 1.0, 11), include_lowest=True)
    grouped = temp.groupby("bucket", observed=False).agg(
        count=("is_win", "size"),
        win_rate=("is_win", "mean"),
        avg_proba=("win_proba", "mean"),
    ).reset_index()

    x = np.arange(len(grouped))

    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax1.bar(x, grouped["count"], color="#9ca3af", alpha=0.55, label="Candidate count")
    ax1.set_ylabel("Count")
    ax1.set_xlabel("Predicted win probability bucket")
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(b) for b in grouped["bucket"]], rotation=35, ha="right")

    ax2 = ax1.twinx()
    ax2.plot(x, grouped["win_rate"] * 100.0, color="#16a34a", marker="o", linewidth=2.0, label="Realized win rate %")
    ax2.plot(x, grouped["avg_proba"] * 100.0, color="#2563eb", marker="x", linewidth=1.5, label="Avg predicted %")
    ax2.set_ylabel("Percent")
    ax2.set_ylim(0, 100)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left")
    plt.title("Track B Short ML - Probability Quality by Bucket")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track B Short ML walk-forward")
    parser.add_argument("--data", type=Path, default=Path("data/XAUUSD_1h_sample.csv"), help="OHLC CSV path")
    parser.add_argument("--initial-capital", type=float, default=10000.0, help="Initial capital")
    parser.add_argument("--train-years", type=float, default=4.0, help="Training years per fold")
    parser.add_argument("--test-years", type=float, default=3.0, help="Test years per fold")
    parser.add_argument("--step-years", type=float, default=1.0, help="Step years between folds")
    parser.add_argument("--max-folds", type=int, default=2, help="Max folds")
    parser.add_argument("--mc-paths", type=int, default=1000, help="Monte Carlo paths")
    parser.add_argument("--full-grid", action="store_true", help="Use full parameter grid")
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
    df = compute_features(df)

    folds_df, oos_trades_df, oos_candidates_df, summary, feat_imp_df = run_walk_forward_ml(
        df,
        initial_capital=args.initial_capital,
        train_years=args.train_years,
        test_years=args.test_years,
        step_years=args.step_years,
        max_folds=args.max_folds,
        quick_grid=not args.full_grid,
    )

    mc_paths = monte_carlo_paths(
        oos_trades_df,
        initial_capital=args.initial_capital,
        n_paths=args.mc_paths,
        n_trades=max(int(len(oos_trades_df)), 1),
    )
    mc_pass_prob, mc_median_ret = plot_monte_carlo(
        mc_paths,
        images_dir / "track_b_short_ml_monte_carlo.png",
        initial_capital=args.initial_capital,
    )

    summary["quick_grid"] = bool(not args.full_grid)
    summary["mc_paths"] = int(args.mc_paths)
    summary["mc_profitability_probability_pct"] = mc_pass_prob
    summary["mc_median_return_pct"] = mc_median_ret

    feat_avg_df = plot_feature_importance(
        feat_imp_df,
        images_dir / "track_b_short_ml_feature_importance.png",
    )

    plot_oos_equity(
        oos_trades_df,
        images_dir / "track_b_short_ml_oos_equity.png",
        initial_capital=args.initial_capital,
    )

    plot_probability_quality(
        oos_candidates_df,
        images_dir / "track_b_short_ml_probability_quality.png",
    )

    folds_df.to_csv(reports_dir / "track_b_short_ml_fold_results.csv", index=False)
    oos_trades_df.to_csv(reports_dir / "track_b_short_ml_oos_trades.csv", index=False)
    oos_candidates_df.to_csv(reports_dir / "track_b_short_ml_oos_candidates.csv", index=False)
    feat_avg_df.to_csv(reports_dir / "track_b_short_ml_feature_importance.csv", index=False)
    (reports_dir / "track_b_short_ml_summary.json").write_text(json.dumps(summary, indent=2))

    lines = [
        "Track B Short ML - Walk-Forward Summary",
        "",
        f"Data: {data_path}",
        f"Train/Test/Step (years): {args.train_years}/{args.test_years}/{args.step_years}",
        f"Horizon per fold: {summary['horizon_years_per_fold']} years",
        f"Folds: {summary['folds']}",
        f"Fold FTMO pass rate: {summary['fold_pass_rate_pct']:.2f}%",
        "",
        f"Selected params: EMA({summary['selected']['fast']}/{summary['selected']['slow']}), "
        f"SL {summary['selected']['sl_pct']}%, TP {summary['selected']['tp_pct']}%, Risk {summary['selected']['risk_pct']}%",
        f"OOS candidates: {summary['candidate_count']}",
        f"OOS accepted trades: {summary['accept_count']} ({summary['accept_rate_pct']:.2f}%)",
        f"Fold filter modes: ML={summary['ml_filter_folds']} | No-filter={summary['no_filter_folds']}",
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
    (reports_dir / "track_b_short_ml_summary.txt").write_text("\n".join(lines))

    print("Saved reports:")
    print(f"- {reports_dir / 'track_b_short_ml_fold_results.csv'}")
    print(f"- {reports_dir / 'track_b_short_ml_oos_trades.csv'}")
    print(f"- {reports_dir / 'track_b_short_ml_oos_candidates.csv'}")
    print(f"- {reports_dir / 'track_b_short_ml_feature_importance.csv'}")
    print(f"- {reports_dir / 'track_b_short_ml_summary.json'}")
    print(f"- {reports_dir / 'track_b_short_ml_summary.txt'}")
    print("Saved images:")
    print(f"- {images_dir / 'track_b_short_ml_oos_equity.png'}")
    print(f"- {images_dir / 'track_b_short_ml_monte_carlo.png'}")
    print(f"- {images_dir / 'track_b_short_ml_feature_importance.png'}")
    print(f"- {images_dir / 'track_b_short_ml_probability_quality.png'}")


if __name__ == "__main__":
    main()
