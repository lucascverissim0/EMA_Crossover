"""
Track C Short FTMO-first optimization.

FTMO-first objective on train validation:
- maximize pass probability (10% target, 10% max total DD, 3% max daily DD)
- minimize median days to pass
- keep Sharpe and return as secondary terms

Outputs:
- reports/track_c_short_ftmo_fold_results.csv
- reports/track_c_short_ftmo_oos_trades.csv
- reports/track_c_short_ftmo_oos_candidates.csv
- reports/track_c_short_ftmo_feature_importance.csv
- reports/track_c_short_ftmo_summary.json
- reports/track_c_short_ftmo_summary.txt
- images/track_c_short_ftmo_oos_equity.png
- images/track_c_short_ftmo_monte_carlo.png
- images/track_c_short_ftmo_feature_importance.png
- images/track_c_short_ftmo_probability_quality.png
- images/track_c_short_ftmo_ftmo_profile.png
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
    "atr14_pct", "rsi14", "ema_spread_pct", "zscore20",
    "ret_1", "ret_6", "bar_range_pct", "volume_ratio",
    "hour_sin", "hour_cos", "dow_sin", "dow_cos",
]


def load_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if "Close" not in df.columns:
        raw = pd.read_csv(csv_path, header=None)
        header = raw.iloc[0].astype(str).tolist()
        values = raw.iloc[3:].copy().reset_index(drop=True)
        values.columns = header
        values = values.rename(columns={header[0]: "timestamp"})
        keep = [c for c in ["timestamp", "Open", "High", "Low", "Close", "Volume"] if c in values.columns]
        out = values[keep].copy()
    else:
        out = df.rename(columns={df.columns[0]: "timestamp"}).copy()

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
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    out["atr14_pct"] = (tr.rolling(14).mean() / close) * 100.0

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean().replace(0.0, np.nan)
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
    feats = data[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).to_numpy(dtype=float)

    rows: List[Dict[str, float]] = []
    in_short = False
    entry_price = 0.0
    entry_ts = None
    entry_idx = -1

    for i in range(1, len(data)):
        price = closes[i]
        ts = timestamps[i]
        sd = signal_diffs[i]

        if not in_short and sd > 0:
            in_short = True
            entry_price = price
            entry_ts = ts
            entry_idx = i
            continue

        if in_short:
            move_pct = ((entry_price - price) / entry_price) * 100.0
            reason = None
            exit_price = price
            realized = move_pct
            if move_pct <= -params.stop_loss_pct:
                reason = "Stop Loss"
                exit_price = entry_price * (1.0 + params.stop_loss_pct / 100.0)
                realized = -params.stop_loss_pct
            elif move_pct >= params.take_profit_pct:
                reason = "Take Profit"
                exit_price = entry_price * (1.0 - params.take_profit_pct / 100.0)
                realized = params.take_profit_pct
            elif sd < 0:
                reason = "Cover Signal"

            if reason is not None:
                fv = feats[entry_idx]
                if np.isfinite(fv).all() and not np.isnan(fv).any():
                    row = {
                        "entry_ts": entry_ts,
                        "exit_ts": ts,
                        "entry_price": float(entry_price),
                        "exit_price": float(exit_price),
                        "move_pct": float(realized),
                        "reason": reason,
                        "is_win": int(realized > 0.0),
                    }
                    for j, c in enumerate(FEATURE_COLUMNS):
                        row[c] = float(fv[j])
                    rows.append(row)
                in_short = False

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out["entry_ts"] = pd.to_datetime(out["entry_ts"])
    out["exit_ts"] = pd.to_datetime(out["exit_ts"])
    return out.sort_values("exit_ts").reset_index(drop=True)


def simulate_filtered_trades(candidates_df: pd.DataFrame, params: Params, initial_capital: float, threshold: float, proba_col: str = "win_proba") -> pd.DataFrame:
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
        dd = ((peak - capital) / peak) * 100.0 if peak > 0 else 0.0
        trades.append({
            "entry_ts": row["entry_ts"], "exit_ts": row["exit_ts"],
            "entry_price": float(row["entry_price"]), "exit_price": float(row["exit_price"]),
            "move_pct": float(row["move_pct"]), "pnl": float(pnl), "reason": row["reason"],
            "equity_after": float(capital), "drawdown_pct": float(dd), "win_proba": float(row[proba_col]),
        })
    return pd.DataFrame(trades)


def compute_metrics(trades_df: pd.DataFrame, initial_capital: float) -> Dict[str, float]:
    if trades_df.empty:
        return {"total_trades": 0.0, "win_rate": 0.0, "total_pnl": 0.0, "return_pct": 0.0,
                "max_drawdown_pct": 0.0, "worst_daily_loss_pct": 0.0, "profit_factor": 0.0,
                "sharpe_daily_annualized": 0.0, "ftmo_pass": 1.0}

    pnl = trades_df["pnl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    total_pnl = float(pnl.sum())

    temp = trades_df.copy()
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"])
    temp["date"] = temp["exit_ts"].dt.date
    daily = temp.groupby("date", as_index=False)["pnl"].sum().sort_values("date")
    daily["daily_loss_pct"] = (daily["pnl"] / initial_capital) * 100.0
    worst_daily = float(daily["daily_loss_pct"].min()) if not daily.empty else 0.0

    equity_daily = initial_capital + daily["pnl"].cumsum()
    dr = equity_daily.pct_change().dropna()
    sharpe = float((dr.mean() / dr.std()) * np.sqrt(252.0)) if (not dr.empty and dr.std() != 0) else 0.0

    gross_win = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0

    max_dd = float(trades_df["drawdown_pct"].max())
    return {
        "total_trades": float(len(trades_df)),
        "win_rate": float((len(wins) / len(trades_df)) * 100.0),
        "total_pnl": total_pnl,
        "return_pct": (total_pnl / initial_capital) * 100.0,
        "max_drawdown_pct": max_dd,
        "worst_daily_loss_pct": worst_daily,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else 0.0,
        "sharpe_daily_annualized": sharpe,
        "ftmo_pass": 1.0 if (max_dd <= 10.0 and worst_daily >= -5.0) else 0.0,
    }


def evaluate_ftmo_rules(trades_df: pd.DataFrame, target_profit_pct: float = 10.0, max_total_dd_pct: float = 10.0, max_daily_dd_pct: float = 3.0, initial_capital: float = 10000.0) -> Tuple[bool, int | None]:
    if trades_df.empty:
        return False, None
    temp = trades_df.copy().sort_values("exit_ts")
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"], errors="coerce")
    temp = temp.dropna(subset=["exit_ts", "pnl"])
    if temp.empty:
        return False, None

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
            return False, None
        if equity < day_start * (1.0 - max_daily_dd_pct / 100.0):
            return False, None
        if equity >= target:
            return True, (d - start_date).days + 1
    return False, None


def ftmo_monte_carlo_probability(trades_df: pd.DataFrame, n_paths: int, seed: int = 42, target_profit_pct: float = 10.0, max_total_dd_pct: float = 10.0, max_daily_dd_pct: float = 3.0, initial_capital: float = 10000.0) -> Tuple[float, int | None]:
    if trades_df.empty:
        return 0.0, None
    temp = trades_df.copy().sort_values("exit_ts")
    temp["exit_ts"] = pd.to_datetime(temp["exit_ts"], errors="coerce")
    temp = temp.dropna(subset=["exit_ts", "pnl"]).reset_index(drop=True)
    if temp.empty:
        return 0.0, None

    target = initial_capital * (1.0 + target_profit_pct / 100.0)
    floor_total = initial_capital * (1.0 - max_total_dd_pct / 100.0)
    dates = temp["exit_ts"].dt.date.to_list()
    pnls = temp["pnl"].astype(float).to_numpy()
    start_date = dates[0]

    rng = np.random.default_rng(seed)
    pass_days: List[int] = []
    for _ in range(n_paths):
        sample = rng.choice(pnls, size=len(pnls), replace=True)
        equity = initial_capital
        day = None
        day_start = equity
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
                break

    prob = (len(pass_days) / n_paths) * 100.0 if n_paths > 0 else 0.0
    return float(prob), (int(np.median(pass_days)) if pass_days else None)


def score_ftmo_objective(metrics: Dict[str, float], ftmo_pass_prob: float, median_days_to_pass: int | None) -> float:
    days = float(median_days_to_pass) if median_days_to_pass is not None else 999.0
    score = 40.0 * (ftmo_pass_prob / 100.0)
    score -= 0.08 * days
    score += metrics["sharpe_daily_annualized"] * 8.0
    score += metrics["return_pct"] * 0.3
    score += min(metrics["profit_factor"], 2.5) * 1.5
    if metrics["max_drawdown_pct"] > 10.0:
        score -= (metrics["max_drawdown_pct"] - 10.0) * 25.0
    if metrics["worst_daily_loss_pct"] < -3.0:
        score -= abs(metrics["worst_daily_loss_pct"] + 3.0) * 35.0
    if metrics["total_trades"] < 30:
        score -= (30.0 - metrics["total_trades"]) * 1.5
    return float(score)


def param_grid(quick_grid: bool = True) -> List[Params]:
    if quick_grid:
        fasts, slows, sls, tps, risks = [10, 12], [26, 30, 40], [0.5, 0.75], [1.5, 2.0], [0.25, 0.5]
    else:
        fasts, slows, sls, tps, risks = [8, 10, 12, 14], [20, 26, 30, 40, 50], [0.5, 0.75, 1.0], [1.0, 1.5, 2.0, 3.0], [0.25, 0.5]
    out: List[Params] = []
    for fast in fasts:
        for slow in slows:
            if fast >= slow or (slow - fast) < 10:
                continue
            for sl in sls:
                for tp in tps:
                    for risk in risks:
                        out.append(Params(fast, slow, sl, tp, risk))
    return out


def fit_filter_and_threshold(candidates_df: pd.DataFrame, params: Params, initial_capital: float) -> Tuple[GradientBoostingClassifier | None, float, float, str, float, int | None]:
    if len(candidates_df) < 80:
        baseline = simulate_filtered_trades(candidates_df, params, initial_capital, 0.0)
        m = compute_metrics(baseline, initial_capital)
        p, d = ftmo_monte_carlo_probability(baseline, n_paths=250, initial_capital=initial_capital)
        return None, 0.0, score_ftmo_objective(m, p, d), "no_filter", p, d

    y = candidates_df["is_win"].to_numpy(dtype=int)
    if y.min() == y.max():
        baseline = simulate_filtered_trades(candidates_df, params, initial_capital, 0.0)
        m = compute_metrics(baseline, initial_capital)
        p, d = ftmo_monte_carlo_probability(baseline, n_paths=250, initial_capital=initial_capital)
        return None, 0.0, score_ftmo_objective(m, p, d), "no_filter", p, d

    X = candidates_df[FEATURE_COLUMNS].to_numpy(dtype=float)
    split = max(50, min(int(len(candidates_df) * 0.7), len(candidates_df) - 20))
    fit_df = candidates_df.iloc[:split].copy()
    val = candidates_df.iloc[split:].copy()
    if len(val) < 20:
        baseline = simulate_filtered_trades(candidates_df, params, initial_capital, 0.0)
        m = compute_metrics(baseline, initial_capital)
        p, d = ftmo_monte_carlo_probability(baseline, n_paths=250, initial_capital=initial_capital)
        return None, 0.0, score_ftmo_objective(m, p, d), "no_filter", p, d

    model = GradientBoostingClassifier(n_estimators=180, learning_rate=0.05, max_depth=3, random_state=42)
    model.fit(fit_df[FEATURE_COLUMNS].to_numpy(dtype=float), fit_df["is_win"].to_numpy(dtype=int))
    val["win_proba"] = model.predict_proba(val[FEATURE_COLUMNS].to_numpy(dtype=float))[:, 1]

    base_trades = simulate_filtered_trades(val, params, initial_capital, 0.0, "win_proba")
    base_metrics = compute_metrics(base_trades, initial_capital)
    best_prob, best_days = ftmo_monte_carlo_probability(base_trades, n_paths=250, initial_capital=initial_capital)
    best_score = score_ftmo_objective(base_metrics, best_prob, best_days)
    best_threshold = 0.0
    best_mode = "no_filter"

    min_val_trades = max(30, int(len(val) * 0.15))
    for threshold in np.arange(0.3, 0.91, 0.05):
        trades = simulate_filtered_trades(val, params, initial_capital, float(threshold), "win_proba")
        if len(trades) < min_val_trades:
            continue
        m = compute_metrics(trades, initial_capital)
        p, d = ftmo_monte_carlo_probability(trades, n_paths=250, initial_capital=initial_capital)
        s = score_ftmo_objective(m, p, d)
        if s > best_score:
            best_score, best_threshold, best_mode, best_prob, best_days = s, float(threshold), "ml_filter", p, d

    model.fit(X, y)
    return model, best_threshold, float(best_score), best_mode, float(best_prob), best_days


def monte_carlo_paths(trades_df: pd.DataFrame, initial_capital: float, n_paths: int, n_trades: int, seed: int = 42) -> np.ndarray:
    if trades_df.empty:
        return np.zeros((0, 0))
    returns = trades_df["pnl"].to_numpy(dtype=float)
    if len(returns) == 0:
        return np.zeros((0, 0))
    rng = np.random.default_rng(seed)
    paths = np.zeros((n_paths, n_trades + 1), dtype=float)
    paths[:, 0] = initial_capital
    for i in range(n_paths):
        sample = rng.choice(returns, size=n_trades, replace=True)
        paths[i, 1:] = initial_capital + np.cumsum(sample)
    return paths


def oos_windows(df: pd.DataFrame, train_bars: int, test_bars: int, step_bars: int, max_folds: int):
    out = []
    start = 0
    fold = 0
    while fold < max_folds:
        train_end = start + train_bars
        test_end = train_end + test_bars
        if test_end > len(df):
            break
        out.append((fold, start, train_end, test_end))
        start += step_bars
        fold += 1
    return out


def run_walk_forward_ftmo(df: pd.DataFrame, initial_capital: float, train_years: float, test_years: float, step_years: float, max_folds: int, quick_grid: bool) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict, pd.DataFrame]:
    bpy = int(24 * 365)
    windows = oos_windows(df, int(train_years * bpy), int(test_years * bpy), int(step_years * bpy), max_folds)
    if not windows:
        raise ValueError("Not enough data for requested walk-forward windows.")

    grid = param_grid(quick_grid=quick_grid)
    print(f"[Track C FTMO] Testing {len(grid)} parameter combinations per fold")

    fold_rows: List[Dict] = []
    oos_trades_all: List[pd.DataFrame] = []
    oos_candidates_all: List[pd.DataFrame] = []
    feat_rows: List[Dict[str, float]] = []

    best_global_params = None
    best_global_score = -1e18

    for fold, train_start, train_end, test_end in windows:
        train_df = df.iloc[train_start:train_end].copy()
        test_df = df.iloc[train_end:test_end].copy()
        print(f"[Track C FTMO] Fold {fold + 1}/{len(windows)} | train bars={len(train_df):,} | test bars={len(test_df):,}")

        best_params = None
        best_model = None
        best_threshold = 0.0
        best_mode = "no_filter"
        best_score = -1e18
        best_train_prob = 0.0
        best_train_days = None

        for idx, params in enumerate(grid):
            train_candidates = generate_trade_candidates(train_df, params)
            model, threshold, score, mode, train_prob, train_days = fit_filter_and_threshold(train_candidates, params, initial_capital)
            if score > best_score:
                best_score = score
                best_params = params
                best_model = model
                best_threshold = threshold
                best_mode = mode
                best_train_prob = train_prob
                best_train_days = train_days
            if (idx + 1) % max(1, len(grid) // 4) == 0:
                print(f"  progress: {idx + 1}/{len(grid)}")

        if best_params is None:
            continue

        test_candidates = generate_trade_candidates(test_df, best_params)
        if not test_candidates.empty:
            test_candidates = test_candidates.copy()
            if best_model is not None and best_mode == "ml_filter":
                test_candidates["win_proba"] = best_model.predict_proba(test_candidates[FEATURE_COLUMNS].to_numpy(dtype=float))[:, 1]
            else:
                test_candidates["win_proba"] = 1.0
            test_candidates["fold"] = fold

            test_trades = simulate_filtered_trades(test_candidates, best_params, initial_capital, best_threshold, "win_proba")
            if not test_trades.empty:
                test_trades["fold"] = fold
                test_trades["fast"] = best_params.fast
                test_trades["slow"] = best_params.slow
                test_trades["stop_loss_pct"] = best_params.stop_loss_pct
                test_trades["take_profit_pct"] = best_params.take_profit_pct
                test_trades["risk_pct"] = best_params.risk_pct
                test_trades["proba_threshold"] = best_threshold
                test_trades["filter_mode"] = best_mode
                oos_trades_all.append(test_trades)
            oos_candidates_all.append(test_candidates)

        test_metrics = compute_metrics(oos_trades_all[-1] if oos_trades_all else pd.DataFrame(), initial_capital)
        fold_rows.append({
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
            "train_ftmo_score": best_score,
            "train_ftmo_pass_probability_pct": best_train_prob,
            "train_ftmo_median_days_to_pass": best_train_days,
            "test_trades": int(test_metrics["total_trades"]),
            "test_candidates": int(len(test_candidates)) if not test_candidates.empty else 0,
            "accept_rate_pct": (int(test_metrics["total_trades"]) / int(len(test_candidates)) * 100.0) if not test_candidates.empty else 0.0,
            "test_sharpe": test_metrics["sharpe_daily_annualized"],
            "test_return_pct": test_metrics["return_pct"],
            "test_max_dd_pct": test_metrics["max_drawdown_pct"],
            "test_ftmo_pass": int(test_metrics["ftmo_pass"]),
        })

        if best_model is not None and hasattr(best_model, "feature_importances_"):
            for feat, imp in zip(FEATURE_COLUMNS, best_model.feature_importances_):
                feat_rows.append({"fold": fold, "feature": feat, "importance": float(imp)})

        if best_score > best_global_score:
            best_global_score = best_score
            best_global_params = best_params

    folds_df = pd.DataFrame(fold_rows)
    oos_trades_df = pd.concat(oos_trades_all, ignore_index=True) if oos_trades_all else pd.DataFrame()
    oos_candidates_df = pd.concat(oos_candidates_all, ignore_index=True) if oos_candidates_all else pd.DataFrame()
    feat_imp_df = pd.DataFrame(feat_rows)
    m = compute_metrics(oos_trades_df, initial_capital)

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
        "oos_trades": int(m["total_trades"]),
        "oos_sharpe_daily_annualized": float(m["sharpe_daily_annualized"]),
        "oos_return_pct": float(m["return_pct"]),
        "oos_max_drawdown_pct": float(m["max_drawdown_pct"]),
        "oos_worst_daily_loss_pct": float(m["worst_daily_loss_pct"]),
        "oos_profit_factor": float(m["profit_factor"]),
        "oos_ftmo_pass": bool(m["ftmo_pass"] > 0.5),
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
    ax1.set_title("Track C Short FTMO - OOS Equity")
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
    plt.title("Track C Short FTMO - Monte Carlo on OOS Trade Distribution")
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
    avg = feat_imp_df.groupby("feature", as_index=False)["importance"].mean().sort_values("importance", ascending=True)
    plt.figure(figsize=(10, 6))
    plt.barh(avg["feature"], avg["importance"], color="#2563eb", alpha=0.9)
    plt.title("Track C Short FTMO - Mean Feature Importance")
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
    grouped = temp.groupby("bucket", observed=False).agg(count=("is_win", "size"), win_rate=("is_win", "mean"), avg_proba=("win_proba", "mean")).reset_index()
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
    plt.title("Track C Short FTMO - Probability Quality by Bucket")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close(fig)


def plot_ftmo_profile(ftmo_pass_prob: float, ftmo_median_days: int | None, out_path: Path) -> None:
    vals = [ftmo_pass_prob, float(ftmo_median_days) if ftmo_median_days is not None else 0.0]
    labs = ["FTMO pass probability %", "FTMO median days to pass"]
    plt.figure(figsize=(9, 5))
    plt.bar(labs, vals, color=["#2563eb", "#0f766e"], alpha=0.9)
    plt.title("Track C FTMO Profile")
    plt.ylabel("Value")
    plt.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track C Short FTMO-first walk-forward")
    parser.add_argument("--data", type=Path, default=Path("data/XAUUSD_1h_sample.csv"), help="OHLC CSV path")
    parser.add_argument("--initial-capital", type=float, default=10000.0, help="Initial capital")
    parser.add_argument("--train-years", type=float, default=4.0, help="Training years per fold")
    parser.add_argument("--test-years", type=float, default=3.0, help="Test years per fold")
    parser.add_argument("--step-years", type=float, default=1.0, help="Step years between folds")
    parser.add_argument("--max-folds", type=int, default=2, help="Max folds")
    parser.add_argument("--mc-paths", type=int, default=1000, help="Monte Carlo paths")
    parser.add_argument("--ftmo-mc-paths", type=int, default=2000, help="Monte Carlo paths for FTMO pass probability")
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

    df = compute_features(load_data(data_path))

    folds_df, oos_trades_df, oos_candidates_df, summary, feat_imp_df = run_walk_forward_ftmo(
        df, initial_capital=args.initial_capital, train_years=args.train_years, test_years=args.test_years,
        step_years=args.step_years, max_folds=args.max_folds, quick_grid=not args.full_grid,
    )

    paths = monte_carlo_paths(oos_trades_df, args.initial_capital, args.mc_paths, max(int(len(oos_trades_df)), 1))
    mc_pass_prob, mc_median_ret = plot_monte_carlo(paths, images_dir / "track_c_short_ftmo_monte_carlo.png", args.initial_capital)

    ftmo_realized_pass, ftmo_realized_days = evaluate_ftmo_rules(oos_trades_df, initial_capital=args.initial_capital)
    ftmo_mc_pass_prob, ftmo_mc_median_days = ftmo_monte_carlo_probability(
        oos_trades_df, n_paths=args.ftmo_mc_paths, initial_capital=args.initial_capital
    )

    summary.update({
        "quick_grid": bool(not args.full_grid),
        "mc_paths": int(args.mc_paths),
        "mc_profitability_probability_pct": mc_pass_prob,
        "mc_median_return_pct": mc_median_ret,
        "ftmo_target_profit_pct": 10.0,
        "ftmo_max_total_drawdown_pct": 10.0,
        "ftmo_max_daily_drawdown_pct": 3.0,
        "ftmo_realized_pass": bool(ftmo_realized_pass),
        "ftmo_realized_days_to_pass": ftmo_realized_days,
        "ftmo_mc_paths": int(args.ftmo_mc_paths),
        "ftmo_mc_pass_probability_pct": float(ftmo_mc_pass_prob),
        "ftmo_mc_median_days_to_pass": ftmo_mc_median_days,
    })

    feat_avg_df = plot_feature_importance(feat_imp_df, images_dir / "track_c_short_ftmo_feature_importance.png")
    plot_oos_equity(oos_trades_df, images_dir / "track_c_short_ftmo_oos_equity.png", args.initial_capital)
    plot_probability_quality(oos_candidates_df, images_dir / "track_c_short_ftmo_probability_quality.png")
    plot_ftmo_profile(ftmo_mc_pass_prob, ftmo_mc_median_days, images_dir / "track_c_short_ftmo_ftmo_profile.png")

    folds_df.to_csv(reports_dir / "track_c_short_ftmo_fold_results.csv", index=False)
    oos_trades_df.to_csv(reports_dir / "track_c_short_ftmo_oos_trades.csv", index=False)
    oos_candidates_df.to_csv(reports_dir / "track_c_short_ftmo_oos_candidates.csv", index=False)
    feat_avg_df.to_csv(reports_dir / "track_c_short_ftmo_feature_importance.csv", index=False)
    (reports_dir / "track_c_short_ftmo_summary.json").write_text(json.dumps(summary, indent=2))

    lines = [
        "Track C Short FTMO - Walk-Forward Summary", "",
        f"Data: {data_path}",
        f"Train/Test/Step (years): {args.train_years}/{args.test_years}/{args.step_years}",
        f"Horizon per fold: {summary['horizon_years_per_fold']} years",
        f"Folds: {summary['folds']}",
        f"Fold FTMO pass rate: {summary['fold_pass_rate_pct']:.2f}%", "",
        f"Selected params: EMA({summary['selected']['fast']}/{summary['selected']['slow']}), SL {summary['selected']['sl_pct']}%, TP {summary['selected']['tp_pct']}%, Risk {summary['selected']['risk_pct']}%",
        f"OOS candidates: {summary['candidate_count']}",
        f"OOS accepted trades: {summary['accept_count']} ({summary['accept_rate_pct']:.2f}%)",
        f"Fold filter modes: ML={summary['ml_filter_folds']} | No-filter={summary['no_filter_folds']}",
        f"OOS Sharpe: {summary['oos_sharpe_daily_annualized']:.3f}",
        f"OOS return: {summary['oos_return_pct']:.2f}%",
        f"OOS max drawdown: {summary['oos_max_drawdown_pct']:.2f}%",
        f"OOS worst daily loss: {summary['oos_worst_daily_loss_pct']:.2f}%",
        f"OOS profit factor: {summary['oos_profit_factor']:.2f}",
        f"OOS FTMO pass: {'YES' if summary['oos_ftmo_pass'] else 'NO'}",
        f"FTMO realized pass (10/10/3): {'YES' if summary['ftmo_realized_pass'] else 'NO'}",
        f"FTMO realized days to pass: {summary['ftmo_realized_days_to_pass']}",
        f"FTMO MC pass probability: {summary['ftmo_mc_pass_probability_pct']:.2f}%",
        f"FTMO MC median days to pass: {summary['ftmo_mc_median_days_to_pass']}", "",
        f"Monte Carlo paths: {summary['mc_paths']}",
        f"MC profitability probability: {summary['mc_profitability_probability_pct']:.2f}%",
        f"MC median return: {summary['mc_median_return_pct']:.2f}%",
    ]
    (reports_dir / "track_c_short_ftmo_summary.txt").write_text("\n".join(lines))

    print("Saved reports:")
    print(f"- {reports_dir / 'track_c_short_ftmo_fold_results.csv'}")
    print(f"- {reports_dir / 'track_c_short_ftmo_oos_trades.csv'}")
    print(f"- {reports_dir / 'track_c_short_ftmo_oos_candidates.csv'}")
    print(f"- {reports_dir / 'track_c_short_ftmo_feature_importance.csv'}")
    print(f"- {reports_dir / 'track_c_short_ftmo_summary.json'}")
    print(f"- {reports_dir / 'track_c_short_ftmo_summary.txt'}")
    print("Saved images:")
    print(f"- {images_dir / 'track_c_short_ftmo_oos_equity.png'}")
    print(f"- {images_dir / 'track_c_short_ftmo_monte_carlo.png'}")
    print(f"- {images_dir / 'track_c_short_ftmo_feature_importance.png'}")
    print(f"- {images_dir / 'track_c_short_ftmo_probability_quality.png'}")
    print(f"- {images_dir / 'track_c_short_ftmo_ftmo_profile.png'}")


if __name__ == "__main__":
    main()
