from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


INITIAL_CAPITAL = 10000.0
STEP1_TARGET_PCT = 10.0
STEP2_TARGET_PCT = 15.0
EXPECTED_RISK_PCT = 0.54
MC_RUNS = 1000
MC_SEED = 42


def load_source(track_c_root: Path, track_d_root: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame, str]:
    frozen_reports = track_d_root / "reports"
    frozen_summary = frozen_reports / "track_d_source_track_c_best_candidate.json"
    frozen_trades = frozen_reports / "track_d_best_candidate_oos_trades.csv"
    frozen_rankings = frozen_reports / "track_d_source_candidate_rankings.csv"

    if frozen_summary.exists() and frozen_trades.exists() and frozen_rankings.exists():
        summary = json.loads(frozen_summary.read_text())
        trades = pd.read_csv(frozen_trades)
        rankings = pd.read_csv(frozen_rankings)
        source_mode = "frozen-track-d-snapshot"
    else:
        reports_dir = track_c_root / "reports"
        summary = json.loads((reports_dir / "track_c_best_candidate.json").read_text())
        trades = pd.read_csv(reports_dir / "track_c_best_candidate_oos_trades.csv")
        rankings = pd.read_csv(reports_dir / "track_c_candidate_rankings.csv")
        source_mode = "current-track-c"

    trades["entry_ts"] = pd.to_datetime(trades["entry_ts"])
    trades["exit_ts"] = pd.to_datetime(trades["exit_ts"])
    return summary, trades, rankings, source_mode


def validate_source(summary: dict) -> None:
    selected = summary.get("selected", {})
    risk_pct = float(selected.get("risk_pct", -1.0))
    if not np.isclose(risk_pct, EXPECTED_RISK_PCT, atol=1e-9):
        raise RuntimeError(
            f"Track C source candidate risk_pct={risk_pct:.6g} does not match expected {EXPECTED_RISK_PCT:.2f}."
        )


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
        )
        .sort_values("date")
        .reset_index(drop=True)
    )
    out["daily_return_pct_on_initial"] = (out["total_pnl"] / INITIAL_CAPITAL) * 100.0
    return out


