# FTMO Live Trading

This folder is an execution-focused workspace for manual and semi-automated challenge operations.

## Included

- `Track_D_NonCanonical_054/`: copied from FTMO challenge research outputs.
- `Track_D_NonCanonical_054/MT5_Automation/`: MT5 runner with Telegram alerts.

## Manual-Execution Phone Workflow

Yes. You can receive Telegram alerts on your phone and place the position manually in MT5.

Recommended setup for manual execution:

1. Keep config `dry_run=true`.
2. Run the MT5 script on schedule (for example, every 1 minute).
3. Let Telegram notify you when a buy/sell/guardrail event is detected.
4. Place or close the trade manually in your FTMO MT5 terminal.

This keeps signal automation while preserving manual execution control.

## Next Folder To Open

- `FTMO_LiveTrading/Track_D_NonCanonical_054/MT5_Automation/README.md`