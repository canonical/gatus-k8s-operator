# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, ConfigData
from pydantic import ValidationError

from charm import GatusCharm
from constants import (
    FAILED_TO_VALIDATE,
    INVALID_FILTER_BY_MESSAGE,
    INVALID_SORT_BY_MESSAGE,
    SERVICE_NAME,
    WEBHOOK_URL_PLACEHOLDER_RE,
)
from exceptions import BlockedStatusError
from gatus import EndpointAlert, GatusConfig, ProviderOverride
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
    ],
)
def test_ui_config_validation(config, expected_status):
    """Test that the charm rejects invalid ui config options."""
    status = GatusValidator.validate(config)

    assert status == expected_status


def test_provider_override_parsed_from_yaml():
    """Test that EndpointAlert.provider_override is parsed correctly from YAML."""
    with open("tests/data/endpoints-with-provider-override.yaml", "r") as f:
        config_string = f.read()

    config = yaml.safe_load(config_string)
    gatus_config = GatusConfig.model_validate(config)

    assert gatus_config.endpoints is not None
    assert len(gatus_config.endpoints) > 0
    endpoint = gatus_config.endpoints[0]
    assert endpoint.alerts is not None
    assert len(endpoint.alerts) > 0
    alert = endpoint.alerts[0]
    assert alert.provider_override is not None
    assert alert.provider_override.webhook_url == "[webhook-url:channel-1]"


def test_endpoint_alert_without_provider_override():
    """Test that EndpointAlert without provider-override parses correctly."""
    alert_data = {"type": "mattermost", "description": "Test alert"}
    alert = EndpointAlert.model_validate(alert_data)
    assert alert.type == "mattermost"
    assert alert.provider_override is None


def test_provider_override_model():
    """Test the ProviderOverride model."""
    override = ProviderOverride.model_validate({"webhook-url": "https://example.com/hook"})
    assert override.webhook_url == "https://example.com/hook"

    empty_override = ProviderOverride()
    assert empty_override.webhook_url is None


def test_resolve_secret_placeholders_substitutes_known_keys():
    """Test that _resolve_secret_placeholders correctly substitutes known keys."""
    raw_yaml = "webhook-url: '[webhook-url:trino]'"
    secret_content = {"trino": "https://chat.example.com/hooks/abc123"}

    def replacer(match):
        key = match.group(1)
        return secret_content[key]

    resolved = WEBHOOK_URL_PLACEHOLDER_RE.sub(replacer, raw_yaml)
    assert resolved == "webhook-url: 'https://chat.example.com/hooks/abc123'"


def test_resolve_secret_placeholders_multiple_keys():
    """Test that _resolve_secret_placeholders substitutes multiple placeholders."""
    raw_yaml = "webhook-url: '[webhook-url:default]'\nprovider-override:\n  webhook-url: '[webhook-url:trino]'"
    secret_content = {
        "default": "https://chat.example.com/hooks/default",
        "trino": "https://chat.example.com/hooks/trino",
    }

    def replacer(match):
        key = match.group(1)
        return secret_content[key]

    resolved = WEBHOOK_URL_PLACEHOLDER_RE.sub(replacer, raw_yaml)
    assert "https://chat.example.com/hooks/default" in resolved
    assert "https://chat.example.com/hooks/trino" in resolved
    assert "[webhook-url:" not in resolved


def test_update_env_resolves_endpoint_placeholders_into_container_env():
    """Test that _update_env resolves placeholders and injects the resolved endpoints."""
    with open("tests/data/endpoints-with-provider-override.yaml", "r") as f:
        endpoints = f.read()
    charm = SimpleNamespace(
        model=SimpleNamespace(
            config=cast(
                ConfigData,
                {
                    "ui-default-sort-by": "name",
                    "ui-default-filter-by": "none",
                    "log-level": "info",
                    "endpoints": endpoints,
                },
            )
        ),
        unit=SimpleNamespace(status=ActiveStatus()),
    )
    charm._get_default_webhook_url = Mock(return_value="https://chat.example.com/hooks/default")
    charm._get_endpoints = Mock(
        return_value=endpoints.replace("[webhook-url:channel-1]", "https://chat.example.com/hooks/trino")
    )

    container = Mock()

    GatusCharm._update_env(cast(GatusCharm, charm), container)

    layer = container.add_layer.call_args.args[1]
    env = layer["services"][SERVICE_NAME]["environment"]
    assert env["MATTERMOST_WEBHOOK_URL"] == "https://chat.example.com/hooks/default"
    assert env["APP_ENDPOINTS"] == endpoints.replace("[webhook-url:channel-1]", "https://chat.example.com/hooks/trino")
    assert env["GATUS_LOG_LEVEL"] == "INFO"
    container.replan.assert_called_once_with()


