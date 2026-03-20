from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

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

YAHOO_TIMEFRAME_MAP = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "60m",
    "D1": "1d",
}

YAHOO_DEFAULT_SYMBOLS = {
    "XAUUSD": "XAUUSD=X",
}

TWELVEDATA_TIMEFRAME_MAP = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
}

TWELVEDATA_DEFAULT_SYMBOLS = {
    "XAUUSD": "XAU/USD",
}

ALPHAVANTAGE_INTERVAL_MAP = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "60min",
}

ALPHAVANTAGE_DEFAULT_FROM_TO = {
    "XAUUSD": ("XAU", "USD"),
}

FINNHUB_RESOLUTION_MAP = {
    "M1": ("1", 60),
    "M5": ("5", 5 * 60),
    "M15": ("15", 15 * 60),
    "M30": ("30", 30 * 60),
    "H1": ("60", 60 * 60),
    "D1": ("D", 24 * 60 * 60),
}

FINNHUB_DEFAULT_SYMBOLS = {
    "XAUUSD": "OANDA:XAU_USD",
}

MASSIVE_TIMESPAN_MAP = {
    "M1": (1, "minute", 60),
    "M5": (5, "minute", 5 * 60),
    "M15": (15, "minute", 15 * 60),
    "M30": (30, "minute", 30 * 60),
    "H1": (1, "hour", 60 * 60),
    "H4": (4, "hour", 4 * 60 * 60),
    "D1": (1, "day", 24 * 60 * 60),
}

