# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Build Gatus database monitors from PostgreSQL relation data."""

import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class PostgreSQLRelationData(BaseModel):
    """Validated PostgreSQL relation data used to create probe targets."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    database: str | None = None
    endpoints: str | None = None
    read_only_endpoints: str = Field(default="", alias="read-only-endpoints")
    username: str | None = None
    password: str | None = None


class DatabaseProbeTarget(BaseModel):
    """Credentials and address for a single PostgreSQL health check."""

    id: str
    host: str
    port: int = Field(ge=1, le=65535)
    dbname: str
    user: str
    password: str
    is_primary: bool


def _split_endpoint(endpoint: str) -> tuple[str, int] | None:
    """Parse a PostgreSQL host:port endpoint, including bracketed IPv6."""
    endpoint = endpoint.strip()
    if endpoint.startswith("["):
        host, separator, port = endpoint[1:].partition("]:")
    else:
        host, separator, port = endpoint.rpartition(":")
        if ":" in host:
            separator = ""

    if not separator or not host:
        logger.warning("Ignoring invalid PostgreSQL endpoint: %s", endpoint)
        return None

    try:
        return host, int(port)
    except ValueError:
        logger.warning("Ignoring invalid PostgreSQL endpoint: %s", endpoint)
        return None


def build_database_monitors(
    databag: dict[str, str],
    default_database: str,
    target_id_prefix: str = "",
    application_name: str | None = None,
) -> tuple[list[dict[str, str | bool]], list[dict[str, str | int | bool]]]:
    """Build public monitor metadata and private probe targets from one relation."""
    try:
        relation = PostgreSQLRelationData.model_validate(databag)
    except ValidationError:
        logger.warning("Ignoring invalid PostgreSQL relation data")
        return [], []

    if not all((relation.endpoints, relation.username, relation.password)):
        return [], []

    database_name = relation.database or default_database
    monitor_prefix = application_name or database_name
    monitors: list[dict[str, str | bool]] = []
    targets: list[dict[str, str | int | bool]] = []
    seen: set[tuple[str, int]] = set()

    for role, endpoint_list, is_primary in (
        ("Primary", relation.endpoints or "", True),
        ("Read-only", relation.read_only_endpoints, False),
    ):
        for endpoint in endpoint_list.split(","):
            parsed_endpoint = _split_endpoint(endpoint)
            if parsed_endpoint is None:
                continue
            host, port = parsed_endpoint
            if (host, port) in seen:
                continue

            target_id = f"{target_id_prefix}-{len(targets)}" if target_id_prefix else str(len(targets))
            address = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
            try:
                target = DatabaseProbeTarget.model_validate(
                    {
                        "id": target_id,
                        "host": host,
                        "port": port,
                        "dbname": database_name,
                        "user": relation.username,
                        "password": relation.password,
                        "is_primary": is_primary,
                    }
                )
            except ValidationError:
                logger.warning("Ignoring invalid PostgreSQL endpoint: %s", endpoint.strip())
                continue

            seen.add((host, port))
            monitors.append(
                {
                    "id": target.id,
                    "name": f"{monitor_prefix} {role} ({address})",
                    "is_primary": is_primary,
                }
            )
            targets.append(target.model_dump())

    return monitors, targets
