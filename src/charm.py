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
        self.framework.observe(self.on.postgresql_relation_changed, self._on_db_relation_changed)
        # self.framework.observe(self.on.gatus_pebble_ready, self._update_config)
        # self.framework.observe(self.on.postgresql_relation_changed, self._update_config)
        # self.framework.observe(self.on.postgresql_relation_departed, self._update_config)

    # OVERRIDE: This method replaces the base class's default behavior
    def _on_pebble_ready(self, event):
        logger.info("_on_pebble_ready")
        container = self.unit.get_container(CONTAINER_NAME)
        if not container.can_connect():
            logger.info("Pebble is not ready yet, deferring config update")
            event.defer()
            return

        # 1. Generate and Push your Config File
        self._write_gatus_config(container)

        # 2. Call the original start logic (so you don't have to rewrite it)
        # This ensures the service starts/restarts correctly after the file is there.
        super()._on_pebble_ready(event)

    # OVERRIDE: This method replaces the base class's default behavior
    def _on_config_changed(self, event):
        logger.info("_on_config_changed")
        container = self.unit.get_container(CONTAINER_NAME)
        if not container.can_connect():
            logger.info("Pebble is not ready yet, deferring config update")
            event.defer()
            return

        # 1. Generate and Push your Config File
        self._write_gatus_config(container)

        # 2. Call the original start logic (so you don't have to rewrite it)
        # This ensures the service starts/restarts correctly after the file is there.
        super()._on_config_changed(event)

    def _on_db_relation_changed(self, event):
        """Update Postgres relation data."""
        logger.info("_on_db_relation_changed triggered")

        container = self.unit.get_container(CONTAINER_NAME)
        if not container.can_connect():
            event.defer()
            return

        # Force a config update now that we know data has changed
        self._write_gatus_config(container)

    def _write_gatus_config(self, container):
        gatus_config = {}

        rel = self.model.get_relation("postgresql")
        logger.info("Gatus relation: %s", rel)
        if rel and rel.data.get(rel.app):
            gatus_config["storage"] = {
                "type": "postgres",
                "path": "${POSTGRESQL_DB_CONNECT_STRING}?sslmode=disable",
            }
            # data = rel.data[rel.app]

        # Construct the full Gatus Configuration
        gatus_config["endpoints"] = [
            {
                "name": "Ubuntu.com",
                "group": "Websites",
                "url": "https://ubuntu.com",
                "interval": "60s",
                "conditions": ["[STATUS] == 200", "[RESPONSE_TIME] < 1000"],
            },
        ]

        container.push("/config/config.yaml", yaml.dump(gatus_config), make_dirs=True)

        # 4. Signal Pebble to restart if the layer/service is managed manually
        # Note: The Go framework extension usually handles the layer + restart automatically
        # based on env vars. Since we updated a file, we might need to force a restart
        # if the framework doesn't detect a layer change.
        try:
            container.restart(SERVICE_NAME)
        except ops.pebble.ChangeError:
            # Service might not be running yet, which is fine
            pass

    # def _on_db_changed(self, event):
    #     # Reuse the logic to write the config and restart
    #     if self.unit.is_leader():
    #          container = self.unit.get_container("app")
    #          if container.can_connect():
    #              self._write_gatus_config(container)
    #              # Force a restart so Gatus picks up the new config
    #              container.restart("app")

    #     # The 'relation_name' comes from the 'charmcraft.yaml file'.
    #     # The 'database_name' is the name of the database that our application requires.
    #     self.database = DatabaseRequires(self, relation_name="postgresql", database_name="gatus-k8s")
    #     # See https://charmhub.io/data-platform-libs/libraries/data_interfaces
    #     self.framework.observe(self.database.on.database_created, self._on_database_created)
    #     self.framework.observe(self.database.on.endpoints_changed, self._on_database_created)
    #
    # def fetch_postgres_relation_data(self) -> dict[str, str]:
    #     """Fetch postgres relation data.
    #
    #     This function retrieves relation data from a postgres database using
    #     the `fetch_relation_data` method of the `database` object. The retrieved data is
    #     then logged for debugging purposes, and any non-empty data is processed to extract
    #     endpoint information, username, and password. This processed data is then returned as
    #     a dictionary. If no data is retrieved, the unit is set to waiting status and
    #     the program exits with a zero status code.
    #     """
    #     relations = self.database.fetch_relation_data()
    #     logger.debug("Got following database data: %s", relations)
    #     for data in relations.values():
    #         if not data:
    #             continue
    #         logger.info("New database endpoint is %s", data["endpoints"])
    #         host, port = data["endpoints"].split(":")
    #         db_data = {
    #             "db_host": host,
    #             "db_port": port,
    #             "db_username": data["username"],
    #             "db_password": data["password"],
    #         }
    #         print(db_data)
    #         return db_data
    #     print(relations)
    #     return {}
    #
    # def get_app_environment(self) -> dict[str, str]:
    #     """Prepare environment variables for the application.
    #
    #     This property method creates a dictionary containing environment variables
    #     for the application. It retrieves the database authentication data by calling
    #     the `fetch_postgres_relation_data` method and uses it to populate the dictionary.
    #     If any of the values are not present, it will be set to None.
    #     The method returns this dictionary as output.
    #     """
    #     db_data = self.fetch_postgres_relation_data()
    #     if not db_data:
    #         return {}
    #     env = {
    #         key: value
    #         for key, value in {
    #             "DEMO_SERVER_DB_HOST": db_data.get("db_host", None),
    #             "DEMO_SERVER_DB_PORT": db_data.get("db_port", None),
    #             "DEMO_SERVER_DB_USER": db_data.get("db_username", None),
    #             "DEMO_SERVER_DB_PASSWORD": db_data.get("db_password", None),
    #         }.items()
    #         if value is not None
    #     }
    #     return env
    #
    # def _update_layer_and_restart(self) -> None:
    #     """Define and start a workload using the Pebble API.
    #
    #     You'll need to specify the right entrypoint and environment
    #     configuration for your specific workload. Tip: you can see the
    #     standard entrypoint of an existing container using docker inspect
    #     Learn more about interacting with Pebble at
    #         https://documentation.ubuntu.com/ops/latest/reference/pebble/
    #     Learn more about Pebble layers at
    #         https://documentation.ubuntu.com/pebble/how-to/use-layers/
    #     """
    #     # Learn more about statuses at
    #     # https://documentation.ubuntu.com/juju/3.6/reference/status/
    #     self.unit.status = ops.MaintenanceStatus("Assembling Pebble layers")
    #     env = self.get_app_environment()
    #     print(env)
    #     try:
    #         # Tell Pebble to incorporate the changes, including restarting the
    #         # service if required.
    #         container = self.unit.get_container(CONTAINER_NAME)
    #         container.replan()
    #         logger.info("Replanned with 'gatus' service")
    #     except (ops.pebble.APIError, ops.pebble.ConnectionError) as e:
    #         logger.info("Unable to connect to Pebble: %s", e)
    #
    # def _on_database_created(self, _: DatabaseCreatedEvent | DatabaseEndpointsChangedEvent) -> None:
    #     """Event is fired when postgres database is created or endpoint is changed."""
    #     self._update_layer_and_restart()
    #
    # def _on_collect_status(self, event: ops.CollectStatusEvent) -> None:
    #     if not self.model.get_relation("database"):
    #         # We need the user to do 'juju integrate'.
    #         event.add_status(ops.BlockedStatus("Waiting for database relation"))
    #     elif not self.database.fetch_relation_data():
    #         # We need the charms to finish integrating.
    #         event.add_status(ops.WaitingStatus("Waiting for database relation"))
    #     # If nothing is wrong, then the status is active.
    #     event.add_status(ops.ActiveStatus())


if __name__ == "__main__":  # pragma: nocover
    ops.main(GatusCharm)
