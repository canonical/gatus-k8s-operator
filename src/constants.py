# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants for the Gatus charm."""

SERVICE_NAME = "go"
CONTAINER_NAME = "app"

INVALID_SORT_BY_MESSAGE = "Invalid default sort order. Valid values are: name, group, health"
INVALID_FILTER_BY_MESSAGE = "Invalid default filter. Valid values are: none, failing, unstable"
FAILED_TO_VALIDATE = "Failed to validate Gatus configuration"
OIDC_INCOMPLETE_CONFIG_MESSAGE = (
    "OIDC config incomplete: oidc-issuer-url, oidc-redirect-url, and oidc-credentials must all be set together"
)
OIDC_INVALID_REDIRECT_URL_MESSAGE = "oidc-redirect-url must end with /authorization-code/callback"
