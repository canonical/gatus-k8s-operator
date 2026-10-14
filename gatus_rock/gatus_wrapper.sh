#!/bin/bash

# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

set -euo pipefail

# Start the local API that checks PostgreSQL endpoints independently of Gatus.
python3 -m uvicorn db_probe:app --host 127.0.0.1 --port 9090 &
probe_pid=$!
unset DB_PROBE_TARGETS

# Keep relation credentials out of the rendered Gatus configuration.
python3 /gatus/render_config.py

# Run Gatus beside the probe and stop both processes if either exits.
export GATUS_CONFIG_PATH=/config
/gatus/bin/gatus &
gatus_pid=$!

# Forward shutdown and preserve the exit status of the first process to stop.
cleanup() {
    kill "$probe_pid" "$gatus_pid" 2>/dev/null || true
    wait "$probe_pid" "$gatus_pid" 2>/dev/null || true
}

trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

set +e
wait -n "$probe_pid" "$gatus_pid"
exit_code=$?
set -e
exit "$exit_code"