def test_update_env_blocks_when_placeholder_key_missing_from_secret():
    """Test that _update_env blocks when an endpoint references a missing secret key."""
    with open("tests/data/endpoints-with-provider-override.yaml", "r") as f:
        endpoints = f.read()

    charm = SimpleNamespace(
        model=SimpleNamespace(
            config=cast(
                ConfigData,
                {
                    "ui-default-sort-by": "name",
                    "ui-default-filter-by": "none",
                    "log-level": "info",
                    "endpoints": endpoints,
                },
            )
        ),
        unit=SimpleNamespace(status=ActiveStatus()),
    )
    charm._get_default_webhook_url = Mock(return_value="https://chat.example.com/hooks/default")
    charm._get_endpoints = Mock(
        side_effect=BlockedStatusError("Failed to resolve secret placeholders in endpoints config.")
    )

    container = Mock()

    with pytest.raises(BlockedStatusError) as exc_info:
        GatusCharm._update_env(cast(GatusCharm, charm), container)

    assert str(exc_info.value) == "Failed to resolve secret placeholders in endpoints config."
    container.add_layer.assert_not_called()
    container.replan.assert_not_called()


def test_validator_skips_endpoints_with_placeholders():
    """Test that validation is skipped for endpoints YAML containing [webhook-url:...] placeholders."""
    with open("tests/data/endpoints-with-provider-override.yaml", "r") as f:
        endpoints = f.read()
    config = cast(
        ConfigData,
        {
            "ui-default-sort-by": "name",
            "ui-default-filter-by": "none",
            "endpoints": endpoints,
        },
    )

    status = GatusValidator.validate(config)
    assert status == ActiveStatus()


def test_validator_does_not_skip_announcements_with_placeholder_literal():
    """Test that announcements validation is not skipped by placeholder-like message text."""
    config = cast(
        ConfigData,
        {
            "ui-default-sort-by": "name",
            "ui-default-filter-by": "none",
            "announcements": (
                "announcements:\n"
                "  - timestamp: 2026-01-08T06:00:00Z\n"
                "    type: information\n"
                "    message: '[webhook-url:channel-1]'\n"
            ),
        },
    )

    status = GatusValidator.validate(config)
    assert status == ActiveStatus()


def test_validator_validates_resolved_endpoints():
    """Test that validation uses resolved_endpoints when provided."""
    with open("tests/data/endpoints-with-provider-override.yaml", "r") as f:
        raw_endpoints = f.read()
    with open("tests/data/endpoints-with-resolved-override.yaml", "r") as f:
        resolved_endpoints = f.read()
    config = cast(
        ConfigData,
        {
            "ui-default-sort-by": "name",
            "ui-default-filter-by": "none",
            "endpoints": raw_endpoints,
        },
    )

    status = GatusValidator.validate(config, endpoints=resolved_endpoints)
    assert status == ActiveStatus()


def test_validator_blocks_on_invalid_resolved_endpoints():
    """Test that validation fails on invalid resolved endpoints."""
    resolved_endpoints = (
        "endpoints:\n"
        "  - name: Trino\n"
        # Missing required 'url' field to trigger Pydantic validation error
        "    alerts:\n"
        "      - type: mattermost\n"
        "        description: Trino is down\n"
    )
    config = cast(
        ConfigData,
        {
            "ui-default-sort-by": "name",
            "ui-default-filter-by": "none",
            "endpoints": "some raw endpoints with [webhook-url:trino]",
        },
    )

    status = GatusValidator.validate(config, endpoints=resolved_endpoints)
    assert isinstance(status, BlockedStatus)
    assert status.message == FAILED_TO_VALIDATE
