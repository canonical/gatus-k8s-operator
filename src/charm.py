#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import typing

import ops
import paas_charm.go
from ops.model import ActiveStatus, ModelError, SecretNotFoundError
from paas_charm.app import App

from constants import (
    MATTERMOST_ALERTING_CONFIG,
    WEBHOOK_URL_PLACEHOLDER_RE,
)
from exceptions import BlockedStatusError, SecretAccessPendingError
from validator import GatusValidator

logger = logging.getLogger(__name__)


class GatusCharm(paas_charm.go.Charm):
    """Go Charm service."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.

        """
        super().__init__(*args)

        self.unit.status = GatusValidator.validate(self.model.config)

    def restart(self, rerun_migrations: bool = False) -> None:
        """Override the default restart to add a validation guard."""
        status = GatusValidator.validate(self.model.config)
        if status.name != "active":
            logger.warning(f"Config invalid, preventing restart: {status.message}")
            self.unit.status = status
            return

        super().restart(rerun_migrations)

    def _get_juju_secret(self, config_name: str, secret_key: str) -> str | None:
        """Get Juju secret contents based on the charm config.

        Args:
            config_name: The name of the charm config. It should refer to a Juju secret ID.
            secret_key: The key of the secret to retrieve.

        """
        content = self._get_juju_secret_content(config_name)
        if content is None:
            return None
        value = content.get(secret_key)
        if value is None:
            logger.error("No '%s' in secret for config '%s'.", secret_key, config_name)
        return value

    def _get_juju_secret_content(self, config_name: str) -> dict[str, str] | None:
        """Get the full content dict of a Juju secret based on the charm config.

        Args:
            config_name: The name of the charm config. It should refer to a Juju secret ID.

        """
        config = self.model.config

        try:
            secret_id = str(config[config_name])
        except KeyError:
            logger.debug("No '%s' in config", config_name)
            return None

        if not secret_id:
            logger.debug("No secret ID in config for '%s'", config_name)
            return None

        try:
            secret = self.model.get_secret(id=secret_id)
            return secret.get_content(refresh=True)
        except SecretNotFoundError:
            raise SecretAccessPendingError(f"Waiting for Juju secret '{secret_id}' to become available")
        except ModelError as e:
            raise SecretAccessPendingError(f"Waiting for access to Juju secret '{secret_id}': {str(e)}")

    def _resolve_secret_placeholders(self, raw_yaml: str, secret_content: dict[str, str]) -> str | None:
        """Replace [webhook-url:channel-name] placeholders with values from the secret content dict.

        Each placeholder [webhook-url:channel-name] is resolved to the value of the
        channel-name key in the Juju secret content dict.

        Args:
            raw_yaml: The raw YAML string that may contain [webhook-url:channel-name] placeholders.
            secret_content: The full content dict of the Juju secret.

        Returns:
            The resolved YAML string, or None if a referenced key was not found.

        """

        def replace_placeholder(match) -> str:
            channel = match.group(1)
            if channel not in secret_content:
                raise KeyError(channel)
            return secret_content[channel]

        try:
            return WEBHOOK_URL_PLACEHOLDER_RE.sub(replace_placeholder, raw_yaml)
        except KeyError as e:
            key = e.args[0]
            logger.error("Secret key '%s' not found in %s secret", key, MATTERMOST_ALERTING_CONFIG)
            return None

    def _get_default_webhook_url(self) -> str | None:
        """Set the default Mattermost webhook URL in the container environment.

        Returns:
            The Mattermost webhook URL, or None if the config/secret is not set (default value is used).

        Raises:
            BlockedStatusError: If the secret exists but does not contain a 'default' key.

        """
        logger.info("Getting default webhook URL from secret")
        alerting_secret = self._get_juju_secret_content(MATTERMOST_ALERTING_CONFIG)
        if not alerting_secret:
            return None
        logger.info("Alerting secret exists")

        default_webhook_url = alerting_secret.get("default")
        if not default_webhook_url:
            raise BlockedStatusError(f"Secret does not contain a 'default' key in {MATTERMOST_ALERTING_CONFIG}")
        # This is the default Mattermost webhook URL set in the `alerting` config
        return default_webhook_url

    def _get_endpoints(self) -> str | None:
        """Get the endpoints config from the charm config.

        Returns:
            The endpoints config, or None if the config is not set (default value is used).

        Raises:
            BlockedStatusError: If there was a problem resolving the placeholders in the endpoints config.

        """
        endpoints = str(self.model.config.get("endpoints", ""))
        if not endpoints:
            logger.info("No endpoints config set, using default")
            return None

        alerting_secret = self._get_juju_secret_content(MATTERMOST_ALERTING_CONFIG)
        has_placeholders = bool(WEBHOOK_URL_PLACEHOLDER_RE.search(endpoints))
        if has_placeholders and not alerting_secret:
            raise BlockedStatusError(
                f"Endpoints config contains secret placeholders but '{MATTERMOST_ALERTING_CONFIG}' is not configured"
            )

        if has_placeholders and alerting_secret:
            # Resolve the endpoints config by replacing [webhook-url:channel-name] placeholders
            endpoints = self._resolve_secret_placeholders(endpoints, alerting_secret)
            if endpoints is None:
                raise BlockedStatusError("Failed to resolve secret placeholders in endpoints config.")

        # Re-validate the charm config with the resolved endpoints to ensure it's valid before applying it
        status = GatusValidator.validate(self.model.config, endpoints=endpoints)
        if status != ActiveStatus():
            raise BlockedStatusError(status.message)

        return endpoints

    def _get_oidc_env(self) -> dict[str, str]:
        """Get OIDC environment variables.

        Returns:
            A dictionary of OIDC environment variables.

        """
        oidc_env = {}

        oauth_relation = self.model.get_relation("oidc")
        logger.debug("Found oauth relation: %s", oauth_relation)
        if oauth_relation and oauth_relation.app:
            app_data = oauth_relation.data[oauth_relation.app]
            if "client_id" in app_data:
                oidc_env["APP_OAUTH_CLIENT_ID"] = app_data["client_id"]
                oidc_env["APP_OAUTH_API_BASE_URL"] = app_data["issuer_url"]

            secret_id = app_data.get("client_secret_id")
            if secret_id:
                secret = self.model.get_secret(id=secret_id)
                oidc_env["APP_OAUTH_CLIENT_SECRET"] = secret.get_content().get("secret", "")

        return oidc_env

    def _create_app(self) -> App:
        """Build an App instance and inject dynamic environment variables."""
        app = super()._create_app()
        logger.info("Intercepted Go App creation for environment lifecycle.")
        original_gen_environment = app.gen_environment

        def custom_gen_environment(*args, **kwargs) -> dict[str, str]:
            """Customize environment variables."""
            env = original_gen_environment(*args, **kwargs)

            # Set the default Mattermost webhook URL
            env["MATTERMOST_WEBHOOK_URL"] = self._get_default_webhook_url() or ""
            # Process the endpoints config, resolving placeholders
            env["APP_ENDPOINTS"] = self._get_endpoints() or ""
            # Set the Gatus application log level
            log_level = str(self.model.config["log-level"])
            if log_level.lower() in ["info", "debug", "warn", "error", "fatal"]:
                env["GATUS_LOG_LEVEL"] = log_level.upper()
            # Set the OIDC environment variables
            oidc_env = self._get_oidc_env()
            if oidc_env:
                env.update(oidc_env)

            return env

        app.gen_environment = custom_gen_environment
        return app


if __name__ == "__main__":  # pragma: nocover
    ops.main(GatusCharm)
