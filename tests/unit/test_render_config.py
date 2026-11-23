# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for render_config.py — the Jinja-based Gatus config renderer."""

import textwrap
from pathlib import Path

import pytest
import render_config as rc
import yaml

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "gatus_rock" / "templates"


def _render(tmp_path: Path, env: dict) -> dict[str, Path]:
    """Run render_configs and return a dict of filename → Path for files that exist."""
    rc.render_configs(config_dir=tmp_path, templates_dir=TEMPLATES_DIR, env=env)
    return {p.name: p for p in tmp_path.iterdir()}


# ---------------------------------------------------------------------------
# ui.yaml — always created
# ---------------------------------------------------------------------------


def test_ui_yaml_always_created(tmp_path):
    files = _render(tmp_path, {})
    assert "ui.yaml" in files


def test_ui_yaml_defaults(tmp_path):
    files = _render(tmp_path, {})
    doc = yaml.safe_load(files["ui.yaml"].read_text())
    assert doc["ui"]["header"] == "Gatus"
    assert doc["ui"]["logo"] == ""
    assert doc["ui"]["dashboard-heading"] == "Health Dashboard"
    assert doc["ui"]["dark-mode"] is True
    assert doc["ui"]["default-sort-by"] == "name"
    assert doc["ui"]["default-filter-by"] == "none"


def test_ui_yaml_env_overrides(tmp_path):
    env = {
        "APP_UI_HEADER": "MyApp",
        "APP_UI_LOGO": "https://example.com/logo.png",
        "APP_UI_DASHBOARD_HEADING": "Status",
        "APP_UI_DASHBOARD_SUBHEADING": "All systems go",
        "APP_UI_DARK_MODE": "false",
        "APP_UI_DEFAULT_SORT_BY": "group",
        "APP_UI_DEFAULT_FILTER_BY": "failing",
    }
    files = _render(tmp_path, env)
    doc = yaml.safe_load(files["ui.yaml"].read_text())
    assert doc["ui"]["header"] == "MyApp"
    assert doc["ui"]["logo"] == "https://example.com/logo.png"
    assert doc["ui"]["dark-mode"] is False
    assert doc["ui"]["default-sort-by"] == "group"
    assert doc["ui"]["default-filter-by"] == "failing"


# ---------------------------------------------------------------------------
# storage.yaml — conditional on POSTGRESQL_DB_CONNECT_STRING
# ---------------------------------------------------------------------------


def test_storage_yaml_absent_when_no_db(tmp_path):
    files = _render(tmp_path, {})
    assert "storage.yaml" not in files


def test_storage_yaml_present_when_db_set(tmp_path):
    env = {"POSTGRESQL_DB_CONNECT_STRING": "postgresql://user:pass@localhost/gatus"}
    files = _render(tmp_path, env)
    assert "storage.yaml" in files
    doc = yaml.safe_load(files["storage.yaml"].read_text())
    assert doc["storage"]["type"] == "postgres"
    assert doc["storage"]["path"] == "postgresql://user:pass@localhost/gatus"


def test_storage_yaml_removed_when_db_unset(tmp_path):
    # Pre-create the file to verify it gets removed.
    storage_file = tmp_path / "storage.yaml"
    storage_file.write_text("storage:\n  path: old\n  type: postgres\n")
    _render(tmp_path, {})
    assert not storage_file.exists()


# ---------------------------------------------------------------------------
# alerting.yaml — conditional on MATTERMOST_WEBHOOK_URL
# ---------------------------------------------------------------------------


def test_alerting_yaml_absent_when_no_webhook(tmp_path):
    files = _render(tmp_path, {})
    assert "alerting.yaml" not in files


def test_alerting_yaml_present_when_webhook_set(tmp_path):
    env = {"MATTERMOST_WEBHOOK_URL": "https://chat.example.com/hooks/abc"}
    files = _render(tmp_path, env)
    assert "alerting.yaml" in files
    doc = yaml.safe_load(files["alerting.yaml"].read_text())
    assert doc["alerting"]["mattermost"]["webhook-url"] == "https://chat.example.com/hooks/abc"
    assert "client" not in doc["alerting"]["mattermost"]


def test_alerting_yaml_includes_insecure_block_when_flag_set(tmp_path):
    env = {
        "MATTERMOST_WEBHOOK_URL": "https://chat.example.com/hooks/abc",
        "APP_MATTERMOST_INSECURE": "true",
    }
    files = _render(tmp_path, env)
    doc = yaml.safe_load(files["alerting.yaml"].read_text())
    assert doc["alerting"]["mattermost"]["client"]["insecure"] is True


def test_alerting_yaml_no_insecure_block_when_flag_false(tmp_path):
    env = {
        "MATTERMOST_WEBHOOK_URL": "https://chat.example.com/hooks/abc",
        "APP_MATTERMOST_INSECURE": "false",
    }
    files = _render(tmp_path, env)
    doc = yaml.safe_load(files["alerting.yaml"].read_text())
    assert "client" not in doc["alerting"]["mattermost"]


def test_alerting_yaml_removed_when_webhook_unset(tmp_path):
    alerting_file = tmp_path / "alerting.yaml"
    alerting_file.write_text("alerting:\n  mattermost:\n    webhook-url: old\n")
    _render(tmp_path, {})
    assert not alerting_file.exists()


# ---------------------------------------------------------------------------
# announcements.yaml — raw pass-through
# ---------------------------------------------------------------------------


