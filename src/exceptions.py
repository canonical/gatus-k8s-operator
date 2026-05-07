# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Exceptions used by the charm."""


class BlockedStatusError(Exception):
    """Exception raised when a BlockedStatus is needed."""

    pass


class SecretAccessPendingError(Exception):
    """Exception raised when a Juju secret exists but is not readable yet."""

    pass
