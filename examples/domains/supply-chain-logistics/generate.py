#!/usr/bin/env python3
"""Generate and statically validate the supply-chain logistics schema."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import db2check  # noqa: E402
import paths  # noqa: E402

DEFAULT_OUTPUT = ROOT / "generated" / "supply-chain-logistics" / "source.sql"
SCHEMA = "LOGISTICS"
DATABASE = "SCLDB"
STOGROUP = "SYSDEFLT"
BUFFERPOOL = "BP0"
MAX_LINE = 72


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    nullable: bool = False
    suffix: str = ""

    def sql(self) -> str:
        parts = [self.name, self.data_type]
        if not self.nullable:
            parts.append("NOT NULL")
        if self.suffix:
            parts.append(self.suffix)
        return " ".join(parts)


@dataclass(frozen=True)
class ForeignKey:
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]


@dataclass(frozen=True)
class ExtraIndex:
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True)
class Table:
    name: str
    purpose: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...]
    uniques: tuple[tuple[str, ...], ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()
    checks: tuple[str, ...] = ()
    extra_indexes: tuple[ExtraIndex, ...] = ()
    tenant_owned: bool = True
    growth: str = "core"
    append_only: bool = False
    implicit_lob: bool = False

    def all_columns(self) -> tuple[Column, ...]:
        audit = [
            Column(
                "CREATED_AT",
                "TIMESTAMP(6)",
                suffix="WITH DEFAULT",
            )
        ]
        if not self.append_only:
            audit.append(
                Column(
                    "CHANGED_AT",
                    "TIMESTAMP(6)",
                    suffix=(
                        "GENERATED ALWAYS FOR EACH ROW ON UPDATE "
                        "AS ROW CHANGE TIMESTAMP"
                    ),
                )
            )
        return self.columns + tuple(audit)

    def all_foreign_keys(self) -> tuple[ForeignKey, ...]:
        if not self.tenant_owned:
            return self.foreign_keys
        tenant_fk = ForeignKey(("TENANT_ID",), "TENANT", ("TENANT_ID",))
        return (tenant_fk,) + self.foreign_keys


def c(
    name: str,
    data_type: str,
    *,
    nullable: bool = False,
    suffix: str = "",
) -> Column:
    return Column(name, data_type, nullable, suffix)


def fk(
    columns: tuple[str, ...],
    ref_table: str,
    ref_columns: tuple[str, ...],
) -> ForeignKey:
    return ForeignKey(columns, ref_table, ref_columns)


def ix(*columns: str, unique: bool = False) -> ExtraIndex:
    return ExtraIndex(tuple(columns), unique)


def tenant_columns(*columns: Column) -> tuple[Column, ...]:
    return (c("TENANT_ID", "BIGINT"),) + columns


TABLES: tuple[Table, ...] = (
    Table(
        "CURRENCY",
        "ISO-style currencies and minor-unit precision.",
        (
            c("CURRENCY_CODE", "CHAR(3)"),
            c("CURRENCY_NAME", "VARCHAR(60)"),
            c("MINOR_UNITS", "SMALLINT"),
        ),
        ("CURRENCY_CODE",),
        checks=("MINOR_UNITS BETWEEN 0 AND 4",),
        tenant_owned=False,
        growth="reference",
    ),
    Table(
        "COUNTRY",
        "Countries used by addresses, carriers, and customs entries.",
        (
            c("COUNTRY_CODE", "CHAR(2)"),
            c("COUNTRY_NAME", "VARCHAR(80)"),
        ),
        ("COUNTRY_CODE",),
        tenant_owned=False,
        growth="reference",
    ),
    Table(
        "UNIT_OF_MEASURE",
        "Canonical quantity, mass, volume, and distance units.",
        (
            c("UOM_CODE", "VARCHAR(12)"),
            c("UOM_NAME", "VARCHAR(60)"),
            c("UOM_CLASS", "VARCHAR(16)"),
        ),
        ("UOM_CODE",),
        checks=(
            "UOM_CLASS IN ('COUNT','MASS','VOLUME','LENGTH','TIME')",
        ),
        tenant_owned=False,
        growth="reference",
    ),
    Table(
        "TRANSPORT_MODE",
        "Transport modes used by shipments and legs.",
        (
            c("MODE_CODE", "VARCHAR(12)"),
            c("MODE_NAME", "VARCHAR(60)"),
        ),
        ("MODE_CODE",),
        tenant_owned=False,
        growth="reference",
    ),
    Table(
        "EQUIPMENT_TYPE",
        "Vehicle, trailer, container, and handling equipment classes.",
        (
            c("EQUIPMENT_TYPE_CODE", "VARCHAR(20)"),
            c("EQUIPMENT_TYPE_NAME", "VARCHAR(80)"),
            c("MODE_CODE", "VARCHAR(12)"),
            c("MAX_WEIGHT", "DECIMAL(18,3)", nullable=True),
            c("WEIGHT_UOM_CODE", "VARCHAR(12)", nullable=True),
            c("MAX_VOLUME", "DECIMAL(18,3)", nullable=True),
            c("VOLUME_UOM_CODE", "VARCHAR(12)", nullable=True),
        ),
        ("EQUIPMENT_TYPE_CODE",),
        foreign_keys=(
            fk(("MODE_CODE",), "TRANSPORT_MODE", ("MODE_CODE",)),
            fk(
                ("WEIGHT_UOM_CODE",),
                "UNIT_OF_MEASURE",
                ("UOM_CODE",),
            ),
            fk(
                ("VOLUME_UOM_CODE",),
                "UNIT_OF_MEASURE",
                ("UOM_CODE",),
            ),
        ),
        checks=(
            "MAX_WEIGHT IS NULL OR MAX_WEIGHT > 0",
            "MAX_VOLUME IS NULL OR MAX_VOLUME > 0",
        ),
        tenant_owned=False,
        growth="reference",
    ),
    Table(
        "TENANT",
        "A shipper or 3PL operating boundary with isolated business data.",
        (
            c("TENANT_ID", "BIGINT"),
            c("TENANT_CODE", "VARCHAR(32)"),
            c("TENANT_NAME", "VARCHAR(120)"),
            c("BASE_CURRENCY_CODE", "CHAR(3)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID",),
        uniques=(("TENANT_CODE",),),
        foreign_keys=(
            fk(
                ("BASE_CURRENCY_CODE",),
                "CURRENCY",
                ("CURRENCY_CODE",),
            ),
        ),
        checks=("STATUS_CODE IN ('ACTIVE','SUSPENDED','CLOSED')",),
        tenant_owned=False,
        growth="reference",
    ),
    Table(
        "BUSINESS_PARTY",
        "Tenant-scoped customers, carriers, suppliers, brokers, and agents.",
        tenant_columns(
            c("PARTY_ID", "BIGINT"),
            c("PARTY_CODE", "VARCHAR(40)"),
            c("LEGAL_NAME", "VARCHAR(160)"),
            c("PARTY_TYPE", "VARCHAR(16)"),
            c("TAX_IDENTIFIER", "VARCHAR(40)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "PARTY_ID"),
        uniques=(("TENANT_ID", "PARTY_CODE"),),
        checks=(
            "PARTY_TYPE IN ('CUSTOMER','CARRIER','SUPPLIER','BROKER',"
            "'AGENT','OTHER')",
            "STATUS_CODE IN ('ACTIVE','INACTIVE','BLOCKED')",
        ),
        growth="core",
    ),
    Table(
        "ADDRESS",
        "Version-neutral postal and geospatial addresses.",
        tenant_columns(
            c("ADDRESS_ID", "BIGINT"),
            c("ADDRESS_LINE_1", "VARCHAR(160)"),
            c("ADDRESS_LINE_2", "VARCHAR(160)", nullable=True),
            c("CITY_NAME", "VARCHAR(80)"),
            c("REGION_CODE", "VARCHAR(40)", nullable=True),
            c("POSTAL_CODE", "VARCHAR(24)", nullable=True),
            c("COUNTRY_CODE", "CHAR(2)"),
            c("LATITUDE", "DECIMAL(8,6)", nullable=True),
            c("LONGITUDE", "DECIMAL(9,6)", nullable=True),
            c("TIME_ZONE_NAME", "VARCHAR(64)"),
        ),
        ("TENANT_ID", "ADDRESS_ID"),
        foreign_keys=(
            fk(("COUNTRY_CODE",), "COUNTRY", ("COUNTRY_CODE",)),
        ),
        checks=(
            "LATITUDE IS NULL OR LATITUDE BETWEEN -90 AND 90",
            "LONGITUDE IS NULL OR LONGITUDE BETWEEN -180 AND 180",
        ),
        extra_indexes=(ix("TENANT_ID", "COUNTRY_CODE", "POSTAL_CODE"),),
        growth="core",
    ),
    Table(
        "FACILITY",
        "Warehouses, yards, ports, stores, and cross-dock locations.",
        tenant_columns(
            c("FACILITY_ID", "BIGINT"),
            c("FACILITY_CODE", "VARCHAR(40)"),
            c("FACILITY_NAME", "VARCHAR(120)"),
            c("FACILITY_TYPE", "VARCHAR(20)"),
            c("OPERATING_PARTY_ID", "BIGINT"),
            c("ADDRESS_ID", "BIGINT"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "FACILITY_ID"),
        uniques=(("TENANT_ID", "FACILITY_CODE"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "OPERATING_PARTY_ID"),
                "BUSINESS_PARTY",
                ("TENANT_ID", "PARTY_ID"),
            ),
            fk(
                ("TENANT_ID", "ADDRESS_ID"),
                "ADDRESS",
                ("TENANT_ID", "ADDRESS_ID"),
            ),
        ),
        checks=(
            "FACILITY_TYPE IN ('WAREHOUSE','YARD','PORT','AIRPORT',"
            "'RAIL','STORE','CROSS_DOCK')",
            "STATUS_CODE IN ('ACTIVE','INACTIVE','MAINTENANCE')",
        ),
        extra_indexes=(ix("TENANT_ID", "OPERATING_PARTY_ID"),),
        growth="core",
    ),
    Table(
        "FACILITY_DOCK",
        "Bookable doors, bays, gates, and loading positions.",
        tenant_columns(
            c("FACILITY_ID", "BIGINT"),
            c("DOCK_ID", "BIGINT"),
            c("DOCK_CODE", "VARCHAR(32)"),
            c("DOCK_TYPE", "VARCHAR(16)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "FACILITY_ID", "DOCK_ID"),
        uniques=(("TENANT_ID", "FACILITY_ID", "DOCK_CODE"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "FACILITY_ID"),
                "FACILITY",
                ("TENANT_ID", "FACILITY_ID"),
            ),
        ),
        checks=(
            "DOCK_TYPE IN ('INBOUND','OUTBOUND','BIDIRECTIONAL')",
            "STATUS_CODE IN ('ACTIVE','INACTIVE','MAINTENANCE')",
        ),
        growth="core",
    ),
    Table(
        "CUSTOMER_ACCOUNT",
        "Commercial terms and credit controls for a customer party.",
        tenant_columns(
            c("CUSTOMER_ID", "BIGINT"),
            c("CUSTOMER_NUMBER", "VARCHAR(40)"),
            c("PARTY_ID", "BIGINT"),
            c("BILLING_CURRENCY_CODE", "CHAR(3)"),
            c("PAYMENT_TERMS_DAYS", "SMALLINT"),
            c("CREDIT_LIMIT", "DECIMAL(19,4)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "CUSTOMER_ID"),
        uniques=(
            ("TENANT_ID", "CUSTOMER_NUMBER"),
            ("TENANT_ID", "PARTY_ID"),
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "PARTY_ID"),
                "BUSINESS_PARTY",
                ("TENANT_ID", "PARTY_ID"),
            ),
            fk(
                ("BILLING_CURRENCY_CODE",),
                "CURRENCY",
                ("CURRENCY_CODE",),
            ),
        ),
        checks=(
            "PAYMENT_TERMS_DAYS BETWEEN 0 AND 365",
            "CREDIT_LIMIT >= 0",
            "STATUS_CODE IN ('ACTIVE','ON_HOLD','CLOSED')",
        ),
        growth="core",
    ),
    Table(
        "CARRIER",
        "Carrier master, authority, settlement currency, and status.",
        tenant_columns(
            c("CARRIER_ID", "BIGINT"),
            c("CARRIER_CODE", "VARCHAR(40)"),
            c("PARTY_ID", "BIGINT"),
            c("AUTHORITY_NUMBER", "VARCHAR(60)", nullable=True),
            c("SETTLEMENT_CURRENCY_CODE", "CHAR(3)"),
            c("SAFETY_RATING", "VARCHAR(16)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "CARRIER_ID"),
        uniques=(
            ("TENANT_ID", "CARRIER_CODE"),
            ("TENANT_ID", "PARTY_ID"),
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "PARTY_ID"),
                "BUSINESS_PARTY",
                ("TENANT_ID", "PARTY_ID"),
            ),
            fk(
                ("SETTLEMENT_CURRENCY_CODE",),
                "CURRENCY",
                ("CURRENCY_CODE",),
            ),
        ),
        checks=("STATUS_CODE IN ('ACTIVE','SUSPENDED','CLOSED')",),
        growth="core",
    ),
    Table(
        "SERVICE_LEVEL",
        "Tenant-specific service promises and tolerance windows.",
        tenant_columns(
            c("SERVICE_LEVEL_ID", "BIGINT"),
            c("SERVICE_LEVEL_CODE", "VARCHAR(32)"),
            c("SERVICE_LEVEL_NAME", "VARCHAR(80)"),
            c("TARGET_TRANSIT_HOURS", "INTEGER"),
            c("DELIVERY_TOLERANCE_MIN", "INTEGER"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "SERVICE_LEVEL_ID"),
        uniques=(("TENANT_ID", "SERVICE_LEVEL_CODE"),),
        checks=(
            "TARGET_TRANSIT_HOURS > 0",
            "DELIVERY_TOLERANCE_MIN >= 0",
            "STATUS_CODE IN ('ACTIVE','INACTIVE')",
        ),
        growth="core",
    ),
    Table(
        "PRODUCT",
        "Customer-owned SKU master with handling and valuation attributes.",
        tenant_columns(
            c("PRODUCT_ID", "BIGINT"),
            c("CUSTOMER_ID", "BIGINT"),
            c("SKU_CODE", "VARCHAR(64)"),
            c("PRODUCT_NAME", "VARCHAR(160)"),
            c("BASE_UOM_CODE", "VARCHAR(12)"),
            c("UNIT_WEIGHT", "DECIMAL(18,3)", nullable=True),
            c("WEIGHT_UOM_CODE", "VARCHAR(12)", nullable=True),
            c("UNIT_VOLUME", "DECIMAL(18,3)", nullable=True),
            c("VOLUME_UOM_CODE", "VARCHAR(12)", nullable=True),
            c("HAZMAT_CODE", "VARCHAR(24)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "PRODUCT_ID"),
        uniques=(("TENANT_ID", "CUSTOMER_ID", "SKU_CODE"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CUSTOMER_ID"),
                "CUSTOMER_ACCOUNT",
                ("TENANT_ID", "CUSTOMER_ID"),
            ),
            fk(
                ("BASE_UOM_CODE",),
                "UNIT_OF_MEASURE",
                ("UOM_CODE",),
            ),
            fk(
                ("WEIGHT_UOM_CODE",),
                "UNIT_OF_MEASURE",
                ("UOM_CODE",),
            ),
            fk(
                ("VOLUME_UOM_CODE",),
                "UNIT_OF_MEASURE",
                ("UOM_CODE",),
            ),
        ),
        checks=(
            "UNIT_WEIGHT IS NULL OR UNIT_WEIGHT > 0",
            "UNIT_VOLUME IS NULL OR UNIT_VOLUME > 0",
            "STATUS_CODE IN ('ACTIVE','INACTIVE','DISCONTINUED')",
        ),
        growth="core",
    ),
    Table(
        "LANE",
        "A priced origin-to-destination facility corridor.",
        tenant_columns(
            c("LANE_ID", "BIGINT"),
            c("LANE_CODE", "VARCHAR(40)"),
            c("ORIGIN_FACILITY_ID", "BIGINT"),
            c("DESTINATION_FACILITY_ID", "BIGINT"),
            c("MODE_CODE", "VARCHAR(12)"),
            c("DISTANCE", "DECIMAL(18,3)", nullable=True),
            c("DISTANCE_UOM_CODE", "VARCHAR(12)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "LANE_ID"),
        uniques=(("TENANT_ID", "LANE_CODE"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "ORIGIN_FACILITY_ID"),
                "FACILITY",
                ("TENANT_ID", "FACILITY_ID"),
            ),
            fk(
                ("TENANT_ID", "DESTINATION_FACILITY_ID"),
                "FACILITY",
                ("TENANT_ID", "FACILITY_ID"),
            ),
            fk(("MODE_CODE",), "TRANSPORT_MODE", ("MODE_CODE",)),
            fk(
                ("DISTANCE_UOM_CODE",),
                "UNIT_OF_MEASURE",
                ("UOM_CODE",),
            ),
        ),
        checks=(
            "ORIGIN_FACILITY_ID <> DESTINATION_FACILITY_ID",
            "DISTANCE IS NULL OR DISTANCE > 0",
            "STATUS_CODE IN ('ACTIVE','INACTIVE')",
        ),
        growth="core",
    ),
    Table(
        "RATE_CONTRACT",
        "Versioned commercial agreement with a customer or carrier.",
        tenant_columns(
            c("RATE_CONTRACT_ID", "BIGINT"),
            c("CONTRACT_NUMBER", "VARCHAR(48)"),
            c("CONTRACT_SIDE", "CHAR(1)"),
            c("CUSTOMER_ID", "BIGINT", nullable=True),
            c("CARRIER_ID", "BIGINT", nullable=True),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("VALID_FROM", "DATE"),
            c("VALID_TO", "DATE"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "RATE_CONTRACT_ID"),
        uniques=(("TENANT_ID", "CONTRACT_NUMBER"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CUSTOMER_ID"),
                "CUSTOMER_ACCOUNT",
                ("TENANT_ID", "CUSTOMER_ID"),
            ),
            fk(
                ("TENANT_ID", "CARRIER_ID"),
                "CARRIER",
                ("TENANT_ID", "CARRIER_ID"),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
        ),
        checks=(
            "VALID_FROM < VALID_TO",
            "STATUS_CODE IN ('DRAFT','ACTIVE','EXPIRED','CANCELLED')",
            "((CONTRACT_SIDE = 'C' AND CUSTOMER_ID IS NOT NULL AND "
            "CARRIER_ID IS NULL) OR (CONTRACT_SIDE = 'P' AND "
            "CARRIER_ID IS NOT NULL AND CUSTOMER_ID IS NULL))",
        ),
        extra_indexes=(
            ix("TENANT_ID", "CUSTOMER_ID", "VALID_FROM"),
            ix("TENANT_ID", "CARRIER_ID", "VALID_FROM"),
        ),
        growth="core",
    ),
    Table(
        "RATE_RULE",
        "Effective-dated pricing component for lane and service choices.",
        tenant_columns(
            c("RATE_CONTRACT_ID", "BIGINT"),
            c("RULE_NO", "INTEGER"),
            c("CHARGE_CODE", "VARCHAR(32)"),
            c("LANE_ID", "BIGINT", nullable=True),
            c("SERVICE_LEVEL_ID", "BIGINT", nullable=True),
            c("EQUIPMENT_TYPE_CODE", "VARCHAR(20)", nullable=True),
            c("BASIS_CODE", "VARCHAR(16)"),
            c("RATE_AMOUNT", "DECIMAL(19,6)"),
            c("MINIMUM_AMOUNT", "DECIMAL(19,4)"),
            c("VALID_FROM", "DATE"),
            c("VALID_TO", "DATE"),
        ),
        ("TENANT_ID", "RATE_CONTRACT_ID", "RULE_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "RATE_CONTRACT_ID"),
                "RATE_CONTRACT",
                ("TENANT_ID", "RATE_CONTRACT_ID"),
            ),
            fk(
                ("TENANT_ID", "LANE_ID"),
                "LANE",
                ("TENANT_ID", "LANE_ID"),
            ),
            fk(
                ("TENANT_ID", "SERVICE_LEVEL_ID"),
                "SERVICE_LEVEL",
                ("TENANT_ID", "SERVICE_LEVEL_ID"),
            ),
            fk(
                ("EQUIPMENT_TYPE_CODE",),
                "EQUIPMENT_TYPE",
                ("EQUIPMENT_TYPE_CODE",),
            ),
        ),
        checks=(
            "BASIS_CODE IN ('FLAT','DISTANCE','WEIGHT','VOLUME','UNIT',"
            "'TIME')",
            "RATE_AMOUNT >= 0",
            "MINIMUM_AMOUNT >= 0",
            "VALID_FROM < VALID_TO",
        ),
        extra_indexes=(ix("TENANT_ID", "LANE_ID", "VALID_FROM"),),
        growth="core",
    ),
    Table(
        "STORAGE_LOCATION",
        "Addressable warehouse bin, zone, staging, or dock location.",
        tenant_columns(
            c("FACILITY_ID", "BIGINT"),
            c("LOCATION_ID", "BIGINT"),
            c("LOCATION_CODE", "VARCHAR(48)"),
            c("LOCATION_TYPE", "VARCHAR(20)"),
            c("PARENT_LOCATION_ID", "BIGINT", nullable=True),
            c("CAPACITY_QUANTITY", "DECIMAL(18,3)", nullable=True),
            c("CAPACITY_UOM_CODE", "VARCHAR(12)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "FACILITY_ID", "LOCATION_ID"),
        uniques=(("TENANT_ID", "FACILITY_ID", "LOCATION_CODE"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "FACILITY_ID"),
                "FACILITY",
                ("TENANT_ID", "FACILITY_ID"),
            ),
            fk(
                ("TENANT_ID", "FACILITY_ID", "PARENT_LOCATION_ID"),
                "STORAGE_LOCATION",
                ("TENANT_ID", "FACILITY_ID", "LOCATION_ID"),
            ),
            fk(
                ("CAPACITY_UOM_CODE",),
                "UNIT_OF_MEASURE",
                ("UOM_CODE",),
            ),
        ),
        checks=(
            "LOCATION_TYPE IN ('ZONE','BIN','STAGING','DOCK','YARD',"
            "'QUARANTINE')",
            "CAPACITY_QUANTITY IS NULL OR CAPACITY_QUANTITY > 0",
            "PARENT_LOCATION_ID IS NULL OR "
            "PARENT_LOCATION_ID <> LOCATION_ID",
            "STATUS_CODE IN ('ACTIVE','BLOCKED','INACTIVE')",
        ),
        growth="core",
    ),
    Table(
        "INVENTORY_LOT",
        "Traceable product lot or serial grouping and shelf-life dates.",
        tenant_columns(
            c("LOT_ID", "BIGINT"),
            c("PRODUCT_ID", "BIGINT"),
            c("LOT_NUMBER", "VARCHAR(64)"),
            c("MANUFACTURED_DATE", "DATE", nullable=True),
            c("EXPIRATION_DATE", "DATE", nullable=True),
            c("COUNTRY_OF_ORIGIN", "CHAR(2)", nullable=True),
            c("QUALITY_STATUS", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "LOT_ID"),
        uniques=(
            ("TENANT_ID", "PRODUCT_ID", "LOT_NUMBER"),
            ("TENANT_ID", "LOT_ID", "PRODUCT_ID"),
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "PRODUCT_ID"),
                "PRODUCT",
                ("TENANT_ID", "PRODUCT_ID"),
            ),
            fk(
                ("COUNTRY_OF_ORIGIN",),
                "COUNTRY",
                ("COUNTRY_CODE",),
            ),
        ),
        checks=(
            "MANUFACTURED_DATE IS NULL OR EXPIRATION_DATE IS NULL OR "
            "MANUFACTURED_DATE <= EXPIRATION_DATE",
            "QUALITY_STATUS IN ('AVAILABLE','HOLD','REJECTED','EXPIRED')",
        ),
        growth="core",
    ),
    Table(
        "INVENTORY_BALANCE",
        "Materialized stock position; movements remain the audit authority.",
        tenant_columns(
            c("FACILITY_ID", "BIGINT"),
            c("LOCATION_ID", "BIGINT"),
            c("PRODUCT_ID", "BIGINT"),
            c("LOT_ID", "BIGINT"),
            c("ON_HAND_QUANTITY", "DECIMAL(18,3)"),
            c("RESERVED_QUANTITY", "DECIMAL(18,3)"),
            c("DAMAGED_QUANTITY", "DECIMAL(18,3)"),
            c("UOM_CODE", "VARCHAR(12)"),
            c("VERSION_NO", "INTEGER"),
        ),
        (
            "TENANT_ID",
            "FACILITY_ID",
            "LOCATION_ID",
            "PRODUCT_ID",
            "LOT_ID",
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "FACILITY_ID", "LOCATION_ID"),
                "STORAGE_LOCATION",
                ("TENANT_ID", "FACILITY_ID", "LOCATION_ID"),
            ),
            fk(
                ("TENANT_ID", "LOT_ID", "PRODUCT_ID"),
                "INVENTORY_LOT",
                ("TENANT_ID", "LOT_ID", "PRODUCT_ID"),
            ),
            fk(("UOM_CODE",), "UNIT_OF_MEASURE", ("UOM_CODE",)),
        ),
        checks=(
            "ON_HAND_QUANTITY >= 0",
            "RESERVED_QUANTITY >= 0",
            "DAMAGED_QUANTITY >= 0",
            "RESERVED_QUANTITY + DAMAGED_QUANTITY <= ON_HAND_QUANTITY",
            "VERSION_NO > 0",
        ),
        extra_indexes=(
            ix("TENANT_ID", "PRODUCT_ID", "FACILITY_ID"),
        ),
        growth="high",
    ),
    Table(
        "FULFILLMENT_ORDER",
        "Inbound, outbound, transfer, or return demand from a customer.",
        tenant_columns(
            c("ORDER_ID", "BIGINT"),
            c("CUSTOMER_ID", "BIGINT"),
            c("ORDER_NUMBER", "VARCHAR(48)"),
            c("EXTERNAL_ORDER_ID", "VARCHAR(80)"),
            c("ORDER_TYPE", "VARCHAR(16)"),
            c("PRIORITY_CODE", "VARCHAR(12)"),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("REQUESTED_SHIP_AT", "TIMESTAMP(6)", nullable=True),
            c("REQUESTED_DELIVERY_AT", "TIMESTAMP(6)", nullable=True),
            c("STATUS_CODE", "VARCHAR(20)"),
        ),
        ("TENANT_ID", "ORDER_ID"),
        uniques=(
            ("TENANT_ID", "CUSTOMER_ID", "ORDER_NUMBER"),
            ("TENANT_ID", "CUSTOMER_ID", "EXTERNAL_ORDER_ID"),
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CUSTOMER_ID"),
                "CUSTOMER_ACCOUNT",
                ("TENANT_ID", "CUSTOMER_ID"),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
        ),
        checks=(
            "ORDER_TYPE IN ('INBOUND','OUTBOUND','TRANSFER','RETURN')",
            "PRIORITY_CODE IN ('LOW','NORMAL','HIGH','EXPEDITE')",
            "REQUESTED_SHIP_AT IS NULL OR REQUESTED_DELIVERY_AT IS NULL "
            "OR REQUESTED_SHIP_AT <= REQUESTED_DELIVERY_AT",
            "STATUS_CODE IN ('DRAFT', 'RELEASED', 'ALLOCATED', "
            "'IN_TRANSIT', 'COMPLETED', 'CANCELLED')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "STATUS_CODE", "REQUESTED_SHIP_AT"),
        ),
        growth="high",
    ),
    Table(
        "ORDER_STOP",
        "Ordered pickup and delivery intent for a fulfillment order.",
        tenant_columns(
            c("ORDER_ID", "BIGINT"),
            c("STOP_NO", "INTEGER"),
            c("STOP_TYPE", "VARCHAR(12)"),
            c("FACILITY_ID", "BIGINT", nullable=True),
            c("ADDRESS_ID", "BIGINT"),
            c("WINDOW_START_AT", "TIMESTAMP(6)"),
            c("WINDOW_END_AT", "TIMESTAMP(6)"),
            c("CONTACT_NAME", "VARCHAR(100)", nullable=True),
            c("CONTACT_PHONE", "VARCHAR(32)", nullable=True),
        ),
        ("TENANT_ID", "ORDER_ID", "STOP_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "ORDER_ID"),
                "FULFILLMENT_ORDER",
                ("TENANT_ID", "ORDER_ID"),
            ),
            fk(
                ("TENANT_ID", "FACILITY_ID"),
                "FACILITY",
                ("TENANT_ID", "FACILITY_ID"),
            ),
            fk(
                ("TENANT_ID", "ADDRESS_ID"),
                "ADDRESS",
                ("TENANT_ID", "ADDRESS_ID"),
            ),
        ),
        checks=(
            "STOP_NO > 0",
            "STOP_TYPE IN ('PICKUP','DELIVERY','RETURN')",
            "WINDOW_START_AT < WINDOW_END_AT",
        ),
        extra_indexes=(ix("TENANT_ID", "FACILITY_ID", "WINDOW_START_AT"),),
        growth="high",
    ),
    Table(
        "ORDER_LINE",
        "Demand quantity and declared value for one product.",
        tenant_columns(
            c("ORDER_ID", "BIGINT"),
            c("LINE_NO", "INTEGER"),
            c("PRODUCT_ID", "BIGINT"),
            c("ORDERED_QUANTITY", "DECIMAL(18,3)"),
            c("ALLOCATED_QUANTITY", "DECIMAL(18,3)"),
            c("SHIPPED_QUANTITY", "DECIMAL(18,3)"),
            c("UOM_CODE", "VARCHAR(12)"),
            c("UNIT_VALUE", "DECIMAL(19,4)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "ORDER_ID", "LINE_NO"),
        uniques=(("TENANT_ID", "ORDER_ID", "LINE_NO", "PRODUCT_ID"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "ORDER_ID"),
                "FULFILLMENT_ORDER",
                ("TENANT_ID", "ORDER_ID"),
            ),
            fk(
                ("TENANT_ID", "PRODUCT_ID"),
                "PRODUCT",
                ("TENANT_ID", "PRODUCT_ID"),
            ),
            fk(("UOM_CODE",), "UNIT_OF_MEASURE", ("UOM_CODE",)),
        ),
        checks=(
            "LINE_NO > 0",
            "ORDERED_QUANTITY > 0",
            "ALLOCATED_QUANTITY BETWEEN 0 AND ORDERED_QUANTITY",
            "SHIPPED_QUANTITY BETWEEN 0 AND ORDERED_QUANTITY",
            "UNIT_VALUE >= 0",
            "STATUS_CODE IN ('OPEN','ALLOCATED','SHIPPED','CLOSED',"
            "'CANCELLED')",
        ),
        extra_indexes=(ix("TENANT_ID", "PRODUCT_ID", "STATUS_CODE"),),
        growth="high",
    ),
    Table(
        "INVENTORY_RESERVATION",
        "Allocation of a specific stock balance to an order line.",
        tenant_columns(
            c("RESERVATION_ID", "BIGINT"),
            c("ORDER_ID", "BIGINT"),
            c("ORDER_LINE_NO", "INTEGER"),
            c("FACILITY_ID", "BIGINT"),
            c("LOCATION_ID", "BIGINT"),
            c("PRODUCT_ID", "BIGINT"),
            c("LOT_ID", "BIGINT"),
            c("RESERVED_QUANTITY", "DECIMAL(18,3)"),
            c("UOM_CODE", "VARCHAR(12)"),
            c("EXPIRES_AT", "TIMESTAMP(6)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "RESERVATION_ID"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "ORDER_ID", "ORDER_LINE_NO", "PRODUCT_ID"),
                "ORDER_LINE",
                ("TENANT_ID", "ORDER_ID", "LINE_NO", "PRODUCT_ID"),
            ),
            fk(
                (
                    "TENANT_ID",
                    "FACILITY_ID",
                    "LOCATION_ID",
                    "PRODUCT_ID",
                    "LOT_ID",
                ),
                "INVENTORY_BALANCE",
                (
                    "TENANT_ID",
                    "FACILITY_ID",
                    "LOCATION_ID",
                    "PRODUCT_ID",
                    "LOT_ID",
                ),
            ),
            fk(("UOM_CODE",), "UNIT_OF_MEASURE", ("UOM_CODE",)),
        ),
        checks=(
            "RESERVED_QUANTITY > 0",
            "STATUS_CODE IN ('ACTIVE','CONSUMED','RELEASED','EXPIRED')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "ORDER_ID", "ORDER_LINE_NO"),
            ix("TENANT_ID", "STATUS_CODE", "EXPIRES_AT"),
        ),
        growth="high",
    ),
    Table(
        "INVENTORY_MOVEMENT",
        "Append-only receipt, move, issue, adjustment, or damage ledger.",
        tenant_columns(
            c("MOVEMENT_ID", "BIGINT"),
            c("PRODUCT_ID", "BIGINT"),
            c("LOT_ID", "BIGINT"),
            c("FROM_FACILITY_ID", "BIGINT", nullable=True),
            c("FROM_LOCATION_ID", "BIGINT", nullable=True),
            c("TO_FACILITY_ID", "BIGINT", nullable=True),
            c("TO_LOCATION_ID", "BIGINT", nullable=True),
            c("MOVEMENT_TYPE", "VARCHAR(16)"),
            c("QUANTITY", "DECIMAL(18,3)"),
            c("UOM_CODE", "VARCHAR(12)"),
            c("SOURCE_TYPE", "VARCHAR(24)"),
            c("SOURCE_ID", "VARCHAR(80)"),
            c("OCCURRED_AT", "TIMESTAMP(6)"),
            c("IDEMPOTENCY_KEY", "VARCHAR(80)"),
        ),
        ("TENANT_ID", "MOVEMENT_ID"),
        uniques=(("TENANT_ID", "IDEMPOTENCY_KEY"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "LOT_ID", "PRODUCT_ID"),
                "INVENTORY_LOT",
                ("TENANT_ID", "LOT_ID", "PRODUCT_ID"),
            ),
            fk(
                ("TENANT_ID", "FROM_FACILITY_ID", "FROM_LOCATION_ID"),
                "STORAGE_LOCATION",
                ("TENANT_ID", "FACILITY_ID", "LOCATION_ID"),
            ),
            fk(
                ("TENANT_ID", "TO_FACILITY_ID", "TO_LOCATION_ID"),
                "STORAGE_LOCATION",
                ("TENANT_ID", "FACILITY_ID", "LOCATION_ID"),
            ),
            fk(("UOM_CODE",), "UNIT_OF_MEASURE", ("UOM_CODE",)),
        ),
        checks=(
            "MOVEMENT_TYPE IN ('RECEIPT','MOVE','ISSUE','ADJUSTMENT',"
            "'DAMAGE','RETURN')",
            "QUANTITY > 0",
            "((FROM_FACILITY_ID IS NULL AND FROM_LOCATION_ID IS NULL) "
            "OR (FROM_FACILITY_ID IS NOT NULL AND "
            "FROM_LOCATION_ID IS NOT NULL))",
            "((TO_FACILITY_ID IS NULL AND TO_LOCATION_ID IS NULL) OR "
            "(TO_FACILITY_ID IS NOT NULL AND "
            "TO_LOCATION_ID IS NOT NULL))",
            "FROM_LOCATION_ID IS NOT NULL OR TO_LOCATION_ID IS NOT NULL",
            "FROM_LOCATION_ID IS NULL OR TO_LOCATION_ID IS NULL OR "
            "FROM_FACILITY_ID <> TO_FACILITY_ID OR "
            "FROM_LOCATION_ID <> TO_LOCATION_ID",
        ),
        extra_indexes=(
            ix("TENANT_ID", "PRODUCT_ID", "LOT_ID", "OCCURRED_AT"),
            ix("TENANT_ID", "SOURCE_TYPE", "SOURCE_ID"),
        ),
        growth="high",
        append_only=True,
    ),
    Table(
        "SHIPMENT",
        "A customer movement plan spanning one or more transport legs.",
        tenant_columns(
            c("SHIPMENT_ID", "BIGINT"),
            c("SHIPMENT_NUMBER", "VARCHAR(48)"),
            c("CUSTOMER_ID", "BIGINT"),
            c("MODE_CODE", "VARCHAR(12)"),
            c("SERVICE_LEVEL_ID", "BIGINT"),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("PLANNED_PICKUP_AT", "TIMESTAMP(6)"),
            c("PLANNED_DELIVERY_AT", "TIMESTAMP(6)"),
            c("TOTAL_WEIGHT", "DECIMAL(18,3)"),
            c("WEIGHT_UOM_CODE", "VARCHAR(12)"),
            c("TOTAL_VOLUME", "DECIMAL(18,3)", nullable=True),
            c("VOLUME_UOM_CODE", "VARCHAR(12)", nullable=True),
            c("STATUS_CODE", "VARCHAR(20)"),
        ),
        ("TENANT_ID", "SHIPMENT_ID"),
        uniques=(("TENANT_ID", "SHIPMENT_NUMBER"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CUSTOMER_ID"),
                "CUSTOMER_ACCOUNT",
                ("TENANT_ID", "CUSTOMER_ID"),
            ),
            fk(("MODE_CODE",), "TRANSPORT_MODE", ("MODE_CODE",)),
            fk(
                ("TENANT_ID", "SERVICE_LEVEL_ID"),
                "SERVICE_LEVEL",
                ("TENANT_ID", "SERVICE_LEVEL_ID"),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
            fk(
                ("WEIGHT_UOM_CODE",),
                "UNIT_OF_MEASURE",
                ("UOM_CODE",),
            ),
            fk(
                ("VOLUME_UOM_CODE",),
                "UNIT_OF_MEASURE",
                ("UOM_CODE",),
            ),
        ),
        checks=(
            "PLANNED_PICKUP_AT <= PLANNED_DELIVERY_AT",
            "TOTAL_WEIGHT >= 0",
            "TOTAL_VOLUME IS NULL OR TOTAL_VOLUME >= 0",
            "STATUS_CODE IN ('PLANNED', 'TENDERING', 'BOOKED', "
            "'IN_TRANSIT', 'DELIVERED', 'CANCELLED', 'CLOSED')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "CUSTOMER_ID", "PLANNED_PICKUP_AT"),
            ix("TENANT_ID", "STATUS_CODE", "PLANNED_DELIVERY_AT"),
        ),
        growth="high",
    ),
    Table(
        "SHIPMENT_ORDER",
        "Many-to-many allocation of customer orders to shipments.",
        tenant_columns(
            c("SHIPMENT_ID", "BIGINT"),
            c("ORDER_ID", "BIGINT"),
        ),
        ("TENANT_ID", "SHIPMENT_ID", "ORDER_ID"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID"),
                "SHIPMENT",
                ("TENANT_ID", "SHIPMENT_ID"),
            ),
            fk(
                ("TENANT_ID", "ORDER_ID"),
                "FULFILLMENT_ORDER",
                ("TENANT_ID", "ORDER_ID"),
            ),
        ),
        extra_indexes=(ix("TENANT_ID", "ORDER_ID", "SHIPMENT_ID"),),
        growth="high",
    ),
    Table(
        "SHIPMENT_ITEM",
        "Quantity of an order line and lot assigned to a shipment.",
        tenant_columns(
            c("SHIPMENT_ID", "BIGINT"),
            c("SHIPMENT_ITEM_NO", "INTEGER"),
            c("ORDER_ID", "BIGINT"),
            c("ORDER_LINE_NO", "INTEGER"),
            c("PRODUCT_ID", "BIGINT"),
            c("LOT_ID", "BIGINT", nullable=True),
            c("QUANTITY", "DECIMAL(18,3)"),
            c("UOM_CODE", "VARCHAR(12)"),
            c("DECLARED_VALUE", "DECIMAL(19,4)"),
        ),
        ("TENANT_ID", "SHIPMENT_ID", "SHIPMENT_ITEM_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID"),
                "SHIPMENT",
                ("TENANT_ID", "SHIPMENT_ID"),
            ),
            fk(
                ("TENANT_ID", "ORDER_ID", "ORDER_LINE_NO", "PRODUCT_ID"),
                "ORDER_LINE",
                ("TENANT_ID", "ORDER_ID", "LINE_NO", "PRODUCT_ID"),
            ),
            fk(
                ("TENANT_ID", "LOT_ID", "PRODUCT_ID"),
                "INVENTORY_LOT",
                ("TENANT_ID", "LOT_ID", "PRODUCT_ID"),
            ),
            fk(("UOM_CODE",), "UNIT_OF_MEASURE", ("UOM_CODE",)),
        ),
        checks=(
            "SHIPMENT_ITEM_NO > 0",
            "QUANTITY > 0",
            "DECLARED_VALUE >= 0",
        ),
        extra_indexes=(
            ix("TENANT_ID", "ORDER_ID", "ORDER_LINE_NO"),
            ix("TENANT_ID", "PRODUCT_ID", "LOT_ID"),
        ),
        growth="high",
    ),
    Table(
        "SHIPMENT_STOP",
        "Immutable address snapshot and operational window for one stop.",
        tenant_columns(
            c("SHIPMENT_ID", "BIGINT"),
            c("STOP_NO", "INTEGER"),
            c("STOP_TYPE", "VARCHAR(12)"),
            c("FACILITY_ID", "BIGINT", nullable=True),
            c("ADDRESS_ID", "BIGINT", nullable=True),
            c("LOCATION_NAME", "VARCHAR(120)"),
            c("ADDRESS_TEXT", "VARCHAR(500)"),
            c("COUNTRY_CODE", "CHAR(2)"),
            c("TIME_ZONE_NAME", "VARCHAR(64)"),
            c("PLANNED_ARRIVAL_AT", "TIMESTAMP(6)"),
            c("PLANNED_DEPARTURE_AT", "TIMESTAMP(6)"),
            c("ACTUAL_ARRIVAL_AT", "TIMESTAMP(6)", nullable=True),
            c("ACTUAL_DEPARTURE_AT", "TIMESTAMP(6)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "SHIPMENT_ID", "STOP_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID"),
                "SHIPMENT",
                ("TENANT_ID", "SHIPMENT_ID"),
            ),
            fk(
                ("TENANT_ID", "FACILITY_ID"),
                "FACILITY",
                ("TENANT_ID", "FACILITY_ID"),
            ),
            fk(
                ("TENANT_ID", "ADDRESS_ID"),
                "ADDRESS",
                ("TENANT_ID", "ADDRESS_ID"),
            ),
            fk(("COUNTRY_CODE",), "COUNTRY", ("COUNTRY_CODE",)),
        ),
        checks=(
            "STOP_NO > 0",
            "STOP_TYPE IN ('PICKUP','DELIVERY','TRANSFER','CUSTOMS')",
            "PLANNED_ARRIVAL_AT <= PLANNED_DEPARTURE_AT",
            "ACTUAL_ARRIVAL_AT IS NULL OR ACTUAL_DEPARTURE_AT IS NULL "
            "OR ACTUAL_ARRIVAL_AT <= ACTUAL_DEPARTURE_AT",
            "STATUS_CODE IN ('PLANNED','ARRIVED','WORKING','DEPARTED',"
            "'SKIPPED')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "FACILITY_ID", "PLANNED_ARRIVAL_AT"),
        ),
        growth="high",
    ),
    Table(
        "SHIPMENT_LEG",
        "A mode-specific movement between two ordered shipment stops.",
        tenant_columns(
            c("SHIPMENT_ID", "BIGINT"),
            c("LEG_NO", "INTEGER"),
            c("FROM_STOP_NO", "INTEGER"),
            c("TO_STOP_NO", "INTEGER"),
            c("MODE_CODE", "VARCHAR(12)"),
            c("PLANNED_DEPARTURE_AT", "TIMESTAMP(6)"),
            c("PLANNED_ARRIVAL_AT", "TIMESTAMP(6)"),
            c("ACTUAL_DEPARTURE_AT", "TIMESTAMP(6)", nullable=True),
            c("ACTUAL_ARRIVAL_AT", "TIMESTAMP(6)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "SHIPMENT_ID", "LEG_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID"),
                "SHIPMENT",
                ("TENANT_ID", "SHIPMENT_ID"),
            ),
            fk(
                ("TENANT_ID", "SHIPMENT_ID", "FROM_STOP_NO"),
                "SHIPMENT_STOP",
                ("TENANT_ID", "SHIPMENT_ID", "STOP_NO"),
            ),
            fk(
                ("TENANT_ID", "SHIPMENT_ID", "TO_STOP_NO"),
                "SHIPMENT_STOP",
                ("TENANT_ID", "SHIPMENT_ID", "STOP_NO"),
            ),
            fk(("MODE_CODE",), "TRANSPORT_MODE", ("MODE_CODE",)),
        ),
        checks=(
            "LEG_NO > 0",
            "FROM_STOP_NO < TO_STOP_NO",
            "PLANNED_DEPARTURE_AT <= PLANNED_ARRIVAL_AT",
            "ACTUAL_DEPARTURE_AT IS NULL OR ACTUAL_ARRIVAL_AT IS NULL "
            "OR ACTUAL_DEPARTURE_AT <= ACTUAL_ARRIVAL_AT",
            "STATUS_CODE IN ('PLANNED', 'TENDERING', 'ASSIGNED', "
            "'IN_TRANSIT', 'COMPLETED', 'CANCELLED')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "STATUS_CODE", "PLANNED_DEPARTURE_AT"),
        ),
        growth="high",
    ),
    Table(
        "CARRIER_TENDER",
        "Append-only carrier offer attempts and responses for a leg.",
        tenant_columns(
            c("SHIPMENT_ID", "BIGINT"),
            c("LEG_NO", "INTEGER"),
            c("TENDER_ATTEMPT_NO", "INTEGER"),
            c("CARRIER_ID", "BIGINT"),
            c("RATE_CONTRACT_ID", "BIGINT", nullable=True),
            c("OFFER_AMOUNT", "DECIMAL(19,4)"),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("OFFERED_AT", "TIMESTAMP(6)"),
            c("RESPONSE_DUE_AT", "TIMESTAMP(6)"),
            c("RESPONDED_AT", "TIMESTAMP(6)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
            c("RESPONSE_REASON", "VARCHAR(240)", nullable=True),
        ),
        (
            "TENANT_ID",
            "SHIPMENT_ID",
            "LEG_NO",
            "TENDER_ATTEMPT_NO",
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID", "LEG_NO"),
                "SHIPMENT_LEG",
                ("TENANT_ID", "SHIPMENT_ID", "LEG_NO"),
            ),
            fk(
                ("TENANT_ID", "CARRIER_ID"),
                "CARRIER",
                ("TENANT_ID", "CARRIER_ID"),
            ),
            fk(
                ("TENANT_ID", "RATE_CONTRACT_ID"),
                "RATE_CONTRACT",
                ("TENANT_ID", "RATE_CONTRACT_ID"),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
        ),
        checks=(
            "TENDER_ATTEMPT_NO > 0",
            "OFFER_AMOUNT >= 0",
            "OFFERED_AT <= RESPONSE_DUE_AT",
            "RESPONDED_AT IS NULL OR RESPONDED_AT >= OFFERED_AT",
            "STATUS_CODE IN ('OFFERED','ACCEPTED','DECLINED','EXPIRED',"
            "'WITHDRAWN')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "CARRIER_ID", "OFFERED_AT"),
            ix("TENANT_ID", "STATUS_CODE", "RESPONSE_DUE_AT"),
        ),
        growth="high",
    ),
    Table(
        "TRANSPORT_LOAD",
        "Carrier movement unit consolidating one or more shipment legs.",
        tenant_columns(
            c("LOAD_ID", "BIGINT"),
            c("LOAD_NUMBER", "VARCHAR(48)"),
            c("CARRIER_ID", "BIGINT"),
            c("EQUIPMENT_TYPE_CODE", "VARCHAR(20)"),
            c("PLANNED_DEPARTURE_AT", "TIMESTAMP(6)"),
            c("PLANNED_ARRIVAL_AT", "TIMESTAMP(6)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "LOAD_ID"),
        uniques=(("TENANT_ID", "LOAD_NUMBER"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CARRIER_ID"),
                "CARRIER",
                ("TENANT_ID", "CARRIER_ID"),
            ),
            fk(
                ("EQUIPMENT_TYPE_CODE",),
                "EQUIPMENT_TYPE",
                ("EQUIPMENT_TYPE_CODE",),
            ),
        ),
        checks=(
            "PLANNED_DEPARTURE_AT <= PLANNED_ARRIVAL_AT",
            "STATUS_CODE IN ('PLANNED','DISPATCHED','IN_TRANSIT',"
            "'COMPLETED','CANCELLED')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "CARRIER_ID", "PLANNED_DEPARTURE_AT"),
        ),
        growth="high",
    ),
    Table(
        "LOAD_LEG",
        "History of shipment-leg assignments to a transport load.",
        tenant_columns(
            c("LOAD_ID", "BIGINT"),
            c("LOAD_SEQUENCE_NO", "INTEGER"),
            c("SHIPMENT_ID", "BIGINT"),
            c("LEG_NO", "INTEGER"),
            c("ASSIGNMENT_NO", "INTEGER"),
            c("ASSIGNED_AT", "TIMESTAMP(6)"),
            c("UNASSIGNED_AT", "TIMESTAMP(6)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "LOAD_ID", "LOAD_SEQUENCE_NO"),
        uniques=(
            ("TENANT_ID", "SHIPMENT_ID", "LEG_NO", "ASSIGNMENT_NO"),
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "LOAD_ID"),
                "TRANSPORT_LOAD",
                ("TENANT_ID", "LOAD_ID"),
            ),
            fk(
                ("TENANT_ID", "SHIPMENT_ID", "LEG_NO"),
                "SHIPMENT_LEG",
                ("TENANT_ID", "SHIPMENT_ID", "LEG_NO"),
            ),
        ),
        checks=(
            "LOAD_SEQUENCE_NO > 0",
            "ASSIGNMENT_NO > 0",
            "UNASSIGNED_AT IS NULL OR UNASSIGNED_AT >= ASSIGNED_AT",
            "STATUS_CODE IN ('ASSIGNED','UNASSIGNED','COMPLETED')",
        ),
        extra_indexes=(ix("TENANT_ID", "STATUS_CODE", "ASSIGNED_AT"),),
        growth="high",
    ),
    Table(
        "VEHICLE",
        "Carrier-owned tractor, trailer, container, or other asset.",
        tenant_columns(
            c("VEHICLE_ID", "BIGINT"),
            c("CARRIER_ID", "BIGINT"),
            c("UNIT_NUMBER", "VARCHAR(48)"),
            c("EQUIPMENT_TYPE_CODE", "VARCHAR(20)"),
            c("REGISTRATION_NUMBER", "VARCHAR(48)", nullable=True),
            c("REGISTRATION_COUNTRY", "CHAR(2)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "VEHICLE_ID"),
        uniques=(
            ("TENANT_ID", "CARRIER_ID", "UNIT_NUMBER"),
            ("TENANT_ID", "VEHICLE_ID", "CARRIER_ID"),
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CARRIER_ID"),
                "CARRIER",
                ("TENANT_ID", "CARRIER_ID"),
            ),
            fk(
                ("EQUIPMENT_TYPE_CODE",),
                "EQUIPMENT_TYPE",
                ("EQUIPMENT_TYPE_CODE",),
            ),
            fk(
                ("REGISTRATION_COUNTRY",),
                "COUNTRY",
                ("COUNTRY_CODE",),
            ),
        ),
        checks=("STATUS_CODE IN ('AVAILABLE','ASSIGNED','MAINTENANCE',"
                "'RETIRED')",),
        growth="core",
    ),
    Table(
        "DRIVER",
        "Carrier driver identity and license validity.",
        tenant_columns(
            c("DRIVER_ID", "BIGINT"),
            c("CARRIER_ID", "BIGINT"),
            c("DRIVER_NUMBER", "VARCHAR(48)"),
            c("DISPLAY_NAME", "VARCHAR(120)"),
            c("LICENSE_NUMBER", "VARCHAR(64)"),
            c("LICENSE_COUNTRY", "CHAR(2)"),
            c("LICENSE_EXPIRES_ON", "DATE"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "DRIVER_ID"),
        uniques=(
            ("TENANT_ID", "CARRIER_ID", "DRIVER_NUMBER"),
            ("TENANT_ID", "DRIVER_ID", "CARRIER_ID"),
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CARRIER_ID"),
                "CARRIER",
                ("TENANT_ID", "CARRIER_ID"),
            ),
            fk(
                ("LICENSE_COUNTRY",),
                "COUNTRY",
                ("COUNTRY_CODE",),
            ),
        ),
        checks=("STATUS_CODE IN ('AVAILABLE','ASSIGNED','OFF_DUTY',"
                "'SUSPENDED','INACTIVE')",),
        growth="core",
    ),
    Table(
        "LOAD_VEHICLE",
        "Effective-dated vehicle assignments to a transport load.",
        tenant_columns(
            c("LOAD_ID", "BIGINT"),
            c("ASSIGNMENT_NO", "INTEGER"),
            c("CARRIER_ID", "BIGINT"),
            c("VEHICLE_ID", "BIGINT"),
            c("ASSIGNMENT_ROLE", "VARCHAR(16)"),
            c("ASSIGNED_AT", "TIMESTAMP(6)"),
            c("UNASSIGNED_AT", "TIMESTAMP(6)", nullable=True),
        ),
        ("TENANT_ID", "LOAD_ID", "ASSIGNMENT_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "LOAD_ID"),
                "TRANSPORT_LOAD",
                ("TENANT_ID", "LOAD_ID"),
            ),
            fk(
                ("TENANT_ID", "VEHICLE_ID", "CARRIER_ID"),
                "VEHICLE",
                ("TENANT_ID", "VEHICLE_ID", "CARRIER_ID"),
            ),
        ),
        checks=(
            "ASSIGNMENT_NO > 0",
            "ASSIGNMENT_ROLE IN ('TRACTOR','TRAILER','CONTAINER',"
            "'OTHER')",
            "UNASSIGNED_AT IS NULL OR UNASSIGNED_AT >= ASSIGNED_AT",
        ),
        extra_indexes=(ix("TENANT_ID", "VEHICLE_ID", "ASSIGNED_AT"),),
        growth="high",
    ),
    Table(
        "LOAD_DRIVER",
        "Effective-dated primary and relief driver assignments.",
        tenant_columns(
            c("LOAD_ID", "BIGINT"),
            c("ASSIGNMENT_NO", "INTEGER"),
            c("CARRIER_ID", "BIGINT"),
            c("DRIVER_ID", "BIGINT"),
            c("ASSIGNMENT_ROLE", "VARCHAR(16)"),
            c("ASSIGNED_AT", "TIMESTAMP(6)"),
            c("UNASSIGNED_AT", "TIMESTAMP(6)", nullable=True),
        ),
        ("TENANT_ID", "LOAD_ID", "ASSIGNMENT_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "LOAD_ID"),
                "TRANSPORT_LOAD",
                ("TENANT_ID", "LOAD_ID"),
            ),
            fk(
                ("TENANT_ID", "DRIVER_ID", "CARRIER_ID"),
                "DRIVER",
                ("TENANT_ID", "DRIVER_ID", "CARRIER_ID"),
            ),
        ),
        checks=(
            "ASSIGNMENT_NO > 0",
            "ASSIGNMENT_ROLE IN ('PRIMARY','RELIEF','TEAM')",
            "UNASSIGNED_AT IS NULL OR UNASSIGNED_AT >= ASSIGNED_AT",
        ),
        extra_indexes=(ix("TENANT_ID", "DRIVER_ID", "ASSIGNED_AT"),),
        growth="high",
    ),
    Table(
        "APPOINTMENT",
        "Dock appointment for a shipment stop and optional facility door.",
        tenant_columns(
            c("APPOINTMENT_ID", "BIGINT"),
            c("SHIPMENT_ID", "BIGINT"),
            c("STOP_NO", "INTEGER"),
            c("FACILITY_ID", "BIGINT"),
            c("DOCK_ID", "BIGINT", nullable=True),
            c("WINDOW_START_AT", "TIMESTAMP(6)"),
            c("WINDOW_END_AT", "TIMESTAMP(6)"),
            c("CHECKED_IN_AT", "TIMESTAMP(6)", nullable=True),
            c("CHECKED_OUT_AT", "TIMESTAMP(6)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "APPOINTMENT_ID"),
        uniques=(("TENANT_ID", "SHIPMENT_ID", "STOP_NO"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID", "STOP_NO"),
                "SHIPMENT_STOP",
                ("TENANT_ID", "SHIPMENT_ID", "STOP_NO"),
            ),
            fk(
                ("TENANT_ID", "FACILITY_ID", "DOCK_ID"),
                "FACILITY_DOCK",
                ("TENANT_ID", "FACILITY_ID", "DOCK_ID"),
            ),
        ),
        checks=(
            "WINDOW_START_AT < WINDOW_END_AT",
            "CHECKED_IN_AT IS NULL OR CHECKED_OUT_AT IS NULL OR "
            "CHECKED_IN_AT <= CHECKED_OUT_AT",
            "STATUS_CODE IN ('REQUESTED', 'CONFIRMED', 'CHECKED_IN', "
            "'COMPLETED', 'NO_SHOW', 'CANCELLED')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "FACILITY_ID", "WINDOW_START_AT"),
            ix("TENANT_ID", "STATUS_CODE", "WINDOW_START_AT"),
        ),
        growth="high",
    ),
    Table(
        "TRACKING_EVENT",
        "Append-only normalized operational milestone from any source.",
        tenant_columns(
            c("EVENT_ID", "BIGINT"),
            c("SHIPMENT_ID", "BIGINT"),
            c("LEG_NO", "INTEGER", nullable=True),
            c("EVENT_CODE", "VARCHAR(32)"),
            c("EVENT_SOURCE", "VARCHAR(24)"),
            c("SOURCE_EVENT_ID", "VARCHAR(96)"),
            c("OCCURRED_AT", "TIMESTAMP(6)"),
            c("RECEIVED_AT", "TIMESTAMP(6)"),
            c("FACILITY_ID", "BIGINT", nullable=True),
            c("LATITUDE", "DECIMAL(8,6)", nullable=True),
            c("LONGITUDE", "DECIMAL(9,6)", nullable=True),
            c("DETAIL_TEXT", "VARCHAR(500)", nullable=True),
        ),
        ("TENANT_ID", "EVENT_ID"),
        uniques=(("TENANT_ID", "EVENT_SOURCE", "SOURCE_EVENT_ID"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID"),
                "SHIPMENT",
                ("TENANT_ID", "SHIPMENT_ID"),
            ),
            fk(
                ("TENANT_ID", "SHIPMENT_ID", "LEG_NO"),
                "SHIPMENT_LEG",
                ("TENANT_ID", "SHIPMENT_ID", "LEG_NO"),
            ),
            fk(
                ("TENANT_ID", "FACILITY_ID"),
                "FACILITY",
                ("TENANT_ID", "FACILITY_ID"),
            ),
        ),
        checks=(
            "RECEIVED_AT >= OCCURRED_AT",
            "LATITUDE IS NULL OR LATITUDE BETWEEN -90 AND 90",
            "LONGITUDE IS NULL OR LONGITUDE BETWEEN -180 AND 180",
        ),
        extra_indexes=(
            ix("TENANT_ID", "SHIPMENT_ID", "OCCURRED_AT"),
            ix("TENANT_ID", "EVENT_CODE", "OCCURRED_AT"),
        ),
        growth="high",
        append_only=True,
    ),
    Table(
        "SENSOR_READING",
        "Append-only temperature, humidity, shock, and location readings.",
        tenant_columns(
            c("READING_ID", "BIGINT"),
            c("SHIPMENT_ID", "BIGINT"),
            c("DEVICE_IDENTIFIER", "VARCHAR(80)"),
            c("MEASUREMENT_TYPE", "VARCHAR(16)"),
            c("MEASUREMENT_VALUE", "DECIMAL(20,6)"),
            c("UOM_CODE", "VARCHAR(12)"),
            c("MEASURED_AT", "TIMESTAMP(6)"),
            c("RECEIVED_AT", "TIMESTAMP(6)"),
            c("LATITUDE", "DECIMAL(8,6)", nullable=True),
            c("LONGITUDE", "DECIMAL(9,6)", nullable=True),
            c("SOURCE_READING_ID", "VARCHAR(96)"),
        ),
        ("TENANT_ID", "READING_ID"),
        uniques=(
            ("TENANT_ID", "DEVICE_IDENTIFIER", "SOURCE_READING_ID"),
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID"),
                "SHIPMENT",
                ("TENANT_ID", "SHIPMENT_ID"),
            ),
            fk(("UOM_CODE",), "UNIT_OF_MEASURE", ("UOM_CODE",)),
        ),
        checks=(
            "MEASUREMENT_TYPE IN ('TEMPERATURE','HUMIDITY','SHOCK',"
            "'PRESSURE','OTHER')",
            "RECEIVED_AT >= MEASURED_AT",
            "LATITUDE IS NULL OR LATITUDE BETWEEN -90 AND 90",
            "LONGITUDE IS NULL OR LONGITUDE BETWEEN -180 AND 180",
        ),
        extra_indexes=(
            ix("TENANT_ID", "SHIPMENT_ID", "MEASURED_AT"),
            ix("TENANT_ID", "DEVICE_IDENTIFIER", "MEASURED_AT"),
        ),
        growth="high",
        append_only=True,
    ),
    Table(
        "DELIVERY_RECEIPT",
        "Consignee acknowledgement and delivered package counts.",
        tenant_columns(
            c("RECEIPT_ID", "BIGINT"),
            c("SHIPMENT_ID", "BIGINT"),
            c("STOP_NO", "INTEGER"),
            c("RECEIVED_BY_NAME", "VARCHAR(120)"),
            c("DELIVERED_AT", "TIMESTAMP(6)"),
            c("PACKAGE_COUNT", "INTEGER"),
            c("CONDITION_CODE", "VARCHAR(16)"),
            c("NOTES", "VARCHAR(500)", nullable=True),
        ),
        ("TENANT_ID", "RECEIPT_ID"),
        uniques=(("TENANT_ID", "SHIPMENT_ID", "STOP_NO"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID", "STOP_NO"),
                "SHIPMENT_STOP",
                ("TENANT_ID", "SHIPMENT_ID", "STOP_NO"),
            ),
        ),
        checks=(
            "PACKAGE_COUNT >= 0",
            "CONDITION_CODE IN ('GOOD','DAMAGED','SHORT','REFUSED')",
        ),
        growth="high",
        append_only=True,
    ),
    Table(
        "CUSTOMS_ENTRY",
        "Shipment customs declaration and release lifecycle.",
        tenant_columns(
            c("CUSTOMS_ENTRY_ID", "BIGINT"),
            c("SHIPMENT_ID", "BIGINT"),
            c("ENTRY_NUMBER", "VARCHAR(64)"),
            c("BROKER_PARTY_ID", "BIGINT"),
            c("IMPORT_COUNTRY_CODE", "CHAR(2)"),
            c("EXPORT_COUNTRY_CODE", "CHAR(2)"),
            c("DECLARED_VALUE", "DECIMAL(19,4)"),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("FILED_AT", "TIMESTAMP(6)", nullable=True),
            c("RELEASED_AT", "TIMESTAMP(6)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "CUSTOMS_ENTRY_ID"),
        uniques=(("TENANT_ID", "ENTRY_NUMBER"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID"),
                "SHIPMENT",
                ("TENANT_ID", "SHIPMENT_ID"),
            ),
            fk(
                ("TENANT_ID", "BROKER_PARTY_ID"),
                "BUSINESS_PARTY",
                ("TENANT_ID", "PARTY_ID"),
            ),
            fk(
                ("IMPORT_COUNTRY_CODE",),
                "COUNTRY",
                ("COUNTRY_CODE",),
            ),
            fk(
                ("EXPORT_COUNTRY_CODE",),
                "COUNTRY",
                ("COUNTRY_CODE",),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
        ),
        checks=(
            "IMPORT_COUNTRY_CODE <> EXPORT_COUNTRY_CODE",
            "DECLARED_VALUE >= 0",
            "RELEASED_AT IS NULL OR FILED_AT IS NOT NULL",
            "RELEASED_AT IS NULL OR RELEASED_AT >= FILED_AT",
            "STATUS_CODE IN ('DRAFT','FILED','HELD','RELEASED','REJECTED')",
        ),
        extra_indexes=(ix("TENANT_ID", "SHIPMENT_ID"),),
        growth="high",
    ),
    Table(
        "EXCEPTION_CASE",
        "Operational disruption tied to an order, shipment, or both.",
        tenant_columns(
            c("EXCEPTION_ID", "BIGINT"),
            c("ORDER_ID", "BIGINT", nullable=True),
            c("SHIPMENT_ID", "BIGINT", nullable=True),
            c("EXCEPTION_TYPE", "VARCHAR(24)"),
            c("SEVERITY_CODE", "VARCHAR(12)"),
            c("OPENED_AT", "TIMESTAMP(6)"),
            c("RESOLVED_AT", "TIMESTAMP(6)", nullable=True),
            c("OWNER_IDENTIFIER", "VARCHAR(80)", nullable=True),
            c("SUMMARY_TEXT", "VARCHAR(500)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "EXCEPTION_ID"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "ORDER_ID"),
                "FULFILLMENT_ORDER",
                ("TENANT_ID", "ORDER_ID"),
            ),
            fk(
                ("TENANT_ID", "SHIPMENT_ID"),
                "SHIPMENT",
                ("TENANT_ID", "SHIPMENT_ID"),
            ),
        ),
        checks=(
            "ORDER_ID IS NOT NULL OR SHIPMENT_ID IS NOT NULL",
            "SEVERITY_CODE IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            "RESOLVED_AT IS NULL OR RESOLVED_AT >= OPENED_AT",
            "STATUS_CODE IN ('OPEN','INVESTIGATING','MITIGATED','RESOLVED',"
            "'CANCELLED')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "STATUS_CODE", "SEVERITY_CODE", "OPENED_AT"),
            ix("TENANT_ID", "SHIPMENT_ID"),
        ),
        growth="high",
    ),
    Table(
        "EXCEPTION_ACTION",
        "Append-only ownership, note, mitigation, and resolution actions.",
        tenant_columns(
            c("EXCEPTION_ID", "BIGINT"),
            c("ACTION_NO", "INTEGER"),
            c("ACTION_TYPE", "VARCHAR(20)"),
            c("ACTOR_IDENTIFIER", "VARCHAR(80)"),
            c("ACTION_AT", "TIMESTAMP(6)"),
            c("DETAIL_TEXT", "VARCHAR(1000)"),
        ),
        ("TENANT_ID", "EXCEPTION_ID", "ACTION_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "EXCEPTION_ID"),
                "EXCEPTION_CASE",
                ("TENANT_ID", "EXCEPTION_ID"),
            ),
        ),
        checks=(
            "ACTION_NO > 0",
            "ACTION_TYPE IN ('NOTE','ASSIGN','ESCALATE','MITIGATE',"
            "'RESOLVE','REOPEN')",
        ),
        growth="high",
        append_only=True,
    ),
    Table(
        "DOCUMENT",
        "Stable document identity, classification, retention, and legal hold.",
        tenant_columns(
            c("DOCUMENT_ID", "BIGINT"),
            c("DOCUMENT_TYPE", "VARCHAR(24)"),
            c("TITLE_TEXT", "VARCHAR(200)"),
            c("CLASSIFICATION_CODE", "VARCHAR(16)"),
            c("RETENTION_UNTIL", "DATE", nullable=True),
            c("LEGAL_HOLD_FLAG", "CHAR(1)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "DOCUMENT_ID"),
        checks=(
            "CLASSIFICATION_CODE IN ('PUBLIC','INTERNAL','CONFIDENTIAL',"
            "'RESTRICTED')",
            "LEGAL_HOLD_FLAG IN ('Y','N')",
            "STATUS_CODE IN ('ACTIVE','ARCHIVED','DELETED')",
        ),
        growth="high",
    ),
    Table(
        "DOCUMENT_VERSION",
        "Immutable document metadata and content digest for one version.",
        tenant_columns(
            c("DOCUMENT_ID", "BIGINT"),
            c("VERSION_NO", "INTEGER"),
            c("FILE_NAME", "VARCHAR(255)"),
            c("MIME_TYPE", "VARCHAR(100)"),
            c("BYTE_LENGTH", "BIGINT"),
            c("SHA256_DIGEST", "BINARY(32)"),
            c("UPLOADED_BY", "VARCHAR(80)"),
        ),
        ("TENANT_ID", "DOCUMENT_ID", "VERSION_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "DOCUMENT_ID"),
                "DOCUMENT",
                ("TENANT_ID", "DOCUMENT_ID"),
            ),
        ),
        checks=(
            "VERSION_NO > 0",
            "BYTE_LENGTH BETWEEN 0 AND 52428800",
        ),
        growth="high",
        append_only=True,
    ),
    Table(
        "DOCUMENT_CONTENT",
        "Immutable document bytes with implicit Db2 LOB support objects.",
        tenant_columns(
            c("DOCUMENT_ID", "BIGINT"),
            c("VERSION_NO", "INTEGER"),
            c("CONTENT_BYTES", "BLOB(50M)"),
        ),
        ("TENANT_ID", "DOCUMENT_ID", "VERSION_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "DOCUMENT_ID", "VERSION_NO"),
                "DOCUMENT_VERSION",
                ("TENANT_ID", "DOCUMENT_ID", "VERSION_NO"),
            ),
        ),
        growth="high",
        append_only=True,
        implicit_lob=True,
    ),
    Table(
        "SHIPMENT_DOCUMENT",
        "Typed shipment link to an exact immutable document version.",
        tenant_columns(
            c("SHIPMENT_ID", "BIGINT"),
            c("DOCUMENT_ID", "BIGINT"),
            c("DOCUMENT_VERSION_NO", "INTEGER"),
            c("DOCUMENT_ROLE", "VARCHAR(24)"),
        ),
        (
            "TENANT_ID",
            "SHIPMENT_ID",
            "DOCUMENT_ID",
            "DOCUMENT_VERSION_NO",
            "DOCUMENT_ROLE",
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID"),
                "SHIPMENT",
                ("TENANT_ID", "SHIPMENT_ID"),
            ),
            fk(
                ("TENANT_ID", "DOCUMENT_ID", "DOCUMENT_VERSION_NO"),
                "DOCUMENT_VERSION",
                ("TENANT_ID", "DOCUMENT_ID", "VERSION_NO"),
            ),
        ),
        extra_indexes=(
            ix("TENANT_ID", "DOCUMENT_ID", "DOCUMENT_VERSION_NO"),
        ),
        growth="high",
    ),
    Table(
        "ORDER_DOCUMENT",
        "Typed order link to an exact immutable document version.",
        tenant_columns(
            c("ORDER_ID", "BIGINT"),
            c("DOCUMENT_ID", "BIGINT"),
            c("DOCUMENT_VERSION_NO", "INTEGER"),
            c("DOCUMENT_ROLE", "VARCHAR(24)"),
        ),
        (
            "TENANT_ID",
            "ORDER_ID",
            "DOCUMENT_ID",
            "DOCUMENT_VERSION_NO",
            "DOCUMENT_ROLE",
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "ORDER_ID"),
                "FULFILLMENT_ORDER",
                ("TENANT_ID", "ORDER_ID"),
            ),
            fk(
                ("TENANT_ID", "DOCUMENT_ID", "DOCUMENT_VERSION_NO"),
                "DOCUMENT_VERSION",
                ("TENANT_ID", "DOCUMENT_ID", "VERSION_NO"),
            ),
        ),
        extra_indexes=(
            ix("TENANT_ID", "DOCUMENT_ID", "DOCUMENT_VERSION_NO"),
        ),
        growth="high",
    ),
    Table(
        "CHARGE",
        "Rated customer receivable or carrier payable for a shipment.",
        tenant_columns(
            c("CHARGE_ID", "BIGINT"),
            c("SHIPMENT_ID", "BIGINT"),
            c("CHARGE_SIDE", "CHAR(1)"),
            c("CUSTOMER_ID", "BIGINT", nullable=True),
            c("CARRIER_ID", "BIGINT", nullable=True),
            c("CHARGE_CODE", "VARCHAR(32)"),
            c("RATE_CONTRACT_ID", "BIGINT", nullable=True),
            c("QUANTITY", "DECIMAL(18,3)"),
            c("RATE_AMOUNT", "DECIMAL(19,6)"),
            c("CHARGE_AMOUNT", "DECIMAL(19,4)"),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "CHARGE_ID"),
        uniques=(("TENANT_ID", "CHARGE_ID", "CHARGE_SIDE"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "SHIPMENT_ID"),
                "SHIPMENT",
                ("TENANT_ID", "SHIPMENT_ID"),
            ),
            fk(
                ("TENANT_ID", "CUSTOMER_ID"),
                "CUSTOMER_ACCOUNT",
                ("TENANT_ID", "CUSTOMER_ID"),
            ),
            fk(
                ("TENANT_ID", "CARRIER_ID"),
                "CARRIER",
                ("TENANT_ID", "CARRIER_ID"),
            ),
            fk(
                ("TENANT_ID", "RATE_CONTRACT_ID"),
                "RATE_CONTRACT",
                ("TENANT_ID", "RATE_CONTRACT_ID"),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
        ),
        checks=(
            "QUANTITY > 0",
            "RATE_AMOUNT >= 0",
            "CHARGE_AMOUNT >= 0",
            "((CHARGE_SIDE = 'C' AND CUSTOMER_ID IS NOT NULL AND "
            "CARRIER_ID IS NULL) OR (CHARGE_SIDE = 'P' AND "
            "CARRIER_ID IS NOT NULL AND CUSTOMER_ID IS NULL))",
            "STATUS_CODE IN ('ESTIMATED','APPROVED','INVOICED',"
            "'DISPUTED','VOIDED')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "SHIPMENT_ID", "CHARGE_SIDE"),
            ix("TENANT_ID", "STATUS_CODE", "CHARGE_SIDE"),
        ),
        growth="high",
    ),
    Table(
        "CUSTOMER_INVOICE",
        "Accounts-receivable invoice header for customer charges.",
        tenant_columns(
            c("CUSTOMER_INVOICE_ID", "BIGINT"),
            c("INVOICE_NUMBER", "VARCHAR(48)"),
            c("CUSTOMER_ID", "BIGINT"),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("INVOICE_DATE", "DATE"),
            c("DUE_DATE", "DATE"),
            c("TOTAL_AMOUNT", "DECIMAL(19,4)"),
            c("PAID_AMOUNT", "DECIMAL(19,4)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "CUSTOMER_INVOICE_ID"),
        uniques=(("TENANT_ID", "INVOICE_NUMBER"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CUSTOMER_ID"),
                "CUSTOMER_ACCOUNT",
                ("TENANT_ID", "CUSTOMER_ID"),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
        ),
        checks=(
            "INVOICE_DATE <= DUE_DATE",
            "TOTAL_AMOUNT >= 0",
            "PAID_AMOUNT BETWEEN 0 AND TOTAL_AMOUNT",
            "STATUS_CODE IN ('DRAFT','ISSUED','PART_PAID','PAID','VOID')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "CUSTOMER_ID", "STATUS_CODE", "DUE_DATE"),
        ),
        growth="high",
    ),
    Table(
        "CUSTOMER_INVOICE_LINE",
        "Receivable invoice line allocated to one customer-side charge.",
        tenant_columns(
            c("CUSTOMER_INVOICE_ID", "BIGINT"),
            c("LINE_NO", "INTEGER"),
            c("CHARGE_ID", "BIGINT"),
            c("CHARGE_SIDE", "CHAR(1)"),
            c("DESCRIPTION_TEXT", "VARCHAR(240)"),
            c("LINE_AMOUNT", "DECIMAL(19,4)"),
        ),
        ("TENANT_ID", "CUSTOMER_INVOICE_ID", "LINE_NO"),
        uniques=(("TENANT_ID", "CHARGE_ID"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CUSTOMER_INVOICE_ID"),
                "CUSTOMER_INVOICE",
                ("TENANT_ID", "CUSTOMER_INVOICE_ID"),
            ),
            fk(
                ("TENANT_ID", "CHARGE_ID", "CHARGE_SIDE"),
                "CHARGE",
                ("TENANT_ID", "CHARGE_ID", "CHARGE_SIDE"),
            ),
        ),
        checks=(
            "LINE_NO > 0",
            "CHARGE_SIDE = 'C'",
            "LINE_AMOUNT >= 0",
        ),
        growth="high",
    ),
    Table(
        "CARRIER_INVOICE",
        "Accounts-payable invoice received from a carrier.",
        tenant_columns(
            c("CARRIER_INVOICE_ID", "BIGINT"),
            c("CARRIER_ID", "BIGINT"),
            c("CARRIER_INVOICE_NUMBER", "VARCHAR(64)"),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("INVOICE_DATE", "DATE"),
            c("RECEIVED_DATE", "DATE"),
            c("TOTAL_AMOUNT", "DECIMAL(19,4)"),
            c("APPROVED_AMOUNT", "DECIMAL(19,4)"),
            c("PAID_AMOUNT", "DECIMAL(19,4)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "CARRIER_INVOICE_ID"),
        uniques=(
            ("TENANT_ID", "CARRIER_ID", "CARRIER_INVOICE_NUMBER"),
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CARRIER_ID"),
                "CARRIER",
                ("TENANT_ID", "CARRIER_ID"),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
        ),
        checks=(
            "TOTAL_AMOUNT >= 0",
            "APPROVED_AMOUNT BETWEEN 0 AND TOTAL_AMOUNT",
            "PAID_AMOUNT BETWEEN 0 AND APPROVED_AMOUNT",
            "STATUS_CODE IN ('RECEIVED', 'MATCHING', 'APPROVED', "
            "'PART_PAID', 'PAID', 'DISPUTED', 'VOID')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "CARRIER_ID", "STATUS_CODE", "INVOICE_DATE"),
        ),
        growth="high",
    ),
    Table(
        "CARRIER_INVOICE_LINE",
        "Payable invoice line matched to one carrier-side charge.",
        tenant_columns(
            c("CARRIER_INVOICE_ID", "BIGINT"),
            c("LINE_NO", "INTEGER"),
            c("CHARGE_ID", "BIGINT"),
            c("CHARGE_SIDE", "CHAR(1)"),
            c("DESCRIPTION_TEXT", "VARCHAR(240)"),
            c("CLAIMED_AMOUNT", "DECIMAL(19,4)"),
            c("APPROVED_AMOUNT", "DECIMAL(19,4)"),
        ),
        ("TENANT_ID", "CARRIER_INVOICE_ID", "LINE_NO"),
        uniques=(("TENANT_ID", "CHARGE_ID"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CARRIER_INVOICE_ID"),
                "CARRIER_INVOICE",
                ("TENANT_ID", "CARRIER_INVOICE_ID"),
            ),
            fk(
                ("TENANT_ID", "CHARGE_ID", "CHARGE_SIDE"),
                "CHARGE",
                ("TENANT_ID", "CHARGE_ID", "CHARGE_SIDE"),
            ),
        ),
        checks=(
            "LINE_NO > 0",
            "CHARGE_SIDE = 'P'",
            "CLAIMED_AMOUNT >= 0",
            "APPROVED_AMOUNT BETWEEN 0 AND CLAIMED_AMOUNT",
        ),
        growth="high",
    ),
    Table(
        "CASH_RECEIPT",
        "Customer cash receipt before allocation to receivable invoices.",
        tenant_columns(
            c("CASH_RECEIPT_ID", "BIGINT"),
            c("CUSTOMER_ID", "BIGINT"),
            c("RECEIPT_REFERENCE", "VARCHAR(80)"),
            c("RECEIVED_AT", "TIMESTAMP(6)"),
            c("AMOUNT", "DECIMAL(19,4)"),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "CASH_RECEIPT_ID"),
        uniques=(("TENANT_ID", "RECEIPT_REFERENCE"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CUSTOMER_ID"),
                "CUSTOMER_ACCOUNT",
                ("TENANT_ID", "CUSTOMER_ID"),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
        ),
        checks=(
            "AMOUNT > 0",
            "STATUS_CODE IN ('RECEIVED','PART_ALLOCATED','ALLOCATED',"
            "'REVERSED')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "CUSTOMER_ID", "RECEIVED_AT"),
        ),
        growth="high",
    ),
    Table(
        "RECEIPT_ALLOCATION",
        "Append-only customer receipt allocation or reversal movement.",
        tenant_columns(
            c("CASH_RECEIPT_ID", "BIGINT"),
            c("ALLOCATION_NO", "INTEGER"),
            c("CUSTOMER_INVOICE_ID", "BIGINT"),
            c("MOVEMENT_TYPE", "VARCHAR(12)"),
            c("AMOUNT", "DECIMAL(19,4)"),
            c("ALLOCATED_AT", "TIMESTAMP(6)"),
            c("REVERSAL_OF_NO", "INTEGER", nullable=True),
        ),
        ("TENANT_ID", "CASH_RECEIPT_ID", "ALLOCATION_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CASH_RECEIPT_ID"),
                "CASH_RECEIPT",
                ("TENANT_ID", "CASH_RECEIPT_ID"),
            ),
            fk(
                ("TENANT_ID", "CUSTOMER_INVOICE_ID"),
                "CUSTOMER_INVOICE",
                ("TENANT_ID", "CUSTOMER_INVOICE_ID"),
            ),
            fk(
                ("TENANT_ID", "CASH_RECEIPT_ID", "REVERSAL_OF_NO"),
                "RECEIPT_ALLOCATION",
                ("TENANT_ID", "CASH_RECEIPT_ID", "ALLOCATION_NO"),
            ),
        ),
        checks=(
            "ALLOCATION_NO > 0",
            "AMOUNT > 0",
            "MOVEMENT_TYPE IN ('ALLOCATE','REVERSE')",
            "((MOVEMENT_TYPE = 'ALLOCATE' AND REVERSAL_OF_NO IS NULL) "
            "OR (MOVEMENT_TYPE = 'REVERSE' AND "
            "REVERSAL_OF_NO IS NOT NULL))",
        ),
        extra_indexes=(
            ix("TENANT_ID", "CUSTOMER_INVOICE_ID", "ALLOCATED_AT"),
        ),
        growth="high",
        append_only=True,
    ),
    Table(
        "CARRIER_PAYMENT",
        "Disbursement to a carrier before payable-invoice allocation.",
        tenant_columns(
            c("CARRIER_PAYMENT_ID", "BIGINT"),
            c("CARRIER_ID", "BIGINT"),
            c("PAYMENT_REFERENCE", "VARCHAR(80)"),
            c("PAID_AT", "TIMESTAMP(6)"),
            c("AMOUNT", "DECIMAL(19,4)"),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "CARRIER_PAYMENT_ID"),
        uniques=(("TENANT_ID", "PAYMENT_REFERENCE"),),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CARRIER_ID"),
                "CARRIER",
                ("TENANT_ID", "CARRIER_ID"),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
        ),
        checks=(
            "AMOUNT > 0",
            "STATUS_CODE IN ('CREATED','SENT','PART_ALLOCATED','ALLOCATED',"
            "'FAILED','REVERSED')",
        ),
        extra_indexes=(ix("TENANT_ID", "CARRIER_ID", "PAID_AT"),),
        growth="high",
    ),
    Table(
        "PAYMENT_ALLOCATION",
        "Append-only carrier payment allocation or reversal movement.",
        tenant_columns(
            c("CARRIER_PAYMENT_ID", "BIGINT"),
            c("ALLOCATION_NO", "INTEGER"),
            c("CARRIER_INVOICE_ID", "BIGINT"),
            c("MOVEMENT_TYPE", "VARCHAR(12)"),
            c("AMOUNT", "DECIMAL(19,4)"),
            c("ALLOCATED_AT", "TIMESTAMP(6)"),
            c("REVERSAL_OF_NO", "INTEGER", nullable=True),
        ),
        ("TENANT_ID", "CARRIER_PAYMENT_ID", "ALLOCATION_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "CARRIER_PAYMENT_ID"),
                "CARRIER_PAYMENT",
                ("TENANT_ID", "CARRIER_PAYMENT_ID"),
            ),
            fk(
                ("TENANT_ID", "CARRIER_INVOICE_ID"),
                "CARRIER_INVOICE",
                ("TENANT_ID", "CARRIER_INVOICE_ID"),
            ),
            fk(
                ("TENANT_ID", "CARRIER_PAYMENT_ID", "REVERSAL_OF_NO"),
                "PAYMENT_ALLOCATION",
                ("TENANT_ID", "CARRIER_PAYMENT_ID", "ALLOCATION_NO"),
            ),
        ),
        checks=(
            "ALLOCATION_NO > 0",
            "AMOUNT > 0",
            "MOVEMENT_TYPE IN ('ALLOCATE','REVERSE')",
            "((MOVEMENT_TYPE = 'ALLOCATE' AND REVERSAL_OF_NO IS NULL) "
            "OR (MOVEMENT_TYPE = 'REVERSE' AND "
            "REVERSAL_OF_NO IS NOT NULL))",
        ),
        extra_indexes=(
            ix("TENANT_ID", "CARRIER_INVOICE_ID", "ALLOCATED_AT"),
        ),
        growth="high",
        append_only=True,
    ),
    Table(
        "ACCOUNTING_PERIOD",
        "Tenant fiscal period and posting gate.",
        tenant_columns(
            c("PERIOD_ID", "BIGINT"),
            c("PERIOD_CODE", "VARCHAR(16)"),
            c("START_DATE", "DATE"),
            c("END_DATE", "DATE"),
            c("STATUS_CODE", "VARCHAR(12)"),
        ),
        ("TENANT_ID", "PERIOD_ID"),
        uniques=(("TENANT_ID", "PERIOD_CODE"),),
        checks=(
            "START_DATE < END_DATE",
            "STATUS_CODE IN ('OPEN','SOFT_CLOSED','CLOSED')",
        ),
        growth="reference",
    ),
    Table(
        "GL_ACCOUNT",
        "Tenant chart of accounts for logistics operational postings.",
        tenant_columns(
            c("GL_ACCOUNT_ID", "BIGINT"),
            c("ACCOUNT_CODE", "VARCHAR(32)"),
            c("ACCOUNT_NAME", "VARCHAR(100)"),
            c("ACCOUNT_TYPE", "VARCHAR(16)"),
            c("POSTABLE_FLAG", "CHAR(1)"),
            c("STATUS_CODE", "VARCHAR(12)"),
        ),
        ("TENANT_ID", "GL_ACCOUNT_ID"),
        uniques=(("TENANT_ID", "ACCOUNT_CODE"),),
        checks=(
            "ACCOUNT_TYPE IN ('ASSET','LIABILITY','EQUITY','REVENUE',"
            "'EXPENSE')",
            "POSTABLE_FLAG IN ('Y','N')",
            "STATUS_CODE IN ('ACTIVE','INACTIVE')",
        ),
        growth="reference",
    ),
    Table(
        "JOURNAL",
        "Accounting header; balanced posting is a service transaction rule.",
        tenant_columns(
            c("JOURNAL_ID", "BIGINT"),
            c("JOURNAL_NUMBER", "VARCHAR(48)"),
            c("PERIOD_ID", "BIGINT"),
            c("POSTING_DATE", "DATE"),
            c("SOURCE_TYPE", "VARCHAR(24)"),
            c("SOURCE_ID", "VARCHAR(80)"),
            c("CURRENCY_CODE", "CHAR(3)"),
            c("STATUS_CODE", "VARCHAR(12)"),
            c("POSTED_AT", "TIMESTAMP(6)", nullable=True),
        ),
        ("TENANT_ID", "JOURNAL_ID"),
        uniques=(
            ("TENANT_ID", "JOURNAL_NUMBER"),
            ("TENANT_ID", "SOURCE_TYPE", "SOURCE_ID"),
        ),
        foreign_keys=(
            fk(
                ("TENANT_ID", "PERIOD_ID"),
                "ACCOUNTING_PERIOD",
                ("TENANT_ID", "PERIOD_ID"),
            ),
            fk(("CURRENCY_CODE",), "CURRENCY", ("CURRENCY_CODE",)),
        ),
        checks=(
            "STATUS_CODE IN ('DRAFT','POSTED','REVERSED')",
            "((STATUS_CODE = 'DRAFT' AND POSTED_AT IS NULL) OR "
            "(STATUS_CODE <> 'DRAFT' AND POSTED_AT IS NOT NULL))",
        ),
        extra_indexes=(ix("TENANT_ID", "PERIOD_ID", "POSTING_DATE"),),
        growth="high",
    ),
    Table(
        "JOURNAL_LINE",
        "Append-only debit or credit line for one journal and account.",
        tenant_columns(
            c("JOURNAL_ID", "BIGINT"),
            c("LINE_NO", "INTEGER"),
            c("GL_ACCOUNT_ID", "BIGINT"),
            c("ENTRY_SIDE", "CHAR(1)"),
            c("AMOUNT", "DECIMAL(19,4)"),
            c("DESCRIPTION_TEXT", "VARCHAR(240)"),
            c("CHARGE_ID", "BIGINT", nullable=True),
        ),
        ("TENANT_ID", "JOURNAL_ID", "LINE_NO"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "JOURNAL_ID"),
                "JOURNAL",
                ("TENANT_ID", "JOURNAL_ID"),
            ),
            fk(
                ("TENANT_ID", "GL_ACCOUNT_ID"),
                "GL_ACCOUNT",
                ("TENANT_ID", "GL_ACCOUNT_ID"),
            ),
            fk(
                ("TENANT_ID", "CHARGE_ID"),
                "CHARGE",
                ("TENANT_ID", "CHARGE_ID"),
            ),
        ),
        checks=(
            "LINE_NO > 0",
            "ENTRY_SIDE IN ('D','C')",
            "AMOUNT > 0",
        ),
        extra_indexes=(ix("TENANT_ID", "GL_ACCOUNT_ID", "JOURNAL_ID"),),
        growth="high",
    ),
    Table(
        "IDEMPOTENCY_REQUEST",
        "Exactly-once facade for retried API commands within a tenant.",
        tenant_columns(
            c("SERVICE_NAME", "VARCHAR(48)"),
            c("IDEMPOTENCY_KEY", "VARCHAR(96)"),
            c("REQUEST_DIGEST", "BINARY(32)"),
            c("RESOURCE_TYPE", "VARCHAR(32)", nullable=True),
            c("RESOURCE_ID", "VARCHAR(80)", nullable=True),
            c("FIRST_RECEIVED_AT", "TIMESTAMP(6)"),
            c("COMPLETED_AT", "TIMESTAMP(6)", nullable=True),
            c("EXPIRES_AT", "TIMESTAMP(6)"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "SERVICE_NAME", "IDEMPOTENCY_KEY"),
        checks=(
            "EXPIRES_AT > FIRST_RECEIVED_AT",
            "COMPLETED_AT IS NULL OR COMPLETED_AT >= FIRST_RECEIVED_AT",
            "STATUS_CODE IN ('PROCESSING','SUCCEEDED','FAILED')",
        ),
        extra_indexes=(ix("TENANT_ID", "STATUS_CODE", "EXPIRES_AT"),),
        growth="high",
    ),
    Table(
        "INBOUND_MESSAGE",
        "Deduplicated integration message and processing outcome.",
        tenant_columns(
            c("SOURCE_SYSTEM", "VARCHAR(48)"),
            c("SOURCE_MESSAGE_ID", "VARCHAR(96)"),
            c("MESSAGE_TYPE", "VARCHAR(48)"),
            c("PAYLOAD_DIGEST", "BINARY(32)"),
            c("RECEIVED_AT", "TIMESTAMP(6)"),
            c("PROCESSED_AT", "TIMESTAMP(6)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
            c("ERROR_CODE", "VARCHAR(40)", nullable=True),
        ),
        ("TENANT_ID", "SOURCE_SYSTEM", "SOURCE_MESSAGE_ID"),
        checks=(
            "PROCESSED_AT IS NULL OR PROCESSED_AT >= RECEIVED_AT",
            "STATUS_CODE IN ('RECEIVED','PROCESSING','PROCESSED','FAILED',"
            "'DEAD_LETTER')",
        ),
        extra_indexes=(ix("TENANT_ID", "STATUS_CODE", "RECEIVED_AT"),),
        growth="high",
    ),
    Table(
        "OUTBOX_EVENT",
        "Append-only transactional event awaiting external publication.",
        tenant_columns(
            c("OUTBOX_EVENT_ID", "BIGINT"),
            c("AGGREGATE_TYPE", "VARCHAR(32)"),
            c("AGGREGATE_ID", "VARCHAR(80)"),
            c("EVENT_TYPE", "VARCHAR(64)"),
            c("EVENT_VERSION", "INTEGER"),
            c("PAYLOAD_JSON", "VARCHAR(2000)"),
            c("OCCURRED_AT", "TIMESTAMP(6)"),
        ),
        ("TENANT_ID", "OUTBOX_EVENT_ID"),
        uniques=(
            (
                "TENANT_ID",
                "AGGREGATE_TYPE",
                "AGGREGATE_ID",
                "EVENT_VERSION",
            ),
        ),
        checks=(
            "EVENT_VERSION > 0",
        ),
        extra_indexes=(
            ix("TENANT_ID", "OCCURRED_AT"),
        ),
        growth="high",
        append_only=True,
    ),
    Table(
        "OUTBOX_DELIVERY",
        "Mutable delivery state kept separate from immutable event payloads.",
        tenant_columns(
            c("OUTBOX_EVENT_ID", "BIGINT"),
            c("DESTINATION_NAME", "VARCHAR(64)"),
            c("ATTEMPT_COUNT", "INTEGER"),
            c("NEXT_ATTEMPT_AT", "TIMESTAMP(6)", nullable=True),
            c("PUBLISHED_AT", "TIMESTAMP(6)", nullable=True),
            c("LAST_ERROR_CODE", "VARCHAR(40)", nullable=True),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "OUTBOX_EVENT_ID", "DESTINATION_NAME"),
        foreign_keys=(
            fk(
                ("TENANT_ID", "OUTBOX_EVENT_ID"),
                "OUTBOX_EVENT",
                ("TENANT_ID", "OUTBOX_EVENT_ID"),
            ),
        ),
        checks=(
            "ATTEMPT_COUNT >= 0",
            "STATUS_CODE IN ('PENDING','PUBLISHED','FAILED','DEAD_LETTER')",
        ),
        extra_indexes=(
            ix("TENANT_ID", "STATUS_CODE", "NEXT_ATTEMPT_AT"),
        ),
        growth="high",
    ),
    Table(
        "BATCH_JOB_RUN",
        "Operational record for scheduler jobs, restarts, and reconciliation.",
        tenant_columns(
            c("JOB_RUN_ID", "BIGINT"),
            c("JOB_NAME", "VARCHAR(64)"),
            c("BUSINESS_DATE", "DATE"),
            c("ATTEMPT_NO", "INTEGER"),
            c("STARTED_AT", "TIMESTAMP(6)"),
            c("FINISHED_AT", "TIMESTAMP(6)", nullable=True),
            c("CHECKPOINT_VALUE", "VARCHAR(200)", nullable=True),
            c("RECORDS_PROCESSED", "BIGINT"),
            c("ERROR_COUNT", "INTEGER"),
            c("STATUS_CODE", "VARCHAR(16)"),
        ),
        ("TENANT_ID", "JOB_RUN_ID"),
        uniques=(("TENANT_ID", "JOB_NAME", "BUSINESS_DATE", "ATTEMPT_NO"),),
        checks=(
            "ATTEMPT_NO > 0",
            "FINISHED_AT IS NULL OR FINISHED_AT >= STARTED_AT",
            "RECORDS_PROCESSED >= 0",
            "ERROR_COUNT >= 0",
            "STATUS_CODE IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED')",
        ),
        extra_indexes=(ix("TENANT_ID", "JOB_NAME", "STARTED_AT"),),
        growth="high",
    ),
    Table(
        "AUDIT_EVENT",
        "Append-only security and business change evidence.",
        tenant_columns(
            c("AUDIT_EVENT_ID", "BIGINT"),
            c("ACTOR_TYPE", "VARCHAR(16)"),
            c("ACTOR_IDENTIFIER", "VARCHAR(80)"),
            c("ACTION_CODE", "VARCHAR(32)"),
            c("OBJECT_TYPE", "VARCHAR(32)"),
            c("OBJECT_ID", "VARCHAR(120)"),
            c("CORRELATION_ID", "VARCHAR(80)"),
            c("BEFORE_DIGEST", "BINARY(32)", nullable=True),
            c("AFTER_DIGEST", "BINARY(32)", nullable=True),
            c("OCCURRED_AT", "TIMESTAMP(6)"),
            c("SOURCE_ADDRESS", "VARCHAR(64)", nullable=True),
        ),
        ("TENANT_ID", "AUDIT_EVENT_ID"),
        checks=("ACTOR_TYPE IN ('USER','SERVICE','JOB','SYSTEM')",),
        extra_indexes=(
            ix("TENANT_ID", "OBJECT_TYPE", "OBJECT_ID", "OCCURRED_AT"),
            ix("TENANT_ID", "CORRELATION_ID"),
        ),
        growth="high",
        append_only=True,
    ),
)


def wrap_sql(text: str, indent: str = "", width: int = MAX_LINE) -> list[str]:
    return textwrap.wrap(
        text,
        width=width,
        initial_indent=indent,
        subsequent_indent=indent + "  ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def comment(text: str) -> list[str]:
    if not text:
        return ["--"]
    return textwrap.wrap(
        text,
        width=MAX_LINE,
        initial_indent="-- ",
        subsequent_indent="-- ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def render_tablespace(number: int, table: Table) -> list[str]:
    if table.growth == "reference":
        maxpartitions, dssize = 1, 1
    elif table.growth == "core":
        maxpartitions, dssize = 16, 4
    else:
        maxpartitions, dssize = 64, 4
    name = f"SC{number:04d}"
    return [
        f"CREATE TABLESPACE {name}",
        f"  IN {DATABASE}",
        f"  BUFFERPOOL {BUFFERPOOL}",
        f"  MAXPARTITIONS {maxpartitions}",
        "  NUMPARTS 1",
        f"  DSSIZE {dssize} G",
        "  SEGSIZE 32",
        "  CCSID UNICODE",
        "  CLOSE YES",
        "  COMPRESS NO",
        "  DEFINE YES",
        "  FREEPAGE 0",
        "  PCTFREE 10 FOR UPDATE 5",
        "  LOCKMAX SYSTEM",
        "  LOCKSIZE ROW",
        "  LOGGED",
        "  TRACKMOD YES",
        f"  USING STOGROUP {STOGROUP} PRIQTY -1 SECQTY -1;",
    ]


def qualified(table_name: str) -> str:
    return f"{SCHEMA}.{table_name}"


def render_table(number: int, table: Table) -> list[str]:
    lines: list[str] = []
    if not table.implicit_lob:
        lines.extend(render_tablespace(number, table))
        lines.extend(["", ""])

    lines.append(f"CREATE TABLE {qualified(table.name)}")
    lines.append("(")
    elements: list[str] = [column.sql() for column in table.all_columns()]
    elements.append(
        f"CONSTRAINT P{number:03d} PRIMARY KEY "
        f"({', '.join(table.primary_key)})"
    )
    for unique_number, columns in enumerate(table.uniques, 1):
        elements.append(
            f"CONSTRAINT U{number:03d}{unique_number:02d} UNIQUE "
            f"({', '.join(columns)})"
        )
    self_references: list[str] = []
    for fk_number, foreign_key in enumerate(table.all_foreign_keys(), 1):
        constraint = (
            f"CONSTRAINT F{number:03d}{fk_number:02d} FOREIGN KEY "
            f"({', '.join(foreign_key.columns)}) REFERENCES "
            f"{qualified(foreign_key.ref_table)} "
            f"({', '.join(foreign_key.ref_columns)})"
        )
        if foreign_key.ref_table == table.name:
            # CREATE TABLE cannot name its own table as the parent, and a
            # self-reference must use CASCADE or NO ACTION (ALTER TABLE).
            self_references.append(constraint + " ON DELETE NO ACTION")
        else:
            elements.append(constraint + " ON DELETE RESTRICT")
    for check_number, expression in enumerate(table.checks, 1):
        elements.append(
            f"CONSTRAINT C{number:03d}{check_number:02d} "
            f"CHECK ({expression})"
        )

    for element_number, element in enumerate(elements):
        suffix = "," if element_number < len(elements) - 1 else ""
        lines.extend(wrap_sql(element + suffix, "  "))
    lines.append(")")
    if table.implicit_lob:
        lines.extend(
            [
                f"  IN DATABASE {DATABASE}",
                "  PARTITION BY SIZE EVERY 4 G",
                f"  BUFFERPOOL {BUFFERPOOL}",
                "  LOGGED",
                "  COMPRESS NO",
                "  TRACKMOD YES",
            ]
        )
    else:
        lines.append(f"  IN {DATABASE}.SC{number:04d}")
    lines.extend(
        [
            "  AUDIT CHANGES",
            "  DATA CAPTURE CHANGES",
            f"  APPEND {'YES' if table.append_only else 'NO'};",
        ]
    )

    if table.implicit_lob:
        return lines

    indexes: list[ExtraIndex] = []
    indexes.append(ExtraIndex(table.primary_key, True))
    indexes.extend(ExtraIndex(columns, True) for columns in table.uniques)

    def covered(columns: tuple[str, ...]) -> bool:
        return any(index.columns[: len(columns)] == columns for index in indexes)

    for foreign_key in table.all_foreign_keys():
        if not covered(foreign_key.columns):
            indexes.append(ExtraIndex(foreign_key.columns))
    for extra in table.extra_indexes:
        if not covered(extra.columns):
            indexes.append(extra)

    for index_number, index in enumerate(indexes, 1):
        lines.extend(["", ""])
        create = "CREATE UNIQUE INDEX" if index.unique else "CREATE INDEX"
        lines.append(
            f"{create} {SCHEMA}.I{number:03d}{index_number:03d}"
        )
        key_text = f"ON {qualified(table.name)} ({', '.join(index.columns)})"
        lines.extend(wrap_sql(key_text, "  "))
        if index_number == 1:
            lines.append("  CLUSTER")
        lines.extend(
            [
                f"  USING STOGROUP {STOGROUP} PRIQTY -1 SECQTY -1",
                "  FREEPAGE 0 PCTFREE 10",
                f"  BUFFERPOOL {BUFFERPOOL}",
                "  CLOSE YES",
                "  DEFER NO;",
            ]
        )
    for constraint in self_references:
        lines.extend(["", "", f"ALTER TABLE {qualified(table.name)}"])
        lines.extend(wrap_sql("ADD " + constraint + ";", "  "))
    return lines


def render_preamble(index_count: int) -> list[str]:
    paragraphs = [
        "SUPPLY CHAIN LOGISTICS: Db2 13 for z/OS physical and logical "
        "schema.",
        "Design state: DESIGN. Authored 2026-09-12. No live Db2 or "
        "administration-product execution has occurred.",
        "Use case: a multi-tenant third-party logistics control tower "
        "accepts inbound, outbound, transfer, and return orders; reserves "
        "warehouse stock; plans multimodal shipments; tenders legs to "
        "carriers; consolidates them into loads; records appointments, "
        "tracking, sensor, customs, delivery, exception, document, billing, "
        "settlement, accounting, audit, and integration evidence.",
        "The transactional spine is ORDER -> SHIPMENT -> LEG -> LOAD. "
        "Inventory reservations attach stock to order lines; shipment items "
        "attach order-line quantities to a shipment; load-leg rows preserve "
        "assignment history. Customer and carrier charges flow into separate "
        "invoice and payment paths before balanced journal posting.",
        "DEPLOYMENT PROFILE: UNVERIFIED. Database SCLDB; SQL schema "
        "LOGISTICS. All application tables, indexes, document bytes, and "
        "implicit LOB objects remain in this one database. Existing STOGROUP "
        "SYSDEFLT and active 4 KB pool BP0 are assumed. Confirm Db2 13, "
        "activated function level and package APPLCOMPAT V13R1M500 or later, "
        "CURRENT RULES DB2, DFSMS settings, default LOB pool, subsystem "
        "defaults, schema privileges, CREATETS/CREATETAB, REFERENCES, and "
        "USE authority before execution.",
        "PHYSICAL DESIGN: one logged PBG UTS per ordinary table. Reference "
        "tables use 1 x 1 GB, core master tables use 16 x 4 GB, and high-growth "
        "transaction tables use 64 x 4 GB. These are growth ceilings, not "
        "initial allocations. Row locking, PCTFREE 10 FOR UPDATE 5, and "
        "Db2-calculated allocation are starting assumptions. Revisit PBR, "
        "buffer pools, compression, MEMBER CLUSTER, index count, retention, "
        "and partition keys using observed volumes and access paths.",
        "DOCUMENT_CONTENT intentionally uses an implicitly created PBG base "
        "space so Db2 also creates the LOB table space, auxiliary table, "
        "auxiliary index, hidden ROWID, and enforcing primary-key index inside "
        "SCLDB. Discover their generated names through SYSIBM.SYSAUXRELS and "
        "include them in backup, extraction, replay, and recovery procedures.",
        "TENANT CONTRACT: every tenant-owned primary and alternate key starts "
        "with TENANT_ID. Every foreign key between tenant-owned tables carries "
        "TENANT_ID on both sides. This prevents an otherwise valid identifier "
        "from crossing tenant boundaries. Services must still set and "
        "authorize the tenant context on every query and write.",
        "TIME AND MONEY CONTRACT: business timestamps are UTC. Facility time "
        "zone names support display and appointment conversion. DECIMAL(19,4) "
        "stores money and every monetary row names a currency; rates use "
        "DECIMAL(19,6). Quantity rows name a unit. No implicit currency or "
        "unit conversion is allowed.",
        "HISTORY CONTRACT: inventory movements, tracking events, sensor "
        "readings, exception actions, document versions/content, receipt and "
        "payment allocations, immutable outbox payloads, and audit events use "
        "compensating rows rather than destructive correction. Stateful rows "
        "such as tenders, loads, invoices, idempotency requests, delivery "
        "attempts, and job runs become immutable at their terminal status by "
        "application policy; row CHECK constraints cannot enforce transitions.",
        "TRANSACTION CONTRACT: atomically update an operational aggregate and "
        "its audit/outbox evidence. Lock or compare VERSION_NO when changing "
        "inventory balances. Serialize allocation consumption, shipment/load "
        "assignment, invoice/payment totals, and journal posting. Validate "
        "that one active assignment exists where required, quantities do not "
        "exceed demand or stock, invoice currency matches charges, allocations "
        "do not exceed settled amounts, journal dates fall in open periods, "
        "and total debits equal credits before posting.",
        "SECURITY CONTRACT: this DDL stores no password, token, private key, or "
        "payment credential. Encrypt and authorize sensitive documents outside "
        "the row model, apply field-level masking where required, and enforce "
        "retention/legal holds through reviewed operational procedures. AUDIT "
        "CHANGES and DATA CAPTURE CHANGES enable Db2 facilities; they do not "
        "install a security audit or CDC consumer.",
        "RUN ORDER: execute sequentially with semicolon terminators and stop at "
        "the first error. This script is not rerunnable or atomic. Each table "
        "is followed by all enforcing and access-path indexes, then COMMIT, so "
        "parent keys exist before child creation. A table that references "
        "itself gets that key from ALTER TABLE after its enforcing index, with "
        "ON DELETE NO ACTION, because IBM allows only CASCADE or NO ACTION "
        "when parent and dependent are the same table. Record successful "
        "statements and repair from a known empty database/schema after "
        "failure.",
        "IBM TRACEABILITY: reviewed local normalized rules and IBM Db2 13 SQL "
        "Reference sections CREATE DATABASE, CREATE TABLESPACE, CREATE TABLE, "
        "CREATE INDEX, ALTER TABLE, referential/check constraints, generated row-change "
        "timestamps, data types, and implicit table/LOB creation. Also reviewed "
        "the Administration Guide topics for PBG and LOB support objects. IBM "
        "SQL Reference was last updated 2026-04-06 and accessed 2026-09-12.",
        "Sources: https://www.ibm.com/docs/en/SSEPEK_13.0.0/pdf/"
        "db2z_13_sqlrefbook.pdf and https://www.ibm.com/docs/en/db2-for-zos/"
        "13.0.0?topic=spaces-creating-partition-by-growth-table and "
        "https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=its-creating-"
        "lob-table-spaces-auxiliary-tables-auxiliary-indexes-explicitly.",
        f"Object totals: {len(TABLES)} base tables; "
        f"{len(TABLES) - 1} explicit PBG table spaces plus one implicit base "
        f"space; {index_count} explicit indexes. Additional implicit document "
        "objects are created by Db2.",
    ]
    lines: list[str] = []
    for paragraph in paragraphs:
        lines.extend(comment(paragraph))
        lines.append("--")
    lines.extend(
        [
            "SET CURRENT RULES = 'DB2';",
            "",
            f"CREATE DATABASE {DATABASE}",
            f"  STOGROUP {STOGROUP}",
            f"  BUFFERPOOL {BUFFERPOOL}",
            f"  INDEXBP {BUFFERPOOL}",
            "  CCSID UNICODE;",
            "",
            "COMMIT;",
        ]
    )
    return lines


def index_count_for(table: Table) -> int:
    if table.implicit_lob:
        return 0
    indexes = [ExtraIndex(table.primary_key, True)]
    indexes.extend(ExtraIndex(columns, True) for columns in table.uniques)

    def covered(columns: tuple[str, ...]) -> bool:
        return any(index.columns[: len(columns)] == columns for index in indexes)

    for foreign_key in table.all_foreign_keys():
        if not covered(foreign_key.columns):
            indexes.append(ExtraIndex(foreign_key.columns))
    for extra in table.extra_indexes:
        if not covered(extra.columns):
            indexes.append(extra)
    return len(indexes)


def render_catalog_review() -> list[str]:
    text = ["", ""]
    text.extend(comment("POST-CREATE CATALOG REVIEW. Run separately."))
    queries = [
        "SELECT NAME, TYPE, STOGROUP, BPOOL, INDEXBP, ENCODING_SCHEME",
        "  FROM SYSIBM.SYSDATABASE",
        f" WHERE NAME = '{DATABASE}';",
        "",
        "SELECT DBNAME, NAME, TYPE, PARTITIONS, MAXPARTITIONS, SEGSIZE,",
        "       DSSIZE, BPOOL, LOCKRULE, LOG, ENCODING_SCHEME",
        "  FROM SYSIBM.SYSTABLESPACE",
        f" WHERE DBNAME = '{DATABASE}'",
        " ORDER BY NAME;",
        "",
        "SELECT CREATOR, NAME, DBNAME, TSNAME, TYPE, STATUS, AUDITING,",
        "       DATACAPTURE, APPEND",
        "  FROM SYSIBM.SYSTABLES",
        f" WHERE CREATOR = '{SCHEMA}'",
        " ORDER BY NAME;",
        "",
        "SELECT CREATOR, NAME, TBCREATOR, TBNAME, UNIQUERULE,",
        "       CLUSTERING, PADDED, BPOOL",
        "  FROM SYSIBM.SYSINDEXES",
        f" WHERE CREATOR = '{SCHEMA}'",
        " ORDER BY TBNAME, NAME;",
        "",
        "SELECT REFTBCREATOR, REFTBNAME, CREATOR, TBNAME, RELNAME,",
        "       DELETERULE, ENFORCED, CHECKEXISTINGDATA",
        "  FROM SYSIBM.SYSRELS",
        f" WHERE CREATOR = '{SCHEMA}'",
        " ORDER BY TBNAME, RELNAME;",
        "",
        "SELECT TBOWNER, TBNAME, COLNAME, PARTITION, AUXTBOWNER,",
        "       AUXTBNAME",
        "  FROM SYSIBM.SYSAUXRELS",
        f" WHERE TBOWNER = '{SCHEMA}'",
        "   AND TBNAME = 'DOCUMENT_CONTENT'",
        " ORDER BY COLNAME, PARTITION;",
    ]
    text.extend("-- " + line if line else "--" for line in queries)
    text.extend(["", ""])
    text.extend(
        comment(
            "Before application use, confirm no incomplete definitions, "
            "capture image copies, establish RUNSTATS/REORG/COPY cadence, test "
            "recovery and tenant isolation, and replay actual product-extracted "
            "DDL under clean names. Static generation is not Db2 acceptance."
        )
    )
    return text


def generate_sql() -> str:
    explicit_indexes = sum(index_count_for(table) for table in TABLES)
    lines = render_preamble(explicit_indexes)
    for number, table in enumerate(TABLES, 1):
        lines.extend(["", ""])
        lines.extend(comment(f"{number:02d}. {table.name}: {table.purpose}"))
        lines.extend(render_table(number, table))
        lines.extend(["", "COMMIT;"])
    lines.extend(render_catalog_review())
    return "\n".join(lines).rstrip() + "\n"


def type_width(data_type: str) -> int:
    upper = data_type.upper()
    if upper == "SMALLINT":
        return 2
    if upper == "INTEGER":
        return 4
    if upper == "BIGINT":
        return 8
    if upper == "DATE":
        return 4
    if upper.startswith("TIMESTAMP"):
        return 16
    if upper.startswith("DECIMAL("):
        precision = int(upper.split("(", 1)[1].split(",", 1)[0])
        return precision // 2 + 1
    if upper.startswith(("CHAR(", "BINARY(")):
        return int(upper.split("(", 1)[1].split(")", 1)[0])
    if upper.startswith("VARCHAR("):
        return int(upper.split("(", 1)[1].split(")", 1)[0]) + 2
    if upper.startswith("BLOB("):
        return 24
    raise ValueError(f"unhandled data type for width: {data_type}")


def validate_schema(sql: str) -> list[str]:
    errors: list[str] = []
    by_name: dict[str, Table] = {}
    for position, table in enumerate(TABLES, 1):
        if table.name in by_name:
            errors.append(f"duplicate table name: {table.name}")
        by_name[table.name] = table
        columns = {column.name: column for column in table.all_columns()}
        if len(columns) != len(table.all_columns()):
            errors.append(f"{table.name}: duplicate column")
        if table.tenant_owned:
            if table.primary_key[0:1] != ("TENANT_ID",):
                errors.append(f"{table.name}: primary key lacks tenant prefix")
            for unique in table.uniques:
                if unique[0:1] != ("TENANT_ID",):
                    errors.append(
                        f"{table.name}: unique key lacks tenant prefix: {unique}"
                    )
        for key in (table.primary_key,) + table.uniques:
            for column in key:
                if column not in columns:
                    errors.append(f"{table.name}: missing key column {column}")
                elif columns[column].nullable:
                    errors.append(f"{table.name}: nullable key column {column}")
        width = sum(type_width(column.data_type) for column in columns.values())
        width += (len(columns) + 7) // 8
        if not table.implicit_lob and width > 4000:
            errors.append(f"{table.name}: estimated row width {width} > 4000")

        earlier = {item.name: item for item in TABLES[:position]}
        for foreign_key in table.all_foreign_keys():
            if foreign_key.ref_table not in earlier:
                errors.append(
                    f"{table.name}: reference target not available: "
                    f"{foreign_key.ref_table}"
                )
                continue
            target = earlier[foreign_key.ref_table]
            if len(foreign_key.columns) != len(foreign_key.ref_columns):
                errors.append(f"{table.name}: foreign-key arity mismatch")
                continue
            target_keys = (target.primary_key,) + target.uniques
            if foreign_key.ref_columns not in target_keys:
                errors.append(
                    f"{table.name}: target columns are not unique: "
                    f"{foreign_key.ref_table}{foreign_key.ref_columns}"
                )
            if target.tenant_owned:
                if foreign_key.columns[0:1] != ("TENANT_ID",):
                    errors.append(
                        f"{table.name}: tenant reference lacks source tenant"
                    )
                if foreign_key.ref_columns[0:1] != ("TENANT_ID",):
                    errors.append(
                        f"{table.name}: tenant reference lacks target tenant"
                    )
            for source_name, target_name in zip(
                foreign_key.columns, foreign_key.ref_columns
            ):
                if source_name not in columns:
                    errors.append(
                        f"{table.name}: missing foreign-key column {source_name}"
                    )
                    continue
                target_columns = {
                    column.name: column for column in target.all_columns()
                }
                if target_name not in target_columns:
                    errors.append(
                        f"{table.name}: missing target column "
                        f"{foreign_key.ref_table}.{target_name}"
                    )
                    continue
                if columns[source_name].data_type != target_columns[
                    target_name
                ].data_type:
                    errors.append(
                        f"{table.name}.{source_name}: type differs from "
                        f"{foreign_key.ref_table}.{target_name}"
                    )

    executable_overflow = [
        (number, line)
        for number, line in enumerate(sql.splitlines(), 1)
        if line and not line.startswith("--") and len(line) > MAX_LINE
    ]
    for number, line in executable_overflow:
        errors.append(
            f"line {number}: executable record is {len(line)} columns: {line}"
        )

    expected_tables = len(TABLES)
    expected_spaces = expected_tables - sum(t.implicit_lob for t in TABLES)
    expected_indexes = sum(index_count_for(table) for table in TABLES)
    counts = {
        "CREATE TABLE ": expected_tables,
        "CREATE TABLESPACE ": expected_spaces,
        "CREATE INDEX ": sum(
            1
            for table in TABLES
            for _ in range(index_count_for(table))
        )
        - sum(
            1
            for table in TABLES
            if not table.implicit_lob
            for index in [ExtraIndex(table.primary_key, True)]
        ),
    }
    if sql.count("CREATE TABLE ") != expected_tables:
        errors.append("generated CREATE TABLE count mismatch")
    if sql.count("CREATE TABLESPACE ") != expected_spaces:
        errors.append("generated CREATE TABLESPACE count mismatch")
    actual_indexes = sql.count("CREATE INDEX ") + sql.count(
        "CREATE UNIQUE INDEX "
    )
    if actual_indexes != expected_indexes:
        errors.append(
            f"generated CREATE INDEX count {actual_indexes} != "
            f"{expected_indexes}"
        )
    del counts
    return errors


def lint(sql: str) -> list[str]:
    """Error and unsupported findings of tools/ddl.py lint with the example profile."""
    profile = json.loads(paths.EXAMPLE_PROFILE.read_text(encoding="utf-8"))
    report = db2check.analyze(sql, db2check.Options.from_profile(profile))
    return [
        f"line {finding.line}: {finding.rule}: {finding.message}"
        for finding in report.findings
        if finding.severity in db2check.FAILING
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the existing output matches a fresh generation.",
    )
    args = parser.parse_args()
    sql = generate_sql()
    errors = validate_schema(sql) + lint(sql)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if args.check:
        if not args.output.exists():
            print(f"ERROR: missing generated artifact: {args.output}")
            return 1
        if args.output.read_text(encoding="utf-8") != sql:
            print(f"ERROR: generated artifact is stale: {args.output}")
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(sql, encoding="utf-8")
    print(
        "PASS: "
        f"{len(TABLES)} tables, "
        f"{len(TABLES) - 1} explicit table spaces, "
        f"{sum(index_count_for(table) for table in TABLES)} indexes, "
        f"executable lines <= {MAX_LINE} columns, tools/ddl.py lint clean"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