def test_announcements_yaml_absent_when_not_set(tmp_path):
    files = _render(tmp_path, {})
    assert "announcements.yaml" not in files


def test_announcements_yaml_raw_passthrough(tmp_path):
    raw = textwrap.dedent("""\
        announcements:
          - timestamp: 2025-08-15T14:00:00Z
            type: outage
            message: Maintenance window
    """)
    env = {"APP_ANNOUNCEMENTS": raw}
    files = _render(tmp_path, env)
    assert "announcements.yaml" in files
    assert files["announcements.yaml"].read_text() == raw


def test_announcements_yaml_removed_when_unset(tmp_path):
    ann_file = tmp_path / "announcements.yaml"
    ann_file.write_text("announcements: []\n")
    _render(tmp_path, {})
    assert not ann_file.exists()


# ---------------------------------------------------------------------------
# endpoints.yaml — raw pass-through or default Ubuntu.com sample
# ---------------------------------------------------------------------------


def test_endpoints_yaml_default_when_not_set(tmp_path):
    files = _render(tmp_path, {})
    assert "endpoints.yaml" in files
    doc = yaml.safe_load(files["endpoints.yaml"].read_text())
    assert doc["endpoints"][0]["name"] == "Ubuntu.com"
    assert doc["endpoints"][0]["url"] == "https://ubuntu.com"


def test_endpoints_yaml_raw_passthrough_when_set(tmp_path):
    raw = textwrap.dedent("""\
        endpoints:
          - name: My API
            url: "https://api.example.com/health"
            interval: 30s
            conditions:
              - "[STATUS] == 200"
    """)
    env = {"APP_ENDPOINTS": raw}
    files = _render(tmp_path, env)
    assert files["endpoints.yaml"].read_text() == raw


# ---------------------------------------------------------------------------
# security.yaml — conditional on full OIDC env set
# ---------------------------------------------------------------------------


_OIDC_BASE = {
    "APP_OIDC_CLIENT_ID": "client-123",
    "APP_OIDC_CLIENT_SECRET": "secret-abc",  # nosec B105
    "APP_OIDC_API_BASE_URL": "https://hydra.example.com",
    "APP_BASE_URL": "https://gatus.example.com",
}


def test_security_yaml_absent_when_oidc_not_set(tmp_path):
    files = _render(tmp_path, {})
    assert "security.yaml" not in files


@pytest.mark.parametrize(
    "missing_key",
    ["APP_OIDC_CLIENT_ID", "APP_OIDC_CLIENT_SECRET", "APP_OIDC_API_BASE_URL", "APP_BASE_URL"],
)
def test_security_yaml_absent_when_any_required_oidc_var_missing(tmp_path, missing_key):
    env = {k: v for k, v in _OIDC_BASE.items() if k != missing_key}
    files = _render(tmp_path, env)
    assert "security.yaml" not in files


def test_security_yaml_present_with_full_oidc_env(tmp_path):
    files = _render(tmp_path, _OIDC_BASE)
    assert "security.yaml" in files
    doc = yaml.safe_load(files["security.yaml"].read_text())
    oidc = doc["security"]["oidc"]
    assert oidc["issuer-url"] == "https://hydra.example.com"
    assert oidc["client-id"] == "client-123"
    assert oidc["client-secret"] == "secret-abc"
    assert oidc["scopes"] == ["openid"]


def test_security_yaml_redirect_url_constructed_correctly(tmp_path):
    env = {**_OIDC_BASE, "APP_BASE_URL": "https://gatus.example.com/"}
    files = _render(tmp_path, env)
    doc = yaml.safe_load(files["security.yaml"].read_text())
    assert doc["security"]["oidc"]["redirect-url"] == "https://gatus.example.com/authorization-code/callback"


def test_security_yaml_custom_redirect_path(tmp_path):
    env = {**_OIDC_BASE, "APP_OIDC_REDIRECT_PATH": "/callback"}
    files = _render(tmp_path, env)
    doc = yaml.safe_load(files["security.yaml"].read_text())
    assert doc["security"]["oidc"]["redirect-url"] == "https://gatus.example.com/callback"


def test_security_yaml_multiple_scopes(tmp_path):
    env = {**_OIDC_BASE, "APP_OIDC_SCOPES": "openid email profile"}
    files = _render(tmp_path, env)
    doc = yaml.safe_load(files["security.yaml"].read_text())
    assert doc["security"]["oidc"]["scopes"] == ["openid", "email", "profile"]


def test_security_yaml_allowed_subjects(tmp_path):
    env = {**_OIDC_BASE, "APP_OIDC_ALLOWED_SUBJECTS": "alice,bob"}
    files = _render(tmp_path, env)
    doc = yaml.safe_load(files["security.yaml"].read_text())
    assert doc["security"]["oidc"]["allowed-subjects"] == ["alice", "bob"]


def test_security_yaml_no_allowed_subjects_key_when_unset(tmp_path):
    files = _render(tmp_path, _OIDC_BASE)
    doc = yaml.safe_load(files["security.yaml"].read_text())
    assert "allowed-subjects" not in doc["security"]["oidc"]


def test_security_yaml_removed_when_oidc_not_configured(tmp_path):
    sec_file = tmp_path / "security.yaml"
    sec_file.write_text("security:\n  oidc: {}\n")
    _render(tmp_path, {})
    assert not sec_file.exists()
