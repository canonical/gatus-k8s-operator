#!/bin/bash

# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

set -euo pipefail

CONFIG_DIR="/config"
UI_FILE="${CONFIG_DIR}/ui.yaml"
STORAGE_FILE="${CONFIG_DIR}/storage.yaml"
ALERTS_FILE="${CONFIG_DIR}/alerting.yaml"
SECURITY_FILE="${CONFIG_DIR}/security.yaml"
ANNOUNCEMENTS_FILE="${CONFIG_DIR}/announcements.yaml"
ENDPOINTS_FILE="${CONFIG_DIR}/endpoints.yaml"

mkdir -p "$CONFIG_DIR"

# UI configuration
cat > "$UI_FILE" <<EOF
ui:
  header: "${APP_UI_HEADER:-Gatus}"
  logo: "${APP_UI_LOGO:-}"
  dashboard-heading: "${APP_UI_DASHBOARD_HEADING:-Health Dashboard}"
  dashboard-subheading: "${APP_UI_DASHBOARD_SUBHEADING:-Monitor the health of your endpoints in real-time}"
  dark-mode: ${APP_UI_DARK_MODE:-true}
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
	rm -f "$STORAGE_FILE"
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
	rm -f "$ALERTS_FILE"
fi

# If there is an app config with announcements, dump it into the announcements.yaml file
if [[ -n "${APP_ANNOUNCEMENTS:-}" ]]; then
	echo "${APP_ANNOUNCEMENTS}" > "$ANNOUNCEMENTS_FILE"
else
	echo "APP_ANNOUNCEMENTS is not set"
	rm -f "$ANNOUNCEMENTS_FILE"
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

# If the oauth relation is established, configure OIDC authentication
if [[ -n "${APP_OAUTH_CLIENT_ID:-}" && -n "${APP_OAUTH_CLIENT_SECRET:-}" && -n "${APP_OAUTH_API_BASE_URL:-}" && -n "${APP_BASE_URL:-}" ]]; then
	echo "Configuring OIDC authentication via OAuth relation"

	REDIRECT_PATH="${APP_OAUTH_REDIRECT_PATH:-/authorization-code/callback}"
	REDIRECT_URI="${APP_BASE_URL%/}/${REDIRECT_PATH#/}"

	cat > "$SECURITY_FILE" <<EOF
security:
  oidc:
    issuer-url: ${APP_OAUTH_API_BASE_URL}
    redirect-url: ${REDIRECT_URI}
    client-id: ${APP_OAUTH_CLIENT_ID}
    client-secret: ${APP_OAUTH_CLIENT_SECRET}
    scopes:
EOF

	# Append scopes as a YAML list (space-separated per oauth relation convention)
	read -ra SCOPES <<< "${APP_OAUTH_SCOPES:-openid}"
	if [[ ${#SCOPES[@]} -eq 0 ]]; then
		SCOPES=("openid")
	fi
	for scope in "${SCOPES[@]}"; do
		echo "      - ${scope}" >> "$SECURITY_FILE"
	done

	# Optionally restrict to specific subjects
	if [[ -n "${APP_OIDC_ALLOWED_SUBJECTS:-}" ]]; then
		echo "    allowed-subjects:" >> "$SECURITY_FILE"
		IFS=',' read -ra SUBJECTS <<< "$APP_OIDC_ALLOWED_SUBJECTS"
		for subject in "${SUBJECTS[@]}"; do
			echo "      - ${subject}" >> "$SECURITY_FILE"
		done
	fi
else
	echo "OAuth not configured, skipping OIDC security"
	rm -f "$SECURITY_FILE"
fi

export GATUS_CONFIG_PATH=$CONFIG_DIR
exec /gatus/bin/gatus
