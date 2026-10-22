# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# To learn more about testing, see https://documentation.ubuntu.com/ops/latest/explanation/testing/
import json
import logging
import pathlib
import shlex
import time

import jubilant

from tests.integration.helper import get_config

logger = logging.getLogger(__name__)

APP_NAME = "gatus-k8s"
PG_APP_NAME = "postgresql-k8s"
SELF_SIGNED_CERT_APP_NAME = "self-signed-certificates"


def test_db_relation(deployed_charm: pathlib.Path, juju: jubilant.Juju):
    """Deploy the database charm and check that the gatus charm can connect to it.

    This test uses an OCI image from a registry as the charm resource.
    Thus, please ensure the --gatus-image option is set in the pytest command.
    """
    # Deploy the database charm
    juju.deploy(
        PG_APP_NAME,
        channel="14/stable",
    )
    # Deploy the self-signed-certificates charm
    juju.deploy(
        SELF_SIGNED_CERT_APP_NAME,
        channel="1/stable",
    )
    juju.wait(jubilant.all_active, timeout=900, delay=30)

    # Add the charm relations
    juju.integrate(f"{PG_APP_NAME}:certificates", f"{SELF_SIGNED_CERT_APP_NAME}:certificates")
    juju.wait(jubilant.all_active, timeout=600, delay=30)
    juju.integrate(f"{APP_NAME}:postgresql", f"{PG_APP_NAME}:database")
    juju.wait(jubilant.all_active, timeout=600, delay=30)
    juju.integrate(f"{APP_NAME}:postgresql_monitor", f"{PG_APP_NAME}:database")
    juju.wait(jubilant.all_active, timeout=600, delay=30)

    # Check that the charms resolve after the relations
    status = juju.status()
    assert status.apps[APP_NAME].units[APP_NAME + "/0"].is_active

    # Get the config of the gatus charm
    config = get_config(juju)

    assert config.storage is not None, "config.storage is None"
    assert config.storage.type == "postgres"
    assert "postgresql-k8s-primary" in config.storage.path
    assert config.endpoints is not None
    assert any(endpoint.name.startswith(f"{PG_APP_NAME} Primary (") for endpoint in config.endpoints)

    probe_urls = [
        endpoint.url
        for endpoint in config.endpoints
        if endpoint.name.startswith(f"{PG_APP_NAME} Primary (") and "/health/" in endpoint.url
    ]
    assert probe_urls, "no db_probe endpoint found in the gatus config"
    probe_url = probe_urls[0]

    # Healthy database: the probe reports ok
    status_code, body = _wait_for_probe_status(juju, probe_url, expected=200)
    assert status_code == 200, body
    assert body["status"] == "ok"
    assert body["in_recovery"] is False

    # Unhealthy database: stop PostgreSQL and expect the probe to report an error
    juju.ssh(f"{PG_APP_NAME}/0", "pebble stop postgresql", container="postgresql")
    try:
        status_code, body = _wait_for_probe_status(juju, probe_url, expected=503)
        assert status_code == 503
        assert body == {"status": "error"}
    finally:
        juju.ssh(f"{PG_APP_NAME}/0", "pebble start postgresql", container="postgresql")

    # The probe recovers once the database is back
    status_code, body = _wait_for_probe_status(juju, probe_url, expected=200)
    assert status_code == 200, body
    assert body["status"] == "ok"


def _query_probe(juju: jubilant.Juju, url: str) -> tuple[int, dict]:
    """Query the db_probe from inside the gatus container and return the status code and JSON body."""
    script = (
        "import json, urllib.request, urllib.error\n"
        "try:\n"
        f"    r = urllib.request.urlopen({url!r}, timeout=10); code, raw = r.status, r.read()\n"
        "except urllib.error.HTTPError as e:\n"
        "    code, raw = e.code, e.read()\n"
        "print(json.dumps({'code': code, 'body': json.loads(raw)}))\n"
    )
    output = juju.ssh(APP_NAME + "/0", f"python3 -c {shlex.quote(script)}", container="app")
    result = json.loads(output.strip().splitlines()[-1])
    return result["code"], result["body"]


def _wait_for_probe_status(juju: jubilant.Juju, url: str, expected: int, timeout: int = 300) -> tuple[int, dict]:
    """Poll the db_probe until it returns the expected status code or the timeout expires."""
    deadline = time.monotonic() + timeout
    while True:
        status_code, body = _query_probe(juju, url)
        if status_code == expected or time.monotonic() > deadline:
            return status_code, body
        time.sleep(10)
