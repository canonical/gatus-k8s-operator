# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import pathlib

import jubilant
import requests

from constants import FAILED_TO_UPDATE_ENVIRONMENT, FAILED_TO_VALIDATE
from tests.integration.helper import get_config

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
    assert workload_status.message == FAILED_TO_UPDATE_ENVIRONMENT


def test_endpoints_config(deployed_charm: pathlib.Path, juju: jubilant.Juju):
    """Test that the endpoint config is correctly parsed."""
    with open("tests/data/endpoints.yaml", "r") as f:
        endpoints_string = f.read()

    juju.config(APP_NAME, {"endpoints": endpoints_string})
    juju.wait(jubilant.all_active, timeout=300, delay=10)

    # Get the config of the gatus charm
    config = get_config(juju)

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


def test_announcements_config(deployed_charm: pathlib.Path, juju: jubilant.Juju):
    """Test that the announcements config is correctly parsed."""
    with open("tests/data/announcements.yaml", "r") as f:
        announcements_string = f.read()

    juju.config(APP_NAME, {"announcements": announcements_string})
    juju.wait(jubilant.all_active, timeout=300, delay=10)

    # Get the config of the gatus charm
    config = get_config(juju)

    assert config.announcements is not None
    assert len(config.announcements) > 0
    assert config.announcements[0].type == "outage"
    assert config.announcements[0].message == "Scheduled maintenance on database servers from 14:00 to 16:00 UTC"

    # Gatus doesn't show announcements in an API, so we cannot test it further for now.


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
    assert workload_status.message in (FAILED_TO_VALIDATE, FAILED_TO_UPDATE_ENVIRONMENT)
