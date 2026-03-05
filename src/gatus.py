# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functions for interacting with the workload.

The intention is that this module could be used outside the context of a charm.
"""

import logging
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class Storage(BaseModel):
    """Configuration for Gatus storage."""

    type: str
    path: str


class Announcement(BaseModel):
    """Configuration for Gatus announcements."""

    timestamp: datetime | str
    type: str = "none"
    message: str
    archived: bool = False

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate the announcement type."""
        announcement_types = ["none", "outage", "warning", "information", "operational"]
        if v not in announcement_types:
            raise ValueError(f"Invalid announcement type: {v}")
        return v


class Mattermost(BaseModel):
    """Configuration for Mattermost alerting."""

    webhook_url: str = Field(alias="webhook-url")
    client: dict | None = None


class Alerting(BaseModel):
    """Configuration for Gatus alerting."""

    mattermost: Mattermost


class EndpointAlert(BaseModel):
    """Configuration for Gatus endpoint alert."""

    type: str
    description: str
    send_on_resolved: bool = Field(default=False, alias="send-on-resolved")


class Endpoint(BaseModel):
    """Configuration for Gatus endpoint."""

    name: str
    group: str | None = None
    url: str
    interval: str | None = None
    conditions: list[str] | None = None
    alerts: list[EndpointAlert] | None = None


class GatusConfig(BaseModel):
    """Configuration for Gatus."""

    storage: Storage | None = None
    announcements: list[Announcement] | None = None
    alerting: Alerting | None = None
    endpoints: list[Endpoint] | None = None
