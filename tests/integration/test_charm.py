# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import pathlib
from typing import NamedTuple

import jubilant
import pytest
import yaml

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(pathlib.Path("charmcraft.yaml").read_text())


class App(NamedTuple):
    """Holds deployed application information for app_fixture."""

    name: str


def test_deploy(charm: pathlib.Path, juju: jubilant.Juju, charm_resources: dict[str, str]):
    """Deploy the charm under test."""
    # TODO: How to deploy the charm with the built rock?
    juju.deploy(charm.resolve(), app="gatus", resources=charm_resources)
    juju.wait(jubilant.all_active)


# @pytest.mark.abort_on_fail
# def test_active(juju: jubilant.Juju):
#     """Check that the charm is active.
#
#     Assume that the charm has already been built and is running.
#     """
#     status = juju.status()
#     print(status)
#     assert False
#     # assert status.apps["gatus"].units["gatus" + "/0"].is_active

