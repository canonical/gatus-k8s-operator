#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Render Gatus configuration files from Jinja2 templates."""

import os
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def render_configs(config_dir: Path, templates_dir: Path, env: dict) -> None:
    """Render all Gatus config files into config_dir using templates from templates_dir.

    Args:
        config_dir: Directory to write rendered config files into.
        templates_dir: Directory containing Jinja2 template files.
        env: Environment variable mapping (typically os.environ).

    """
    jinja_env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    def render(template_name: str, context: dict) -> str:
        return jinja_env.get_template(template_name).render(**context)

    def write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def remove(path: Path) -> None:
        path.unlink(missing_ok=True)

    config_dir.mkdir(parents=True, exist_ok=True)

    # UI configuration — always created.
    write(
        config_dir / "ui.yaml",
        render(
            "ui.yaml.j2",
            {
                "ui_header": env.get("APP_UI_HEADER", "Gatus"),
                "ui_logo": env.get("APP_UI_LOGO", ""),
                "ui_dashboard_heading": env.get("APP_UI_DASHBOARD_HEADING", "Health Dashboard"),
                "ui_dashboard_subheading": env.get(
                    "APP_UI_DASHBOARD_SUBHEADING",
                    "Monitor the health of your endpoints in real-time",
                ),
                "ui_dark_mode": env.get("APP_UI_DARK_MODE", "true"),
                "ui_default_sort_by": env.get("APP_UI_DEFAULT_SORT_BY", "name"),
                "ui_default_filter_by": env.get("APP_UI_DEFAULT_FILTER_BY", "none"),
            },
        ),
    )

    # Storage — created only when POSTGRESQL_DB_CONNECT_STRING is set.
    db_connect_string = env.get("POSTGRESQL_DB_CONNECT_STRING", "")
    if db_connect_string:
        write(
            config_dir / "storage.yaml",
            render("storage.yaml.j2", {"db_connect_string": db_connect_string}),
        )
    else:
        print("POSTGRESQL_DB_CONNECT_STRING is not set", file=sys.stderr)
        remove(config_dir / "storage.yaml")

    # Alerting — created only when MATTERMOST_WEBHOOK_URL is set.
    webhook_url = env.get("MATTERMOST_WEBHOOK_URL", "")
    if webhook_url:
        write(
            config_dir / "alerting.yaml",
            render(
                "alerting.yaml.j2",
                {
                    "webhook_url": webhook_url,
                    "insecure": env.get("APP_MATTERMOST_INSECURE", "false") == "true",
                },
            ),
        )
    else:
        print("MATTERMOST_WEBHOOK_URL is not set", file=sys.stderr)
        remove(config_dir / "alerting.yaml")

    # Announcements — raw pass-through; created only when APP_ANNOUNCEMENTS is set.
    announcements = env.get("APP_ANNOUNCEMENTS", "")
    if announcements:
        write(config_dir / "announcements.yaml", announcements)
    else:
        print("APP_ANNOUNCEMENTS is not set", file=sys.stderr)
        remove(config_dir / "announcements.yaml")

    # Endpoints — raw pass-through when APP_ENDPOINTS is set; default sample otherwise.
    endpoints = env.get("APP_ENDPOINTS", "")
    if endpoints:
        print("Using endpoints from config", file=sys.stderr)
        write(config_dir / "endpoints.yaml", endpoints)
    else:
        write(config_dir / "endpoints.yaml", render("endpoints.yaml.j2", {}))

    # Security (OIDC) — created only when the full required env set is present.
    # NOTE: charm.py sets APP_OAUTH_* but this script reads APP_OIDC_*.
    # This is a pre-existing mismatch: OIDC is currently never activated in practice.
    client_id = env.get("APP_OIDC_CLIENT_ID", "")
    client_secret = env.get("APP_OIDC_CLIENT_SECRET", "")
    api_base_url = env.get("APP_OIDC_API_BASE_URL", "")
    base_url = env.get("APP_BASE_URL", "")

    if client_id and client_secret and api_base_url and base_url:
        print("Configuring OIDC authentication via OAuth relation", file=sys.stderr)
        redirect_path = env.get("APP_OIDC_REDIRECT_PATH", "/authorization-code/callback")
        redirect_url = base_url.rstrip("/") + "/" + redirect_path.lstrip("/")

        scopes_str = env.get("APP_OIDC_SCOPES", "openid")
        scopes = scopes_str.split() if scopes_str.strip() else ["openid"]

        allowed_subjects_str = env.get("APP_OIDC_ALLOWED_SUBJECTS", "")
        allowed_subjects = [s for s in allowed_subjects_str.split(",") if s] if allowed_subjects_str else []

        write(
            config_dir / "security.yaml",
            render(
                "security.yaml.j2",
                {
                    "issuer_url": api_base_url,
                    "redirect_url": redirect_url,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scopes": scopes,
                    "allowed_subjects": allowed_subjects,
                },
            ),
        )
    else:
        print("OAuth not configured, skipping OIDC security", file=sys.stderr)
        remove(config_dir / "security.yaml")


def main() -> None:
    """Entry point: render configs from real environment into /config."""
    render_configs(
        config_dir=Path("/config"),
        templates_dir=_TEMPLATES_DIR,
        env=dict(os.environ),
    )


if __name__ == "__main__":
    main()
