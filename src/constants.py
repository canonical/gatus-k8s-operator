# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants for the Gatus charm."""

import re

SERVICE_NAME = "go"
CONTAINER_NAME = "app"

INVALID_SORT_BY_MESSAGE = "Invalid default sort order. Valid values are: name, group, health."
INVALID_FILTER_BY_MESSAGE = "Invalid default filter. Valid values are: none, failing, unstable."
FAILED_TO_VALIDATE = "Failed to validate Gatus configuration. Please check logs."
FAILED_TO_UPDATE_ENVIRONMENT = "Failed to update environment variables. Please check logs."

WEBHOOK_URL_PLACEHOLDER_RE = re.compile(r"\[webhook-url:([^\]]+)\]")

MATTERMOST_ALERTING_CONFIG = "mattermost-alerting"
