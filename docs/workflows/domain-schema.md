# Domain schemas: the SQL-first route

Most requests describe a business domain (banking, insurance, logistics) rather
than a bounded compiler family. Write the DDL directly, then let the tools hold it
to IBM rules and to the QA goal of variety. [AGENTS.md](../../AGENTS.md) has the
short gate list; this page explains each step.

## Steps

1. Plan which tables carry which variants. The `core` baseline in
   [variety-baseline.json](../../qa/variety-baseline.json) lists the minimum: PBG and PBR,
   partition overrides, distinct SEGSIZE/LOCKSIZE/LOCKMAX/COMPRESS/free-space/
   MAXROWS/CLOSE/TRACKMOD/CCSID values, at least twelve type families, four default
   forms, identity ALWAYS and BY DEFAULT, row-change and hidden columns, unique and
   check constraints, three delete rules, NOT ENFORCED, single and composite keys,
   PARTITION BY RANGE, several AUDIT/DATA CAPTURE/APPEND/VOLATILE values, explicit
   and implicit placement, LOB support, and index variety (unique, WHERE NOT NULL,
   INCLUDE, ASC/DESC, CLUSTER, PADDED/NOT PADDED, PARTITIONED, FREEPAGE/PCTFREE).
   Realistic schemas usually repeat one production option set; that is not enough
   for extraction testing. [The exemplar](../../examples/varied-schema.sql) shows one way
   to spread these variants over five tables.
2. Avoid the [dialect traps](../../kb/dialect-traps.md). In particular: 8-byte database and
   table-space names, 30-byte column names unless TABLE_COL_NAME_EXPANSION is on, no
   `DEFAULT CURRENT TIMESTAMP`, no self-referencing FK inside CREATE TABLE (add it
   with ALTER TABLE and `ON DELETE NO ACTION` or `CASCADE`), an
   enforcing unique index for every key in an explicit table space before children,
   and LOB support objects (or `IN DATABASE`) for LOB columns.
3. `python3 tools/ddl.py lint <sql> --profile <profile>` must PASS. Read each
   finding's IBM source; findings are rules, not style.
4. `python3 tools/ddl.py coverage <sql> --baseline core` must meet every
   requirement unless the user narrowed scope. The text output also lists normalized
   clauses the script never exercises; use them to choose companion cases.
5. `python3 tools/ddl.py bundle <sql> ...` writes the source copy, catalog queries
   and expectations, cleanup scripts, name map, inventory of implicit objects, lint
   and coverage results, and a case record. Then run
   `.venv/bin/python tools/qa.py validate-case <bundle>/case.json`.

Use `--assume KIND:NAME` for objects that already exist on the target, such as a
storage group, database or distinct type. Use `--max-line 72` when the SQL must fit
fixed 72-column records. Function-level and APPLCOMPAT requirements come from
[the function-level chapter](../../kb/function-levels.md); `lint` prints
`compatibility.minimum_applcompat` with `--json`.

## Worked examples

- [varied-schema.sql](../../examples/varied-schema.sql): five tables that pass `lint`
  and meet the `core` baseline.
- [supply-chain-logistics](../../examples/domains/supply-chain-logistics/design.md):
  a 68-table generated domain schema with its request, plan and design case. It
  passes `lint` but meets only 11 of 43 `core` requirements, because its request
  fixes one uniform PBG layout. It shows realistic topology, not syntax variety.

Track a domain schema under `examples/domains/<id>/` only when it should be kept;
otherwise write it under the git-ignored `generated/<id>/`.

## After the gates

Follow [product verification](product-verification.md). Record the target
environment from [the checklist](../environment.md) before any execution.
