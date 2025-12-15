# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import pathlib

import jubilant
import pytest
import requests
import yaml
from pydantic import ValidationError

from constants import FAILED_TO_VALIDATE
from gatus import GatusConfig

logger = logging.getLogger(__name__)

APP_NAME = "gatus-k8s"
PG_APP_NAME = "postgresql-k8s"
SELF_SIGNED_CERT_APP_NAME = "self-signed-certificates"


def test_deploy(charm: pathlib.Path, juju: jubilant.Juju, charm_resources: dict[str, str]):
    """Deploy the charm and check that the application is active.

    This test uses an OCI image from a registry as the charm resource.
    Thus, please ensure the --gatus-image option is set in the pytest command.
    """
    juju.deploy(charm.resolve(), app=APP_NAME, resources=charm_resources)
    juju.wait(jubilant.all_active, timeout=300, delay=10)
    status = juju.status()
    unit = status.apps[APP_NAME].units[APP_NAME + "/0"]
    # Check that the charm hooks are successful
    assert unit.is_active

    # Check that the underlying application is listening on port 8080
    ip = unit.address
    response = requests.get(f"http://{ip}:8080/api/v1/endpoints/statuses", timeout=5)
    logger.info("Response: %s", response.text)
    response.raise_for_status()

    data = response.json()
    logger.info("Data: %s", data)
    # Check if the default endpoint, Ubuntu.com, is in the response
    assert any(endpoint.get("name") == "Ubuntu.com" for endpoint in data)


@pytest.mark.skip(reason="Slow")
def test_db_relation(charm: pathlib.Path, juju: jubilant.Juju, charm_resources: dict[str, str]):
    """Deploy the database charm and check that the gatus charm can connect to it.

    This test uses an OCI image from a registry as the charm resource.
    Thus, please ensure the --gatus-image option is set in the pytest command.
    """
    # Deploy the database charm
    juju.deploy(
        PG_APP_NAME,
        channel="14/stable",
    )
    # Deploy the self-signed-certificates charm
    juju.deploy(
        SELF_SIGNED_CERT_APP_NAME,
        channel="1/stable",
    )
    juju.wait(jubilant.all_active, timeout=600, delay=30)

    # Add the charm relations
    juju.integrate(PG_APP_NAME, SELF_SIGNED_CERT_APP_NAME)
    juju.wait(jubilant.all_active, timeout=300, delay=30)
    juju.integrate(APP_NAME, PG_APP_NAME)
    juju.wait(jubilant.all_active, timeout=300, delay=30)

    # Check that the charms resolve after the relations
    status = juju.status()
    assert status.apps[APP_NAME].units[APP_NAME + "/0"].is_active

    # Get the config of the gatus charm
    config = get_config(juju)
    logger.info("Gatus config:")
    logger.info(config)

    assert config.storage is not None
    assert config.storage.type == "postgres"
    assert "postgresql-k8s-primary" in config.storage.path


def test_mattermost_alerting(juju: jubilant.Juju):
    """Add a secret to the charm and check that the alerting config is updated."""
    # Add a secret to the Juju model
    secreturi = juju.add_secret(
        name="gatus-webhooks",
        content={
            "mattermost-webhook-url": "http://localhost:8080/hooks/xxx",
        },
    )
    assert secreturi is not None
    assert secreturi.startswith("secret:")

    # Grant secret to charm and update the charm config
    juju.grant_secret(
        identifier=secreturi,
        app=APP_NAME,
    )
    secret_id = secreturi[len("secret:") :]
    juju.config(APP_NAME, {"mattermost-alerting": secret_id})
    juju.wait(jubilant.all_active, timeout=300, delay=10)

    # Get the config of the gatus charm
    config = get_config(juju)
    logger.info("Gatus config:")
    logger.info(config)

    assert config.alerting is not None
    assert config.alerting.mattermost is not None
    assert config.alerting.mattermost.webhook_url == "http://localhost:8080/hooks/xxx"

    # Test that the charm reacts to updates to the secret
    juju.update_secret(
        identifier=secreturi,
        content={
            "mattermost-webhook-url": "http://localhost:8080/hooks/yyy",
        },
    )
    juju.wait(jubilant.all_active, timeout=300, delay=10)

    # Get the config of the gatus charm
    config = get_config(juju)
    logger.info("Gatus config:")
    logger.info(config)

    assert config.alerting is not None
    assert config.alerting.mattermost is not None
    assert config.alerting.mattermost.webhook_url == "http://localhost:8080/hooks/yyy"


