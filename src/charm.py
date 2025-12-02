#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import typing

import ops
import paas_charm.go
import yaml

# from charms.data_platform_libs.v0.data_interfaces import (
#     DatabaseCreatedEvent,
#     DatabaseEndpointsChangedEvent,
#     DatabaseRequires,
# )

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

        # Add observers to trigger config updates
        # self.framework.observe(self.on.postgresql_relation_changed, self._on_db_relation_changed)
        # self.framework.observe(self.on.gatus_pebble_ready, self._update_config)
        # self.framework.observe(self.on.postgresql_relation_changed, self._update_config)
        # self.framework.observe(self.on.postgresql_relation_departed, self._update_config)

    def _get_container(self, event) -> ops.model.Container | None:
        """Get the container if it is available."""
        container = self.unit.get_container(CONTAINER_NAME)
        if not container.can_connect():
            logger.info("Pebble is not ready yet, deferring config update")
            event.defer()
            return

        return container
    #
    # def _on_pebble_ready(self, event):
    #     """Override the default _on_pebble_ready."""
    #     logger.info("_on_pebble_ready")
    #     container = self._get_container(event)
    #     if not container:
    #         return
    #
    #     self._write_gatus_config(container)
    #     super()._on_pebble_ready(event)
    #
    def _on_config_changed(self, event):
        """Override the default _on_config_changed."""
        logger.info("_on_config_changed")
        container = self._get_container(event)
        if not container:
            return

        self._write_gatus_config(container)
        super()._on_config_changed(event)
    #
    # def _on_db_relation_changed(self, event):
    #     """Update Postgres relation data."""
    #     logger.info("_on_db_relation_changed triggered")
    #     container = self._get_container(event)
    #     if not container:
    #         return
    #
    #     self._write_gatus_config(container)

    def _write_gatus_config(self, container):
        config = self.model.config
        logger.info("Gatus config: %s", config)

        self._alerting_config(container, config)

        # rel = self.model.get_relation("postgresql")
        # logger.info("Gatus postgresql relation: %s", rel)
        # if rel and rel.data.get(rel.app):
        #     path = "${POSTGRESQL_DB_CONNECT_STRING}"
        #     jdbc_parameters = str(config.get("jdbc-parameters", ""))
        #     if len(jdbc_parameters) > 0:
        #         path = f"{path}?{jdbc_parameters}"
        #     gatus_config["storage"] = {
        #         "type": "postgres",
        #         "path": path,
        #     }
        #     # data = rel.data[rel.app]

        # gatus_config["endpoints"] = [
        #     {
        #         "name": "Ubuntu.com",
        #         "group": "Websites",
        #         "url": "https://ubuntu.com",
        #         "interval": "60s",
        #         "conditions": ["[STATUS] == 200", "[RESPONSE_TIME] < 1000"],
        #     },
        # ]
        # container.push("/config/config.yaml", yaml.dump(gatus_config), make_dirs=True)


        # container.push("/config/storage.yaml", yaml.dump(gatus_config), make_dirs=True)
        #
        # # Construct the full Gatus Configuration
        # gatus_config = {}
        # gatus_config["endpoints"] = [
        #     {
        #         "name": "Ubuntu.com",
        #         "group": "Websites",
        #         "url": "https://ubuntu.com",
        #         "interval": "60s",
        #         "conditions": ["[STATUS] == 200", "[RESPONSE_TIME] < 1000"],
        #     },
        # ]
        #
        # container.push("/config/endpoints.yaml", yaml.dump(gatus_config), make_dirs=True)

        # 4. Signal Pebble to restart if the layer/service is managed manually
        # Note: The Go framework extension usually handles the layer + restart automatically
        # based on env vars. Since we updated a file, we might need to force a restart
        # if the framework doesn't detect a layer change.
        try:
            container.restart(SERVICE_NAME)
        except ops.pebble.ChangeError:
            # Service might not be running yet, which is fine
            pass

    def _alerting_config(self, container, config):
        logger.info("Updating alerting config")
        gatus_config = {}

        if "juju-secret" not in config:
            logger.info("No juju-secret in config")
            return

        secret_id = config["juju-secret"]
        if not secret_id:
            logger.info("No juju-secret id in config")
            return

        secret = self.model.get_secret(id=secret_id)
        if not secret:
            logger.info("No secret found")
            return

        content = secret.get_content()
        if "mattermost-webhook-url" not in content:
            logger.info("No mattermost-webhook-url in secret")
            return

        gatus_config["alerting"] = {
            "mattermost": {
                "webhook-url": content["mattermost-webhook-url"],
                "client": {
                    "insecure": True,
                },
            }
        }

        container.push(
            "/config/alerting.yaml",
            yaml.dump(gatus_config),
            make_dirs=True,
        )


if __name__ == "__main__":  # pragma: nocover
    ops.main(GatusCharm)
