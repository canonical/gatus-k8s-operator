# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
from datetime import datetime, timezone

import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus
from pydantic import ValidationError

from gatus import GatusConfig
from validator import (
    INVALID_FILTER_BY_MESSAGE,
    INVALID_SORT_BY_MESSAGE,
    GatusValidator,
)

logger = logging.getLogger(__name__)


def test_gatus_config():
    """Test that the GatusConfig class correctly reflects the config.yaml file."""
    with open("tests/data/config.yaml", "r") as f:
        config_string = f.read()

    try:
        config = yaml.safe_load(config_string)
        gatus_config: GatusConfig = GatusConfig.model_validate(config)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse config.yaml: {e}")
        raise
    except ValidationError as e:
        logger.error(f"Failed to validate config.yaml: {e}")
        raise

    assert gatus_config.storage is not None
    assert gatus_config.storage.type == "postgres"
    assert gatus_config.storage.path == "postgresql://postgres:postgres@localhost:5432/gatus"

    assert gatus_config.announcements is not None
    assert len(gatus_config.announcements) > 0
    assert gatus_config.announcements[0].timestamp == datetime(2025, 8, 15, 14, 0, 0, tzinfo=timezone.utc)
    assert gatus_config.announcements[0].type == "outage"
    assert gatus_config.announcements[0].message == "Scheduled maintenance on database servers from 14:00 to 16:00 UTC"

    assert gatus_config.alerting is not None
    assert gatus_config.alerting.mattermost.webhook_url == "http://localhost:8080/hooks/xxx"

    assert gatus_config.endpoints is not None
    assert len(gatus_config.endpoints) > 0
    assert gatus_config.endpoints[0].name == "Ubuntu.com"
    assert gatus_config.endpoints[0].group == "Websites"
    assert gatus_config.endpoints[0].url == "https://ubuntu.com"
    assert gatus_config.endpoints[0].interval == "60s"

    assert gatus_config.endpoints[0].conditions is not None
    assert len(gatus_config.endpoints[0].conditions) > 0
    assert gatus_config.endpoints[0].conditions[0] == "[STATUS] == 200"

    assert gatus_config.endpoints[0].alerts is not None
    assert len(gatus_config.endpoints[0].alerts) > 0
    assert gatus_config.endpoints[0].alerts[0].type == "mattermost"


def test_invalid_announcements():
    """Test that the charm rejects invalid announcements."""
    with open("tests/data/announcements-invalid.yaml", "r") as f:
        config_string = f.read()

    try:
        config = yaml.safe_load(config_string)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse yaml: {e}")
        raise

    with pytest.raises(ValidationError):
        GatusConfig.model_validate(config)


def test_invalid_endpoints():
    """Test that the charm rejects invalid endpoints."""
    with open("tests/data/endpoints-invalid.yaml", "r") as f:
        config_string = f.read()

    try:
        config = yaml.safe_load(config_string)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse yaml: {e}")
        raise

    with pytest.raises(ValidationError):
        GatusConfig.model_validate(config)


@pytest.mark.parametrize(
    "config, expected_status",
    [
        pytest.param(
            {
                "ui-default-sort-by": "name",
                "ui-default-filter-by": "none",
            },
            ActiveStatus(),
            id="Valid config",
        ),
        pytest.param(
            {
                "ui-default-sort-by": "invalid",
                "ui-default-filter-by": "none",
            },
            BlockedStatus(INVALID_SORT_BY_MESSAGE),
            id="Invalid default-sort-by",
        ),
        pytest.param(
            {
                "ui-default-sort-by": "name",
                "ui-default-filter-by": "invalid",
            },
            BlockedStatus(INVALID_FILTER_BY_MESSAGE),
            id="Invalid default-filter-by",
        ),
    ],
)
def test_config(config, expected_status, base_state):
    """Test that the charm rejects invalid ui-default-sort-by."""
    status = GatusValidator.validate(config)

    assert status == expected_status
