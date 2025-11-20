# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import pathlib
from typing import NamedTuple

import jubilant
import yaml

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(pathlib.Path("charmcraft.yaml").read_text())


class App(NamedTuple):
    """Holds deployed application information for app_fixture."""

    name: str


def test_deploy(charm: pathlib.Path, juju: jubilant.Juju, charm_resources: dict[str, str]):
    """Deploy the charm and check that the application is active.

    This test uses an OCI image from a registry as the charm resource.
    Thus, please ensure the --gatus-image option is set in the pytest command.
    """
    juju.deploy(charm.resolve(), app="gatus", resources=charm_resources)
    juju.wait(jubilant.all_active)
    status = juju.status()
    assert status.apps["gatus"].units["gatus" + "/0"].is_active
