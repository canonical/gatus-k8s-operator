#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import time

import ops

import gatus

logger = logging.getLogger(__name__)

SERVICE_NAME = "gatus"


class GatusCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on[SERVICE_NAME].pebble_ready, self._on_pebble_ready)
        self.container = self.unit.get_container(SERVICE_NAME)

    def _on_pebble_ready(self, event: ops.PebbleReadyEvent):
        """Handle pebble-ready event."""
        self.unit.status = ops.MaintenanceStatus("starting workload")
        self.container.replan()

        self.unit.open_port(protocol="tcp", port=8080)  # Open a port for the workload.
        self.wait_for_ready()
        version = gatus.get_version()
        if version is not None:
            self.unit.set_workload_version(version)
        self.unit.status = ops.ActiveStatus()

    def is_ready(self) -> bool:
        """Check whether the workload is ready to use."""
        for name, service_info in self.container.get_services().items():
            if not service_info.is_running():
                logger.info("the workload is not ready (service '%s' is not running)", name)
                return False

        checks = self.container.get_checks(level=ops.pebble.CheckLevel.READY)
        for check_info in checks.values():
            if check_info.status != ops.pebble.CheckStatus.UP:
                return False
        return True

    def wait_for_ready(self) -> None:
        """Wait for the workload to be ready to use."""
        for _ in range(3):
            if self.is_ready():
                return
            time.sleep(1)
        logger.error("the workload was not ready within the expected time")
        raise RuntimeError("workload is not ready")


if __name__ == "__main__":  # pragma: nocover
    ops.main(GatusCharm)
