#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import typing

import ops
import paas_charm.go
from ops.framework import EventBase
from ops.model import Container, ModelError, SecretNotFoundError
from ops.pebble import LayerDict

logger = logging.getLogger(__name__)

SERVICE_NAME = "go"
CONTAINER_NAME = "app"


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

    def _get_container(self, event: EventBase) -> Container | None:
        """Get the container if it is available.

        Args:
            event: The event that triggered the method.

        """
        container = self.unit.get_container(CONTAINER_NAME)
        if not container.can_connect():
            logger.info("Pebble is not ready yet, deferring config update")
            event.defer()
            return

        return container

    def _update(self, event: EventBase):
        """Update the application configuration when relevant.

        Args:
            event: The event that triggered the method.

        """
        logger.info("Updating config")
        container = self._get_container(event)
        if not container:
            return

        self._update_env(container)

        try:
            container.restart(SERVICE_NAME)
        except ops.pebble.ChangeError as e:
            # Service may not exist yet (e.g., during initial setup), but log the error for visibility.
            logger.error("Failed to restart service '%s': %s", SERVICE_NAME, e)

    def _get_juju_secret(self, config_name: str, secret_key: str) -> str | None:
        """Get Juju secret contents based on the charm config.

        Args:
            config_name: The name of the charm config. It should refer to a Juju secret ID.
            secret_key: The key of the secret to retrieve.

        """
        config = self.model.config

        try:
            secret_id = str(config[config_name])
        except KeyError:
            logger.info("No '%s' in config", config_name)
            return None

        if not secret_id:
            logger.info("No secret ID in config for '%s'", config_name)
            return None

        try:
            logger.info("Retrieving secret '%s'", secret_id)
            secret = self.model.get_secret(id=secret_id)
            content = secret.get_content()
            value = content[secret_key]
        except SecretNotFoundError:
            logger.error(
                "Secret '%s' not found.",
                secret_id,
            )
            return None
        except ModelError as e:
            logger.error(
                "Permission denied accessing secret '%s': %s. Run juju grant-secret",
                secret_id,
                str(e),
            )
            return None
        except KeyError:
            logger.error(
                "No '%s' in secret '%s'.",
                secret_key,
                secret_id,
            )
            return None

        return value

    def _update_env(self, container: Container):
        """Create a pebble layer to add environment variables to the container.

        This is necessary for handling Juju secrets.

        Args:
            container: The container in which to inject the environment variables.

        """
        env = {}

        mattermost_webhook_url = self._get_juju_secret("mattermost-alerting", "mattermost-webhook-url")
        if mattermost_webhook_url:
            logger.info("Mattermost webhook URL found in secret: %s", mattermost_webhook_url)
            env["MATTERMOST_WEBHOOK_URL"] = mattermost_webhook_url

        log_level = str(self.model.config["log-level"])
        if log_level.lower() in ["info", "debug", "warn", "error", "fatal"]:
            env["GATUS_LOG_LEVEL"] = log_level.upper()

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


if __name__ == "__main__":  # pragma: nocover
    ops.main(GatusCharm)
