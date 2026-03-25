"""Extended FTMO balance sweep to test higher multipliers (up to 4.0) for faster pass times."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def load_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], errors="coerce")
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], errors="coerce")
    df = df.dropna(subset=["exit_ts", "pnl"]).sort_values("exit_ts").reset_index(drop=True)
    return df


def apply_risk_multiplier(trades_df: pd.DataFrame, mult: float, initial_capital: float) -> pd.DataFrame:
    temp = trades_df.copy().sort_values("exit_ts").reset_index(drop=True)
    temp["pnl"] = temp["pnl"].astype(float) * float(mult)

    equity = initial_capital + temp["pnl"].cumsum()
    peak = equity.cummax()
    drawdown_pct = np.where(peak > 0, ((peak - equity) / peak) * 100.0, 0.0)

    temp["equity_after"] = equity
    temp["drawdown_pct"] = drawdown_pct
    return temp


def compute_metrics(trades_df: pd.DataFrame, initial_capital: float) -> Dict[str, float]:
    if trades_df.empty:
        return {
            "return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "worst_daily_loss_pct": 0.0,
            "sharpe_daily_annualized": 0.0,
            "final_equity": float(initial_capital),
            "trades": 0,
        }

    total_pnl = float(trades_df["pnl"].sum())
    max_dd = float(trades_df["drawdown_pct"].max())

    daily = trades_df.copy()
    daily["date"] = daily["exit_ts"].dt.date
    daily_pnl = daily.groupby("date", as_index=False)["pnl"].sum()
    daily_pnl["daily_loss_pct"] = (daily_pnl["pnl"] / float(initial_capital)) * 100.0
    worst_daily = float(daily_pnl["daily_loss_pct"].min()) if not daily_pnl.empty else 0.0

    equity_daily = float(initial_capital) + daily_pnl["pnl"].cumsum()
    daily_returns = equity_daily.pct_change().dropna()
    if daily_returns.empty or float(daily_returns.std()) == 0.0:
        sharpe = 0.0
    else:
        sharpe = float((daily_returns.mean() / daily_returns.std()) * np.sqrt(252.0))

    final_equity = float(trades_df["equity_after"].iloc[-1]) if "equity_after" in trades_df.columns and not trades_df.empty else float(initial_capital)

    return {
        "return_pct": (total_pnl / float(initial_capital)) * 100.0,
        "max_drawdown_pct": max_dd,
        "worst_daily_loss_pct": worst_daily,
        "sharpe_daily_annualized": sharpe,
        "final_equity": final_equity,
        "trades": int(len(trades_df)),
    }


def evaluate_ftmo_rules(
    trades_df: pd.DataFrame,
    target_profit_pct: float,
    max_total_dd_pct: float,
    max_daily_dd_pct: float,
    initial_capital: float,
) -> Tuple[bool, int | None, str | None]:
    if trades_df.empty:
        return False, None, "No trades"

    temp = trades_df.copy().sort_values("exit_ts")
    target_equity = initial_capital * (1.0 + target_profit_pct / 100.0)
    total_dd_floor = initial_capital * (1.0 - max_total_dd_pct / 100.0)

    start_date = temp["exit_ts"].iloc[0].date()
    equity = float(initial_capital)
    current_day = None
    day_start_equity = equity

    for _, row in temp.iterrows():
        trade_day = row["exit_ts"].date()
        if current_day is None or trade_day != current_day:
            current_day = trade_day
            day_start_equity = equity

        equity += float(row["pnl"])

        if equity < total_dd_floor:
            return False, None, "Total drawdown breach"

        daily_floor = day_start_equity * (1.0 - max_daily_dd_pct / 100.0)
        if equity < daily_floor:
            return False, None, "Daily drawdown breach"

        if equity >= target_equity:
            days = (trade_day - start_date).days + 1
            return True, int(days), None

    return False, None, "Target not reached"


def ftmo_monte_carlo_probability(
    trades_df: pd.DataFrame,
    n_paths: int,
    seed: int,
    target_profit_pct: float,
    max_total_dd_pct: float,
    max_daily_dd_pct: float,
    initial_capital: float,
) -> Tuple[float, int | None]:
    if trades_df.empty:
        return 0.0, None

    temp = trades_df.copy().sort_values("exit_ts").reset_index(drop=True)
    pnls = temp["pnl"].astype(float).to_numpy()
    dates = temp["exit_ts"].dt.date.to_list()
    if len(pnls) == 0:
        return 0.0, None

    target_equity = initial_capital * (1.0 + target_profit_pct / 100.0)
    total_dd_floor = initial_capital * (1.0 - max_total_dd_pct / 100.0)
    start_date = dates[0]

    rng = np.random.default_rng(seed)
    pass_days: List[int] = []

    for _ in range(int(n_paths)):
        sampled = rng.choice(pnls, size=len(pnls), replace=True)
        equity = float(initial_capital)
        current_day = None
        day_start_equity = equity

        for i, pnl in enumerate(sampled):
            trade_day = dates[i]
            if current_day is None or trade_day != current_day:
                current_day = trade_day
                day_start_equity = equity

            equity += float(pnl)
            if equity < total_dd_floor:
                break

            daily_floor = day_start_equity * (1.0 - max_daily_dd_pct / 100.0)
            if equity < daily_floor:
                break

            if equity >= target_equity:
                pass_days.append((trade_day - start_date).days + 1)
                break

    pass_prob = (len(pass_days) / float(n_paths)) * 100.0 if n_paths > 0 else 0.0
    median_days = int(np.median(pass_days)) if pass_days else None
    return float(pass_prob), median_days


def pareto_front(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    temp = df.sort_values(["mc_pass_prob_pct", "return_pct"], ascending=[False, False]).reset_index(drop=True)
    keep = []
    best_ret = -1e18
    for _, row in temp.iterrows():
        if float(row["return_pct"]) > best_ret:
            keep.append(True)
            best_ret = float(row["return_pct"])
        else:
            keep.append(False)
    return temp.loc[keep].reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extended sweep to find fastest FTMO pass time under 10/10/3 constraints")
    parser.add_argument(
        "--trades",
        type=Path,
        default=Path("FTMO_Challenge/Short_Strategy/Track_C_Short_FTMO/reports/track_c_short_ftmo_oos_trades.csv"),
        help="Path to Track C OOS trades CSV",
    )
    parser.add_argument("--initial-capital", type=float, default=10000.0)
    parser.add_argument("--target-profit-pct", type=float, default=10.0)
    parser.add_argument("--max-total-dd-pct", type=float, default=10.0)
    parser.add_argument("--max-daily-dd-pct", type=float, default=3.0)
    parser.add_argument("--min-mult", type=float, default=0.80)
    parser.add_argument("--max-mult", type=float, default=4.00)
    parser.add_argument("--step", type=float, default=0.1)
    parser.add_argument("--mc-paths", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    trades_path = args.trades if args.trades.is_absolute() else (Path.cwd() / args.trades)
    if not trades_path.exists():
        raise FileNotFoundError(f"Trades CSV not found: {trades_path}")

    track_root = trades_path.parent.parent
    reports_dir = track_root / "reports"
    images_dir = track_root / "images"
    reports_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    trades = load_trades(trades_path)
    rows: List[Dict] = []

    multipliers = np.arange(args.min_mult, args.max_mult + 1e-9, args.step)
    for mult in multipliers:
        sim = apply_risk_multiplier(trades, float(mult), args.initial_capital)
        m = compute_metrics(sim, args.initial_capital)

        realized_pass, realized_days, failure_reason = evaluate_ftmo_rules(
            sim,
            target_profit_pct=args.target_profit_pct,
            max_total_dd_pct=args.max_total_dd_pct,
            max_daily_dd_pct=args.max_daily_dd_pct,
            initial_capital=args.initial_capital,
        )

        mc_pass_prob, mc_median_days = ftmo_monte_carlo_probability(
            sim,
            n_paths=args.mc_paths,
            seed=args.seed,
            target_profit_pct=args.target_profit_pct,
            max_total_dd_pct=args.max_total_dd_pct,
            max_daily_dd_pct=args.max_daily_dd_pct,
            initial_capital=args.initial_capital,
        )

        feasible = bool(m["max_drawdown_pct"] <= args.max_total_dd_pct and m["worst_daily_loss_pct"] >= -args.max_daily_dd_pct)

        rows.append(
            {
                "risk_multiplier": float(round(mult, 4)),
                "return_pct": float(m["return_pct"]),
                "max_drawdown_pct": float(m["max_drawdown_pct"]),
                "worst_daily_loss_pct": float(m["worst_daily_loss_pct"]),
                "sharpe_daily_annualized": float(m["sharpe_daily_annualized"]),
                "final_equity": float(m["final_equity"]),
                "trades": int(m["trades"]),
                "feasible_10_10_3": feasible,
                "realized_pass": bool(realized_pass),
                "realized_days_to_pass": realized_days,
                "realized_failure_reason": failure_reason,
                "mc_pass_prob_pct": float(mc_pass_prob),
                "mc_median_days_to_pass": mc_median_days,
            }
        )

    sweep_df = pd.DataFrame(rows)
    feasible_df = sweep_df[sweep_df["feasible_10_10_3"]].copy().sort_values("risk_multiplier")
    pareto_df = pareto_front(feasible_df)

    out_csv = reports_dir / "track_c_ftmo_balance_sweep_extended.csv"
    out_pareto_csv = reports_dir / "track_c_ftmo_balance_pareto_extended.csv"
    out_json = reports_dir / "track_c_ftmo_balance_extended_summary.json"
    out_txt = reports_dir / "track_c_ftmo_balance_extended_summary.txt"
    out_png = images_dir / "track_c_ftmo_balance_frontier_extended.png"
    out_best_equity_png = images_dir / "track_c_ftmo_best_balance_equity_extended.png"

    sweep_df.to_csv(out_csv, index=False)
    pareto_df.to_csv(out_pareto_csv, index=False)

    # Find best for minimizing median days while maintaining 80%+ pass probability
    best_fastest = None
    if not feasible_df.empty:
        qualified = feasible_df[feasible_df["mc_pass_prob_pct"] >= 80.0].copy()
        if not qualified.empty:
            fastest = qualified.sort_values("mc_median_days_to_pass").iloc[0].to_dict()
            best_fastest = fastest

    # Also calculate a balanced best (same as original sweep)
    best_balance = None
    if not feasible_df.empty:
        scored = feasible_df.copy()
        scored["score"] = (
            scored["mc_pass_prob_pct"] * 1.0
            + scored["return_pct"] * 0.35
            + scored["sharpe_daily_annualized"] * 0.8
            - scored["max_drawdown_pct"] * 0.10
            - scored["mc_median_days_to_pass"].fillna(999.0) * 0.05  # Increased weight for speed
        )
        best_balance = scored.sort_values("score", ascending=False).iloc[0].to_dict()

    summary = {
        "constraints": {
            "target_profit_pct": float(args.target_profit_pct),
            "max_total_dd_pct": float(args.max_total_dd_pct),
            "max_daily_dd_pct": float(args.max_daily_dd_pct),
            "mc_paths": int(args.mc_paths),
        },
        "sweep": {
            "min_multiplier": float(args.min_mult),
            "max_multiplier": float(args.max_mult),
            "step": float(args.step),
            "tested_points": int(len(sweep_df)),
            "feasible_points": int(len(feasible_df)),
        },
        "best_balance": best_balance,
        "fastest_with_80_pct_pass": best_fastest,
    }
    out_json.write_text(json.dumps(summary, indent=2))

    lines = [
        "Track C FTMO Balance Sweep - EXTENDED (0.8 to 4.0 multiplier)",
        "Looking for fastest pass time under FTMO 10% target / 10% total DD / 3% daily DD",
        "",
        f"Tested multipliers: {args.min_mult:.2f} to {args.max_mult:.2f} (step {args.step:.2f})",
        f"Total tested: {len(sweep_df)} points",
        f"Feasible under 10/10/3: {len(feasible_df)} points",
        "",
        "=== FASTEST PATH (80%+ pass probability) ===",
    ]

    if best_fastest is not None:
        lines.extend(
            [
                f"  Risk multiplier: {best_fastest['risk_multiplier']:.2f}",
                f"  Return %: {best_fastest['return_pct']:.2f}",
                f"  Final equity: ${best_fastest['final_equity']:.2f}",
                f"  Sharpe: {best_fastest['sharpe_daily_annualized']:.3f}",
                f"  Max DD %: {best_fastest['max_drawdown_pct']:.2f}",
                f"  Worst daily loss %: {best_fastest['worst_daily_loss_pct']:.2f}",
                f"  MC pass probability: {best_fastest['mc_pass_prob_pct']:.2f}%",
                f"  >>> MC median days to pass: {best_fastest['mc_median_days_to_pass']} days <<<",
                f"  Realized pass: {'YES (' + str(best_fastest['realized_days_to_pass']) + ' days)' if best_fastest['realized_pass'] else 'NO'}",
            ]
        )
    else:
        lines.append("  No points with 80%+ pass probability found.")

    lines.extend(
        [
            "",
            "=== BEST BALANCE (overall trade-off) ===",
        ]
    )

    if best_balance is not None:
        lines.extend(
            [
                f"  Risk multiplier: {best_balance['risk_multiplier']:.2f}",
                f"  Return %: {best_balance['return_pct']:.2f}",
                f"  Final equity: ${best_balance['final_equity']:.2f}",
                f"  Sharpe: {best_balance['sharpe_daily_annualized']:.3f}",
                f"  Max DD %: {best_balance['max_drawdown_pct']:.2f}",
                f"  Worst daily loss %: {best_balance['worst_daily_loss_pct']:.2f}",
                f"  MC pass probability %: {best_balance['mc_pass_prob_pct']:.2f}",
                f"  MC median days to pass: {best_balance['mc_median_days_to_pass']}",
                f"  Realized pass: {'YES' if best_balance['realized_pass'] else 'NO'}",
                f"  Realized days to pass: {best_balance['realized_days_to_pass']}",
            ]
        )
    else:
        lines.append("  No feasible points found under 10/10/3 constraints.")

    out_txt.write_text("\n".join(lines))

    # Visual 1: MC pass probability vs return, with marker size as max DD
    fig, ax = plt.subplots(figsize=(12, 7))
    infeasible = sweep_df[~sweep_df["feasible_10_10_3"]]
    feasible = sweep_df[sweep_df["feasible_10_10_3"]]

    if not infeasible.empty:
        ax.scatter(
            infeasible["mc_pass_prob_pct"],
            infeasible["return_pct"],
            s=np.clip(infeasible["max_drawdown_pct"] * 12.0, 20, 260),
            alpha=0.35,
            c="#d62728",
            label="Infeasible (violates 10/10/3)",
            edgecolors="none",
        )

    if not feasible.empty:
        ax.scatter(
            feasible["mc_pass_prob_pct"],
            feasible["return_pct"],
            s=np.clip(feasible["max_drawdown_pct"] * 12.0, 20, 260),
            alpha=0.8,
            c="#2ca02c",
            label="Feasible (10/10/3)",
            edgecolors="black",
            linewidths=0.4,
        )

    if not pareto_df.empty:
        pareto_sorted = pareto_df.sort_values("mc_pass_prob_pct")
        ax.plot(
            pareto_sorted["mc_pass_prob_pct"],
            pareto_sorted["return_pct"],
            color="#1f77b4",
            linewidth=2.0,
            marker="o",
            markersize=4,
            label="Pareto frontier",
        )

    if best_fastest is not None and best_fastest["mc_pass_prob_pct"] >= 80:
        ax.scatter(
            [best_fastest["mc_pass_prob_pct"]],
            [best_fastest["return_pct"]],
            s=300,
            marker="^",
            c="#9467bd",
            edgecolors="black",
            linewidths=1.0,
            label="Fastest (80%+ pass)",
            zorder=5,
        )

    if best_balance is not None:
        ax.scatter(
            [best_balance["mc_pass_prob_pct"]],
            [best_balance["return_pct"]],
            s=300,
            marker="*",
            c="#ff7f0e",
            edgecolors="black",
            linewidths=1.0,
            label="Best balance",
            zorder=5,
        )

    ax.set_title("Track C Extended FTMO Balance (0.8-4.0 multiplier range)\n10% target / 10% total DD / 3% daily DD", fontsize=13, fontweight="bold")
    ax.set_xlabel("Monte Carlo Pass Probability (%)", fontsize=11)
    ax.set_ylabel("OOS Return (%)", fontsize=11)
    ax.grid(alpha=0.25)
    ax.legend(loc="best", fontsize=10)
    fig.tight_layout()
    fig.savefig(out_png, dpi=160)
    plt.close(fig)

    # Visual 2: Median days vs multiplier
    if not feasible_df.empty:
        fig, ax = plt.subplots(figsize=(12, 6))
        feas_sorted = feasible_df.sort_values("risk_multiplier")
        ax.plot(feas_sorted["risk_multiplier"], feas_sorted["mc_median_days_to_pass"], 
                marker="o", linewidth=2.0, markersize=6, color="#0f766e", label="MC median days")
        if best_fastest is not None:
            ax.scatter([best_fastest["risk_multiplier"]], [best_fastest["mc_median_days_to_pass"]], 
                      s=200, marker="^", c="#9467bd", edgecolors="black", linewidths=1.0, 
                      label="Fastest (80%+ pass)", zorder=5)
        
        ax.set_title("Track C: MC Median Days to Pass vs Risk Multiplier", fontsize=13, fontweight="bold")
        ax.set_xlabel("Risk Multiplier", fontsize=11)
        ax.set_ylabel("Median Days to Pass (MC)", fontsize=11)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=10)
        fig.tight_layout()
        fig.savefig(images_dir / "track_c_ftmo_median_days_vs_multiplier.png", dpi=160)
        plt.close(fig)

    # Visual 3: Best equity curve
    if best_fastest is not None:
        best_mult = float(best_fastest["risk_multiplier"])
        best_sim = apply_risk_multiplier(trades, best_mult, args.initial_capital)
        if not best_sim.empty:
            curve = best_sim.sort_values("exit_ts").copy()
            equity = curve["equity_after"].astype(float)
            peak = equity.cummax()
            dd = np.where(peak > 0, ((peak - equity) / peak) * 100.0, 0.0)

            fig, ax1 = plt.subplots(figsize=(13, 6))
            ax1.plot(curve["exit_ts"], equity, color="#0f766e", linewidth=2.0, label="Equity")
            ax1.plot(curve["exit_ts"], peak, color="#14b8a6", linewidth=1.0, linestyle="--", label="Peak")
            ax1.axhline(y=args.initial_capital * 1.1, color="green", linestyle=":", linewidth=1.5, label="FTMO target (+10%)")
            ax1.set_title(f"Track C Fastest Multiplier Equity Curve ({best_mult:.2f}x multiplier, {best_fastest['mc_median_days_to_pass']}d median)")
            ax1.set_xlabel("Exit timestamp")
            ax1.set_ylabel("Equity ($)")
            ax1.grid(alpha=0.2)

            ax2 = ax1.twinx()
            ax2.plot(curve["exit_ts"], dd, color="#dc2626", linewidth=1.0, alpha=0.85, label="Drawdown %")
            ax2.set_ylabel("Drawdown (%)")

            h1, l1 = ax1.get_legend_handles_labels()
            h2, l2 = ax2.get_legend_handles_labels()
            ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
            fig.tight_layout()
            fig.savefig(out_best_equity_png, dpi=170)
            plt.close(fig)

    print(f"\n✓ Saved: {out_csv}")
    print(f"✓ Saved: {out_pareto_csv}")
    print(f"✓ Saved: {out_json}")
    print(f"✓ Saved: {out_txt}")
    print(f"✓ Saved: {out_png}")
    if best_fastest is not None:
        print(f"✓ Saved: {out_best_equity_png}")
        print(f"\n>>> FASTEST PATH FOUND <<<")
        print(f"Multiplier: {best_fastest['risk_multiplier']:.2f}x")
        print(f"Median days to pass: {best_fastest['mc_median_days_to_pass']} days")
        print(f"Pass probability: {best_fastest['mc_pass_prob_pct']:.1f}%")
    print(f"✓ Saved: {images_dir / 'track_c_ftmo_median_days_vs_multiplier.png'}")


if __name__ == "__main__":
    main()
