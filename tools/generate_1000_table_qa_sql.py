#!/usr/bin/env python3
"""Generate the Db2 13 1,000-table positive DDL and seed-data workload."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "kb" / "test-design" / "create-1000-table-qa-workload.sql"

TABLE_COUNT = 1000
DATABASE = "Q1KDB001"
STOGROUP = "Q1KSG01"
SCHEMA = "QA1K"

FAMILIES = (
    "baseline",
    "numeric-types",
    "identity-always",
    "identity-by-default-descending",
    "character-graphic",
    "binary-types",
    "row-change-timestamp",
    "system-time-period",
    "business-time-exclusive",
    "business-time-inclusive",
    "bitemporal-foundation",
    "generated-data-change-operation",
    "rowid-and-hidden-column",
    "column-primary-key",
    "composite-primary-key",
    "composite-foreign-key",
    "like-with-identity",
    "as-fullselect-with-no-data",
    "materialized-query-table",
    "wide-32k-row",
)

PBR_FAMILIES = {7, 8, 9, 10, 14}
INDEX_FAMILIES = {2, 3, 7, 8, 9, 10, 12, 13, 14}
IDENTITY_FAMILIES = {2, 3, 16}


def table_name(number: int) -> str:
    return f"T{number:07d}"


def tablespace_name(number: int) -> str:
    return f"S{number:07d}"


def index_name(number: int) -> str:
    return f"I{number:07d}"


def constraint_name(prefix: str, number: int) -> str:
    return f"{prefix}{number:07d}"


def cycle_first(number: int) -> int:
    return ((number - 1) // len(FAMILIES)) * len(FAMILIES) + 1


def family_number(number: int) -> int:
    return (number - 1) % len(FAMILIES)


def encoding(number: int) -> str:
    if family_number(number) == 4:
        return "EBCDIC"
    return ("EBCDIC", "UNICODE", "ASCII")[(number - 1) // len(FAMILIES) % 3]


def page_and_pool(family: int) -> tuple[int, str]:
    if family == 19:
        return 32, "BP32K"
    if family in {4, 10}:
        return 8, "BP8K0"
    return 4, "BP0"


def dssize(number: int) -> int:
    return (1, 2, 4)[number % 3]


def seed_ids(number: int) -> tuple[int, int]:
    base = number * 10000
    return base + 1000, base + 9000


def tenant_values(number: int) -> tuple[str, str]:
    return f"T{number:07d}A", f"T{number:07d}B"


def create_tablespace(number: int) -> str:
    family = family_number(number)
    page_size, bufferpool = page_and_pool(family)
    size = dssize(number)
    segment_size = (4, 8, 16, 32, 64)[number % 5]
    compress = ("NO", "YES FIXEDLENGTH", "YES HUFFMAN")[number % 3]
    define = "NO" if number % 4 == 0 else "YES"
    gbpcache = ("CHANGED", "ALL", "NONE")[number % 3]
    locksize = ("ANY", "PAGE", "ROW", "TABLESPACE")[number % 4]
    lockmax = "0" if locksize == "TABLESPACE" else "SYSTEM"
    pctfree = (0, 5, 10, 20)[number % 4]
    pctfree_update = (0, 5, 10)[number % 3]
    member_cluster = number % 11 == 0

    partitioning = (
        "  NUMPARTS 4\n"
        "  PAGENUM RELATIVE\n"
        f"  DSSIZE {size} G"
        if family in PBR_FAMILIES
        else "  MAXPARTITIONS 64\n"
        "  NUMPARTS 1\n"
        f"  DSSIZE {size} G"
    )

    clauses = [
        f"CREATE TABLESPACE {tablespace_name(number)}",
        f"  IN {DATABASE}",
        f"  BUFFERPOOL {bufferpool}",
        partitioning,
        f"  SEGSIZE {segment_size}",
        f"  CCSID {encoding(number)}",
        f"  CLOSE {'NO' if number % 5 == 0 else 'YES'}",
        f"  COMPRESS {compress}",
        f"  DEFINE {define}",
        f"  FREEPAGE {(number % 4) * 2}",
        f"  PCTFREE {pctfree} FOR UPDATE {pctfree_update}",
        f"  GBPCACHE {gbpcache}",
        f"  LOCKMAX {lockmax}",
        f"  LOCKSIZE {locksize}",
        "  LOGGED",
        f"  MAXROWS {(64, 128, 255)[number % 3]}",
    ]
    if member_cluster:
        clauses.append("  MEMBER CLUSTER")
    clauses.extend(
        [
            f"  TRACKMOD {'NO' if number % 2 else 'YES'}",
            f"  USING STOGROUP {STOGROUP}",
            "    PRIQTY -1",
            "    SECQTY -1",
            "    ERASE NO;",
        ]
    )
    return "\n".join(clauses)


def common_columns(number: int, identity: str | None = None) -> list[str]:
    id_definition = identity or "ID BIGINT NOT NULL"
    return [
        id_definition,
        "TENANT_ID VARCHAR(12) NOT NULL",
        "STATUS CHAR(1) NOT NULL DEFAULT 'N'",
        "CREATED_AT TIMESTAMP(6) NOT NULL WITH DEFAULT",
    ]


def check_constraint(number: int) -> str:
    return (
        f"CONSTRAINT {constraint_name('C', number)} "
        "CHECK (STATUS IN ('N', 'A', 'X'))"
    )


def explicit_elements(number: int) -> tuple[list[str], str | None]:
    family = family_number(number)
    primary = constraint_name("P", number)
    unique = constraint_name("U", number)
    foreign = constraint_name("F", number)

    if family == 0:
        return common_columns(number) + [
            "AMOUNT DECIMAL(15,2) NOT NULL DEFAULT 0",
            "EVENT_DATE DATE NOT NULL WITH DEFAULT",
            check_constraint(number),
        ], None
    if family == 1:
        return common_columns(number) + [
            "SMALL_VALUE SMALLINT DEFAULT 0",
            "INT_VALUE INTEGER DEFAULT 0",
            "BIG_VALUE BIGINT DEFAULT 0",
            "DEC_VALUE DECIMAL(31,9) DEFAULT 0",
            "NUM_VALUE NUMERIC(9,4) DEFAULT 0",
            "FLOAT_VALUE FLOAT(24) DEFAULT 0",
            "REAL_VALUE REAL DEFAULT 0",
            "DOUBLE_VALUE DOUBLE PRECISION DEFAULT 0",
            "DF16_VALUE DECFLOAT(16)",
            "DF34_VALUE DECFLOAT(34)",
            check_constraint(number),
        ], None
    if family == 2:
        identity = (
            "ID BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY "
            "(START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999999 "
            "NO CYCLE CACHE 20 NO ORDER)"
        )
        return common_columns(number, identity) + [
            f"CONSTRAINT {primary} PRIMARY KEY (ID)",
            check_constraint(number),
        ], "ID ASC"
    if family == 3:
        identity = (
            "ID BIGINT NOT NULL GENERATED BY DEFAULT AS IDENTITY "
            "(START WITH -1 INCREMENT BY -1 NO MINVALUE MAXVALUE -1 "
            "NO CYCLE CACHE 20 NO ORDER)"
        )
        return common_columns(number, identity) + [
            f"CONSTRAINT {unique} UNIQUE (ID)",
            check_constraint(number),
        ], "ID DESC"
    if family == 4:
        return common_columns(number) + [
            "FIXED_TEXT CHARACTER(40) FOR SBCS DATA DEFAULT ''",
            "MIXED_TEXT VARCHAR(6000) FOR MIXED DATA",
            "GRAPHIC_TEXT GRAPHIC(100)",
            "VGRAPHIC_TEXT VARGRAPHIC(500)",
            check_constraint(number),
        ], None
    if family == 5:
        return common_columns(number) + [
            "FIXED_BYTES BINARY(64) WITH DEFAULT",
            "VARIABLE_BYTES VARBINARY(1024)",
            check_constraint(number),
        ], None
    if family == 6:
        return common_columns(number) + [
            (
                "ROW_CHANGED TIMESTAMP(6) WITHOUT TIME ZONE NOT NULL "
                "GENERATED ALWAYS FOR EACH ROW ON UPDATE AS ROW CHANGE TIMESTAMP"
            ),
            check_constraint(number),
        ], None
    if family == 7:
        return common_columns(number) + [
            (
                "SYS_START TIMESTAMP(12) WITHOUT TIME ZONE NOT NULL "
                "GENERATED ALWAYS AS ROW BEGIN"
            ),
            (
                "SYS_END TIMESTAMP(12) WITHOUT TIME ZONE NOT NULL "
                "GENERATED ALWAYS AS ROW END"
            ),
            (
                "TRANS_START TIMESTAMP(12) WITHOUT TIME ZONE NOT NULL "
                "GENERATED ALWAYS AS TRANSACTION START ID"
            ),
            "PERIOD FOR SYSTEM_TIME (SYS_START, SYS_END)",
            f"CONSTRAINT {primary} PRIMARY KEY (ID)",
            check_constraint(number),
        ], "ID ASC"
    if family == 8:
        return common_columns(number) + [
            "BUS_START DATE NOT NULL DEFAULT '2020-01-01'",
            "BUS_END DATE NOT NULL DEFAULT '9999-12-30'",
            "PERIOD FOR BUSINESS_TIME (BUS_START, BUS_END EXCLUSIVE)",
            f"CONSTRAINT {primary} PRIMARY KEY (ID, BUSINESS_TIME WITHOUT OVERLAPS)",
            check_constraint(number),
        ], "ID ASC, BUSINESS_TIME WITHOUT OVERLAPS"
    if family == 9:
        return common_columns(number) + [
            "BUS_START DATE NOT NULL",
            "BUS_END DATE NOT NULL",
            "PERIOD FOR BUSINESS_TIME (BUS_START, BUS_END INCLUSIVE)",
            (
                f"CONSTRAINT {unique} UNIQUE "
                "(TENANT_ID, BUSINESS_TIME WITHOUT OVERLAPS)"
            ),
            check_constraint(number),
        ], "TENANT_ID ASC, BUSINESS_TIME WITHOUT OVERLAPS"
    if family == 10:
        return common_columns(number) + [
            (
                "SYS_START TIMESTAMP(12) WITHOUT TIME ZONE NOT NULL "
                "GENERATED ALWAYS AS ROW BEGIN"
            ),
            (
                "SYS_END TIMESTAMP(12) WITHOUT TIME ZONE NOT NULL "
                "GENERATED ALWAYS AS ROW END"
            ),
            (
                "TRANS_START TIMESTAMP(12) WITHOUT TIME ZONE NOT NULL "
                "GENERATED ALWAYS AS TRANSACTION START ID"
            ),
            "BUS_START TIMESTAMP(6) WITHOUT TIME ZONE NOT NULL DEFAULT '2020-01-01-00.00.00'",
            "BUS_END TIMESTAMP(6) WITHOUT TIME ZONE NOT NULL DEFAULT '9999-12-30-00.00.00'",
            "PERIOD FOR SYSTEM_TIME (SYS_START, SYS_END)",
            "PERIOD FOR BUSINESS_TIME (BUS_START, BUS_END EXCLUSIVE)",
            f"CONSTRAINT {primary} PRIMARY KEY (ID)",
            check_constraint(number),
        ], "ID ASC"
    if family == 11:
        return common_columns(number) + [
            "CHANGE_OP CHAR(1) GENERATED ALWAYS AS (DATA CHANGE OPERATION)",
            check_constraint(number),
        ], None
    if family == 12:
        return common_columns(number) + [
            "RID ROWID NOT NULL GENERATED ALWAYS",
            "INTERNAL_TAG CHAR(8) NOT NULL DEFAULT 'HIDDEN' IMPLICITLY HIDDEN",
            check_constraint(number),
        ], "RID ASC"
    if family == 13:
        columns = common_columns(number)
        columns[0] = f"ID BIGINT NOT NULL CONSTRAINT {primary} PRIMARY KEY"
        return columns + [check_constraint(number)], "ID ASC"
    if family == 14:
        return common_columns(number) + [
            f"CONSTRAINT {primary} PRIMARY KEY (TENANT_ID, ID)",
            check_constraint(number),
        ], "TENANT_ID ASC, ID ASC"
    if family == 15:
        parent_number = number - 1
        return common_columns(number) + [
            "PARENT_TENANT VARCHAR(12) NOT NULL",
            "PARENT_ID BIGINT NOT NULL",
            (
                f"CONSTRAINT {foreign} FOREIGN KEY (PARENT_TENANT, PARENT_ID) "
                f"REFERENCES {SCHEMA}.{table_name(parent_number)} (TENANT_ID, ID) "
                "ON DELETE RESTRICT"
            ),
            check_constraint(number),
        ], None
    if family == 19:
        return common_columns(number) + [
            "SHORT_TEXT VARCHAR(2000)",
            "WIDE_TEXT VARCHAR(20000)",
            "WIDE_BYTES VARBINARY(8000)",
            "FIXED_TRAILER CHAR(200) DEFAULT ''",
            check_constraint(number),
        ], None
    raise ValueError(f"family {family} is not an explicit-element family")


def placement_and_options(number: int, minimal: bool = False) -> str:
    family = family_number(number)
    size = dssize(number)
    lines = [f"  IN {DATABASE}.{tablespace_name(number)}"]
    if family in PBR_FAMILIES:
        base = number * 10000
        lines.extend(
            [
                "  PARTITION BY RANGE (ID ASC)",
                "    (",
                f"      PARTITION 1 ENDING AT ({base + 2499}),",
                f"      PARTITION 2 ENDING AT ({base + 4999}),",
                f"      PARTITION 3 ENDING AT ({base + 7499}),",
                "      PARTITION 4 ENDING AT (MAXVALUE)",
                "    )",
            ]
        )
    elif not minimal and family in {0, 2, 4, 6, 12, 19}:
        lines.append(f"  PARTITION BY SIZE EVERY {size} G")

    if not minimal:
        lines.extend(
            [
                f"  AUDIT {('NONE', 'CHANGES', 'ALL')[number % 3]}",
                f"  DATA CAPTURE {'CHANGES' if number % 4 == 0 else 'NONE'}",
                f"  CCSID {encoding(number)}",
                f"  {'VOLATILE' if number % 6 == 0 else 'NOT VOLATILE'} CARDINALITY",
                f"  APPEND {'YES' if number % 7 == 0 and number % 11 != 0 else 'NO'}",
            ]
        )
    else:
        lines.append(f"  CCSID {encoding(number)}")
    return "\n".join(lines)


def create_table(number: int) -> tuple[str, str | None]:
    family = family_number(number)
    name = table_name(number)

    if family == 16:
        source_number = cycle_first(number) + 2
        sql = (
            f"CREATE TABLE {SCHEMA}.{name}\n"
            f"  LIKE {SCHEMA}.{table_name(source_number)}\n"
            "  INCLUDING IDENTITY COLUMN ATTRIBUTES\n"
            f"{placement_and_options(number, minimal=True)};"
        )
        return sql, None

    if family == 17:
        source_number = cycle_first(number)
        sql = (
            f"CREATE TABLE {SCHEMA}.{name}\n"
            "  (ID, TENANT_ID, STATUS, AMOUNT_COPY)\n"
            "  AS\n"
            f"    (SELECT ID, TENANT_ID, STATUS, AMOUNT\n"
            f"       FROM {SCHEMA}.{table_name(source_number)})\n"
            "  WITH NO DATA\n"
            "  INCLUDING COLUMN DEFAULTS\n"
            f"{placement_and_options(number, minimal=True)};"
        )
        return sql, None

    if family == 18:
        source_number = cycle_first(number)
        sql = (
            f"CREATE TABLE {SCHEMA}.{name}\n"
            "  (TENANT_ID, STATUS, ROW_COUNT, TOTAL_AMOUNT)\n"
            "  AS\n"
            "    (SELECT TENANT_ID, STATUS, COUNT_BIG(*), SUM(AMOUNT)\n"
            f"       FROM {SCHEMA}.{table_name(source_number)}\n"
            "      GROUP BY TENANT_ID, STATUS)\n"
            "  DATA INITIALLY DEFERRED\n"
            "  REFRESH DEFERRED\n"
            "  MAINTAINED BY SYSTEM\n"
            "  ENABLE QUERY OPTIMIZATION\n"
            f"{placement_and_options(number, minimal=True)};"
        )
        return sql, None

    elements, key = explicit_elements(number)
    rendered_elements = ",\n    ".join(elements)
    sql = (
        f"CREATE TABLE {SCHEMA}.{name}\n"
        "  (\n"
        f"    {rendered_elements}\n"
        "  )\n"
        f"{placement_and_options(number)};"
    )
    return sql, key


def create_index(number: int, key: str) -> str:
    return (
        f"CREATE UNIQUE INDEX {SCHEMA}.{index_name(number)}\n"
        f"  ON {SCHEMA}.{table_name(number)} ({key})\n"
        f"  USING STOGROUP {STOGROUP}\n"
        "    PRIQTY -1\n"
        "    SECQTY -1\n"
        "    ERASE NO\n"
        "  FREEPAGE 0\n"
        "  PCTFREE 10\n"
        "  GBPCACHE CHANGED\n"
        "  DEFINE YES\n"
        "  COMPRESS NO\n"
        "  INCLUDE NULL KEYS\n"
        "  BUFFERPOOL BP0\n"
        "  CLOSE YES\n"
        "  DEFER NO\n"
        "  COPY NO;"
    )


def seed_data(number: int) -> str:
    family = family_number(number)
    name = f"{SCHEMA}.{table_name(number)}"
    first_id, second_id = seed_ids(number)
    first_tenant, second_tenant = tenant_values(number)

    if family == 18:
        return f"REFRESH TABLE {name};"
    if family in IDENTITY_FAMILIES:
        if family == 16:
            columns = "TENANT_ID, STATUS, CREATED_AT"
            values = (
                f"('{first_tenant}', 'A', CURRENT TIMESTAMP),\n"
                f"    ('{second_tenant}', 'N', CURRENT TIMESTAMP)"
            )
        else:
            columns = "TENANT_ID, STATUS"
            values = f"('{first_tenant}', 'A'),\n    ('{second_tenant}', 'N')"
        return f"INSERT INTO {name} ({columns})\n  VALUES {values};"
    if family == 15:
        parent_number = number - 1
        parent_first_id, parent_second_id = seed_ids(parent_number)
        parent_first_tenant, parent_second_tenant = tenant_values(parent_number)
        return (
            f"INSERT INTO {name}\n"
            "  (ID, TENANT_ID, STATUS, PARENT_TENANT, PARENT_ID)\n"
            f"  VALUES ({first_id}, '{first_tenant}', 'A', "
            f"'{parent_first_tenant}', {parent_first_id}),\n"
            f"         ({second_id}, '{second_tenant}', 'N', "
            f"'{parent_second_tenant}', {parent_second_id});"
        )
    if family == 17:
        return (
            f"INSERT INTO {name} (ID, TENANT_ID, STATUS, AMOUNT_COPY)\n"
            f"  VALUES ({first_id}, '{first_tenant}', 'A', 10.25),\n"
            f"         ({second_id}, '{second_tenant}', 'N', 90.75);"
        )
    if family == 9:
        return (
            f"INSERT INTO {name} (ID, TENANT_ID, STATUS, BUS_START, BUS_END)\n"
            f"  VALUES ({first_id}, '{first_tenant}', 'A', "
            "'2020-01-01', '2020-12-31'),\n"
            f"         ({second_id}, '{first_tenant}', 'N', "
            "'2021-01-01', '2021-12-31');"
        )
    return (
        f"INSERT INTO {name} (ID, TENANT_ID, STATUS)\n"
        f"  VALUES ({first_id}, '{first_tenant}', 'A'),\n"
        f"         ({second_id}, '{second_tenant}', 'N');"
    )


def header() -> str:
    family_lines = "\n".join(
        f"--   {number:02d}: {name}" for number, name in enumerate(FAMILIES, start=1)
    )
    return f"""-- IBM Db2 13 for z/OS 1,000-table QA workload.
