#!/bin/bash

# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

set -euo pipefail

python3 /gatus/render_config.py

python3 /gatus/db_probe.py &
probe_pid=$!
unset DB_PROBE_TARGETS

export GATUS_CONFIG_PATH=/config
/gatus/bin/gatus &
gatus_pid=$!

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
