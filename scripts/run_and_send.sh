#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/haseeb/repositories/langgraph_routine_maintenance_agent"
cd "$PROJECT_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . ".env"
  set +a
fi

CONFIG_PATH="${LANGGRAPH_MAINTENANCE_CONFIG:-examples/repos.yaml}"
TIMEOUT_SECONDS="${LANGGRAPH_MAINTENANCE_TIMEOUT_SECONDS:-3600}"
MAX_CONCURRENCY="${LANGGRAPH_MAINTENANCE_MAX_CONCURRENCY:-4}"

MODE_FLAG="--no-llm"
if [[ "${LANGGRAPH_MAINTENANCE_USE_LLM:-0}" == "1" ]]; then
  MODE_FLAG="--llm"
fi

write_script_failure_report() {
  local stage="$1"
  local message="$2"
  local reports_dir="reports"
  local timestamp
  local run_id
  mkdir -p "$reports_dir"
  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  run_id="$(date -u +"%Y%m%d%H%M%S")"
  cat > "${reports_dir}/${run_id}-failure.md" <<EOF
# Routine Maintenance Failure Report - ${timestamp:0:10}

- Run ID: \`${run_id}\`
- Timestamp: \`${timestamp}\`
- Stage: \`${stage}\`
- Config path: \`${CONFIG_PATH}\`

Normal repository inspection did not complete. This report was generated for the failed run and is not copied to \`latest.md\`.

## Error

${message}
EOF
}

set +e
timeout "$TIMEOUT_SECONDS" uv run langgraph-maintenance run \
  --config "$CONFIG_PATH" \
  "$MODE_FLAG" \
  --send-discord \
  --summary-only \
  --max-concurrency "$MAX_CONCURRENCY"
status=$?
set -e

if [[ "$status" -eq 124 ]]; then
  write_script_failure_report "script_timeout" "The maintenance run exceeded LANGGRAPH_MAINTENANCE_TIMEOUT_SECONDS. Discord delivery was skipped to avoid sending a stale report."
  exit "$status"
fi

if [[ "$status" -ne 0 ]]; then
  mkdir -p reports
  if ! find reports -maxdepth 1 -type f -name '*-failure.md' -mmin -5 | grep -q .; then
    write_script_failure_report "script_failure" "The maintenance command exited with status ${status}. Discord delivery was skipped to avoid sending a stale report."
  fi
  exit "$status"
fi