-- Generated by tools/generate_1000_table_qa_sql.py. Do not edit by hand.
-- Official source IDs: ibm-create-stogroup, ibm-create-database,
-- ibm-create-tablespace, ibm-create-table, ibm-create-index.
-- Documentation baseline: 2026-09-03, V13R1M509.
--
-- Replace {{{{VCAT}}}} with a valid 1-8 character ICF catalog or alias.
-- Prerequisites: APPLCOMPAT V13R1M509, authorization, SMS non-specific
-- volume allocation, and active BP0, BP8K0, and BP32K buffer pools.
-- Run only in an isolated QA subsystem. This creates 1 storage group,
-- 1 database, 1,000 table spaces, 1,000 tables, supporting indexes, and
-- seed rows. The PBR cases allocate four partitions and can consume
-- substantial catalog, storage, and utility resources.
--
-- This is a positive workload. Expected-failure cases are excluded because
-- one intentional error can stop batch execution. LOB/XML definitions are
-- excluded because they require additional support table spaces and would
-- violate the one-table-space-per-table invariant. Current-level hash,
-- accelerator-only, FIELDPROC, VALIDPROC, security-label, and key-label cases
-- require deprecated or external environment capabilities and are excluded.
--
-- Twenty definition families repeat 50 times with varied table-space
-- encodings, page sizes, compression, allocation, free-space, cache, lock,
-- audit, data-capture, volatility, append, and partition attributes:
{family_lines}
--
-- Optional cleanup after preserving evidence:
--   DROP DATABASE {DATABASE};
--   DROP STOGROUP {STOGROUP};

