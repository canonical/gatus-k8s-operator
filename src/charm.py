#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import typing

import ops
import paas_charm.go
import yaml
from ops.framework import EventBase
from ops.model import BlockedStatus, Container, ModelError, SecretNotFoundError
from ops.pebble import LayerDict, PathError
from pydantic import ValidationError

from gatus import GatusConfig

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
        self._update_env(container)

        validation_msg = self._validate_config(container)
        if validation_msg:
            self.unit.status = BlockedStatus(validation_msg)
            return

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
            logger.debug("No '%s' in config", config_name)
            return None

        if not secret_id:
            logger.debug("No secret ID in config for '%s'", config_name)
            return None

        try:
            secret = self.model.get_secret(id=secret_id)
            content = secret.get_content(refresh=True)
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
            env["MATTERMOST_WEBHOOK_URL"] = mattermost_webhook_url

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

    def _validate_config(self, container: Container):
        """Validate the application configuration.

        Args:
            container: The container from which to pull the config files.

        """
        config_keys = ["storage", "announcements", "endpoints", "alerting"]
        config_dict = {}

        for config_key in config_keys:
            filepath = f"/config/{config_key}.yaml"
            try:
                file_content = container.pull(filepath).read()
                data = yaml.safe_load(file_content)
                # Merge the dicts
                config_dict = config_dict | data
            except PathError:
                # The file does not need to exist
                logger.info(f"File {filepath} not found in container {container.name}.")
            except yaml.YAMLError as e:
                msg = f"Failed to parse YAML based on {config_key}."
                logger.error(msg, e)
                return msg

        try:
            GatusConfig.model_validate(config_dict)
        except ValidationError as e:
            msg = f"Failed to validate Gatus configuration: {e}"
            logger.error(msg, e)
            return msg

        return None


if __name__ == "__main__":  # pragma: nocover
    ops.main(GatusCharm)
