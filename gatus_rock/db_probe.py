#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""HTTP health probe for PostgreSQL relation endpoints."""

import json
import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
app = FastAPI()
targets = {
    str(target["id"]): target
    for target in json.loads(os.environ.get("DB_PROBE_TARGETS", "[]"))
}


def query_database(target: dict[str, str | int | bool]) -> dict[str, bool | list[str]] | None:
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

@app.get("/health/{target_id}")
def health(target_id: str) -> JSONResponse:
    """Report query and role health for a configured PostgreSQL endpoint."""
    target = targets.get(target_id)
    if target is None:
        return JSONResponse(status_code=404, content={"status": "error"})

    database_status = query_database(target)
    if database_status is None:
        return JSONResponse(status_code=503, content={"status": "error"})

    return JSONResponse(status_code=200, content={"status": "ok", **database_status})
