#!/bin/bash

# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

set -euo pipefail

CONFIG_DIR="/config"
UI_FILE="${CONFIG_DIR}/ui.yaml"
STORAGE_FILE="${CONFIG_DIR}/storage.yaml"
ALERTS_FILE="${CONFIG_DIR}/alerting.yaml"
ANNOUNCEMENTS_FILE="${CONFIG_DIR}/announcements.yaml"
ENDPOINTS_FILE="${CONFIG_DIR}/endpoints.yaml"

mkdir -p "$CONFIG_DIR"

# UI configuration
cat > "$UI_FILE" <<EOF
ui:
  header: "${APP_UI_HEADER:-Gatus}"
  logo: "${APP_UI_LOGO:-}"
  dark-mode: "${APP_UI_DARK_MODE:-false}"
  default-sort-by: "${APP_UI_DEFAULT_SORT_BY:-name}"
  default-filter-by: "${APP_UI_DEFAULT_FILTER_BY:-none}"
EOF

# If there is a PostgreSQL database relation, use it to configure the storage
if [[ -n "${POSTGRESQL_DB_CONNECT_STRING:-}" ]]; then
	cat > "$STORAGE_FILE" <<EOF
storage:
  path: ${POSTGRESQL_DB_CONNECT_STRING}
  type: postgres
EOF

else
	echo "POSTGRESQL_DB_CONNECT_STRING is not set"
fi

# If there is a Juju secret with the Mattermost webhook URL, use it to configure alerting
if [[ -n "${MATTERMOST_WEBHOOK_URL:-}" ]]; then
	cat > "$ALERTS_FILE" <<EOF
alerting:
  mattermost:
    webhook-url: ${MATTERMOST_WEBHOOK_URL}
EOF
	if [[ "${APP_MATTERMOST_INSECURE:-false}" == "true" ]]; then
		cat >> "$ALERTS_FILE" <<EOF
    client:
      insecure: true
EOF
	fi
else
	echo "MATTERMOST_WEBHOOK_URL is not set"
fi

# If there is an app config with announcements, dump it into the announcements.yaml file
if [[ -n "${APP_ANNOUNCEMENTS:-}" ]]; then
	echo "${APP_ANNOUNCEMENTS}" > "$ANNOUNCEMENTS_FILE"
else
	echo "APP_ANNOUNCEMENTS is not set"
fi

# If there is an app config with endpoints, dump it into the endpoints.yaml file
if [[ -n "${APP_ENDPOINTS:-}" ]]; then
	echo "Using endpoints from config"
	echo "${APP_ENDPOINTS}" > "$ENDPOINTS_FILE"
else
	# Gatus requires at least one endpoint, so use a sample one
	cat > "$ENDPOINTS_FILE" <<EOF
endpoints:
  - name: Ubuntu.com
    group: Websites
    url: "https://ubuntu.com"
    interval: 60s
    conditions:
      - "[STATUS] == 200"
EOF
fi

export GATUS_CONFIG_PATH=$CONFIG_DIR
exec /gatus/bin/gatus
