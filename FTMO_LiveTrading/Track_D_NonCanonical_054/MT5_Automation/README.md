# Track D MT5 + Telegram Alerts

This runner supports a phone-alert workflow for Track D while keeping execution manual until you are ready.

## Core Files

- `config.example.json`
- `run_track_d_mt5.py`
- `send_telegram_test.py`
- `state/track_d_ftmo_state.json` (created at runtime)
- `state/track_d_mt5_journal.jsonl` (created at runtime)

## Configure

1. Copy config:

```bash
cp FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/config.example.json FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/config.json
```

2. Set these values in `config.json`:
- `mt5.login`
- `mt5.server`
- `trading.symbol`
- `ftmo.starting_balance`

3. Enable Telegram alerts:
- set `telegram.enabled=true`
- set `telegram.chat_id`
- set `telegram.bot_token_env` (default `TELEGRAM_BOT_TOKEN`)

4. Export secrets:

```bash
export MT5_PASSWORD='your-mt5-password'
export TELEGRAM_BOT_TOKEN='123456:ABCDEF...'
```

5. Send a test message to confirm Telegram wiring:

```bash
python FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/send_telegram_test.py
```

## Run (Manual-Execution Mode)

Use dry-run mode (default) and no `--execute` flag:

```bash
python FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/run_track_d_mt5.py
```

This still sends Telegram alerts, but it does not send MT5 orders.
Important: in MT5 mode this command still connects to MT5 to read account data, positions, and candles.

## Run (No-MT5 API Scan Mode)

To scan market data and send Telegram alerts without any MT5 access:

1. Set `trading.market_data_mode` to `api` in `config.json` (already done in current live config).
2. Run:

```bash
python FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/run_track_d_mt5.py
```

Or force API mode from CLI regardless of config:

```bash
python FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/run_track_d_mt5.py --market-data-only
```

Notes for API mode:
- Data source is configured by `trading.api_provider`:
	- `yahoo` (default): set `trading.api_symbol` like `XAUUSD=X`
	- `twelvedata`: set `trading.api_symbol` like `XAU/USD` and export key from `trading.api_key_env`
	- `alphavantage`: set `trading.api_symbol` like `XAUUSD` (or `XAU/USD`) and export key from `trading.api_key_env`
	- `finnhub`: set `trading.api_symbol` like `OANDA:XAU_USD` and export key from `trading.api_key_env`
	- `massive`: set `trading.api_symbol` like `C:XAUUSD` and export key from `trading.api_key_env`
- Optional failover chain: set `trading.api_provider_fallbacks`, for example `['yahoo']`.
- No MT5 terminal initialization, no MT5 login, and no MT5 position/account reads.
- Alerts are signal-based (`buy_cross` / `sell_cross`) only.
- FTMO guardrails are marked as informational (`api_mode_no_mt5_guardrails`) because no broker/account equity is available.

Example TwelveData setup:

```bash
export MARKET_DATA_API_KEY='your-twelvedata-key'
python FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/run_track_d_mt5.py --market-data-only
```

Example Alpha Vantage setup:

```bash
export ALPHAVANTAGE_API_KEY='your-alpha-vantage-key'
python FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/run_track_d_mt5.py --market-data-only
```

Alpha Vantage free-tier note:
- Free keys are throttled and may return a `Note` message when limits are hit.
- The runner retries automatically when this happens.
- Intraday FX may be premium on Alpha Vantage for some pairs (including gold spot symbols).
- A practical free-tier setup is to use `trading.api_symbol = GLD` as a gold proxy on `H1` candles.

Example Finnhub setup:

```bash
export FINNHUB_API_KEY='your-finnhub-key'
python FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/run_track_d_mt5.py --market-data-only
```

Example Massive setup:

```bash
export MASSIVE_API_KEY='your-massive-key'
python FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/run_track_d_mt5.py --market-data-only
```

What `403` means:
- The request was authenticated but access is forbidden for that endpoint/symbol/plan.
- Common causes: subscription entitlement mismatch, wrong market scope, or key restrictions.

## Run (Automated Execution Mode)

Only after dry-run validation:

```bash
python FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/run_track_d_mt5.py --execute
```

## Hourly Scheduler (Background)

The workspace includes helper scripts for continuous hourly runs:

- `start_hourly_bot.sh`
- `stop_hourly_bot.sh`
- `status_hourly_bot.sh`
- `run_hourly.sh`

Persistent secrets are loaded from:

- `.env.live`

Start hourly bot:

```bash
bash FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/start_hourly_bot.sh
```

Check status and recent logs:

```bash
bash FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/status_hourly_bot.sh
```

Stop hourly bot:

```bash
bash FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/stop_hourly_bot.sh
```

## GitHub Actions (Hourly Alternative)

You can run this bot hourly in GitHub Actions using:

- `.github/workflows/track-d-hourly-alerts.yml`

Required repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `MASSIVE_API_KEY`

How to enable:

1. Open repository Settings -> Secrets and variables -> Actions.
2. Add both secrets listed above.
3. Open Actions tab and run `Track D Hourly Alerts` once via `Run workflow`.
4. Confirm you receive Telegram heartbeat/status messages.

Notes:

- Schedule is hourly (`cron: 5 * * * *`, UTC).
- GitHub-hosted jobs are not an always-on daemon; each run starts and stops.

## Alert Behavior

- Sends alerts when actions are detected (buy, close, guardrail close).
- Heartbeat alerts are controlled by `telegram.notify_on_no_action`.
- With heartbeat enabled, each run sends:
	- bot status (`running` or `running_with_errors`)
	- API status (`ok` or `error`) and provider name
	- latest signal and guardrail context
- On data/API failures, a heartbeat with error details is sent instead of failing silently.
- Entry alerts include:
	- entry price
	- stop loss
	- take profit
	- lot size
	- risk amount in USD
- Guardrail alerts include:
	- daily and total loss percentages
	- explicit guardrail reasons from the current run

## Can You Trade Manually From Alerts?

Yes. This is exactly what dry-run + Telegram is for:
- get signal and guardrail context on your phone
- manually place or close positions in MT5
- avoid auto-execution until you are confident in operations