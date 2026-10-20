# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

import ops
import paas_charm.go
import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, ConfigData, ModelError, SecretNotFoundError
from ops.testing import Harness
from pydantic import ValidationError

from charm import GatusCharm
from constants import (
    FAILED_TO_VALIDATE,
    INVALID_FILTER_BY_MESSAGE,
    INVALID_SORT_BY_MESSAGE,
    WEBHOOK_URL_PLACEHOLDER_RE,
)
from database_monitors import build_database_monitors
from exceptions import SecretAccessPendingError
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


def test_postgresql_relations_have_distinct_requirers(tmp_path):
    charmcraft = yaml.safe_load((Path(__file__).parents[2] / "charmcraft.yaml").read_text())
    charmcraft["peers"] = {"secret-storage": {"interface": "secret-storage"}}
    charmcraft["containers"] = {"app": {}}
    charmcraft["requires"].update(
        {
            "ingress": {"interface": "ingress", "optional": True},
            "logging": {"interface": "loki_push_api", "optional": True},
        }
    )
    charmcraft["provides"] = {
        "metrics-endpoint": {"interface": "prometheus_scrape"},
        "grafana-dashboard": {"interface": "grafana_dashboard"},
    }
    actions = {"rotate-secret-key": {"description": "Rotate secret key", "params": {}}}
    harness = Harness(
        GatusCharm,
        meta=yaml.safe_dump(charmcraft),
        config=yaml.safe_dump(charmcraft["config"]),
        actions=yaml.safe_dump(actions),
    )

    try:
        with patch.object(GatusCharm, "build_cos_dir", return_value=tmp_path):
            harness.begin()
        charm = harness.charm

        assert list(charm._database_requirers) == ["postgresql"]
        assert charm._monitor_database_requirer.relation_name == "postgresql_monitor"
        assert "postgresql_monitor" in charm.framework.meta.requires
    finally:
        harness.cleanup()


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


def test_get_juju_secret_content_raises_pending_when_secret_not_found():
    """Test that missing Juju secrets are treated as pending to survive grant propagation lag."""
    charm = SimpleNamespace(
        model=SimpleNamespace(
            config={"mattermost-alerting": "secret:123"},
            get_secret=Mock(side_effect=SecretNotFoundError("secret:123")),
        )
    )

    with pytest.raises(SecretAccessPendingError, match="Waiting for Juju secret 'secret:123' to become available"):
        GatusCharm._get_juju_secret_content(cast(GatusCharm, charm), "mattermost-alerting")


def test_get_juju_secret_content_raises_pending_when_secret_access_denied():
    """Test that temporary Juju secret permission failures are retried instead of dropped."""
    secret = Mock()
    secret.get_content.side_effect = ModelError("permission denied")
    charm = SimpleNamespace(
        model=SimpleNamespace(
            config={"mattermost-alerting": "secret:123"},
            get_secret=Mock(return_value=secret),
        )
    )

    with pytest.raises(
        SecretAccessPendingError, match="Waiting for access to Juju secret 'secret:123': permission denied"
    ):
        GatusCharm._get_juju_secret_content(cast(GatusCharm, charm), "mattermost-alerting")


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


def test_create_app_injects_mattermost_webhook_url():
    """Test that _create_app wraps gen_environment to inject the Mattermost webhook URL."""
    original_gen_env = Mock(return_value={"EXISTING_VAR": "value"})
    mock_app = Mock()
    mock_app.gen_environment = original_gen_env

    mock_charm = Mock(spec=GatusCharm)
    mock_charm.model = SimpleNamespace(
        config={
            "log-level": "info",
            "mattermost-alerting": "secret:123",
            "endpoints": "endpoints:\n  - name: Test",
        },
        get_secret=Mock(
            return_value=Mock(get_content=Mock(return_value={"default": "https://chat.example.com/hooks/abc123"}))
        ),
    )
    mock_charm._get_juju_secret_content = lambda config_name: (
        "https://chat.example.com/hooks/abc123" if config_name == "mattermost-alerting" else None
    )
    mock_charm._default_webhook_url = "https://chat.example.com/hooks/abc123"
    mock_charm._get_endpoints = lambda: "endpoints:\n  - name: Test"
    mock_charm._database_monitor_targets = lambda: ([], [])

    with patch.object(paas_charm.go.Charm, "_create_app", return_value=mock_app):
        # Call the actual method on the mock charm
        wrapped_app = GatusCharm._create_app(mock_charm)
        env = wrapped_app.gen_environment()

        assert env["MATTERMOST_WEBHOOK_URL"] == "https://chat.example.com/hooks/abc123"
        assert env["EXISTING_VAR"] == "value"


