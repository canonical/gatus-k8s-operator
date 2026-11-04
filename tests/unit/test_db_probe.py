# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the PostgreSQL HTTP health probe."""

import json
import sys
from unittest.mock import MagicMock, Mock

import db_probe
from fastapi.responses import JSONResponse

TARGET = {
    "id": "0",
    "host": "10.146.72.61",
    "port": 5432,
    "dbname": "gatus",
    "user": "gatus-user",
    "password": "hidden-password",  # nosec B105
}


def test_query_database_returns_schema_and_replication_status(monkeypatch):
    cursor = Mock()
    cursor.fetchone.return_value = (False, False, ["public", "monitoring"])
    connection = Mock()
    connection.cursor.return_value = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    psycopg2 = Mock(connect=Mock(return_value=connection))
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)

    assert db_probe.query_database(TARGET) == {
        "status": "ok",
        "transaction_read_only": False,
        "in_recovery": False,
        "schemas": ["public", "monitoring"],
    }
    connection_parameters = {key: TARGET[key] for key in ("host", "port", "dbname", "user", "password")}
    psycopg2.connect.assert_called_once_with(**connection_parameters, connect_timeout=3)
    assert "current_setting('transaction_read_only')" in cursor.execute.call_args.args[0]
    assert "pg_is_in_recovery()" in cursor.execute.call_args.args[0]
    connection.close.assert_called_once_with()


def test_query_database_returns_none_when_connection_fails(monkeypatch):
    psycopg2 = Mock(connect=Mock(side_effect=OSError("unreachable")))
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)

    assert db_probe.query_database(TARGET) is None


def test_query_database_returns_none_when_query_fails(monkeypatch):
    cursor = Mock()
    cursor.execute.side_effect = RuntimeError("query failed")
    connection = Mock()
    connection.cursor.return_value = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    psycopg2 = Mock(connect=Mock(return_value=connection))
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)

    assert db_probe.query_database(TARGET) is None
    connection.close.assert_called_once_with()


def test_health_endpoint_returns_database_status_when_query_succeeds(monkeypatch):
    monkeypatch.setitem(db_probe.targets, "0", TARGET)
    monkeypatch.setattr(
        db_probe,
        "query_database",
        lambda target: {
            "status": "ok",
            "transaction_read_only": False,
            "in_recovery": False,
            "schemas": ["public"],
        },
    )
    response = db_probe.health("0")

    assert response == {
        "status": "ok",
        "transaction_read_only": False,
        "in_recovery": False,
        "schemas": ["public"],
    }


def test_health_endpoint_returns_service_unavailable_when_query_fails(monkeypatch):
    monkeypatch.setitem(db_probe.targets, "0", TARGET)
    monkeypatch.setattr(db_probe, "query_database", lambda target: None)

    response = db_probe.health("0")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert json.loads(bytes(response.body)) == {"status": "error"}


def test_health_endpoint_returns_not_found_for_unknown_target():
    response = db_probe.health("unknown")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404
    assert json.loads(bytes(response.body)) == {"status": "error"}
