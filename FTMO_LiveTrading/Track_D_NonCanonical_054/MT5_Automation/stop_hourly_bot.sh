#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${SCRIPT_DIR}/state/hourly_runner.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "Hourly bot is not running (no PID file)."
  exit 0
fi

PID="$(cat "${PID_FILE}")"
if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
  kill "${PID}"
  echo "Stopped hourly bot PID ${PID}"
else
  echo "No running process found for PID ${PID}"
fi

rm -f "${PID_FILE}"
