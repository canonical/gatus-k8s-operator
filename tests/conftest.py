# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
"""Module for test customizations."""


def pytest_addoption(parser):
    """Add parser switches."""
    parser.addoption("--gatus-image", action="store")
    parser.addoption("--charm-file", action="store", default=None)


def pytest_configure(config):
    """Add config options."""
    config.addinivalue_line("markers", "abort_on_fail")