MASSIVE_DEFAULT_SYMBOLS = {
    "XAUUSD": "C:XAUUSD",
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


def fetch_rates_yahoo(symbol: str, timeframe_name: str, bars_count: int, trading_cfg: dict[str, Any]) -> pd.DataFrame:
    interval = YAHOO_TIMEFRAME_MAP.get(timeframe_name.upper())
    if interval is None:
        supported = ", ".join(sorted(YAHOO_TIMEFRAME_MAP.keys()))
        raise ValueError(f"Unsupported timeframe for Yahoo mode: {timeframe_name}. Supported: {supported}")

    api_symbol = (
        str(trading_cfg.get("yahoo_symbol", "")).strip()
        or str(trading_cfg.get("api_symbol", "")).strip()
        or YAHOO_DEFAULT_SYMBOLS.get(symbol, symbol)
    )
    yahoo_range = str(trading_cfg.get("yahoo_range", "60d"))
    encoded_symbol = quote(api_symbol)
    query = urlencode(
        {
            "interval": interval,
            "range": yahoo_range,
            "includePrePost": "false",
            "events": "div,splits",
        }
    )
    base_urls = [
        "https://query1.finance.yahoo.com/v8/finance/chart",
        "https://query2.finance.yahoo.com/v8/finance/chart",
    ]

    payload = None
    last_error: Exception | None = None
    for base_url in base_urls:
        url = f"{base_url}/{encoded_symbol}?{query}"
        for attempt in range(3):
            try:
                request = Request(
                    url=url,
                    method="GET",
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (X11; Linux x86_64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/126.0.0.0 Safari/537.36"
                        ),
                        "Accept": "application/json,text/plain,*/*",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                last_error = exc
                if exc.code == 429 and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except (URLError, TimeoutError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                break
        if payload is not None:
            break

    if payload is None:
        raise RuntimeError(f"Yahoo API request failed for {api_symbol}: {last_error}")

    chart = payload.get("chart", {})
    result = chart.get("result") or []
    if not result:
        raise RuntimeError(f"Yahoo API returned no data for {api_symbol}: {chart.get('error')}")

    series = result[0]
    timestamps = series.get("timestamp") or []
    quote_block = ((series.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote_block.get("open") or []
    highs = quote_block.get("high") or []
    lows = quote_block.get("low") or []
    closes = quote_block.get("close") or []
    volumes = quote_block.get("volume") or []

    min_len = min(len(timestamps), len(opens), len(highs), len(lows), len(closes), len(volumes))
    if min_len == 0:
        raise RuntimeError(f"Yahoo API returned empty series for {api_symbol}")

    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps[:min_len], unit="s", utc=True),
            "Open": opens[:min_len],
            "High": highs[:min_len],
            "Low": lows[:min_len],
            "Close": closes[:min_len],
            "Volume": volumes[:min_len],
        }
    )
    frame = frame.dropna(subset=["Close"]).copy()
    if frame.empty:
        raise RuntimeError(f"Yahoo API returned only null closes for {api_symbol}")
    if len(frame) < bars_count:
        return frame
    return frame.tail(bars_count).reset_index(drop=True)


def fetch_rates_twelvedata(symbol: str, timeframe_name: str, bars_count: int, trading_cfg: dict[str, Any]) -> pd.DataFrame:
    interval = TWELVEDATA_TIMEFRAME_MAP.get(timeframe_name.upper())
    if interval is None:
        supported = ", ".join(sorted(TWELVEDATA_TIMEFRAME_MAP.keys()))
        raise ValueError(f"Unsupported timeframe for TwelveData mode: {timeframe_name}. Supported: {supported}")

    api_symbol = str(trading_cfg.get("api_symbol", "")).strip() or TWELVEDATA_DEFAULT_SYMBOLS.get(symbol, symbol)
    api_key_env = str(trading_cfg.get("api_key_env", "MARKET_DATA_API_KEY"))
    api_key = os.getenv(api_key_env, "")
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable for TwelveData: {api_key_env}")

    query = urlencode(
        {
            "symbol": api_symbol,
            "interval": interval,
            "outputsize": str(max(50, int(bars_count))),
            "timezone": "UTC",
            "apikey": api_key,
        }
    )
    url = f"https://api.twelvedata.com/time_series?{query}"
    request = Request(
        url=url,
        method="GET",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
    )

    with urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("status") == "error":
        raise RuntimeError(f"TwelveData error: {payload.get('message')}")

    values = payload.get("values") or []
    if not values:
        raise RuntimeError(f"TwelveData returned no values for {api_symbol}")

    frame = pd.DataFrame(values)
    for column in ["open", "high", "low", "close", "volume"]:
        if column not in frame.columns:
            frame[column] = np.nan

    frame["timestamp"] = pd.to_datetime(frame["datetime"], utc=True)
    frame = frame.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )

    for column in ["Open", "High", "Low", "Close", "Volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["Close"]).sort_values("timestamp").reset_index(drop=True)
    if len(frame) < bars_count:
        return frame
    return frame.tail(bars_count).reset_index(drop=True)


def fetch_rates_alphavantage(symbol: str, timeframe_name: str, bars_count: int, trading_cfg: dict[str, Any]) -> pd.DataFrame:
    timeframe = timeframe_name.upper()
    interval = ALPHAVANTAGE_INTERVAL_MAP.get(timeframe)
    use_daily_endpoint = timeframe == "D1"
    if interval is None and not use_daily_endpoint:
        supported = ", ".join(sorted(ALPHAVANTAGE_INTERVAL_MAP.keys()) + ["D1"])
        raise ValueError(f"Unsupported timeframe for Alpha Vantage mode: {timeframe_name}. Supported: {supported}")

    api_key_env = str(trading_cfg.get("api_key_env", "ALPHAVANTAGE_API_KEY"))
    api_key = os.getenv(api_key_env, "")
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable for Alpha Vantage: {api_key_env}")

    api_symbol = str(trading_cfg.get("api_symbol", "")).strip().upper()
    default_from, default_to = ALPHAVANTAGE_DEFAULT_FROM_TO.get(symbol, ("", ""))
    stock_symbol = ""
    if len(api_symbol) == 6:
        from_symbol = api_symbol[:3]
        to_symbol = api_symbol[3:]
    elif "/" in api_symbol:
        parts = [part.strip().upper() for part in api_symbol.split("/", 1)]
        from_symbol, to_symbol = parts[0], parts[1]
    elif api_symbol:
        from_symbol, to_symbol = "", ""
        stock_symbol = api_symbol
    else:
        from_symbol, to_symbol = default_from, default_to

    if not stock_symbol and (not from_symbol or not to_symbol):
        stock_symbol = str(trading_cfg.get("api_fallback_symbol", "GLD")).strip().upper()

    def request_alpha(function_name: str, intraday_interval: str | None = None, symbol_param: str | None = None) -> dict[str, Any]:
        params = {
            "function": function_name,
            "outputsize": "full" if int(bars_count) > 100 else "compact",
            "apikey": api_key,
        }
        if symbol_param:
            params["symbol"] = symbol_param
        else:
            params["from_symbol"] = from_symbol
            params["to_symbol"] = to_symbol
        if intraday_interval:
            params["interval"] = intraday_interval

        query = urlencode(params)
        url = f"https://www.alphavantage.co/query?{query}"
        request = Request(
            url=url,
            method="GET",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
            },
        )

        payload_local: dict[str, Any] | None = None
        for attempt in range(3):
            with urlopen(request, timeout=15) as response:
                payload_local = json.loads(response.read().decode("utf-8"))

            if payload_local.get("Note"):
                if attempt < 2:
                    time.sleep(12)
                    continue
                raise RuntimeError(f"Alpha Vantage throttle message: {payload_local['Note']}")
            break

        if payload_local is None:
            raise RuntimeError("Alpha Vantage returned no payload")
        return payload_local

    if stock_symbol:
        if use_daily_endpoint:
            payload = request_alpha("TIME_SERIES_DAILY_ADJUSTED", symbol_param=stock_symbol)
            ts_key = "Time Series (Daily)"
        else:
            payload = request_alpha("TIME_SERIES_INTRADAY", interval, symbol_param=stock_symbol)
            ts_key = f"Time Series ({interval})"
    else:
        if use_daily_endpoint:
            payload = request_alpha("FX_DAILY")
            ts_key = "Time Series FX (Daily)"
        else:
            payload = request_alpha("FX_INTRADAY", interval)
            ts_key = f"Time Series FX ({interval})"
        info_text = str(payload.get("Information", ""))
        if "premium endpoint" in info_text.lower():
            payload = request_alpha("TIME_SERIES_DAILY_ADJUSTED", symbol_param="GLD")
            ts_key = "Time Series (Daily)"

    if payload.get("Error Message"):
        raise RuntimeError(f"Alpha Vantage error: {payload['Error Message']}")
    if payload.get("Information"):
        raise RuntimeError(f"Alpha Vantage info: {payload['Information']}")

    series = payload.get(ts_key)
    if not isinstance(series, dict) or not series:
        symbol_desc = stock_symbol or f"{from_symbol}/{to_symbol}"
        raise RuntimeError(f"Alpha Vantage returned no time series for {symbol_desc} interval {interval}")

    rows: list[dict[str, Any]] = []
    for timestamp_str, values in series.items():
        rows.append(
            {
                "timestamp": pd.to_datetime(timestamp_str, utc=True),
                "Open": values.get("1. open"),
                "High": values.get("2. high"),
                "Low": values.get("3. low"),
                "Close": values.get("4. close"),
                "Volume": 0.0,
            }
        )

    frame = pd.DataFrame(rows)
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["Close"]).sort_values("timestamp").reset_index(drop=True)
    if len(frame) < bars_count:
        return frame
    return frame.tail(bars_count).reset_index(drop=True)


