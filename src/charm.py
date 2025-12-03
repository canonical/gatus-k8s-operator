#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import typing

import ops
import paas_charm.go

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

    def _get_container(self, event) -> ops.model.Container | None:
        """Get the container if it is available."""
        container = self.unit.get_container(CONTAINER_NAME)
        if not container.can_connect():
            logger.info("Pebble is not ready yet, deferring config update")
            event.defer()
            return

        return container

    def _update(self, event):
        container = self._get_container(event)
        if not container:
            return
        config = self.model.config
        logger.info("Gatus config: %s", config)

        self._update_env(container)

        try:
            container.restart(SERVICE_NAME)
        except ops.pebble.ChangeError:
            pass

    def _get_mattermost_webhook_url(self) -> str | None:
        """Get the secret contents based on the charm config."""
        juju_secret = "juju-secret"  # nosec: B105
        config = self.model.config

        if juju_secret not in config:
            logger.info("No '%s' in config", juju_secret)
            return

        secret_id = str(config[juju_secret])
        if not secret_id:
            logger.info("No '%s' in config", juju_secret)
            return

        secret = self.model.get_secret(id=secret_id)
        if not secret:
            logger.info("No secret found")
            return

        content = secret.get_content()
        if "mattermost-webhook-url" not in content:
            logger.info("No mattermost-webhook-url in secret")
            return

        return content["mattermost-webhook-url"]

    def _update_env(self, container):
        """Create a pebble layer to add environment variables to the container.

        This is necessary for handling Juju secrets.
        """
        env = {}

        mattermost_webhook_url = self._get_mattermost_webhook_url()
        if mattermost_webhook_url:
            env["MATTERMOST_WEBHOOK_URL"] = mattermost_webhook_url

        log_level = str(self.model.config["log-level"])
        if log_level.lower() in ["info", "debug", "warn", "error", "fatal"]:
            env["GATUS_LOG_LEVEL"] = log_level.upper()

        env_layer = {"services": {"go": {"override": "merge", "environment": env}}}

        container.add_layer("go-env-layer", env_layer, combine=True)
        container.replan()


if __name__ == "__main__":  # pragma: nocover
    ops.main(GatusCharm)
