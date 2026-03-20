from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError as exc:  # pragma: no cover - depends on local MT5 install
    mt5 = None
    MT5_IMPORT_ERROR = exc
else:
    MT5_IMPORT_ERROR = None


TIMEFRAME_MAP = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}


@dataclass
class StrategyConfig:
    fast_ema: int
    slow_ema: int
    stop_loss_pct: float
    take_profit_pct: float
    risk_pct: float


@dataclass
class GuardrailStatus:
    trading_allowed: bool
    hard_breach: bool
    soft_stop_hit: bool
    daily_loss_pct: float
    total_loss_pct: float
    notes: list[str]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_mt5(config: dict[str, Any]) -> None:
    if mt5 is None:
        raise RuntimeError(
            "MetaTrader5 package is not installed. Install it in the trading environment. "
            f"Original import error: {MT5_IMPORT_ERROR}"
        )

    mt5_cfg = config["mt5"]
    initialize_kwargs = {}
    if mt5_cfg.get("path"):
        initialize_kwargs["path"] = mt5_cfg["path"]
    if mt5_cfg.get("portable"):
        initialize_kwargs["portable"] = True

    if not mt5.initialize(**initialize_kwargs):
        raise RuntimeError(f"mt5.initialize() failed: {mt5.last_error()}")

    login = mt5_cfg.get("login")
    server = mt5_cfg.get("server")
    password_env = mt5_cfg.get("password_env")
    password = os.getenv(password_env, "") if password_env else ""

    if login and server and password:
        if not mt5.login(int(login), password=password, server=server):
            raise RuntimeError(f"mt5.login() failed: {mt5.last_error()}")


def shutdown_mt5() -> None:
    if mt5 is not None:
        mt5.shutdown()


def mt5_timeframe(name: str) -> int:
    attr_name = TIMEFRAME_MAP.get(name.upper())
    if attr_name is None or mt5 is None or not hasattr(mt5, attr_name):
        raise ValueError(f"Unsupported timeframe: {name}")
    return getattr(mt5, attr_name)


def fetch_rates(symbol: str, timeframe_name: str, bars_count: int) -> pd.DataFrame:
    timeframe = mt5_timeframe(timeframe_name)
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars_count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No MT5 rates returned for {symbol} on {timeframe_name}. Last error: {mt5.last_error()}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(
        columns={
            "time": "timestamp",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "tick_volume": "Volume",
        }
    )
    return df


def apply_ema_strategy(df: pd.DataFrame, strategy: StrategyConfig) -> pd.DataFrame:
    out = df.copy()
    out["fast_ema"] = out["Close"].ewm(span=strategy.fast_ema, adjust=False).mean()
    out["slow_ema"] = out["Close"].ewm(span=strategy.slow_ema, adjust=False).mean()
    out["signal"] = (out["fast_ema"] > out["slow_ema"]).astype(int)
    out["signal_diff"] = out["signal"].diff().fillna(0)
    return out


def latest_signal(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) < 3:
        raise RuntimeError("Need at least 3 bars to evaluate signal state.")

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    buy_cross = bool(previous["fast_ema"] <= previous["slow_ema"] and latest["fast_ema"] > latest["slow_ema"])
    sell_cross = bool(previous["fast_ema"] >= previous["slow_ema"] and latest["fast_ema"] < latest["slow_ema"])
    return {
        "timestamp": str(latest["timestamp"]),
        "close": float(latest["Close"]),
        "fast_ema": float(latest["fast_ema"]),
        "slow_ema": float(latest["slow_ema"]),
        "buy_cross": buy_cross,
        "sell_cross": sell_cross,
        "signal": int(latest["signal"]),
    }


def load_state(state_path: Path, starting_balance: float, account_equity: float) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    if state_path.exists():
        state = load_json(state_path)
    else:
        state = {}

    if not state.get("starting_balance"):
        state["starting_balance"] = float(starting_balance)
    if not state.get("peak_equity"):
        state["peak_equity"] = float(account_equity)
    if state.get("day_reference_date") != today:
        state["day_reference_date"] = today
        state["day_start_equity"] = float(account_equity)
    if not state.get("day_start_equity"):
        state["day_start_equity"] = float(account_equity)
    state["peak_equity"] = max(float(state["peak_equity"]), float(account_equity))
    return state


