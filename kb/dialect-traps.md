# Db2 for z/OS DDL traps for agents

Language models mix Db2 for z/OS with Db2 LUW, Oracle, PostgreSQL, MySQL and SQL
Server. Each row below is enforced by `tools/ddl.py lint`; the rule ID is in
parentheses. Authority is the IBM Db2 13 for z/OS statement page cited, not other
products' documentation.

## Statement shape

| Do not write | Write instead | Why |
|---|---|---|
| `CREATE TABLE IF NOT EXISTS`, `DROP TABLE IF EXISTS` | Plain CREATE/DROP; use a preflight catalog query | Not in the CREATE/DROP diagrams (`dialect.if-not-exists`, `dialect.if-exists`; `ibm-create-table`, `ibm-drop`) |
| `CREATE OR REPLACE TABLE/INDEX/VIEW/TABLESPACE` | CREATE after a recorded DROP | OR REPLACE exists only for routines and advanced triggers (`dialect.or-replace`) |
| `ORGANIZE BY ROW`, `DISTRIBUTE BY`, `INDEX IN ts`, `LONG IN ts`, `MANAGED BY`, `EXTENTSIZE`, `PAGESIZE 8K` | `IN db.ts`; the BUFFERPOOL selects page size; USING STOGROUP/PRIQTY/SECQTY | LUW storage syntax (`dialect.clause`; `ibm-create-table`, `ibm-create-tablespace`) |
| Table space or database names longer than 8 bytes, or with `_`, `$`, `#`, `@` | Start with a letter; letters and digits only; 8 bytes at most | IBM forbids special characters in these names; `_` and national extenders are flagged for confirmation (`name.length`, `name.short-identifier-form`, `name.short-identifier-extender`; `ibm-limits`, `ibm-naming-conventions`) |
| Column names longer than 30 bytes | 30 bytes, unless the profile records TABLE_COL_NAME_EXPANSION ON | (`name.length`, `name.column-expansion`; `ibm-limits`, `ibm-fl100`) |
| Two tables `IN db.ts` with the same explicit table space | One table per UTS | (`table.tablespace-eligibility`; `ibm-create-table`) |
| `CREATE SYNONYM` | `CREATE ALIAS` | Synonyms cannot be created at APPLCOMPAT V12R1M504+ (`fl.removed-feature`; `ibm-applcompat-incompatible`) |

## Columns and data types

| Do not write | Write instead | Why |
|---|---|---|
| `BOOLEAN`, `TINYINT`, `NUMBER`, `VARCHAR2`, `TEXT`, `NVARCHAR`, `DATETIME`, `UUID`, `JSON`, `SERIAL` | SMALLINT/CHAR(1) + CHECK, SMALLINT, DECIMAL, VARCHAR, CLOB, VARGRAPHIC, TIMESTAMP, BINARY(16), CLOB/BLOB, identity | Not in the built-in-type diagram (`dialect.data-type`; `ibm-create-table`) |
| `col INTEGER NULL` | Omit NOT NULL | No NULL attribute (`dialect.null-attribute`) |
| `DEFAULT CURRENT TIMESTAMP`, `DEFAULT CURRENT DATE`, `DEFAULT NOW()` | `NOT NULL WITH DEFAULT` (value-less) on a datetime column | DEFAULT accepts constant, USER, SESSION_USER, CURRENT SQLID, NULL, or a cast function for distinct types (`table.default-value-form`) |
| `AUTO_INCREMENT`, `IDENTITY(1,1)` | `GENERATED ALWAYS AS IDENTITY (START WITH 1, INCREMENT BY 1)` on an exact numeric scale-0 column | (`dialect.clause`, `table.identity-cardinality`) |
| `ON UPDATE CURRENT_TIMESTAMP` | `TIMESTAMP NOT NULL GENERATED ALWAYS FOR EACH ROW ON UPDATE AS ROW CHANGE TIMESTAMP` (one per table) | (`dialect.clause`, `table.generated-not-null`) |
| `VARCHAR(5000)` in a 4 KB table space | At most 4046 bytes (VARGRAPHIC 2023) for 4 KB pages, or a larger page-size pool | (`table.data-type-range`; `ibm-limits`) |
| `DECIMAL(38, 2)`, `CHAR(300)` | DECIMAL precision 1-31; CHAR 1-255 | (`table.data-type-range`) |

