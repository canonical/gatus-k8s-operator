#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""HTTP health probe for PostgreSQL relation endpoints."""

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

Target = dict[str, str | int]


def check_database(target: Target) -> bool:
    """Return whether a PostgreSQL endpoint accepts and executes a query."""
    try:
        import psycopg2

        connection_parameters = {
            key: target[key] for key in ("host", "port", "dbname", "user", "password")
        }
        connection = psycopg2.connect(**connection_parameters, connect_timeout=3)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)
        finally:
            connection.close()
    except Exception as exc:
        logger.warning("PostgreSQL health check failed (%s)", type(exc).__name__)
        return False


class DatabaseProbeHandler(BaseHTTPRequestHandler):
    """Serve PostgreSQL query results as HTTP health statuses."""

    def do_GET(self) -> None:
        """Check the configured database endpoint selected by the request path."""
        path = urlsplit(self.path).path
        target_id = path.removeprefix("/health/")
        targets = cast(DatabaseProbeServer, self.server).targets
        target = targets.get(target_id) if target_id and "/" not in target_id else None

        if target is None:
            status_code, status = 404, "error"
        else:
            healthy = check_database(target)
            status_code, status = (200, "ok") if healthy else (503, "error")

        payload = json.dumps({"status": status}).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        """Avoid logging health-check requests on every monitoring interval."""


class DatabaseProbeServer(ThreadingHTTPServer):
    """HTTP server that maps local health URLs to PostgreSQL targets."""

    daemon_threads = True

    def __init__(
        self,
        targets: list[Target],
        server_address: tuple[str, int] = ("127.0.0.1", 9090),
    ):
        self.targets = {str(target["id"]): target for target in targets}
        super().__init__(server_address, DatabaseProbeHandler)


def main() -> None:
    """Start the local health API."""
    logging.basicConfig(level=logging.INFO)
    targets = json.loads(os.environ.get("DB_PROBE_TARGETS", "[]"))
    server = DatabaseProbeServer(targets)
    server.serve_forever()


if __name__ == "__main__":
    main()
