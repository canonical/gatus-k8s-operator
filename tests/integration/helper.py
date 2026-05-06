# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging

import jubilant
import yaml
from pydantic import ValidationError

from gatus import GatusConfig

logger = logging.getLogger(__name__)

APP_NAME = "gatus-k8s"
PG_APP_NAME = "postgresql-k8s"
SELF_SIGNED_CERT_APP_NAME = "self-signed-certificates"


def get_config(juju: jubilant.Juju) -> GatusConfig:
    """Get the config of a charmed application."""
    pebble_plan = juju.ssh(
        target=APP_NAME + "/0",
        container="app",
        command="pebble plan",
    )
    logger.info("Pebble plan: %s", pebble_plan)

    config_files = juju.ssh(
        target=APP_NAME + "/0",
        container="app",
        command="ls /config",
    )
    logger.info("Config files in container: %s", config_files)

    configs = []
    config_files = [
        "storage",
        "alerting",
        "announcements",
        "endpoints",
    ]
    # Retrieve the config files from the container
    for config_file in config_files:
        config_path = f"/config/{config_file}.yaml"
        try:
            config_string = juju.ssh(
                target=APP_NAME + "/0",
                container="app",
                command=f"cat {config_path}",
            )
            logger.info("%s config: %s", config_file, config_string)
            configs.append(config_string)
        except jubilant.CLIError:
            # Skip the config if it doesn't exist
            logger.info("%s config not found", config_file)

    config_string = "\n".join(configs)

    try:
        config = yaml.safe_load(config_string)
        gatus_config: GatusConfig = GatusConfig.model_validate(config)

        logger.info("Gatus application config:")
        logger.info(config)

        return gatus_config
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse yaml: {e}")
        raise
    except ValidationError as e:
        logger.error(f"Failed to validate yaml: {e}")
        raise
