# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import pathlib

import jubilant
import yaml
from pydantic import ValidationError

from gatus import GatusConfig

logger = logging.getLogger(__name__)

APP_NAME = "gatus-k8s"
PG_APP_NAME = "postgresql-k8s"


def test_deploy(charm: pathlib.Path, juju: jubilant.Juju, charm_resources: dict[str, str]):
    """Deploy the charm and check that the application is active.

    This test uses an OCI image from a registry as the charm resource.
    Thus, please ensure the --gatus-image option is set in the pytest command.
    """
    juju.deploy(charm.resolve(), app=APP_NAME, resources=charm_resources)
    juju.wait(jubilant.all_active, timeout=600)
    status = juju.status()
    assert status.apps[APP_NAME].units[APP_NAME + "/0"].is_active


def test_db_relation(charm: pathlib.Path, juju: jubilant.Juju, charm_resources: dict[str, str]):
    """Deploy the database charm and check that the gatus charm can connect to it.

    This test uses an OCI image from a registry as the charm resource.
    Thus, please ensure the --gatus-image option is set in the pytest command.
    """
    # Deploy the database charm
    juju.deploy(
        PG_APP_NAME,
        channel="14/stable",
        config={"profile": "testing"},
    )
    juju.wait(lambda status: status.apps[PG_APP_NAME].is_active, timeout=20 * 60)

    # Deploy the gatus charm
    # It should be able to start without the database relation
    # TODO: this carries over from the previous test?
    # juju.deploy(charm.resolve(), app=APP_NAME, resources=charm_resources)
    # juju.wait(jubilant.all_active, timeout=600)
    # status = juju.status()
    # assert status.apps[APP_NAME].units[APP_NAME + "/0"].is_active
    # assert status.apps[APP_NAME].units[APP_NAME + "/0"].workload_status == "active"

    # Configure the charm with JDBC parameters for PostgreSQL connection
    juju.config(APP_NAME, {"jdbc-parameters": "sslmode=disable"})
    # Add the database relation
    juju.integrate(PG_APP_NAME, APP_NAME)
    juju.wait(jubilant.all_active, timeout=600)

    # Check that the charm resolves after the database relation
    status = juju.status()
    print(status.apps[APP_NAME].units[APP_NAME + "/0"].workload_status)
    # assert status.apps[APP_NAME].units[APP_NAME + "/0"].is_active
    # assert status.apps[APP_NAME].units[APP_NAME + "/0"].workload_status == "active"

    # Get the config of the gatus charm
    config = get_config(juju, APP_NAME)

    assert config.storage is not None
    assert config.storage.type == "postgres"
    assert "${POSTGRESQL_DB_CONNECT_STRING}" in config.storage.path


def get_config(juju: jubilant.Juju, app_name: str) -> GatusConfig:
    """Get the config of a charmed application."""
    config_string = juju.ssh(
        target=APP_NAME + "/0",
        container="app",
        command="cat /config/config.yaml",
    )

    try:
        config = yaml.safe_load(config_string)
        gatus_config: GatusConfig = GatusConfig.model_validate(config)
        return gatus_config
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse config.yaml: {e}")
        raise
    except ValidationError as e:
        logger.error(f"Failed to validate config.yaml: {e}")
        raise