def fetch_rates_finnhub(symbol: str, timeframe_name: str, bars_count: int, trading_cfg: dict[str, Any]) -> pd.DataFrame:
    timeframe = timeframe_name.upper()
    mapping = FINNHUB_RESOLUTION_MAP.get(timeframe)
    if mapping is None:
        supported = ", ".join(sorted(FINNHUB_RESOLUTION_MAP.keys()))
        raise ValueError(f"Unsupported timeframe for Finnhub mode: {timeframe_name}. Supported: {supported}")

    resolution, seconds_per_bar = mapping
    api_symbol = (
        str(trading_cfg.get("finnhub_symbol", "")).strip()
        or str(trading_cfg.get("api_symbol", "")).strip()
        or FINNHUB_DEFAULT_SYMBOLS.get(symbol, symbol)
    )
    api_key_env = str(trading_cfg.get("api_key_env", "FINNHUB_API_KEY"))
    api_key = os.getenv(api_key_env, "")
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable for Finnhub: {api_key_env}")

    to_ts = int(datetime.now(timezone.utc).timestamp())
    lookback_bars = max(int(bars_count) + 50, 120)
    from_ts = to_ts - lookback_bars * seconds_per_bar

    def fetch_endpoint(endpoint: str, endpoint_symbol: str) -> dict[str, Any]:
        query = urlencode(
            {
                "symbol": endpoint_symbol,
                "resolution": resolution,
                "from": str(from_ts),
                "to": str(to_ts),
                "token": api_key,
            }
        )
        url = f"https://finnhub.io/api/v1/{endpoint}?{query}"
        request = Request(
            url=url,
            method="GET",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
            },
        )
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    payload = None
    errors: list[str] = []

    endpoint_attempts: list[tuple[str, str]] = [("forex/candle", api_symbol)]
    stock_symbol = str(trading_cfg.get("api_fallback_symbol", "GLD")).strip().upper()
    if stock_symbol:
        endpoint_attempts.append(("stock/candle", stock_symbol))

    for endpoint, endpoint_symbol in endpoint_attempts:
        try:
            candidate = fetch_endpoint(endpoint, endpoint_symbol)
        except HTTPError as exc:
            errors.append(f"{endpoint}:{endpoint_symbol} HTTP {exc.code}")
            continue
        except URLError as exc:
            errors.append(f"{endpoint}:{endpoint_symbol} URL error {exc}")
            continue

        status = str(candidate.get("s", ""))
        if status == "ok":
            payload = candidate
            break

        error_text = candidate.get("error") or candidate.get("message") or status
        errors.append(f"{endpoint}:{endpoint_symbol} {error_text}")

    if payload is None:
        raise RuntimeError("Finnhub request failed: " + " | ".join(errors))

    timestamps = payload.get("t") or []
    opens = payload.get("o") or []
    highs = payload.get("h") or []
    lows = payload.get("l") or []
    closes = payload.get("c") or []
    volumes = payload.get("v") or []

    min_len = min(len(timestamps), len(opens), len(highs), len(lows), len(closes))
    if min_len == 0:
        raise RuntimeError(f"Finnhub returned empty candles for {api_symbol}")

    if len(volumes) < min_len:
        volumes = list(volumes) + [0.0] * (min_len - len(volumes))

    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps[:min_len], unit="s", utc=True),
            "Open": opens[:min_len],
            "High": highs[:min_len],
            "Low": lows[:min_len],
            "Close": closes[:min_len],
            "Volume": volumes[:min_len],
        }
    )

    for column in ["Open", "High", "Low", "Close", "Volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["Close"]).sort_values("timestamp").reset_index(drop=True)
    if len(frame) < bars_count:
        return frame
    return frame.tail(bars_count).reset_index(drop=True)


def fetch_rates_massive(symbol: str, timeframe_name: str, bars_count: int, trading_cfg: dict[str, Any]) -> pd.DataFrame:
    timeframe = timeframe_name.upper()
    mapping = MASSIVE_TIMESPAN_MAP.get(timeframe)
    if mapping is None:
        supported = ", ".join(sorted(MASSIVE_TIMESPAN_MAP.keys()))
        raise ValueError(f"Unsupported timeframe for Massive mode: {timeframe_name}. Supported: {supported}")

    multiplier, timespan, seconds_per_bar = mapping
    api_symbol = (
        str(trading_cfg.get("massive_symbol", "")).strip()
        or str(trading_cfg.get("api_symbol", "")).strip()
        or MASSIVE_DEFAULT_SYMBOLS.get(symbol, symbol)
    )
    api_key_env = str(trading_cfg.get("api_key_env", "MASSIVE_API_KEY"))
    api_key = os.getenv(api_key_env, "")
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable for Massive: {api_key_env}")

    to_dt = datetime.now(timezone.utc)
    lookback_bars = max(int(bars_count) + 50, 120)
    from_dt = datetime.fromtimestamp(int(to_dt.timestamp()) - lookback_bars * seconds_per_bar, tz=timezone.utc)
    from_str = from_dt.strftime("%Y-%m-%d")
    to_str = to_dt.strftime("%Y-%m-%d")

    query = urlencode(
        {
            "adjusted": "true",
            "sort": "asc",
            "limit": str(max(500, int(bars_count) + 50)),
            "apiKey": api_key,
        }
    )
    url = (
        f"https://api.massive.com/v2/aggs/ticker/{quote(api_symbol, safe=':')}/range/"
        f"{multiplier}/{timespan}/{from_str}/{to_str}?{query}"
    )
    request = Request(
        url=url,
        method="GET",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
    )

    payload: dict[str, Any] | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                time.sleep(12)
                continue
            raise RuntimeError(f"Massive HTTP error {exc.code}") from exc

    if payload is None:
        raise RuntimeError(f"Massive returned no payload for {api_symbol}")

    status = str(payload.get("status", "")).upper()
    if payload.get("error"):
        raise RuntimeError(f"Massive error: {payload.get('error')}")
    if status not in {"OK", "DELAYED"}:
        raise RuntimeError(f"Massive request failed for {api_symbol}: status={status or 'unknown'}")

    results = payload.get("results") or []
    if not results:
        raise RuntimeError(f"Massive returned empty candles for {api_symbol}")

    frame = pd.DataFrame(results)
    frame = frame.rename(
        columns={
            "t": "timestamp_ms",
            "o": "Open",
            "h": "High",
            "l": "Low",
            "c": "Close",
            "v": "Volume",
        }
    )
    frame["timestamp"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        if column not in frame.columns:
            frame[column] = 0.0 if column == "Volume" else np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["Close"]).sort_values("timestamp").reset_index(drop=True)
    if len(frame) < bars_count:
        return frame
    return frame.tail(bars_count).reset_index(drop=True)


def fetch_rates_api(symbol: str, timeframe_name: str, bars_count: int, trading_cfg: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    primary_provider = str(trading_cfg.get("api_provider", "yahoo")).lower()
    fallback_providers = [str(item).lower() for item in trading_cfg.get("api_provider_fallbacks", [])]
    providers = [primary_provider] + [provider for provider in fallback_providers if provider and provider != primary_provider]

    errors: list[str] = []
    for provider in providers:
        try:
            if provider == "yahoo":
                return fetch_rates_yahoo(symbol, timeframe_name, bars_count, trading_cfg), provider
            if provider == "twelvedata":
                return fetch_rates_twelvedata(symbol, timeframe_name, bars_count, trading_cfg), provider
            if provider == "alphavantage":
                return fetch_rates_alphavantage(symbol, timeframe_name, bars_count, trading_cfg), provider
            if provider == "finnhub":
                return fetch_rates_finnhub(symbol, timeframe_name, bars_count, trading_cfg), provider
            if provider == "massive":
                return fetch_rates_massive(symbol, timeframe_name, bars_count, trading_cfg), provider
            errors.append(f"{provider}: unsupported provider")
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    raise RuntimeError("All API providers failed: " + " | ".join(errors))


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


def maybe_send_telegram(config: dict[str, Any], message: str) -> dict[str, Any]:
    tg_cfg = config.get("telegram", {})
    if not tg_cfg.get("enabled", False):
        return {"sent": False, "reason": "disabled"}

    bot_token_env = tg_cfg.get("bot_token_env")
    bot_token = os.getenv(bot_token_env, "") if bot_token_env else ""
    chat_id = str(tg_cfg.get("chat_id", "")).strip()

    if not bot_token:
        return {"sent": False, "reason": f"missing env token: {bot_token_env}"}
    if not chat_id:
        return {"sent": False, "reason": "missing chat_id"}

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = Request(url=url, data=body, method="POST")

    try:
        with urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8")
        return {"sent": True, "response": payload}
    except Exception as exc:
        return {"sent": False, "reason": str(exc)}


def format_float(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value)


def format_bool_flag(value: Any) -> str:
    return "TRUE" if bool(value) else "FALSE"


def format_result_for_telegram(result: dict[str, Any]) -> str:
    signal = result.get("signal", {})
    guard = result.get("guardrail", {})
    actions = result.get("actions", [])
    account = result.get("account", {})
    data_provider = result.get("data_provider", "n/a")
    api_status = result.get("api_status", "unknown")
    bot_status = result.get("bot_status", "unknown")
    error_text = result.get("error")
    signal = result.get("signal", {})
    recommendation = result.get("recommendation", {})

    go_long = bool(recommendation.get("go_long", signal.get("buy_cross", False)))
    go_short = bool(recommendation.get("go_short", signal.get("sell_cross", False)))
    entry_price = recommendation.get("entry_price")
    sl_price = recommendation.get("sl_price")
    tp_price = recommendation.get("tp_price")
    lot_size = recommendation.get("lot_size")
    heartbeat_only = len(actions) == 0

    if heartbeat_only and not go_long and not go_short:
        entry_price = None
        sl_price = None
        tp_price = None
        lot_size = None

    if actions:
        action_lines = []
        for action in actions:
            action_type = action.get("type", "unknown")
            mode = action.get("result", {}).get("mode", "unknown")
            if action_type == "open_buy":
                action_lines.append(
                    (
                        "Action: "
                        f"open_buy ({mode}) | "
                        f"entry={format_float(action.get('entry_price'), 3)} | "
                        f"sl={format_float(action.get('stop_loss_price'), 3)} | "
                        f"tp={format_float(action.get('take_profit_price'), 3)} | "
                        f"lot={format_float(action.get('volume'), 2)} | "
                        f"risk_usd={format_float(action.get('risk_amount'), 2)}"
                    )
                )
            elif action_type in {"close_sell_signal", "close_guardrail"}:
                ticket = action.get("ticket")
                reason = action.get("reason", "")
                reason_text = f" | reason={reason}" if reason else ""
                ticket_text = f" | ticket={ticket}" if ticket is not None else ""
                action_lines.append(f"Action: {action_type} ({mode}){ticket_text}{reason_text}")
            else:
                action_lines.append(f"Action: {action_type} ({mode})")
    else:
        action_lines = ["Action: no action"]

    lines = [
        "Track D MT5 Alert",
        f"Run: {result.get('run_utc')}",
        f"Symbol: {result.get('symbol')}",
        f"Dry run: {result.get('dry_run')}",
        f"Heartbeat message: {format_bool_flag(heartbeat_only)}",
        f"Go_Long: {format_bool_flag(go_long)}",
        f"Go_Short: {format_bool_flag(go_short)}",
        f"Entry_Price: {format_float(entry_price, 3)}",
        f"SL_Price: {format_float(sl_price, 3)}",
        f"TP_Price: {format_float(tp_price, 3)}",
        f"Lot_Size: {format_float(lot_size, 2)}",
        f"Bot status: {bot_status}",
        f"API status: {api_status} ({data_provider})",
        (
            "Account: "
            f"balance={format_float(account.get('balance'), 2)} "
            f"equity={format_float(account.get('equity'), 2)}"
        ),
        (
            "Signal: "
            f"buy_cross={signal.get('buy_cross')} "
            f"sell_cross={signal.get('sell_cross')} "
            f"close={format_float(signal.get('close'), 3)}"
        ),
        (
            "Guardrail: "
            f"allowed={guard.get('trading_allowed')} "
            f"daily={format_float(guard.get('daily_loss_pct'), 2)}% "
            f"total={format_float(guard.get('total_loss_pct'), 2)}%"
        ),
        f"Open positions: {result.get('open_positions')}",
    ]
    lines.extend(action_lines)

    notes = guard.get("notes", [])
    if notes:
        lines.append("Guardrail reasons: " + " | ".join(notes))

    if error_text:
        lines.append(f"Error: {error_text}")

    return "\n".join(lines)


def local_run_time(run_utc: str, tz_name: str | None) -> str | None:
    if not run_utc:
        return None
    if not tz_name:
        return None
    try:
        dt = datetime.fromisoformat(run_utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo(tz_name))
        return local_dt.isoformat()
    except Exception:
        return None


def run_cycle(config: dict[str, Any], base_dir: Path, execute: bool) -> dict[str, Any]:
    market_data_mode = str(config.get("trading", {}).get("market_data_mode", "mt5")).lower()
    if market_data_mode not in {"mt5", "api"}:
        raise ValueError("trading.market_data_mode must be one of: mt5, api")

    if market_data_mode == "api":
        dry_run = True
        strategy = StrategyConfig(
            fast_ema=int(config["strategy"]["fast_ema"]),
            slow_ema=int(config["strategy"]["slow_ema"]),
            stop_loss_pct=float(config["strategy"]["stop_loss_pct"]),
            take_profit_pct=float(config["strategy"]["take_profit_pct"]),
            risk_pct=float(config["strategy"]["risk_pct"]),
        )
        rates, provider = fetch_rates_api(
            symbol=config["trading"]["symbol"],
            timeframe_name=config["trading"]["timeframe"],
            bars_count=int(config["trading"]["bars_count"]),
            trading_cfg=config["trading"],
        )
        signal_df = apply_ema_strategy(rates, strategy)
        signal = latest_signal(signal_df)
        actions: list[dict[str, Any]] = []
        entry_price = float(signal["close"])
        go_long = bool(signal["buy_cross"])
        go_short = bool(signal["sell_cross"])
        sl_price = None
        tp_price = None
        if go_long:
            sl_price = entry_price * (1.0 - strategy.stop_loss_pct / 100.0)
            tp_price = entry_price * (1.0 + strategy.take_profit_pct / 100.0)
        elif go_short:
            sl_price = entry_price * (1.0 + strategy.stop_loss_pct / 100.0)
            tp_price = entry_price * (1.0 - strategy.take_profit_pct / 100.0)

        if signal["buy_cross"]:
            actions.append({"type": "signal_buy_cross", "reason": "ema_buy_cross", "result": {"mode": "signal"}})
        elif signal["sell_cross"]:
            actions.append({"type": "signal_sell_cross", "reason": "ema_sell_cross", "result": {"mode": "signal"}})

        guardrail = {
            "trading_allowed": True,
            "hard_breach": False,
            "soft_stop_hit": False,
            "daily_loss_pct": 0.0,
            "total_loss_pct": 0.0,
            "notes": ["api_mode_no_mt5_guardrails"],
        }

        state_path = base_dir / "state" / "track_d_ftmo_state.json"
        state = load_json(state_path) if state_path.exists() else {}
        state["last_run_utc"] = utc_now_iso()
        state["last_signal"] = signal
        state["last_guardrail"] = guardrail
        state["last_actions"] = actions
        save_json(state_path, state)

        result = {
            "run_utc": utc_now_iso(),
            "symbol": config["trading"]["symbol"],
            "dry_run": dry_run,
            "market_data_mode": "api",
            "data_provider": provider,
            "api_status": "ok",
            "bot_status": "running",
            "account": {
                "balance": None,
                "equity": None,
            },
            "signal": signal,
            "recommendation": {
                "go_long": go_long,
                "go_short": go_short,
                "entry_price": entry_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "lot_size": None,
            },
            "guardrail": guardrail,
            "open_positions": 0,
            "actions": actions,
        }
        append_journal(base_dir, result)
        return result

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
    recommendation = {
        "go_long": bool(signal["buy_cross"]),
        "go_short": bool(signal["sell_cross"]),
        "entry_price": None,
        "sl_price": None,
        "tp_price": None,
        "lot_size": None,
    }

    if positions and guard.hard_breach and bool(config["trading"].get("close_on_guardrail_breach", True)):
        for position in positions:
            actions.append(
                {
                    "type": "close_guardrail",
                    "ticket": int(position.ticket),
                    "reason": "guardrail_hard_breach",
                    "result": close_position(position, config, dry_run),
                }
            )
    elif positions and signal["sell_cross"] and bool(config["trading"].get("close_on_sell_signal", True)):
        for position in positions:
            actions.append(
                {
                    "type": "close_sell_signal",
                    "ticket": int(position.ticket),
                    "reason": "ema_sell_cross",
                    "result": close_position(position, config, dry_run),
                }
            )
    elif (not positions and signal["buy_cross"] and bool(config["trading"].get("allow_new_entries", True)) and guard.trading_allowed):
        tick = mt5.symbol_info_tick(config["trading"]["symbol"])
        if tick is None:
            raise RuntimeError(f"mt5.symbol_info_tick({config['trading']['symbol']}) returned None")
        entry_price = float(tick.ask)
        stop_loss_price = entry_price * (1.0 - strategy.stop_loss_pct / 100.0)
        take_profit_price = entry_price * (1.0 + strategy.take_profit_pct / 100.0)
        risk_amount = float(account_info.balance) * (strategy.risk_pct / 100.0)
        volume = estimate_order_volume(config["trading"]["symbol"], entry_price, stop_loss_price, risk_amount)
        recommendation = {
            "go_long": True,
            "go_short": False,
            "entry_price": entry_price,
            "sl_price": stop_loss_price,
            "tp_price": take_profit_price,
            "lot_size": volume,
        }
        actions.append(
            {
                "type": "open_buy",
                "risk_amount": risk_amount,
                "volume": volume,
                "entry_price": entry_price,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
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
        "market_data_mode": "mt5",
        "data_provider": "mt5",
        "api_status": "n/a",
        "bot_status": "running",
        "account": {
            "balance": float(account_info.balance),
            "equity": float(account_info.equity),
        },
        "signal": signal,
        "recommendation": recommendation,
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
        default="config.json",
        help="Path to runtime config JSON. Relative paths are resolved from this script folder.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually send orders. Without this flag, the script stays in dry-run mode.",
    )
    parser.add_argument(
        "--market-data-only",
        action="store_true",
        help="Use Yahoo market data and skip all MT5 connectivity and order logic.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    base_dir = script_dir
    config_arg = Path(args.config)
    config_path = config_arg if config_arg.is_absolute() else (script_dir / config_arg)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_path}. Copy config.example.json to config.json and edit it first."
        )

    config = load_json(config_path)

    if args.market_data_only:
        config.setdefault("trading", {})["market_data_mode"] = "api"

    market_data_mode = str(config.get("trading", {}).get("market_data_mode", "mt5")).lower()
    if args.execute and market_data_mode == "api":
        raise ValueError("--execute cannot be used with API market-data-only mode.")

    try:
        if market_data_mode == "mt5":
            initialize_mt5(config)
            try:
                result = run_cycle(config, base_dir=base_dir, execute=args.execute)
            finally:
                shutdown_mt5()
        else:
            result = run_cycle(config, base_dir=base_dir, execute=False)
    except Exception as exc:
        result = {
            "run_utc": utc_now_iso(),
            "symbol": config.get("trading", {}).get("symbol"),
            "dry_run": True,
            "market_data_mode": market_data_mode,
            "data_provider": config.get("trading", {}).get("api_provider", "mt5"),
            "api_status": "error",
            "bot_status": "running_with_errors",
            "account": {"balance": None, "equity": None},
            "signal": {},
            "recommendation": {
                "go_long": False,
                "go_short": False,
                "entry_price": None,
                "sl_price": None,
                "tp_price": None,
                "lot_size": None,
            },
            "guardrail": {
                "trading_allowed": False,
                "hard_breach": False,
                "soft_stop_hit": False,
                "daily_loss_pct": 0.0,
                "total_loss_pct": 0.0,
                "notes": ["cycle_error"],
            },
            "open_positions": 0,
            "actions": [],
            "error": str(exc),
        }
        append_journal(base_dir, result)

    should_notify = bool(result.get("actions")) or bool(config.get("telegram", {}).get("notify_on_no_action", False))
    if should_notify:
        telegram_message = format_result_for_telegram(result)
        tz_name = config.get("telegram", {}).get("timezone")
        run_local = local_run_time(result.get("run_utc", ""), tz_name)
        if run_local:
            telegram_message += f"\nLocal time ({tz_name}): {run_local}"
        result["telegram"] = maybe_send_telegram(config, telegram_message)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()