def test_create_app_injects_endpoints_config():
    """Test that _create_app injects the endpoints config into environment."""
    endpoints_yaml = "endpoints:\n  - name: Test\n    url: http://example.com"

    mock_app = Mock()
    mock_app.gen_environment = Mock(return_value={})

    mock_charm = Mock(spec=GatusCharm)
    mock_charm.model = SimpleNamespace(
        config={
            "log-level": "debug",
            "endpoints": endpoints_yaml,
        },
        get_secret=Mock(return_value=None),
    )
    mock_charm._get_endpoints = lambda: endpoints_yaml
    mock_charm._default_webhook_url = None
    mock_charm._database_monitor_targets = lambda: ([], [])

    with patch.object(paas_charm.go.Charm, "_create_app", return_value=mock_app):
        wrapped_app = GatusCharm._create_app(mock_charm)
        env = wrapped_app.gen_environment()

        assert env["APP_ENDPOINTS"] == endpoints_yaml
        assert env["GATUS_LOG_LEVEL"] == "DEBUG"


def test_create_app_injects_log_level():
    """Test that _create_app injects valid log level into environment."""
    mock_app = Mock()
    mock_app.gen_environment = Mock(return_value={})

    mock_charm = Mock(spec=GatusCharm)
    mock_charm.model = SimpleNamespace(
        config={
            "log-level": "error",
            "endpoints": "",
        },
        get_secret=Mock(return_value=None),
    )
    mock_charm._get_endpoints = lambda: ""
    mock_charm._default_webhook_url = None
    mock_charm._database_monitor_targets = lambda: ([], [])

    with patch.object(paas_charm.go.Charm, "_create_app", return_value=mock_app):
        wrapped_app = GatusCharm._create_app(mock_charm)
        env = wrapped_app.gen_environment()

        assert env["GATUS_LOG_LEVEL"] == "ERROR"


def test_database_monitor_targets_use_primary_and_replica_endpoints():
    relation = {
        "database": "gatus",
        "endpoints": "10.146.72.61:5432",
        "read-only-endpoints": "10.146.72.55:5432,10.146.72.59:5432",
        "username": "gatus-user",
        "password": "hidden-password",  # nosec B105
    }
    database = Mock()
    database.fetch_relation_data.return_value = {32: relation}
    charm = SimpleNamespace(
        _monitor_database_requirer=database,
        _broken_monitor_relation_ids=set(),
        model=SimpleNamespace(
            relations={
                "postgresql": [],
                "postgresql_monitor": [SimpleNamespace(id=32, app=None)],
            }
        ),
        app=SimpleNamespace(name="gatus"),
    )

    monitors, probe_targets = GatusCharm._database_monitor_targets(cast(GatusCharm, charm))

    assert len(monitors) == 3
    assert [target["host"] for target in probe_targets] == [
        "10.146.72.61",
        "10.146.72.55",
        "10.146.72.59",
    ]
    assert [target["is_primary"] for target in probe_targets] == [True, False, False]
    assert all(target["password"] == "hidden-password" for target in probe_targets)
    assert "hidden-password" not in json.dumps(monitors)


def test_database_monitor_builder_validates_ports_and_formats_ipv6():
    relation = {
        "endpoints": "[2001:db8::61]:5432,10.146.72.62:70000",
        "read-only-endpoints": "",
        "username": "gatus-user",
        "password": "hidden-password",  # nosec B105
    }

    monitors, targets = build_database_monitors(relation, "gatus")

    assert monitors == [
        {
            "id": "0",
            "name": "gatus Primary ([2001:db8::61]:5432)",
            "is_primary": True,
        }
    ]
    assert targets[0]["host"] == "2001:db8::61"
    assert targets[0]["port"] == 5432
    assert "hidden-password" not in json.dumps(monitors)