def evaluate_guardrails(account_info: Any, ftmo_cfg: dict[str, Any], state: dict[str, Any]) -> GuardrailStatus:
    equity = float(account_info.equity)
    starting_balance = float(state["starting_balance"])
    day_start_equity = float(state["day_start_equity"])

    daily_loss_pct = ((equity - day_start_equity) / starting_balance) * 100.0
    total_loss_pct = ((equity - starting_balance) / starting_balance) * 100.0

    notes: list[str] = []
    hard_breach = False
    soft_stop_hit = False

    if daily_loss_pct <= -float(ftmo_cfg["daily_loss_limit_pct"]):
        hard_breach = True
        notes.append("Daily FTMO loss limit breached.")
    if total_loss_pct <= -float(ftmo_cfg["max_loss_limit_pct"]):
        hard_breach = True
        notes.append("Maximum FTMO loss limit breached.")

    if daily_loss_pct <= -float(ftmo_cfg["soft_daily_stop_pct"]):
        soft_stop_hit = True
        notes.append("Soft daily stop reached.")
    if total_loss_pct <= -float(ftmo_cfg["soft_max_loss_stop_pct"]):
        soft_stop_hit = True
        notes.append("Soft max-loss stop reached.")

    return GuardrailStatus(
        trading_allowed=not hard_breach and not soft_stop_hit,
        hard_breach=hard_breach,
        soft_stop_hit=soft_stop_hit,
        daily_loss_pct=daily_loss_pct,
        total_loss_pct=total_loss_pct,
        notes=notes,
    )


def track_d_positions(symbol: str, magic_number: int) -> list[Any]:
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        raise RuntimeError(f"mt5.positions_get() failed: {mt5.last_error()}")
    return [position for position in positions if int(position.magic) == int(magic_number)]


def normalized_volume(symbol: str, desired_volume: float) -> float:
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        raise RuntimeError(f"mt5.symbol_info({symbol}) returned None")

    min_volume = float(symbol_info.volume_min)
    max_volume = float(symbol_info.volume_max)
    step = float(symbol_info.volume_step)

    clipped = max(min_volume, min(max_volume, desired_volume))
    steps = math.floor(clipped / step)
    volume = steps * step
    return round(max(volume, min_volume), 8)


def estimate_order_volume(symbol: str, entry_price: float, stop_loss_price: float, risk_amount: float) -> float:
    loss_per_lot = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, 1.0, entry_price, stop_loss_price)
    if loss_per_lot is None:
        raise RuntimeError(f"mt5.order_calc_profit() failed: {mt5.last_error()}")
    loss_per_lot = abs(float(loss_per_lot))
    if loss_per_lot <= 0:
        raise RuntimeError("Calculated loss per lot is non-positive; cannot size position.")
    return normalized_volume(symbol, risk_amount / loss_per_lot)


def ensure_symbol_selected(symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol {symbol} not found in MT5 terminal.")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Failed to select symbol {symbol}: {mt5.last_error()}")


def send_buy_order(symbol: str, volume: float, sl: float, tp: float, config: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"mt5.symbol_info_tick({symbol}) returned None")

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY,
        "price": float(tick.ask),
        "sl": float(sl),
        "tp": float(tp),
        "deviation": int(config["trading"]["slippage_points"]),
        "magic": int(config["trading"]["magic_number"]),
        "comment": str(config["trading"]["comment"]),
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    if dry_run:
        return {"mode": "dry-run", "request": request}

    result = mt5.order_send(request)
    if result is None:
        raise RuntimeError(f"mt5.order_send() returned None: {mt5.last_error()}")
    return {"mode": "live", "retcode": int(result.retcode), "comment": result.comment, "request": request}


