"""Quick Track C smooth EMA optimizer using recent data."""
import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
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


def run_backtest(df: pd.DataFrame, params: Params, initial_capital: float = 10000.0) -> Dict:
    """Run backtest and return metrics."""
    data = build_signals(df, params.fast, params.slow)
    capital = initial_capital
    peak = initial_capital
    in_pos = False
    entry_price = 0.0
    pnls = []
    daily_pnls = {}

    for i in range(1, len(data)):
        row = data.iloc[i]
        price = float(row["Close"])
        ts = row["timestamp"]
        date = ts.date()

        if not in_pos and row["signal_diff"] > 0:
            in_pos = True
            entry_price = price
            risk_dollars = capital * (params.risk_pct / 100.0)
            stop_move = entry_price * (params.stop_loss_pct / 100.0)
            if stop_move <= 0:
                continue
            position_size = risk_dollars / stop_move
            continue

        if in_pos:
            pnl_pct = ((price - entry_price) / entry_price) * 100.0
            exit_price = price
            reason = None

            if pnl_pct <= -params.stop_loss_pct:
                reason = "SL"
                exit_price = entry_price * (1.0 - params.stop_loss_pct / 100.0)
            elif pnl_pct >= params.take_profit_pct:
                reason = "TP"
                exit_price = entry_price * (1.0 + params.take_profit_pct / 100.0)
            elif row["signal_diff"] < 0:
                reason = "Signal"

            if reason:
                pnl = position_size * (exit_price - entry_price)
                capital += pnl
                peak = max(peak, capital)
                pnls.append(pnl)
                if date not in daily_pnls:
                    daily_pnls[date] = 0
                daily_pnls[date] += pnl
                in_pos = False

    if not pnls:
        return {
            "total_trades": 0,
            "return_pct": 0.0,
            "max_dd_pct": 0.0,
            "worst_daily_pct": 0.0,
            "win_rate": 0.0,
            "pf": 0.0,
            "trades_per_day": 0.0,
        }

    total_pnl = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / len(pnls)) * 100.0
    return_pct = (total_pnl / initial_capital) * 100.0
    pf = sum(wins) / abs(sum(losses)) if losses else 0.0

    # Max drawdown
    equity_curve = [initial_capital]
    for p in pnls:
        equity_curve.append(equity_curve[-1] + p)
    max_dd = 0.0
    peak_equity = equity_curve[0]
    for e in equity_curve:
        peak_equity = max(peak_equity, e)
        dd = ((peak_equity - e) / peak_equity) * 100.0
        max_dd = max(max_dd, dd)

    # Worst daily loss
    daily_loss_pcts = [(day_pnl / initial_capital) * 100.0 for day_pnl in daily_pnls.values()]
    worst_daily = min(daily_loss_pcts) if daily_loss_pcts else 0.0

    trades_per_day = len(pnls) / max(len(daily_pnls), 1)

    return {
        "total_trades": len(pnls),
        "return_pct": return_pct,
        "max_dd_pct": max_dd,
        "worst_daily_pct": worst_daily,
        "win_rate": win_rate,
        "pf": pf,
        "trades_per_day": trades_per_day,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/XAUUSD_1h_sample.csv")
    parser.add_argument("--output-dir", default="FTMO_Challenge/Long_Strategy/Track_C_Time_Optimized/reports")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*70}")
    print(f"Track C Enhanced Smooth EMA Optimizer")
    print(f"{'='*70}\n")

    df = load_data(Path(args.data))
    # Use recent 40% for faster testing
    sample_idx = int(len(df) * 0.6)
    df_sample = df.iloc[sample_idx:].copy()
    print(f"Using {len(df_sample):,} recent bars for optimization\n")

    # Grid of smooth parameters
    candidates = []
    grid_size = 0

    for fast in [8, 10, 12]:
        for slow in [20, 26, 30]:
            if fast >= slow or (slow - fast) < 10:
                continue
            for sl in [0.75, 1.0, 1.25]:
                for tp in [3.0, 4.0]:
                    for risk in [0.5]:
                        params =Params(fast, slow, sl, tp, risk)
                        metrics = run_backtest(df_sample, params)
                        
                        # Score: prioritize lower DD
                        score = (-metrics["max_dd_pct"] * 10.0 + 
                                metrics["return_pct"] * 1.0 + 
                                metrics["trades_per_day"] * 2.0)
                        
                        candidates.append({
                            "fast": fast,
                            "slow": slow,
                            "sl": sl,
                            "tp": tp,
                            "score": score,
                            **metrics
                        })
                        grid_size += 1

    candidates.sort(key=lambda x: x["score"], reverse=True)
    print(f"Tested {grid_size} parameter combinations\n")

    # Show results
    print(f"{'='*70}\nTOP 10 CANDIDATES\n{'='*70}\n")
    for i, c in enumerate(candidates[:10], 1):
        print(f"{i}. EMA({c['fast']}/{c['slow']}) SL {c['sl']}% TP {c['tp']}%")
        print(f"   Return: {c['return_pct']:6.2f}% | DD: {c['max_dd_pct']:6.2f}% | Trades: {c['total_trades']:3d} ({c['trades_per_day']:4.2f}/day)")
        print()

    best = candidates[0]
    print(f"{'='*70}\nCOMPARISON\n{'='*70}")
    print(f"\nCURRENT:  EMA(12/20) SL 0.5% TP 3.0% → Return 165.78%, DD 9.99%")
    print(f"ENHANCED: EMA({best['fast']}/{best['slow']}) SL {best['sl']}% TP {best['tp']}% → Return {best['return_pct']:.2f}%, DD {best['max_dd_pct']:.2f}%")
    dd_imp = 9.99 - best['max_dd_pct']
    print(f"\nDRAWDOWN IMPROVEMENT: {dd_imp:+.2f}% {'✓' if dd_imp > 0 else '✗'}\n")

    # Save results
    candidates_df = pd.DataFrame(candidates)
    csv_file = output_dir / "track_c_smooth_candidates.csv"
    candidates_df.to_csv(csv_file, index=False)
    
    with open(output_dir / "track_c_smooth_best.json", "w") as f:
        json.dump({"best": best, "drawdown_improvement_pct": dd_imp}, f, indent=2)

    print(f"Results saved to: {csv_file}\n")


if __name__ == "__main__":
    main()
