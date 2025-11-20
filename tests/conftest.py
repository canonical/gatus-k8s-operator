# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
"""Module for test customizations."""


def pytest_addoption(parser):
    """Add parser switches."""
    parser.addoption(
        "--gatus-image", action="store", help="Registry path to Gatus OCI image, e.g. localhost:32000/gatus:1.0"
    )
    parser.addoption(
        "--charm-file", action="store", default=None, help="File path to charm file, e.g. ./gatus-k8s_amd64.charm"
    )


def pytest_configure(config):
    """Add config options."""
    config.addinivalue_line("markers", "abort_on_fail")