## Keys and referential constraints

| Do not write | Write instead | Why |
|---|---|---|
| A nullable PRIMARY KEY or UNIQUE column | NOT NULL key columns | (`table.key-not-null`) |
| `PRIMARY KEY` on a table in an explicit table space with no index | `CREATE UNIQUE INDEX` with the same columns in the same order, before any child FK | The table stays incomplete and children cannot reference it (`table.incomplete-definition`, `table.fk-parent-unique-index`; `ibm-create-index`) |
| `REFERENCES same_table` inside CREATE TABLE | `ALTER TABLE ... ADD FOREIGN KEY ... REFERENCES same_table` after the parent index exists | The parent must already exist outside CREATE SCHEMA (`table.fk-self-reference`) |
| A self-reference with `ON DELETE RESTRICT`, `SET NULL` or no rule under `CURRENT RULES 'DB2'` | `ON DELETE NO ACTION` or `ON DELETE CASCADE` | The same table as parent and dependent allows only those rules (`table.fk-self-reference-delete-rule`; `ibm-alter-table`) |
| `ON UPDATE CASCADE`, `ON DELETE SET DEFAULT`, `DEFERRABLE` | ON DELETE RESTRICT, NO ACTION, CASCADE or SET NULL; NOT ENFORCED if needed | (`dialect.referential-on-update`, `dialect.referential-action`, `dialect.clause`) |
| FK column types that only resemble the parent's (INTEGER to BIGINT, CHAR(10) to VARCHAR(10)) | Identical type, length, scale and subtype | (`table.fk-type-identity`) |
| Composite foreign keys longer than 255 bytes | Foreign key length at most 255 minus the nullable column count | (`table.fk-key-length`) |
| `ON DELETE SET NULL` with all FK columns NOT NULL | At least one nullable FK column | (`table.fk-set-null`) |

## Table spaces and indexes

| Do not write | Write instead | Why |
|---|---|---|
| `SEGSIZE 30`, `DSSIZE 3 G`, `MAXROWS 300`, `PCTFREE 60 FOR UPDATE 50` | SEGSIZE multiple of 4 in 4-64; PBG DSSIZE power of two; MAXROWS 1-255; PCTFREE + FOR UPDATE at most 99 | (`tablespace.*`; `ibm-create-tablespace`) |
| `COMPRESS`, `DSSIZE`, `BUFFERPOOL`, `LOGGED` on CREATE TABLE with `IN db.ts` | Put them on CREATE TABLESPACE | Table-level forms apply only to implicit spaces (`table.explicit-space-physical-conflict`) |
| A table in `NUMPARTS n` without `PARTITION BY RANGE` | One `PARTITION k ENDING AT (...)` per partition | (`table.partitioning-mismatch`) |
| LOB columns in an explicit table space with nothing else | LOB table space, `CREATE AUX TABLE ... PART k`, and `CREATE UNIQUE INDEX ... ON aux` per partition, or use `IN DATABASE` for implicit LOB objects | (`table.lob-auxiliary-missing`, `auxtable.part-required`) |
| `INCLUDE` on a nonunique index; `PARTITIONED` on PBG; two CLUSTER indexes | UNIQUE with INCLUDE; PARTITIONED only on PBR tables; one CLUSTER index per table | (`index.include-requires-unique`, `index.partitioned-pbg`, `index.cluster`) |
| `CREATE INDEX ... WHERE status = 'A'` | `UNIQUE WHERE NOT NULL` is the only predicate form | (`dialect.partial-index`) |
| `DROP INDEX` of a primary-key index in cleanup | Drop the table space or database that owns the table | (`cleanup.drop-enforcing-index`) |
| `COMPRESS YES HUFFMAN` or multi-row `INSERT ... VALUES (...), (...)` without checking the level | Record APPLCOMPAT; HUFFMAN needs V12R1M509, multi-row INSERT V13R1M506 | (`fl.applcompat-gate`; [function levels](function-levels.md)) |
| SQL PL bodies with `;` as the script terminator | `--#SET TERMINATOR @` before the routine, `@` after `END` | (`script.sqlpl-terminator`; `ibm-procedure-body`) |