def test_invalid_endpoints_config(juju: jubilant.Juju):
    """Test that the endpoint config is correctly parsed."""
    with open("tests/data/endpoints-invalid.yaml", "r") as f:
        endpoints_string = f.read()
    juju.config(APP_NAME, {"endpoints": endpoints_string})

    # Wait for the model to settle
    juju.wait(lambda status: jubilant.all_agents_idle(status, APP_NAME), timeout=300, delay=10)

    # Check that the charm is blocked by the invalid config
    status = juju.status()
    workload_status = status.apps[APP_NAME].units[APP_NAME + "/0"].workload_status
    assert workload_status.current == "blocked"
    assert workload_status.message == FAILED_TO_VALIDATE


def test_endpoints_config(juju: jubilant.Juju):
    """Test that the endpoint config is correctly parsed."""
    with open("tests/data/endpoints.yaml", "r") as f:
        endpoints_string = f.read()

    juju.config(APP_NAME, {"endpoints": endpoints_string})
    juju.wait(jubilant.all_active, timeout=300, delay=10)

    # Get the config of the gatus charm
    config = get_config(juju)
    logger.info("Gatus config:")
    logger.info(config)

    assert config.endpoints is not None
    assert len(config.endpoints) > 0
    assert config.endpoints[0].name == "GitHub"
    assert config.endpoints[0].group == "Websites"
    assert config.endpoints[0].url == "https://github.com"

    status = juju.status()
    unit = status.apps[APP_NAME].units[APP_NAME + "/0"]
    # Check that the charm hooks are successful
    assert unit.is_active

    # Check that the underlying application is listening on port 8080
    ip = unit.address
    response = requests.get(f"http://{ip}:8080/api/v1/endpoints/statuses", timeout=5)
    logger.info("Response: %s", response.text)
    response.raise_for_status()

    data = response.json()
    logger.info("Data: %s", data)
    # Check if the configured endpoint, GitHub, is in the response
    assert any(endpoint.get("name") == "GitHub" for endpoint in data)


def test_invalid_announcements_config(juju: jubilant.Juju):
    """Test that the endpoint config is correctly parsed."""
    with open("tests/data/announcements-invalid.yaml", "r") as f:
        announcements_string = f.read()
    juju.config(APP_NAME, {"announcements": announcements_string})

    # Wait for the model to settle
    juju.wait(lambda status: jubilant.all_agents_idle(status, APP_NAME), timeout=300, delay=10)

    # Check that the charm is blocked by the invalid config
    status = juju.status()
    workload_status = status.apps[APP_NAME].units[APP_NAME + "/0"].workload_status
    assert workload_status.current == "blocked"
    assert workload_status.message == FAILED_TO_VALIDATE


def test_announcements_config(juju: jubilant.Juju):
    """Test that the announcements config is correctly parsed."""
    with open("tests/data/announcements.yaml", "r") as f:
        announcements_string = f.read()

    juju.config(APP_NAME, {"announcements": announcements_string})
    juju.wait(jubilant.all_active, timeout=300, delay=10)

    # Get the config of the gatus charm
    config = get_config(juju)
    logger.info("Gatus config:")
    logger.info(config)

    assert config.announcements is not None
    assert len(config.announcements) > 0
    assert config.announcements[0].type == "outage"
    assert config.announcements[0].message == "Scheduled maintenance on database servers from 14:00 to 16:00 UTC"

    # Gatus doesn't show announcements in an API, so we cannot test it further for now.


def get_config(juju: jubilant.Juju) -> GatusConfig:
    """Get the config of a charmed application."""
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
        return gatus_config
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse yaml: {e}")
        raise
    except ValidationError as e:
        logger.error(f"Failed to validate yaml: {e}")
        raise
