import logging
import pathlib

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
    juju.integrate(APP_NAME, PG_APP_NAME)
    juju.wait(jubilant.all_active, timeout=600, delay=30)

    # Check that the charms resolve after the relations
    status = juju.status()
    assert status.apps[APP_NAME].units[APP_NAME + "/0"].is_active

    # Get the config of the gatus charm
    config = get_config(juju)

    assert config.storage is not None, "config.storage is None"
    assert config.storage.type == "postgres"
    assert "postgresql-k8s-primary" in config.storage.path

