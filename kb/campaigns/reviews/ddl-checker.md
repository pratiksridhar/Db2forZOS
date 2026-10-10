# Static DDL checker, coverage, diff and bundle review, 2026-10-10

This review covers `tools/db2sql.py`, `tools/db2check.py`, the `lint`, `coverage`,
`diff` and `bundle` commands of `tools/ddl.py`, and the data files
`kb/data/db2z13-ddl-checks.json`, `kb/data/db2z13-catalog-columns.json`,
`kb/data/db2z13-function-levels.json` and `kb/authoring/variety-baseline.json`.
It does not re-certify existing chapters, models or the legacy workload.

## Why these tools exist

The repository's practical use is agents writing domain schemas (banking, insurance,
logistics) for product extraction tests. Before this change the only automatic
check of agent-written SQL was lexical framing. Three checked-in or local domain
scripts showed the gap:

- `banking.sql` (4) and `supply-chain-logistics.sql` (3) define self-referencing
  foreign keys inside `CREATE TABLE`. IBM requires the parent table to exist and
  says T1 and T2 cannot be the same table outside the schema processor, so these
  statements fail on Db2. The fix is `ALTER TABLE ... ADD FOREIGN KEY` after the
  parent's enforcing index exists.
- All three scripts use one table-space option set for every table and none of
  PBR, partition overrides, XML, temporal, compression, encoding variety, hidden
  columns, `INCLUDE`, `DESC`, partitioned indexes or unenforced keys. `banking.sql`
  meets 11 of 43 requirements of the `core` variety baseline.
- Each session wrote its own generator with partial checks (counts, record width),
  so no shared rule was applied twice.

## Sources reviewed

HTML statement and catalog topics were retrieved on 2026-10-10 through IBM's
documentation content service. Exact facts used by rules:

- `ibm-create-table`: column-definition and built-in-type diagrams (types and
  default lengths; `DEFAULT` forms limited to constant, `USER`, `SESSION_USER`,
  `CURRENT SQLID`, `NULL`, or cast function for distinct types); primary/unique
  keys (NOT NULL, excluded types, 64 columns, `2000 - n - 2m - 3d`); foreign keys
  (excluded types including DECFLOAT, 64 columns, length `255 - n`, parent key
  must match a primary or unique key in the same order, identical column
  descriptions, no self-reference outside `CREATE SCHEMA`, `SET NULL` needs a
  nullable column, `PERIOD BUSINESS_TIME` on both sides with `ON DELETE RESTRICT`);
  identity (exact numeric scale 0, one per table, defaults START WITH = MINVALUE,
  INCREMENT BY 1, NO CYCLE, CACHE 20, NO ORDER); row-change timestamp (one per
  table, NOT NULL, no DEFAULT); IN-clause eligibility (no implicit, LOB, XML or
  non-UTS space and no partitioned space that already holds a table); LOB
  auxiliary objects; the absence of `IF NOT EXISTS`, `OR REPLACE` and `ON UPDATE`.
- `ibm-create-tablespace`: SEGSIZE multiple of 4 in 4-64; MAXPARTITIONS 1-4096
  and Table 1 ceilings by DSSIZE and page size; NUMPARTS 1-4096 and at most
  MAXPARTITIONS; PBG DSSIZE powers of two 1-256 G; PBR RPN DSSIZE 1-1024 G and
  partition DSSIZE only with PAGENUM RELATIVE; FREEPAGE 0-255; PCTFREE 0-99; FOR
  UPDATE -1 to 99 with a sum of at most 99; MAXROWS 1-255; LOCKSIZE values;
  LOCKMAX with LOCKSIZE TABLESPACE; PRIQTY/SECQTY values; DFSMS note above 4 G.
- `ibm-create-lob-tablespace`: LOCKSIZE ANY or LOB; default DSSIZE 4 G.
- `ibm-create-auxiliary-table`: LOB table space placement, STORES/COLUMN, and PART
  for partitioned base tables; `ibm-applcompat-incompatible` adds that PART is
  required for PBG base tables from APPLCOMPAT V12R1M504.
- `ibm-create-index`: key columns and types, INCLUDE rules, PARTITIONED only for
  PBR, unique partitioned secondary superset rule, CLUSTER restrictions, DESC and
  RANDOM restrictions, FREEPAGE/PCTFREE ranges, key-length formulas, auxiliary
  index form, and "same columns in the same order" for enforcing indexes;
  `ibm-clustering-indexes`: one clustering index per table.
- `ibm-limits`: identifier lengths (8 bytes for database, table space, index
  space and buffer pool; 128 for tables, indexes, constraints, schemas, storage
  groups; 30 bytes for columns unless TABLE_COL_NAME_EXPANSION is on), 750/749
  columns, CHECK at most 3800 bytes, string limits by page size.
- `ibm-naming-conventions`: buffer-pool names and short-identifier form.
- `ibm-record-lengths`: record overhead and maximum record sizes.
- Catalog tables SYSDATABASE, SYSTABLESPACE, SYSTABLEPART, SYSTABLES, SYSCOLUMNS,
  SYSINDEXES, SYSINDEXPART, SYSKEYS, SYSRELS, SYSFOREIGNKEYS, SYSCHECKS and
  SYSAUXRELS: column names and declared types are recorded in
  `db2z13-catalog-columns.json`; generated queries can select only those columns.
  Code values used in assertions (for example LOCKRULE, LOCKMAX -1 for SYSTEM,
  TRACKMOD blank for YES, UNIQUERULE P/C/R/U/D/N/G, DEFAULT I/J/E/F/A/D/Q/R/X/U/S/N/Y,
  ORDERING A/D/R and blank for INCLUDE) come from those pages.
- Function levels: see [the function-level chapter](../../function-levels.md).

## Severity and scope

`error` means a documented rule is violated. `unsupported` means the construct is
outside the modeled clause subset or is another dialect's syntax; it fails by
default because silence would look like approval. `warning` covers environment-
dependent results and estimates (row length). `notice` lists unchecked statements
and level requirements.

The reader is structural, not a Db2 grammar. Views, aliases, sequences, routines,
triggers, GRANT, COMMENT and LABEL are recognized for ordering and reported as not
checked. Expressions in CHECK constraints, generated expressions, XML modifiers
and fullselects are not validated. Name resolution assumes the script's own SET
CURRENT SCHEMA/SQLID statements. Static acceptance never replaces execution on a
recorded subsystem.

## Diff and bundle limits

`diff` compares parsed definitions with field-aware name maps. Omitted versus
explicit values are equal only for defaults that IBM documents as fixed; values
supplied by subsystem parameters, the database, or APPLCOMPAT are reported as
environment-dependent unless the profile resolves them. Identity defaults are
resolved for ascending sequences only.

`bundle` derives catalog queries and expectations only for objects the script
creates with known names. Implicit objects with generated names are listed in
`inventory.json` but not compared. Unnamed constraints get Db2-generated names, so
RELNAME keys may differ between source and replay; name every constraint in QA
scripts.

## Validation performed

Unit tests require a triggering fixture for every rule in the catalog, verify that
all rule, source, clause and gate references resolve, lint every rendered campaign
model case and the legacy 1,000-table workload, check the exemplar against the
`core` baseline, round-trip a bundle contract through `tools/qa.py compare`, and
cover diff default handling. No Db2 subsystem or administration product was used.
