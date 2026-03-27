#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import typing

import ops
import paas_charm.go
from ops.framework import EventBase
from ops.model import BlockedStatus, Container, ModelError, SecretNotFoundError
from ops.pebble import LayerDict

from constants import CONTAINER_NAME, MATTERMOST_ALERTING_CONFIG, MM_WEBHOOK_PLACEHOLDER_RE, SERVICE_NAME
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

        self.framework.observe(self.on.app_pebble_ready, self._update)
        self.framework.observe(self.on.config_changed, self._update)
        self.framework.observe(self.on.secret_changed, self._update)

        self.unit.status = GatusValidator.validate(self.model.config)

    def restart(self, rerun_migrations: bool = False) -> None:
        """Override the default restart to add a validation guard."""
        status = GatusValidator.validate(self.model.config)
        if status.name != "active":
            logger.warning(f"Config invalid, preventing restart: {status.message}")
            self.unit.status = status
            return

        super().restart(rerun_migrations)

    def _update(self, event: EventBase):
        """Update the application configuration when relevant.

        Args:
            event: The event that triggered the method.

        """
        logger.info("Updating config")

        # Get the application container
        container = self.unit.get_container(CONTAINER_NAME)
        if not container.can_connect():
            logger.info("Pebble is not ready yet, deferring config update")
            event.defer()
            return

        # Update environment variables based on config
        if not self._update_env(container):
            return

        self.restart()

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
            logger.error("Secret '%s' not found.", secret_id)
            return None
        except ModelError as e:
            logger.error(
                "Permission denied accessing secret '%s': %s. Run juju grant-secret",
                secret_id,
                str(e),
            )
            return None

    def _resolve_secret_placeholders(self, raw_yaml: str, secret_content: dict[str, str]) -> str | None:
        """Replace [mm-webhook:channel-name] placeholders with values from the secret content dict.

        Each placeholder [mm-webhook:channel-name] is resolved to the value of the
        channel-name key in the Juju secret content dict.

        Args:
            raw_yaml: The raw YAML string that may contain [mm-webhook:channel-name] placeholders.
            secret_content: The full content dict of the Juju secret.

        Returns:
            The resolved YAML string, or None if a referenced key was not found (in which case
            the charm unit status is set to BlockedStatus).

        """

        def replace_placeholder(match) -> str:
            channel = match.group(1)
            if channel not in secret_content:
                raise KeyError(channel)
            return secret_content[channel]

        try:
            return MM_WEBHOOK_PLACEHOLDER_RE.sub(replace_placeholder, raw_yaml)
        except KeyError as e:
            key = e.args[0]
            logger.error("Secret key '%s' not found in mattermost-alerting secret", key)
            self.unit.status = BlockedStatus(f"Secret key '{key}' not found in mattermost-alerting secret")
            return None

    def _update_env(self, container: Container) -> bool:
        """Create a pebble layer to add environment variables to the container.

        This is necessary for handling Juju secrets and resolving secret placeholders
        in the endpoints config.

        Args:
            container: The container in which to inject the environment variables.

        Returns:
            True if the update was successful, False if the charm was put into BlockedStatus.

        """
        env = {}

        secret_content = self._get_juju_secret_content(MATTERMOST_ALERTING_CONFIG)
        if secret_content:
            webhook_url = secret_content.get("default")
            if webhook_url:
                env["MATTERMOST_WEBHOOK_URL"] = webhook_url

            endpoints_raw = str(self.model.config.get("endpoints", ""))
            if endpoints_raw and MM_WEBHOOK_PLACEHOLDER_RE.search(endpoints_raw):
                resolved = self._resolve_secret_placeholders(endpoints_raw, secret_content)
                if resolved is None:
                    return False
                env["APP_ENDPOINTS"] = resolved
        elif MM_WEBHOOK_PLACEHOLDER_RE.search(str(self.model.config.get("endpoints", ""))):
            logger.error("Endpoints config contains secret placeholders but mattermost-alerting is not configured")
            self.unit.status = BlockedStatus(
                "Endpoints config contains secret placeholders but mattermost-alerting is not configured"
            )
            return False

        log_level = str(self.model.config["log-level"])
        if log_level.lower() in ["info", "debug", "warn", "error", "fatal"]:
            env["GATUS_LOG_LEVEL"] = log_level.upper()
        else:
            logger.warn("Invalid log level: %s", log_level)

        env_layer = LayerDict(
            {
                "services": {
                    SERVICE_NAME: {
                        "override": "merge",
                        "environment": env,
                    }
                }
            }
        )

        container.add_layer("go-env-layer", env_layer, combine=True)
        container.replan()
        return True


if __name__ == "__main__":  # pragma: nocover
    ops.main(GatusCharm)
