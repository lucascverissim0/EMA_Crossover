"""
Enhanced Track C Optimizer - Smooth EMA Parameters for Lower Drawdown.

Track C currently has:
- Fast EMA: 12, Slow EMA: 20, SL: 0.5% -> Drawdown 9.99%

This optimizer explores smoother EMA configurations to reduce drawdown while 
maintaining speed advantage.

Strategy:
- Test wider EMA spreads for smoother entries
- Test higher stop loss levels (tight stops can paradoxically increase DD)
- Prioritize: Drawdown reduction > Speed > Return
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

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


def run_backtest(df: pd.DataFrame, params: Params, initial_capital: float = 10000.0) -> Tuple[pd.DataFrame, Dict]:
    """Run backtest and return trades + metrics."""
    data = build_signals(df, params.fast, params.slow)

    trades: List[Dict] = []
    capital = initial_capital
    peak = initial_capital
    in_pos = False
    entry_price = 0.0
    entry_ts = None
    position_size = 0.0

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

    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

    # Compute metrics
    if trades_df.empty:
        metrics = {
            "total_trades": 0,
            "win_rate": 0.0,
            "return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "worst_daily_loss_pct": 0.0,
            "profit_factor": 0.0,
            "trades_per_day": 0.0,
        }
    else:
        pnl = trades_df["pnl"]
        total_pnl = float(pnl.sum())
        wins = pnl[pnl > 0]
        losses = pnl[pnl < 0]

        win_rate = float((len(wins) / len(trades_df)) * 100.0)
        return_pct = (total_pnl / initial_capital) * 100.0
        max_dd = float(trades_df["drawdown_pct"].max())

        temp = trades_df.copy()
        temp["exit_ts"] = pd.to_datetime(temp["exit_ts"])
        temp["date"] = temp["exit_ts"].dt.date
        daily = temp.groupby("date", as_index=False)["pnl"].sum()
        daily["daily_loss_pct"] = (daily["pnl"] / initial_capital) * 100.0
        worst_daily = float(daily["daily_loss_pct"].min()) if not daily.empty else 0.0

        gross_win = float(wins.sum()) if not wins.empty else 0.0
        gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
        pf = (gross_win / gross_loss) if gross_loss > 0 else 0.0

        num_days = (temp["date"].max() - temp["date"].min()).days + 1 if not temp.empty else 1
        trades_per_day = len(trades_df) / max(num_days, 1)

        metrics = {
            "total_trades": int(len(trades_df)),
            "win_rate": win_rate,
            "return_pct": return_pct,
            "max_drawdown_pct": max_dd,
            "worst_daily_loss_pct": worst_daily,
            "profit_factor": pf,
            "trades_per_day": trades_per_day,
        }

    return trades_df, metrics


def score_smooth(metrics: Dict) -> float:
    """
    Score function prioritizing:
    1. Lower drawdown (primary objective for Track C enhancement)
    2. Reasonable return
    3. Speed (trades per day)
    """
    # Penalize high drawdown heavily
    score = -metrics["max_drawdown_pct"] * 10.0
    
    # Add return bonus (but not as important as DD reduction)
    score += metrics["return_pct"] * 1.0
    
    # Add speed bonus (trades per day)
    score += metrics["trades_per_day"] * 2.0
    
    # Add win rate bonus
    score += metrics["win_rate"] * 0.2
    
    # Profit factor bonus
    score += min(metrics["profit_factor"], 2.0) * 3.0
    
    return score


def smooth_ema_grid() -> List[Params]:
    """
    Generate parameter grid focused on smooth EMA configurations.
    
    Key insight: Wider EMA spreads = smoother signals = fewer whipsaws
    """
    grid: List[Params] = []
    
    # Explore wider spreads for smoothness
    # Also test if slightly higher stop loss helps (0.5% is too tight)
    fasts = [8, 10, 12]
    slows = [20, 26, 30]          # Wider spreads for smoothness
    sls = [0.75, 1.0, 1.25]        # Slightly higher SL to reduce whipsaws
    tps = [3.0, 4.0]               # Balanced TP
    risks = [0.5]                  # Keep risk consistent

    for f in fasts:
        for s in slows:
            if f >= s:
                continue
            # Prioritize larger spreads
            spread = s - f
            if spread < 10:  # Only consider spreads >= 10
                continue
            for sl in sls:
                for tp in tps:
                    for r in risks:
                        grid.append(Params(f, s, sl, tp, r))
    
    return grid


def run_optimization(df: pd.DataFrame, initial_capital: float = 10000.0) -> Tuple[List[Dict], Dict]:
    """Run optimization and return ranked candidates."""
    grid = smooth_ema_grid()
    print(f"[Smooth EMA Optimizer] Testing {len(grid)} smooth parameter combinations...")

        candidates = []
        sample_size = 0.3  # Default sample size for recent data

        # Use recent data only (faster testing, but still representative)
        sample_idx = int(len(df) * (1.0 - sample_size))
        df_sample = df.iloc[sample_idx:].copy()
        print(f"[Optimization] Using {len(df_sample):,} recent bars ({sample_size*100:.0f}% of data) for testing...\n")

    for idx, params in enumerate(grid):
            trades_df, metrics = run_backtest(df_sample, params, initial_capital)
        score = score_smooth(metrics)

        candidates.append(
            {
                "fast": params.fast,
                "slow": params.slow,
                "stop_loss_pct": params.stop_loss_pct,
                "take_profit_pct": params.take_profit_pct,
                "risk_pct": params.risk_pct,
                "score": score,
                "return_pct": metrics["return_pct"],
                "max_drawdown_pct": metrics["max_drawdown_pct"],
                "worst_daily_loss_pct": metrics["worst_daily_loss_pct"],
                "win_rate": metrics["win_rate"],
                "profit_factor": metrics["profit_factor"],
                "total_trades": metrics["total_trades"],
                "trades_per_day": metrics["trades_per_day"],
            }
        )

        if (idx + 1) % max(1, len(grid) // 10) == 0:
            print(f"  [{idx + 1}/{len(grid)}] ... processing")

    # Sort by score (descending = best first)
    candidates.sort(key=lambda x: x["score"], reverse=True)

    return candidates, {
        "total_candidates": len(candidates),
        "grid_size": len(grid),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        default="data/XAUUSD_1h_sample.csv",
        help="Path to OHLCV CSV data",
    )
    parser.add_argument(
        "--output-dir",
        default="FTMO_Challenge/Track_C_Time_Optimized/reports",
        help="Output directory for results",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of top candidates to display",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*70}")
    print(f"Enhanced Track C Optimizer - Smooth EMA Parameters")
    print(f"Objective: Reduce Drawdown")
    print(f"{'='*70}")

    df = load_data(Path(args.data))
    print(f"Loaded {len(df)} bars from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}\n")

    candidates, summary = run_optimization(df, initial_capital=10000.0)

    # Save all candidates
    candidates_df = pd.DataFrame(candidates)
    candidates_file = output_dir / "track_c_smooth_candidates.csv"
    candidates_df.to_csv(candidates_file, index=False)
    print(f"\n[Results] Saved all candidates: {candidates_file}")

    # Display top candidates
    print(f"\n{'='*70}")
    print(f"TOP {args.top_n} CANDIDATES (Sorted by Drawdown Reduction)")
    print(f"{'='*70}\n")

    for idx, cand in enumerate(candidates[:args.top_n], 1):
        print(
            f"{idx}. EMA({cand['fast']}/{cand['slow']}) | "
            f"SL {cand['stop_loss_pct']}% TP {cand['take_profit_pct']}% Risk {cand['risk_pct']}%"
        )
        print(
            f"   Return: {cand['return_pct']:>7.2f}% | "
            f"Drawdown: {cand['max_drawdown_pct']:>6.2f}% | "
            f"Worst Daily: {cand['worst_daily_loss_pct']:>6.2f}%"
        )
        print(
            f"   Win Rate: {cand['win_rate']:>5.1f}% | "
            f"PF: {cand['profit_factor']:>4.2f} | "
            f"Trades/day: {cand['trades_per_day']:>5.2f} ({cand['total_trades']:>4d} total)"
        )
        print()

    # Best candidate comparison
    best = candidates[0]
    print(f"{'='*70}")
    print(f"BEST SMOOTH CANDIDATE (vs Current Track C)")
    print(f"{'='*70}")
    print(f"\nCURRENT TRACK C:")
    print(f"  EMA(12/20), SL 0.5%, TP 3.0%, Risk 0.5%")
    print(f"  Return: 165.78% | Drawdown: 9.99% | MC Pass: 87.60%")

    print(f"\nBEST SMOOTH ENHANCEMENT:")
    print(f"  EMA({best['fast']}/{best['slow']}), SL {best['stop_loss_pct']}%, TP {best['take_profit_pct']}%, Risk {best['risk_pct']}%")
    print(f"  Return: {best['return_pct']:.2f}% | Drawdown: {best['max_drawdown_pct']:.2f}%")
    print(f"  Trades/day: {best['trades_per_day']:.2f} | Win Rate: {best['win_rate']:.1f}%")

    dd_improvement = 9.99 - best["max_drawdown_pct"]
    print(f"\nDRAWDOWN IMPROVEMENT: {dd_improvement:+.2f}% {'✓' if dd_improvement > 0 else '✗'}")

    # Save summary
    summary_file = output_dir / "track_c_smooth_summary.json"
    with open(summary_file, "w") as f:
        json.dump(
            {
                "optimization": summary,
                "best_candidate": best,
                "current_track_c": {
                    "fast": 12,
                    "slow": 20,
                    "stop_loss_pct": 0.5,
                    "take_profit_pct": 3.0,
                    "risk_pct": 0.5,
                    "return_pct": 165.78,
                    "max_drawdown_pct": 9.99,
                    "mc_pass_prob": 87.60,
                },
                "improvement": {
                    "drawdown_reduction_pct": dd_improvement,
                    "return_change_pct": best["return_pct"] - 165.78,
                },
            },
            f,
            indent=2,
        )
    print(f"\n[Results] Saved summary: {summary_file}\n")


if __name__ == "__main__":
    main()
