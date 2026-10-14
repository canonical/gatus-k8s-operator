# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the PostgreSQL HTTP health probe."""

import json
import sys
import threading
from http.client import HTTPConnection
from unittest.mock import MagicMock, Mock

import db_probe

TARGET = {
    "id": "0",
    "host": "10.146.72.61",
    "port": 5432,
    "dbname": "gatus",
    "user": "gatus-user",
    "password": "hidden-password",  # nosec B105
}


def test_check_database_executes_select_one(monkeypatch):
    cursor = Mock()
    cursor.fetchone.return_value = (1,)
    connection = Mock()
    connection.cursor.return_value = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    psycopg2 = Mock(connect=Mock(return_value=connection))
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)

    assert db_probe.check_database(TARGET)
    connection_parameters = {key: TARGET[key] for key in ("host", "port", "dbname", "user", "password")}
    psycopg2.connect.assert_called_once_with(**connection_parameters, connect_timeout=3)
    cursor.execute.assert_called_once_with("SELECT 1")
    connection.close.assert_called_once_with()


def test_check_database_returns_false_when_connection_fails(monkeypatch):
    psycopg2 = Mock(connect=Mock(side_effect=OSError("unreachable")))
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)

    assert not db_probe.check_database(TARGET)


def test_check_database_returns_false_when_query_fails(monkeypatch):
    cursor = Mock()
    cursor.execute.side_effect = RuntimeError("query failed")
    connection = Mock()
    connection.cursor.return_value = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    psycopg2 = Mock(connect=Mock(return_value=connection))
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)

    assert not db_probe.check_database(TARGET)
    connection.close.assert_called_once_with()


def test_probe_http_response_reflects_query_health(monkeypatch):
    monkeypatch.setattr(db_probe, "check_database", lambda target: target["id"] == "0")
    server = db_probe.DatabaseProbeServer(
        [TARGET, {**TARGET, "id": "1"}],
        ("127.0.0.1", 0),
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()

    try:
        connection = HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", "/health/0")
        healthy = connection.getresponse()
        assert healthy.status == 200
        assert json.loads(healthy.read()) == {"status": "ok"}

        connection.request("GET", "/health/1")
        failed = connection.getresponse()
        assert failed.status == 503
        assert json.loads(failed.read()) == {"status": "error"}

        connection.request("GET", "/health/unknown")
        missing = connection.getresponse()
        assert missing.status == 404
        assert json.loads(missing.read()) == {"status": "error"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
