"""Gatus K8s operator charm fixtures."""

import pytest
from ops import testing

from charm import CONTAINER_NAME


@pytest.fixture(name="base_state")
def base_state_fixture(gatus_container):
    input_state = {
        "leader": True,
        "config": {},
        "containers": {gatus_container},
    }
    yield input_state


@pytest.fixture(name="gatus_container")
def gatus_container_fixture():
    """Gatus container fixture."""
    yield testing.Container(
        name=CONTAINER_NAME,
        can_connect=True,
    )  # type: ignore[call-arg]
