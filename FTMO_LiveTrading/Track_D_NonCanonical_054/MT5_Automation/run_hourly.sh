#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.live"
LOG_FILE="${SCRIPT_DIR}/state/hourly_cycle.log"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-3600}"

mkdir -p "${SCRIPT_DIR}/state"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ENV_FILE}"
  set +a
fi

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") missing TELEGRAM_BOT_TOKEN" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ -z "${MASSIVE_API_KEY:-}" ]]; then
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") missing MASSIVE_API_KEY" | tee -a "${LOG_FILE}"
  exit 1
fi

while true; do
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") starting hourly cycle" >> "${LOG_FILE}"
  python "${SCRIPT_DIR}/run_track_d_mt5.py" --market-data-only >> "${LOG_FILE}" 2>&1 || true
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") cycle complete; sleeping ${INTERVAL_SECONDS}s" >> "${LOG_FILE}"
  sleep "${INTERVAL_SECONDS}"
done
