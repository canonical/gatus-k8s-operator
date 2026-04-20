# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import sys
import types
from datetime import datetime, timezone
from importlib import import_module
from unittest.mock import patch

import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus
from pydantic import ValidationError

from constants import (
    INVALID_FILTER_BY_MESSAGE,
    INVALID_SORT_BY_MESSAGE,
    OIDC_INCOMPLETE_CONFIG_MESSAGE,
    OIDC_INVALID_REDIRECT_URL_MESSAGE,
)
from gatus import GatusConfig
from validator import GatusValidator

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
            id="Valid default config",
        ),
        pytest.param(
            {
                "ui-default-sort-by": "group",
                "ui-default-filter-by": "failing",
            },
            ActiveStatus(),
            id="Valid modified config",
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
        pytest.param(
            {
                "ui-default-sort-by": "name",
                "ui-default-filter-by": "none",
                "oidc-issuer-url": "https://issuer.example.com",
                "oidc-redirect-url": "https://gatus.example.com/authorization-code/callback",
                "oidc-credentials": "secret:oidc-credentials",
            },
            ActiveStatus(),
            id="Valid OIDC config",
        ),
        pytest.param(
            {
                "ui-default-sort-by": "name",
                "ui-default-filter-by": "none",
                "oidc-issuer-url": "https://issuer.example.com",
                "oidc-redirect-url": "https://gatus.example.com/authorization-code/callback",
            },
            BlockedStatus(OIDC_INCOMPLETE_CONFIG_MESSAGE),
            id="Incomplete OIDC config",
        ),
        pytest.param(
            {
                "ui-default-sort-by": "name",
                "ui-default-filter-by": "none",
                "oidc-scopes": "openid,email",
            },
            BlockedStatus(OIDC_INCOMPLETE_CONFIG_MESSAGE),
            id="OIDC optional field set without required fields",
        ),
        pytest.param(
            {
                "ui-default-sort-by": "name",
                "ui-default-filter-by": "none",
                "oidc-issuer-url": "https://issuer.example.com",
                "oidc-redirect-url": "https://gatus.example.com/callback",
                "oidc-credentials": "secret:oidc-credentials",
            },
            BlockedStatus(OIDC_INVALID_REDIRECT_URL_MESSAGE),
            id="Invalid OIDC redirect URL",
        ),
    ],
)
def test_ui_config_validation(config, expected_status):
    """Test that the charm rejects invalid ui config options."""
    status = GatusValidator.validate(config)

    assert status == expected_status


def test_update_env_includes_oidc_vars():
    """Test that OIDC values are propagated to the workload environment."""
    paas_charm_module = types.ModuleType("paas_charm")
    paas_charm_go_module = types.ModuleType("paas_charm.go")
    setattr(paas_charm_go_module, "Charm", type("DummyCharm", (), {}))
    setattr(paas_charm_module, "go", paas_charm_go_module)

    class FakeContainer:
        def __init__(self):
            self.layer = {}

        def add_layer(self, _: str, layer, combine: bool = False):
            self.layer = layer

        def replan(self):
            return

    class FakeCharm:
        def __init__(self):
            self.model = types.SimpleNamespace(
                config={
                    "oidc-issuer-url": "https://accounts.google.com",
                    "oidc-redirect-url": "https://gatus.example.com/authorization-code/callback",
                    "oidc-scopes": "openid,email,profile",
                    "oidc-allowed-subjects": "alice@example.com,bob@example.com",
                    "log-level": "info",
                }
            )

        def _get_juju_secret(self, config_name: str, secret_key: str):
            return {
                ("oidc-credentials", "oidc-client-id"): "oidc-client-id-value",
                ("oidc-credentials", "oidc-client-secret"): "oidc-client-secret-value",
            }.get((config_name, secret_key))

    with patch.dict(
        sys.modules,
        {
            "paas_charm": paas_charm_module,
            "paas_charm.go": paas_charm_go_module,
        },
    ):
        if "charm" in sys.modules:
            del sys.modules["charm"]
        charm_module = import_module("charm")

    fake_charm = FakeCharm()
    fake_container = FakeContainer()
    charm_module.GatusCharm._update_env(fake_charm, fake_container)

    env = fake_container.layer["services"]["go"]["environment"]
    assert env["OIDC_ISSUER_URL"] == "https://accounts.google.com"
    assert env["OIDC_REDIRECT_URL"] == "https://gatus.example.com/authorization-code/callback"
    assert env["OIDC_CLIENT_ID"] == "oidc-client-id-value"
    assert env["OIDC_CLIENT_SECRET"] == "oidc-client-secret-value"
    assert env["OIDC_SCOPES"] == "openid,email,profile"
    assert env["OIDC_ALLOWED_SUBJECTS"] == "alice@example.com,bob@example.com"
