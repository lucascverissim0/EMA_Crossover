#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${SCRIPT_DIR}/state/hourly_runner.pid"
OUT_FILE="${SCRIPT_DIR}/state/hourly_runner.out"
LOG_FILE="${SCRIPT_DIR}/state/hourly_cycle.log"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "Status: stopped"
  exit 0
fi

PID="$(cat "${PID_FILE}")"
if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
  echo "Status: running (PID ${PID})"
  if [[ -f "${OUT_FILE}" ]]; then
    echo "--- recent runner output ---"
    tail -n 20 "${OUT_FILE}"
  fi
  if [[ -f "${LOG_FILE}" ]]; then
    echo "--- recent cycle log ---"
    tail -n 20 "${LOG_FILE}"
  fi
else
  echo "Status: stale PID file (PID ${PID} not running)"
fi