def compute_trades_per_day(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 1.0
    counts = trades.assign(exit_date=trades["exit_ts"].dt.date).groupby("exit_date")["pnl"].count()
    if counts.empty:
        return 1.0
    return float(counts.mean())


def monte_carlo_paths(trades: pd.DataFrame, runs: int = MC_RUNS) -> np.ndarray:
    if trades.empty:
        return np.empty((0, 0))
    pnls = trades["pnl"].to_numpy(dtype=float)
    num_trades = len(pnls)
    samples = np.random.choice(pnls, size=(runs, num_trades), replace=True)
    return INITIAL_CAPITAL + np.cumsum(samples, axis=1)


def first_hit_index(paths: np.ndarray, threshold: float) -> np.ndarray:
    if paths.size == 0:
        return np.array([], dtype=float)
    hits = np.full(paths.shape[0], np.nan, dtype=float)
    for index in range(paths.shape[0]):
        found = np.where(paths[index] >= threshold)[0]
        if found.size > 0:
            hits[index] = float(found[0])
    return hits


def step_timing_stats(paths: np.ndarray, trades_per_day: float) -> dict:
    if paths.size == 0:
        return {
            "step1_pass_probability_pct": 0.0,
            "step2_pass_probability_pct": 0.0,
            "step1_avg_trades": None,
            "step2_avg_trades": None,
            "step1_avg_days": None,
            "step2_avg_days": None,
        }

    step1_equity = INITIAL_CAPITAL * (1.0 + STEP1_TARGET_PCT / 100.0)
    step2_equity = INITIAL_CAPITAL * (1.0 + STEP2_TARGET_PCT / 100.0)
    step1_hits = first_hit_index(paths, step1_equity)
    step2_hits = first_hit_index(paths, step2_equity)

    step1_valid = step1_hits[~np.isnan(step1_hits)]
    step2_valid = step2_hits[~np.isnan(step2_hits)]
    step1_avg_trades = float(np.mean(step1_valid)) if step1_valid.size > 0 else None
    step2_avg_trades = float(np.mean(step2_valid)) if step2_valid.size > 0 else None

    tpd = max(trades_per_day, 1e-9)
    return {
        "step1_pass_probability_pct": float((step1_valid.size / len(paths)) * 100.0),
        "step2_pass_probability_pct": float((step2_valid.size / len(paths)) * 100.0),
        "step1_avg_trades": step1_avg_trades,
        "step2_avg_trades": step2_avg_trades,
        "step1_avg_days": (step1_avg_trades / tpd) if step1_avg_trades is not None else None,
        "step2_avg_days": (step2_avg_trades / tpd) if step2_avg_trades is not None else None,
    }


def compute_metrics(trades: pd.DataFrame, daily: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "total_trades": 0,
            "total_pnl": 0.0,
            "return_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "worst_daily_loss_pct": 0.0,
            "trades_per_day": 0.0,
            "expectancy_usd": 0.0,
            "equity_curve": np.array([INITIAL_CAPITAL]),
            "peak_curve": np.array([INITIAL_CAPITAL]),
            "dd_curve": np.array([0.0]),
        }

    pnl = trades["pnl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    total_pnl = float(pnl.sum())
    equity_curve = INITIAL_CAPITAL + pnl.cumsum().to_numpy(dtype=float)
    peak_curve = np.maximum.accumulate(equity_curve)
    dd_curve = np.where(peak_curve > 0, ((peak_curve - equity_curve) / peak_curve) * 100.0, 0.0)

    gross_win = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 0.0

    worst_daily_loss_pct = float(daily["daily_return_pct_on_initial"].min()) if not daily.empty else 0.0

    return {
        "total_trades": int(len(trades)),
        "total_pnl": total_pnl,
        "return_pct": float((total_pnl / INITIAL_CAPITAL) * 100.0),
        "win_rate_pct": float((len(wins) / len(trades)) * 100.0),
        "profit_factor": float(profit_factor),
        "max_drawdown_pct": float(dd_curve.max()) if len(dd_curve) else 0.0,
        "worst_daily_loss_pct": worst_daily_loss_pct,
        "trades_per_day": compute_trades_per_day(trades),
        "expectancy_usd": float(total_pnl / len(trades)),
        "equity_curve": np.insert(equity_curve, 0, INITIAL_CAPITAL),
        "peak_curve": np.insert(peak_curve, 0, INITIAL_CAPITAL),
        "dd_curve": np.insert(dd_curve, 0, 0.0),
    }


def plot_trade_activity(daily: pd.DataFrame, out_path: Path) -> None:
    if daily.empty:
        return

    plt.figure(figsize=(14, 6))
    ax1 = plt.gca()
    ax2 = ax1.twinx()

    x = np.arange(len(daily))
    labels = daily["date"].astype(str)
    ax1.bar(x, daily["trades"], alpha=0.45, color="#0f766e", label="Trades per day")
    ax2.plot(x, daily["trades"].cumsum(), color="#111827", linewidth=2.2, label="Cumulative trades")

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=45, ha="right")
    ax1.set_title("Track D Trade Activity")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Trades per day")
    ax2.set_ylabel("Cumulative trades")

    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper left")

    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def plot_probable_path(paths: np.ndarray, timing: dict, out_path: Path) -> None:
    if paths.size == 0:
        return

    p10 = np.percentile(paths, 10, axis=0)
    p25 = np.percentile(paths, 25, axis=0)
    p50 = np.percentile(paths, 50, axis=0)
    p75 = np.percentile(paths, 75, axis=0)
    p90 = np.percentile(paths, 90, axis=0)
    x = np.arange(paths.shape[1])

    step1_equity = INITIAL_CAPITAL * (1.0 + STEP1_TARGET_PCT / 100.0)
    step2_equity = INITIAL_CAPITAL * (1.0 + STEP2_TARGET_PCT / 100.0)

    plt.figure(figsize=(14, 6))
    plt.fill_between(x, p10, p90, alpha=0.2, color="#c7d2fe", label="10-90 percentile")
    plt.fill_between(x, p25, p75, alpha=0.35, color="#2563eb", label="25-75 percentile")
    plt.plot(x, p50, linewidth=2.2, color="#111827", label="Median path")
    plt.axhline(step1_equity, linestyle="--", linewidth=1.5, color="#16a34a", label="Step 1 (+10%)")
    plt.axhline(step2_equity, linestyle="--", linewidth=1.5, color="#f97316", label="Step 2 (+15%)")

    if timing["step1_avg_trades"] is not None:
        step1_x = timing["step1_avg_trades"]
        plt.axvline(step1_x, color="#16a34a", linewidth=1.2, alpha=0.9)
        plt.text(step1_x, step1_equity, f"  Avg S1: {step1_x:.1f} trades / {timing['step1_avg_days']:.1f} days", color="#16a34a", va="bottom")
    if timing["step2_avg_trades"] is not None:
        step2_x = timing["step2_avg_trades"]
        plt.axvline(step2_x, color="#f97316", linewidth=1.2, alpha=0.9)
        plt.text(step2_x, step2_equity, f"  Avg S2: {step2_x:.1f} trades / {timing['step2_avg_days']:.1f} days", color="#f97316", va="bottom")

    plt.title("Track D Probable Path (Monte Carlo OOS)")
    plt.xlabel("Trade #")
    plt.ylabel("Equity ($)")
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def plot_monte_carlo(paths: np.ndarray, out_path: Path) -> None:
    if paths.size == 0:
        return

    plt.figure(figsize=(14, 6))
    to_plot = min(250, paths.shape[0])
    choice = np.random.choice(paths.shape[0], to_plot, replace=False)
    for index in choice:
        plt.plot(paths[index], alpha=0.08, linewidth=0.8, color="#ea580c")
    plt.plot(paths.mean(axis=0), color="#111827", linewidth=2.0, label="Mean path")
    plt.axhline(INITIAL_CAPITAL, color="#16a34a", linestyle="--", linewidth=1.2, label="Initial capital")
    plt.title("Track D Monte Carlo Paths")
    plt.xlabel("Trade #")
    plt.ylabel("Equity ($)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def render_dashboard(summary: dict, metrics: dict, daily: pd.DataFrame, out_path: Path) -> None:
    plt.figure(figsize=(16, 10))
    grid = plt.GridSpec(2, 2, height_ratios=[1.2, 1], width_ratios=[1.4, 1])

    ax_eq = plt.subplot(grid[0, 0])
    x = np.arange(len(metrics["equity_curve"]))
    ax_eq.plot(x, metrics["equity_curve"], color="#0f766e", linewidth=2.2, label="Equity")
    ax_eq.plot(x, metrics["peak_curve"], color="#2dd4bf", linewidth=1.4, linestyle="--", label="Running peak")
    ax_eq.set_title("Track D Equity Path (Pinned 0.54% Risk Candidate)", fontsize=12, weight="bold")
    ax_eq.set_xlabel("Trade #")
    ax_eq.set_ylabel("Equity ($)")
    ax_eq.grid(alpha=0.2)
    ax_eq.legend(loc="upper left")

    ax_dd = ax_eq.twinx()
    ax_dd.plot(x, metrics["dd_curve"], color="#dc2626", linewidth=1.2, alpha=0.9, label="Drawdown %")
    ax_dd.set_ylabel("Drawdown (%)", color="#dc2626")
    ax_dd.tick_params(axis="y", colors="#dc2626")

    ax_daily = plt.subplot(grid[1, 0])
    if not daily.empty:
        daily_x = np.arange(len(daily))
        daily_pnl = daily["total_pnl"].to_numpy(dtype=float)
        colors = np.where(daily_pnl >= 0, "#0ea5e9", "#f97316")
        ax_daily.bar(daily_x, daily_pnl, color=colors, alpha=0.85)
    ax_daily.axhline(0, color="#111827", linewidth=1)
    ax_daily.set_title("Track D Daily PnL Distribution", fontsize=12, weight="bold")
    ax_daily.set_xlabel("Trading day index")
    ax_daily.set_ylabel("PnL ($)")
    ax_daily.grid(alpha=0.2)

    ax_text = plt.subplot(grid[:, 1])
    ax_text.axis("off")

    selected = summary.get("selected", {})
    lines = [
        "TRACK D SNAPSHOT",
        "",
        f"Source: {summary.get('source_track', 'Track C')} non-canonical candidate",
        f"Params: EMA({selected.get('fast')}/{selected.get('slow')}), SL {selected.get('sl_pct')}%, TP {selected.get('tp_pct')}%, Risk {selected.get('risk_pct')}%",
        "",
        f"Total trades: {metrics['total_trades']}",
        f"Trades/day: {metrics['trades_per_day']:.2f}",
        f"Expectancy/trade: ${metrics['expectancy_usd']:.2f}",
        f"Win rate: {metrics['win_rate_pct']:.2f}%",
        f"Profit factor: {metrics['profit_factor']:.2f}",
        f"Total return: {metrics['return_pct']:.2f}%",
        f"Total equity: ${INITIAL_CAPITAL + metrics['total_pnl']:.2f}",
        f"Max drawdown: {metrics['max_drawdown_pct']:.2f}%",
        f"Worst daily loss: {metrics['worst_daily_loss_pct']:.2f}%",
        "",
        f"MC pass probability: {summary.get('mc_pass_probability_pct', 0.0):.2f}%",
        f"MC Step 1 avg days: {summary.get('mc_step1_avg_days_to_pass', 0.0):.1f}",
        f"MC Step 2 avg days: {summary.get('mc_step2_avg_days_to_pass', 0.0):.1f}",
        "",
        "Interpretation:",
        "- Faster candidate than canonical Track C target set",
        "- Not the recommended strict-FTMO canonical path",
        "- Suitable only for discretionary review of higher-risk execution",
    ]

    ax_text.text(
        0.02,
        0.98,
        "\n".join(lines),
        va="top",
        ha="left",
        fontsize=10.5,
        family="monospace",
        bbox={"boxstyle": "round,pad=0.6", "facecolor": "#f8fafc", "edgecolor": "#cbd5e1"},
    )

    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()


def build_track_d_summary(source_summary: dict, source_root: Path, source_mode: str) -> dict:
    summary = dict(source_summary)
    summary["track"] = "Track D - Non-Canonical 0.54%"
    summary["canonical"] = False
    summary["status"] = "Pinned snapshot of Track C 0.54% candidate"
    summary["source_track"] = "Track C - Time Optimized"
    summary["source_mode"] = source_mode
    summary["source_files"] = {
        "frozen_summary_json": str(source_root / "reports" / "track_d_source_track_c_best_candidate.json"),
        "frozen_trades_csv": str(source_root / "reports" / "track_d_best_candidate_oos_trades.csv"),
        "frozen_rankings_csv": str(source_root / "reports" / "track_d_source_candidate_rankings.csv"),
    }
    summary["snapshot_generated_utc"] = datetime.now(timezone.utc).isoformat()
    return summary


def write_text_summary(summary: dict, out_path: Path) -> None:
    selected = summary.get("selected", {})
    lines = [
        "TRACK D - NON-CANONICAL 0.54% SNAPSHOT",
        "=" * 60,
        "Source: Track C current best-candidate artifact family",
        "Purpose: discretionary trading review without overwriting canonical Track C outputs",
        f"Canonical: {summary.get('canonical')}",
        f"Status: {summary.get('status')}",
        "",
        f"Selected params: EMA({selected.get('fast')}/{selected.get('slow')}), SL {selected.get('sl_pct')}%, TP {selected.get('tp_pct')}%, Risk {selected.get('risk_pct')}%",
        f"Fold pass rate: {summary.get('fold_pass_rate_pct', 0.0):.2f}%",
        f"OOS return: {summary.get('oos_return_pct', 0.0):.2f}%",
        f"OOS max drawdown: {summary.get('oos_max_dd_pct', 0.0):.2f}%",
        f"OOS worst daily loss: {summary.get('oos_worst_daily_loss_pct', 0.0):.2f}%",
        f"OOS trades: {summary.get('oos_trades', 0)}",
        f"Monte Carlo pass probability: {summary.get('mc_pass_probability_pct', 0.0):.2f}%",
        f"Step 1 avg days: {summary.get('mc_step1_avg_days_to_pass', 0.0):.1f}",
        f"Step 2 avg days: {summary.get('mc_step2_avg_days_to_pass', 0.0):.1f}",
        "",
        "Interpretation:",
        "- Track D is intentionally non-canonical.",
        "- It preserves the faster 0.54% risk candidate for separate discretionary review.",
        "- It should not be confused with the strict Track C canonical path.",
    ]
    out_path.write_text("\n".join(lines))


def main() -> None:
    np.random.seed(MC_SEED)

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[2]
    track_d_root = repo_root / "FTMO_Challenge" / "Track_D_NonCanonical_054"
    track_c_root = repo_root / "FTMO_Challenge" / "Track_C_Time_Optimized"
    reports_dir = track_d_root / "reports"
    images_dir = track_d_root / "images"

    source_summary, trades, rankings, source_mode = load_source(track_c_root, track_d_root)
    validate_source(source_summary)

    daily = build_daily_activity(trades)
    metrics = compute_metrics(trades, daily)
    paths = monte_carlo_paths(trades, runs=MC_RUNS)
    timing = step_timing_stats(paths, trades_per_day=metrics["trades_per_day"])

    summary = build_track_d_summary(source_summary, track_d_root, source_mode)

    (reports_dir / "track_d_best_candidate.json").write_text(json.dumps(summary, indent=2))
    write_text_summary(summary, reports_dir / "track_d_best_candidate.txt")
    trades.to_csv(reports_dir / "track_d_best_candidate_oos_trades.csv", index=False)
    daily.to_csv(reports_dir / "track_d_daily_activity.csv", index=False)
    rankings.to_csv(reports_dir / "track_d_source_candidate_rankings.csv", index=False)
    if source_mode == "current-track-c":
        shutil.copy2(track_c_root / "reports" / "track_c_best_candidate.json", reports_dir / "track_d_source_track_c_best_candidate.json")

    plot_trade_activity(daily, images_dir / "track_d_trade_activity.png")
    plot_probable_path(paths, timing, images_dir / "track_d_probable_path.png")
    plot_monte_carlo(paths, images_dir / "track_d_monte_carlo.png")
    render_dashboard(summary, metrics, daily, images_dir / "track_d_performance_dashboard.png")

    print(f"Saved: {reports_dir / 'track_d_best_candidate.json'}")
    print(f"Saved: {reports_dir / 'track_d_best_candidate.txt'}")
    print(f"Saved: {reports_dir / 'track_d_best_candidate_oos_trades.csv'}")
    print(f"Saved: {reports_dir / 'track_d_daily_activity.csv'}")
    print(f"Saved: {reports_dir / 'track_d_source_candidate_rankings.csv'}")
    print(f"Saved: {images_dir / 'track_d_trade_activity.png'}")
    print(f"Saved: {images_dir / 'track_d_probable_path.png'}")
    print(f"Saved: {images_dir / 'track_d_monte_carlo.png'}")
    print(f"Saved: {images_dir / 'track_d_performance_dashboard.png'}")


if __name__ == "__main__":
    main()