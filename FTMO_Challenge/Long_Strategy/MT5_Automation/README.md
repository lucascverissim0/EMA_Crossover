# MT5 Automation For Track D

This folder contains a dry-run-first MT5 automation scaffold for the pinned `Track D` FTMO challenge workflow.

## What It Does

- Connects to a running MT5 terminal.
- Pulls recent bars for `XAUUSD`.
- Recomputes the Track D EMA crossover state.
- Checks whether a new buy entry or a sell-based exit is present.
- Applies FTMO hard limits and softer internal stop rules before allowing new entries.
- Sizes volume from account balance, entry price, stop loss distance, and the Track D `0.54%` risk target.
- Writes state and a journal entry after every run.

## Important Constraints

- The script runs one cycle per execution. That is intentional.
- Default mode is dry-run. No orders are sent unless you pass `--execute`.
- This scaffold only supports the current long-only Track D logic.
- FTMO daily/max loss handling is approximated from MT5 account equity and local state. You still need broker-side monitoring.

## Files

- `config.example.json`: sample runtime configuration
- `run_track_d_mt5.py`: one-cycle MT5 runner
- `state/track_d_ftmo_state.json`: local FTMO state snapshot, created at runtime
- `state/track_d_mt5_journal.jsonl`: append-only run log, created at runtime

## Setup

### 1. Install dependencies in the trading environment

The trading machine should have:

```bash
pip install MetaTrader5 python-dotenv pandas numpy
```

If you want to keep dependency lists in sync, add `MetaTrader5` in your production environment from `requirements_advanced.txt`.

### 2. Prepare MT5

- Install MetaTrader 5 on the Windows machine that will trade.
- Log in to your FTMO account in MT5.
- Enable Algo Trading in the terminal.
- Confirm the tradable symbol name matches your broker naming, for example `XAUUSD`, `XAUUSDm`, or `XAUUSD.`.

### 3. Create runtime config

Copy:

```bash
cp FTMO_Challenge/Long_Strategy/MT5_Automation/config.example.json FTMO_Challenge/Long_Strategy/MT5_Automation/config.json
```

Then edit:
- `mt5.login`
- `mt5.server`
- `trading.symbol`
- `ftmo.starting_balance`

Set your password in an environment variable before launching:

```bash
export MT5_PASSWORD='your-password'
```

### 4. Dry-run first

From repo root:

```bash
python FTMO_Challenge/Long_Strategy/MT5_Automation/run_track_d_mt5.py --config FTMO_Challenge/Long_Strategy/MT5_Automation/config.json
```

Review:
- computed signal
- guardrail status
- intended action
- estimated position volume

### 5. Enable live execution only after validation

```bash
python FTMO_Challenge/Long_Strategy/MT5_Automation/run_track_d_mt5.py --config FTMO_Challenge/Long_Strategy/MT5_Automation/config.json --execute
```

## Suggested Operating Model

### Phase 1: Dry-run on the FTMO demo terminal

- Run the script every 1 to 5 minutes.
- Confirm it enters only on fresh H1 buy crossovers.
- Confirm it exits on sell crossover or guardrail breach.
- Compare orders against the Track D dashboard and manual chart review.

### Phase 2: Live but reduced risk

- Keep `Track D` logic but lower actual `risk_pct` in the config below the research setting.
- Start with a fraction of the intended size.
- Confirm journal integrity and state resets across trading days.

### Phase 3: Full challenge automation

- Run on a dedicated Windows VPS with MT5 always open.
- Use Windows Task Scheduler every minute.
- Alert on guardrail breach, rejected orders, or missing data.
- Review journal and MT5 history at the end of every FTMO trading day.

## FTMO Guardrail Logic In This Scaffold

The script blocks new entries when either of these soft stops are hit:
- `soft_daily_stop_pct`
- `soft_max_loss_stop_pct`

It marks a hard breach when either of these FTMO limits is hit:
- `daily_loss_limit_pct`
- `max_loss_limit_pct`

With `close_on_guardrail_breach=true`, existing Track D positions are closed when a hard breach is detected.

## Practical Steps Needed To Fully Automate Your FTMO Challenge

1. Normalize the exact MT5 symbol name used by your FTMO server.
2. Validate lot sizing with your broker contract specs.
3. Decide whether to trade the exact research risk (`0.54%`) or a lower live risk.
4. Add notification hooks for fills, rejections, and guardrail stops.
5. Run dry for several days before enabling `--execute`.
6. Keep Track C as the compliance benchmark while Track D is the faster execution profile.

## Recommended Next Build Steps

1. Add Telegram or email alerts.
2. Add a spread filter and trading-hours filter.
3. Add a persistent order reconciliation layer.
4. Add an MT5 account-history based daily loss calculator instead of relying only on local state.