def test_database_monitor_targets_refresh_when_relation_changes_or_is_removed():
    database = Mock()
    database.fetch_relation_data.return_value = {
        32: {
            "database": "gatus",
            "endpoints": "10.146.72.61:5432",
            "read-only-endpoints": "10.146.72.55:5432",
            "username": "gatus-user",
            "password": "hidden-password",  # nosec B105
        }
    }
    charm = SimpleNamespace(
        _monitor_database_requirer=database,
        _broken_monitor_relation_ids=set(),
        model=SimpleNamespace(
            relations={
                "postgresql": [],
                "postgresql_monitor": [SimpleNamespace(id=32, app=None)],
            }
        ),
        app=SimpleNamespace(name="gatus"),
    )

    first_monitors, _ = GatusCharm._database_monitor_targets(cast(GatusCharm, charm))
    database.fetch_relation_data.return_value = {
        33: {
            "database": "gatus",
            "endpoints": "10.146.72.62:5432",
            "read-only-endpoints": "10.146.72.56:5432",
            "username": "gatus-user",
            "password": "hidden-password",  # nosec B105
        }
    }
    charm.model.relations["postgresql_monitor"] = [SimpleNamespace(id=33, app=None)]
    updated_monitors, _ = GatusCharm._database_monitor_targets(cast(GatusCharm, charm))
    database.fetch_relation_data.return_value = {}
    charm.model.relations["postgresql_monitor"] = []
    removed_monitors, removed_targets = GatusCharm._database_monitor_targets(cast(GatusCharm, charm))

    assert "10.146.72.61" in str(first_monitors[0]["name"])
    assert str(first_monitors[0]["name"]) == "gatus Primary (10.146.72.61:5432)"
    assert "10.146.72.62" in str(updated_monitors[0]["name"])
    assert removed_monitors == []
    assert removed_targets == []


def test_database_monitor_targets_include_each_external_relation_with_unique_ids():
    monitor_database = Mock()
    relation_data = {
        41: {
            "database": "payments",
            "endpoints": "10.0.0.1:5432",
            "read-only-endpoints": "10.0.0.2:5432,10.0.0.3:5432",
            "username": "payments-user",
            "password": "payments-password",  # nosec B105
        },
        42: {
            "database": "analytics",
            "endpoints": "10.0.1.1:5432",
            "read-only-endpoints": "10.0.1.2:5432,10.0.1.3:5432",
            "username": "analytics-user",
            "password": "analytics-password",  # nosec B105
        },
    }
    monitor_database.fetch_relation_data.return_value = relation_data
    charm = SimpleNamespace(
        _database_requirers={},
        _monitor_database_requirer=monitor_database,
        _broken_monitor_relation_ids=set(),
        model=SimpleNamespace(
            relations={
                "postgresql": [],
                "postgresql_monitor": [
                    SimpleNamespace(id=41, app=SimpleNamespace(name="dbaas-stg-jira-data-sink")),
                    SimpleNamespace(id=42, app=SimpleNamespace(name="dbaas-stg-data-mesh-el-salesforce")),
                ],
            }
        ),
        app=SimpleNamespace(name="gatus"),
        restart=Mock(),
    )

    monitors, targets = GatusCharm._database_monitor_targets(cast(GatusCharm, charm))

    assert len(monitors) == 6
    assert len({monitor["id"] for monitor in monitors}) == 6
    assert [monitor["id"] for monitor in monitors] == [
        "monitor-41-0",
        "monitor-41-1",
        "monitor-41-2",
        "monitor-42-0",
        "monitor-42-1",
        "monitor-42-2",
    ]
    assert [monitor["is_primary"] for monitor in monitors] == [
        True,
        False,
        False,
        True,
        False,
        False,
    ]
    assert [str(monitor["name"]) for monitor in monitors] == [
        "dbaas-stg-jira-data-sink Primary (10.0.0.1:5432)",
        "dbaas-stg-jira-data-sink Read-only (10.0.0.2:5432)",
        "dbaas-stg-jira-data-sink Read-only (10.0.0.3:5432)",
        "dbaas-stg-data-mesh-el-salesforce Primary (10.0.1.1:5432)",
        "dbaas-stg-data-mesh-el-salesforce Read-only (10.0.1.2:5432)",
        "dbaas-stg-data-mesh-el-salesforce Read-only (10.0.1.3:5432)",
    ]
    assert len(targets) == 6
    monitor_database.fetch_relation_data.assert_called_with(
        relation_ids=[41, 42],
        fields=["database", "endpoints", "password", "read-only-endpoints", "username"],
    )

    relation_data[42]["read-only-endpoints"] = "10.0.1.4:5432,10.0.1.5:5432"
    updated_monitors, _ = GatusCharm._database_monitor_targets(cast(GatusCharm, charm))
    assert any("10.0.1.4:5432" in str(monitor["name"]) for monitor in updated_monitors)

    GatusCharm._on_monitor_database_relation_broken(
        cast(GatusCharm, charm),
        cast(ops.RelationBrokenEvent, SimpleNamespace(relation=SimpleNamespace(id=41))),
    )
    remaining_monitors, remaining_targets = GatusCharm._database_monitor_targets(cast(GatusCharm, charm))
    assert len(remaining_monitors) == 3
    assert len(remaining_targets) == 3
    assert all(str(monitor["id"]).startswith("monitor-42-") for monitor in remaining_monitors)
    assert charm.restart.call_count == 1
