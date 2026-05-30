#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
SERVICE_NAME="langgraph-maintenance-agent.service"
TIMER_NAME="langgraph-maintenance-agent.timer"

mkdir -p "$SYSTEMD_USER_DIR"
sed "s#{{PROJECT_DIR}}#${PROJECT_DIR}#g" \
  "${PROJECT_DIR}/systemd/${SERVICE_NAME}" > "${SYSTEMD_USER_DIR}/${SERVICE_NAME}"
cp "${PROJECT_DIR}/systemd/${TIMER_NAME}" "${SYSTEMD_USER_DIR}/${TIMER_NAME}"

systemctl --user daemon-reload
systemctl --user enable --now "$TIMER_NAME"
systemctl --user list-timers "$TIMER_NAME"
