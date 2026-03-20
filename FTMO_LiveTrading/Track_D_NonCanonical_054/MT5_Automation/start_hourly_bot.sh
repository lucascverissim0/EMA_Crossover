#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${SCRIPT_DIR}/state/hourly_runner.pid"
OUT_FILE="${SCRIPT_DIR}/state/hourly_runner.out"
RUNNER="${SCRIPT_DIR}/run_hourly.sh"

mkdir -p "${SCRIPT_DIR}/state"

if [[ -f "${PID_FILE}" ]]; then
  PID="$(cat "${PID_FILE}")"
  if [[ -n "${PID}" ]] && kill -0 "${PID}" 2>/dev/null; then
    echo "Hourly bot already running with PID ${PID}"
    exit 0
  fi
fi

nohup bash "${RUNNER}" >> "${OUT_FILE}" 2>&1 &
PID=$!
echo "${PID}" > "${PID_FILE}"
echo "Hourly bot started with PID ${PID}"
echo "Logs: ${OUT_FILE}"
