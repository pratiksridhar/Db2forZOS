# Working with related table cases

Use `table-relational` when you need a source-derived parent/child fixture with
composite referential integrity, enforcing indexes and varied column/CHECK clauses.
Start with [the main table chapter](table.md) and the
[scoped IBM review](../campaigns/reviews/table-relational.md).

```sh
python3 tools/qa.py build --model table-relational \
  --profile kb/campaigns/profiles/example.json \
  --run R01 --negative --out generated/relational-demo
```

The profile is unverified. Generation executes no SQL; open the bundle's RUN.md
and replace environment settings before an authorized subsystem run.

## What each case creates

A parent has NOT NULL `(TENANT_ID, PARENT_ID)` as its primary key and a separate
NOT NULL `EXTERNAL_CODE` unique key. Two explicit enforcing indexes complete the
parent before child creation. The child has a composite `(P_TENANT, P_ID)` FK,
monetary/status/date columns, a varied QA_VALUE column, and one named CHECK.
Each table has its own explicit logged PBG table space in the same campaign
database. Source and replay have distinct schemas and databases.

Four independent choices are crossed:

- FK nullability: both NOT NULL, only P_ID nullable, or both nullable.
- ON DELETE: omitted, RESTRICT, NO ACTION, CASCADE, or SET NULL.
- QA_VALUE: VARCHAR(1), VARCHAR(1024) with the exact default `MiXeD  `,
  DECIMAL(31,9) with a zero default, or TIMESTAMP(12).
- CHECK: nonnegative amount; amount range plus allowed status values;
  or an end date that is null or no earlier than the start date.

The full domain is 180 combinations; 168 are valid. SET NULL with both FK columns
NOT NULL is the sole encoded invalid interaction. Pairwise covers feasible pairs
within that domain, not every three-way interaction. Use the coverage report to
see selected counts and any budget gaps.

**SET NULL needs at least one nullable FK column.** With only P_ID nullable, a
parent deletion sets P_ID to null and leaves P_TENANT unchanged. With both
nullable, it nulls both. Omitted ON DELETE defaults to RESTRICT only because this
compiler requires CURRENT RULES DB2.

## Extraction and source checks

Extract the child plus its parent, both enforcing indexes and both table spaces.
The case name map includes their qualified names. The child intentionally has no
PRIMARY KEY/UNIQUE constraint: its CREATE TABLE action completes its definition
without requiring an index after the action.

Catalog queries assert the intended parent and table-space relationships using
each side's actual names, ordered parent and foreign keys, enforcement flags,
column definitions and literal defaults. Parent STATUS must be X; child STATUS
must be blank. Missing exports or values that violate encoded assertions fail the scoped
contract, even when source and replay are identical.
CHECKCONDITION is compared as raw text. Formatting-only differences can therefore
require a manual review; never erase literal case or whitespace to hide a mismatch.
Raw equality does not validate the CHECK predicate's intended behavior.

## Behavioral probes for an execution harness

Run probes on an isolated, successfully created positive case. Capture every
statement result and reset the fixture between independent probes. Do the same
on source and actual product replay. These instructions do not authorize execution.

1. Insert parent `(TENANT_ID, PARENT_ID, EXTERNAL_CODE) = (17, 23, 'EXT-1')`.
   Insert child ID 101 referencing `(17, 23)`, with amount 1.00, status A,
   VALID_FROM 2026-01-01 and VALID_TO 2026-01-02. Omit QA_VALUE so its selected
   default/null behavior is exercised. These values satisfy every modeled CHECK.
2. Try a second child referring to `(17, 999)`. It must fail the FK, independent
   of selected nullability. Keep the expected diagnostic unspecified until Db2
   produces one; an authority/setup failure is not the intended result.
3. For `amount` or `compound`, try amount -1.00. For `compound`, separately try
   status Z with a valid amount. For `date-or-null`, try VALID_TO 2025-12-31.
   Each must fail CK_VALUE; an allowed row and a null end date must succeed.
4. On a fresh valid parent/child pair, delete the parent. RESTRICT, omitted and
   NO ACTION must reject this simple delete. CASCADE removes the child. SET NULL
   retains it with the null changes described above. Capture the final child
   values, not just the delete SQLCODE.
5. Roll back or remove only probe rows recorded as inserted by the harness.
   Per-case DDL cleanup drops the child table space, then the parent table space;
   those drops own the contained tables and indexes. Do not directly drop the
   enforcing indexes or add unrelated objects to campaign table spaces.

This family does not model larger graphs, cycles, key-width limits, temporal
relationships, LOB/XML support objects or arbitrary CHECK expressions. Extend a
separate bounded model with IBM-reviewed constraints before claiming those paths.
