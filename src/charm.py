#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import typing

import ops
import paas_charm.go
from ops.model import ActiveStatus, BlockedStatus, ModelError, SecretNotFoundError
from paas_charm.app import App

from constants import (
    MATTERMOST_ALERTING_CONFIG,
    WEBHOOK_URL_PLACEHOLDER_RE,
)
from exceptions import SecretAccessPendingError
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

    @property
    def _alerting_secret(self) -> dict[str, str] | None:
        """Get the Juju secret content for the alerting config.

        Returns:
            The Juju secret content, or None if the secret does not exist.

        """
        return self._get_juju_secret_content(MATTERMOST_ALERTING_CONFIG)

    @property
    def _default_webhook_url(self) -> str | None:
        """The default Mattermost webhook URL from the 'mattermost-alerting' secret.

        Returns:
            The Mattermost webhook URL, or None if the config/secret is not set (default value is used).

        """
        if not self._alerting_secret:
            return None

        default_webhook_url = self._alerting_secret.get("default")
        if not default_webhook_url:
            return None
        # This is the default Mattermost webhook URL set in the `alerting` config
        return default_webhook_url

    @property
    def _endpoints_config(self) -> str:
        """The endpoints config from the charm config.

        Returns:
            The endpoints config, or empty string if the config is not set (default value is used).

        """
        return str(self.model.config.get("endpoints", ""))

    def _get_endpoints(self) -> str | None:
        """Get the endpoints config from the charm config.

        Returns:
            The endpoints config, or the default value.

        """
        alerting_secret = self._get_juju_secret_content(MATTERMOST_ALERTING_CONFIG)
        if not alerting_secret:
            return self._endpoints_config

        endpoints = self._resolve_secret_placeholders(self._endpoints_config, alerting_secret)

        return endpoints

    def _create_app(self) -> App:
        """Build an App instance and inject dynamic environment variables."""
        app = super()._create_app()
        logger.info("Intercepted Go App creation for environment lifecycle.")
        original_gen_environment = app.gen_environment

        def custom_gen_environment(*args, **kwargs) -> dict[str, str]:
            """Customize environment variables."""
            env = original_gen_environment(*args, **kwargs)

            webhook_url = self._default_webhook_url
            endpoints = self._get_endpoints()

            # Set the default Mattermost webhook URL
            env["MATTERMOST_WEBHOOK_URL"] = webhook_url or ""
            # Process the endpoints config, resolving placeholders
            env["APP_ENDPOINTS"] = endpoints or ""

            # Set the Gatus application log level
            log_level = str(self.model.config["log-level"])
            if log_level.lower() in ["info", "debug", "warn", "error", "fatal"]:
                env["GATUS_LOG_LEVEL"] = log_level.upper()

            return env

        app.gen_environment = custom_gen_environment
        return app

    def is_ready(self) -> bool:
        """Extend the default is_ready with additional validation.

        All charm-blocking validations should happen in this function.

        Returns:
            True if the charm is ready, False otherwise.

        """
        if self._alerting_secret and not self._default_webhook_url:
            logger.warning("Alerting secret exists but default webhook URL is not set")
            self.update_app_and_unit_status(BlockedStatus("Secret exists but 'default' webhook URL is not set"))
            return False

        alerting_secret = self._get_juju_secret_content(MATTERMOST_ALERTING_CONFIG)
        has_placeholders = bool(WEBHOOK_URL_PLACEHOLDER_RE.search(self._endpoints_config))
        if has_placeholders and not alerting_secret:
            self.update_app_and_unit_status(
                BlockedStatus(
                    "Endpoints config contains secret placeholders but '{MATTERMOST_ALERTING_CONFIG}' is not configured"
                )
            )
            return False

        if has_placeholders and alerting_secret:
            # Resolve the endpoints config by replacing [webhook-url:channel-name] placeholders
            endpoints = self._resolve_secret_placeholders(self._endpoints_config, alerting_secret)
            if endpoints is None:
                self.update_app_and_unit_status(
                    BlockedStatus("Failed to resolve secret placeholders in endpoints config.")
                )
                return False

            status = GatusValidator.validate(self.model.config, endpoints=endpoints)
            if status != ActiveStatus():
                logger.warning(f"Config invalid, preventing restart: {status.message}")
                self.update_app_and_unit_status(status)
                return False

        status = GatusValidator.validate(self.model.config)
        if status != ActiveStatus():
            logger.warning(f"Config invalid, preventing restart: {status.message}")
            self.update_app_and_unit_status(status)
            return False

        return super().is_ready()


if __name__ == "__main__":  # pragma: nocover
    ops.main(GatusCharm)