CREATE STOGROUP {STOGROUP}
  VOLUMES ('*')
  VCAT {{{{VCAT}}}};

CREATE DATABASE {DATABASE}
  BUFFERPOOL BP0
  INDEXBP BP0
  STOGROUP {STOGROUP}
  CCSID EBCDIC;

COMMIT;
"""


def build() -> str:
    sections = [header().rstrip()]
    for number in range(1, TABLE_COUNT + 1):
        family = family_number(number)
        sections.append(
            "\n".join(
                [
                    f"-- Case {number:04d}: {FAMILIES[family]}; "
                    f"encoding={encoding(number)}; "
                    f"table-space={'PBR-RPN' if family in PBR_FAMILIES else 'PBG'}.",
                    create_tablespace(number),
                ]
            )
        )
        table_sql, key = create_table(number)
        case_parts = [table_sql]
        if key is not None:
            case_parts.append(create_index(number, key))
        case_parts.append(seed_data(number))
        if number % 25 == 0:
            case_parts.append("COMMIT;")
        sections.append("\n\n".join(case_parts))
    return "\n\n".join(sections) + "\n"


def validate(sql: str) -> None:
    assert len(re.findall(r"^CREATE STOGROUP ", sql, re.MULTILINE)) == 1
    assert len(re.findall(r"^CREATE DATABASE ", sql, re.MULTILINE)) == 1
    assert len(re.findall(r"^CREATE TABLESPACE S\d{7}$", sql, re.MULTILINE)) == TABLE_COUNT
    assert len(re.findall(rf"^CREATE TABLE {SCHEMA}\.T\d{{7}}$", sql, re.MULTILINE)) == TABLE_COUNT

    table_spaces = re.findall(r"^CREATE TABLESPACE (S\d{7})$", sql, re.MULTILINE)
    tables = re.findall(rf"^CREATE TABLE {SCHEMA}\.(T\d{{7}})$", sql, re.MULTILINE)
    assert len(table_spaces) == len(set(table_spaces)) == TABLE_COUNT
    assert len(tables) == len(set(tables)) == TABLE_COUNT

    for number in range(1, TABLE_COUNT + 1):
        placement = f"IN {DATABASE}.{tablespace_name(number)}"
        assert sql.count(placement) == 1, placement

    assert sql.count("{{VCAT}}") == 2
    assert "CREATE LOB TABLESPACE" not in sql
    assert not re.search(r"^\s+[A-Z0-9_]+ XML(?:\s|$)", sql, re.MULTILINE)


def main() -> None:
    sql = build()
    validate(sql)
    OUTPUT.write_text(sql, encoding="utf-8")
    print(f"generated {OUTPUT.relative_to(ROOT)} ({TABLE_COUNT} tables)")


if __name__ == "__main__":
    main()
