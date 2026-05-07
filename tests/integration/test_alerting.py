# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# The integration tests use the Jubilant library. See https://documentation.ubuntu.com/jubilant/
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/

import logging
import pathlib

import jubilant
import yaml

from tests.integration.helper import get_config

logger = logging.getLogger(__name__)

APP_NAME = "gatus-k8s"
PG_APP_NAME = "postgresql-k8s"
SELF_SIGNED_CERT_APP_NAME = "self-signed-certificates"

def test_mattermost_alerting(deployed_charm: pathlib.Path, juju: jubilant.Juju):
    """Add a secret to the charm and check that the alerting config is updated."""
    # Add a secret to the Juju model
    secreturi = juju.add_secret(
        name="gatus-webhooks",
        content={
            "default": "http://localhost:8080/hooks/xxx",
        },
    )
    assert secreturi is not None, "secreturi is None"
    assert secreturi.startswith("secret:")

    # Grant secret to charm and update the charm config
    logger.info("Granting secret %s to charm", secreturi)
    juju.grant_secret(
        identifier=secreturi,
        app=APP_NAME,
    )
    secret_id = secreturi[len("secret:") :]
    juju.config(APP_NAME, {"mattermost-alerting": secret_id})
    juju.wait(jubilant.all_active, timeout=300, delay=10)

    # Get the config of the gatus charm
    config = get_config(juju)

    assert config.alerting is not None, "config.alerting is None"
    assert config.alerting.mattermost is not None, "config.alerting.mattermost is None"
    assert config.alerting.mattermost.webhook_url == "http://localhost:8080/hooks/xxx"

    # Test that the charm reacts to updates to the secret
    juju.update_secret(
        identifier=secreturi,
        content={
            "default": "http://localhost:8080/hooks/yyy",
        },
    )
    juju.wait(jubilant.all_active, timeout=300, delay=10)

    # Get the config of the gatus charm
    config = get_config(juju)

    assert config.alerting is not None, "after update, config.alerting is None"
    assert config.alerting.mattermost is not None, "after update, config.alerting.mattermost is None"
    assert config.alerting.mattermost.webhook_url == "http://localhost:8080/hooks/yyy"


def test_endpoints_provider_override_webhook(deployed_charm: pathlib.Path, juju: jubilant.Juju):
    """Resolve provider-override webhook placeholders in endpoints config."""
    secreturi = juju.add_secret(
        name="gatus-webhooks-provider-override",
        content={
            "default": "http://localhost:8080/hooks/default",
            "channel-1": "http://localhost:8080/hooks/channel-1",
        },
    )
    assert secreturi is not None
    assert secreturi.startswith("secret:")

    logger.info("Granting secret %s to charm", secreturi)
    juju.grant_secret(identifier=secreturi, app=APP_NAME)
    secret_id = secreturi[len("secret:") :]
    juju.config(APP_NAME, {"mattermost-alerting": secret_id})

    with open("tests/data/endpoints-with-provider-override.yaml", "r") as f:
        endpoints_string = f.read()
    juju.config(APP_NAME, {"endpoints": endpoints_string})
    juju.wait(jubilant.all_active, timeout=300, delay=10)

    resolved_endpoints = juju.ssh(
        target=APP_NAME + "/0",
        container="app",
        command="cat /config/endpoints.yaml",
    )
    logger.info("Resolved endpoints config: %s", resolved_endpoints)

    assert "[webhook-url:channel-1]" not in resolved_endpoints

    endpoints = yaml.safe_load(resolved_endpoints)
    webhook_url = endpoints["endpoints"][0]["alerts"][0]["provider-override"]["webhook-url"]
    assert webhook_url == "http://localhost:8080/hooks/channel-1"