def close_position(position: Any, config: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    tick = mt5.symbol_info_tick(position.symbol)
    if tick is None:
        raise RuntimeError(f"mt5.symbol_info_tick({position.symbol}) returned None")

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": float(position.volume),
        "type": mt5.ORDER_TYPE_SELL,
        "position": int(position.ticket),
        "price": float(tick.bid),
        "deviation": int(config["trading"]["slippage_points"]),
        "magic": int(config["trading"]["magic_number"]),
        "comment": f"{config['trading']['comment']} close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    if dry_run:
        return {"mode": "dry-run", "request": request}

    result = mt5.order_send(request)
    if result is None:
        raise RuntimeError(f"mt5.order_send() returned None: {mt5.last_error()}")
    return {"mode": "live", "retcode": int(result.retcode), "comment": result.comment, "request": request}


def journal_path(base_dir: Path) -> Path:
    return base_dir / "state" / "track_d_mt5_journal.jsonl"


def append_journal(base_dir: Path, payload: dict[str, Any]) -> None:
    path = journal_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def run_cycle(config: dict[str, Any], base_dir: Path, execute: bool) -> dict[str, Any]:
    ensure_symbol_selected(config["trading"]["symbol"])
    dry_run = bool(config["trading"].get("dry_run", True)) if not execute else False

    account_info = mt5.account_info()
    if account_info is None:
        raise RuntimeError(f"mt5.account_info() failed: {mt5.last_error()}")

    state_path = base_dir / "state" / "track_d_ftmo_state.json"
    state = load_state(
        state_path=state_path,
        starting_balance=float(config["ftmo"]["starting_balance"]),
        account_equity=float(account_info.equity),
    )
    guard = evaluate_guardrails(account_info, config["ftmo"], state)

    strategy = StrategyConfig(
        fast_ema=int(config["strategy"]["fast_ema"]),
        slow_ema=int(config["strategy"]["slow_ema"]),
        stop_loss_pct=float(config["strategy"]["stop_loss_pct"]),
        take_profit_pct=float(config["strategy"]["take_profit_pct"]),
        risk_pct=float(config["strategy"]["risk_pct"]),
    )

    rates = fetch_rates(
        symbol=config["trading"]["symbol"],
        timeframe_name=config["trading"]["timeframe"],
        bars_count=int(config["trading"]["bars_count"]),
    )
    signal_df = apply_ema_strategy(rates, strategy)
    signal = latest_signal(signal_df)
    positions = track_d_positions(config["trading"]["symbol"], int(config["trading"]["magic_number"]))

    actions: list[dict[str, Any]] = []

    if positions and guard.hard_breach and bool(config["trading"].get("close_on_guardrail_breach", True)):
        for position in positions:
            actions.append({"type": "close_guardrail", "result": close_position(position, config, dry_run)})
    elif positions and signal["sell_cross"] and bool(config["trading"].get("close_on_sell_signal", True)):
        for position in positions:
            actions.append({"type": "close_sell_signal", "result": close_position(position, config, dry_run)})
    elif (not positions and signal["buy_cross"] and bool(config["trading"].get("allow_new_entries", True)) and guard.trading_allowed):
        tick = mt5.symbol_info_tick(config["trading"]["symbol"])
        if tick is None:
            raise RuntimeError(f"mt5.symbol_info_tick({config['trading']['symbol']}) returned None")
        entry_price = float(tick.ask)
        stop_loss_price = entry_price * (1.0 - strategy.stop_loss_pct / 100.0)
        take_profit_price = entry_price * (1.0 + strategy.take_profit_pct / 100.0)
        risk_amount = float(account_info.balance) * (strategy.risk_pct / 100.0)
        volume = estimate_order_volume(config["trading"]["symbol"], entry_price, stop_loss_price, risk_amount)
        actions.append(
            {
                "type": "open_buy",
                "risk_amount": risk_amount,
                "volume": volume,
                "result": send_buy_order(
                    config["trading"]["symbol"],
                    volume,
                    stop_loss_price,
                    take_profit_price,
                    config,
                    dry_run,
                ),
            }
        )

    state["last_run_utc"] = utc_now_iso()
    state["last_signal"] = signal
    state["last_guardrail"] = {
        "trading_allowed": guard.trading_allowed,
        "hard_breach": guard.hard_breach,
        "soft_stop_hit": guard.soft_stop_hit,
        "daily_loss_pct": guard.daily_loss_pct,
        "total_loss_pct": guard.total_loss_pct,
        "notes": guard.notes,
    }
    state["last_actions"] = actions
    save_json(state_path, state)

    result = {
        "run_utc": utc_now_iso(),
        "symbol": config["trading"]["symbol"],
        "dry_run": dry_run,
        "account": {
            "balance": float(account_info.balance),
            "equity": float(account_info.equity),
        },
        "signal": signal,
        "guardrail": state["last_guardrail"],
        "open_positions": len(positions),
        "actions": actions,
    }
    append_journal(base_dir, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one MT5 automation cycle for Track D.")
    parser.add_argument(
        "--config",
        default="FTMO_Challenge/MT5_Automation/config.json",
        help="Path to runtime config JSON.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually send orders. Without this flag, the script stays in dry-run mode.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    base_dir = repo_root / "FTMO_Challenge" / "MT5_Automation"
    config_path = repo_root / args.config

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_path}. Copy config.example.json to config.json and edit it first."
        )

    config = load_json(config_path)

    initialize_mt5(config)
    try:
        result = run_cycle(config, base_dir=base_dir, execute=args.execute)
    finally:
        shutdown_mt5()

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()