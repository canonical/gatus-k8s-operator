#!/usr/bin/env python3
"""Stub charm mocking PostgreSQL for integration tests."""

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus


class PostgresStub(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.db_relation_joined, self._on_db_relation_joined)
        self.unit.status = ActiveStatus("Started; awaiting relation")

    def _on_db_relation_joined(self, event):
        # This triggers immediately when you run `juju integrate`
        # 1. Get the relation data bucket for this application
        relation_data = event.relation.data[self.app]
        # 2. Inject the fake data your main charm expects
        #    (Adjust keys to match exactly what your charm looks for)
        relation_data["connection_string"] = "postgres://user:pass@1.2.3.4:5432/mydb"
        relation_data["database"] = "mydb"
        self.unit.status = ActiveStatus("Data injected")


if __name__ == "__main__":
    main(PostgresStub)
