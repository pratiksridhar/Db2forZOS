import importlib.util
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402

GENERATOR = paths.DOMAINS / "supply-chain-logistics" / "generate.py"
_spec = importlib.util.spec_from_file_location("supply_chain_logistics", GENERATOR)
logistics = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = logistics
_spec.loader.exec_module(logistics)


class SupplyChainLogisticsSchemaTests(unittest.TestCase):
    def test_generated_schema_is_statically_valid(self):
        sql = logistics.generate_sql()
        self.assertEqual([], logistics.validate_schema(sql))

    def test_expected_object_topology_is_present(self):
        names = {table.name for table in logistics.TABLES}
        self.assertEqual(68, len(names))
        self.assertTrue(
            {
                "FULFILLMENT_ORDER",
                "INVENTORY_RESERVATION",
                "INVENTORY_MOVEMENT",
                "SHIPMENT",
                "SHIPMENT_LEG",
                "TRANSPORT_LOAD",
                "CARRIER_TENDER",
                "TRACKING_EVENT",
                "DOCUMENT_CONTENT",
                "CUSTOMER_INVOICE",
                "CARRIER_INVOICE",
                "JOURNAL_LINE",
                "IDEMPOTENCY_REQUEST",
                "INBOUND_MESSAGE",
                "OUTBOX_EVENT",
                "OUTBOX_DELIVERY",
                "AUDIT_EVENT",
            }.issubset(names)
        )

    def test_tenant_owned_keys_and_references_are_tenant_scoped(self):
        by_name = {table.name: table for table in logistics.TABLES}
        for table in logistics.TABLES:
            if not table.tenant_owned:
                continue
            self.assertEqual("TENANT_ID", table.primary_key[0], table.name)
            for unique in table.uniques:
                self.assertEqual("TENANT_ID", unique[0], table.name)
            for foreign_key in table.all_foreign_keys():
                target = by_name[foreign_key.ref_table]
                if target.tenant_owned:
                    self.assertEqual(
                        ("TENANT_ID",),
                        foreign_key.columns[:1],
                        table.name,
                    )
                    self.assertEqual(
                        ("TENANT_ID",),
                        foreign_key.ref_columns[:1],
                        table.name,
                    )

    def test_physical_counts_and_source_record_width(self):
        sql = logistics.generate_sql()
        self.assertEqual(67, sql.count("CREATE TABLESPACE "))
        self.assertEqual(68, sql.count("CREATE TABLE "))
        self.assertEqual(
            260,
            sql.count("CREATE INDEX ")
            + sql.count("CREATE UNIQUE INDEX "),
        )
        overflow = [
            (number, line)
            for number, line in enumerate(sql.splitlines(), 1)
            if line
            and not line.startswith("--")
            and len(line) > logistics.MAX_LINE
        ]
        self.assertEqual([], overflow)


if __name__ == "__main__":
    unittest.main()
