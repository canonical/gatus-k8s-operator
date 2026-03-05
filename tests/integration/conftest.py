# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import os
import pathlib
import sys
import time

import jubilant
import pytest
from pytest import FixtureRequest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def juju(request: FixtureRequest):
    """Create a temporary Juju model for running tests."""
    with jubilant.temp_model() as juju:
        yield juju

        if request.session.testsfailed:
            logger.info("Collecting Juju logs...")
            time.sleep(0.5)  # Wait for Juju to process logs.
            log = juju.debug_log(limit=1000)
            logger.error("Juju debug log:")
            for line in log.splitlines():
                logger.error(line)
            sys.exit(1)


@pytest.fixture(scope="session")
def charm():
    """Return the path of the charm under test."""
    # charm_path = request.config.getoption("--charm-path")

    if "CHARM_PATH" in os.environ:
        charm_path = pathlib.Path(os.environ["CHARM_PATH"])
        if not charm_path.exists():
            raise FileNotFoundError(f"Charm does not exist: {charm_path}")
        return charm_path
    # Modify below if you're building for multiple bases or architectures.
    charm_paths = list(pathlib.Path(".").glob("*.charm"))
    if not charm_paths:
        raise FileNotFoundError("No .charm file in current directory")
    if len(charm_paths) > 1:
        path_list = ", ".join(str(path) for path in charm_paths)
        raise ValueError(f"More than one .charm file in current directory: {path_list}")
    return charm_paths[0]


@pytest.fixture(scope="session")
def charm_resources(request: FixtureRequest) -> dict[str, str]:
    """Prepare the OCI resources for the charm, read from option or env vars."""
    gatus_image = request.config.getoption("--gatus-image")
    if gatus_image:
        return {
            "app-image": gatus_image,
        }

    resource_name = os.environ.get("OCI_RESOURCE_NAME")
    rock_image_uri = os.environ.get("ROCK_IMAGE")

    if not resource_name or not rock_image_uri:
        pytest.fail(
            "Environment variables OCI_RESOURCE_NAME and/or ROCK_IMAGE are not set. "
            "Please set '--gatus-image' or run tests via 'make integration-test'."
        )

    return {resource_name: rock_image_uri}
