#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""HTTP health probe for PostgreSQL relation endpoints."""

import json
import logging
import os
from typing import Literal, TypedDict

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
app = FastAPI()


class PostgreSQLHealthResponse(TypedDict):
    """Successful PostgreSQL health response."""

    status: Literal["ok"]
    transaction_read_only: bool
    in_recovery: bool
    schemas: list[str]


targets = {
    str(target["id"]): target
    for target in json.loads(os.environ.get("DB_PROBE_TARGETS", "[]"))
}


def query_database(target: dict[str, str | int | bool]) -> PostgreSQLHealthResponse | None:
    """Return schema and role status, or None when the PostgreSQL query fails."""
    connection = None
    try:
        import psycopg2

        connection_parameters = {
            key: target[key]
            for key in ("host", "port", "dbname", "user", "password")
        }
        connection = psycopg2.connect(**connection_parameters, connect_timeout=3)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_setting('transaction_read_only')::boolean,
                    pg_is_in_recovery(),
                    ARRAY(
                        SELECT schema_name
                        FROM information_schema.schemata
                        ORDER BY schema_name
                    )
                """
            )
            transaction_read_only, in_recovery, schemas = cursor.fetchone()
            return {
                "status": "ok",
                "transaction_read_only": transaction_read_only,
                "in_recovery": in_recovery,
                "schemas": schemas,
            }
    except Exception as exc:
        logger.warning("PostgreSQL status query failed (%s)", type(exc).__name__)
        return None
    finally:
        if connection is not None:
            connection.close()


@app.get("/health/{target_id}", response_model=None)
def health(target_id: str) -> PostgreSQLHealthResponse | JSONResponse:
    """Report query and role health for a configured PostgreSQL endpoint."""
    target = targets.get(target_id)
    if target is None:
        return JSONResponse(status_code=404, content={"status": "error"})

    database_status = query_database(target)
    if database_status is None:
        return JSONResponse(status_code=503, content={"status": "error"})

    return database_status
