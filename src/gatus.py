# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functions for interacting with the workload.

The intention is that this module could be used outside the context of a charm.
"""

import logging

logger = logging.getLogger(__name__)


def get_version() -> str | None:
    """Get the running version of the workload."""
    # TODO: Get actual version from the workload from the rock.
    return "v5.32.0"
