# ALTER TABLE options, catalog evidence and case outcomes, 2026-10-10

This review covers changes to `tools/ddl.py lint`, `bundle` and `diff`, the new
`tools/qa.py snapshot`, `record` and `status` commands, typed catalog contracts, and
the supply-chain example. It does not re-certify the [checker review](ddl-checker.md),
the [diff review](diff-product-output.md), chapters or models.

## Why

- Catalog comparison needed hand-built JSON: 11 result sets and 95 rows for the
  exemplar alone, twice per case.
- A product that set `DATA CAPTURE` or a similar option with `ALTER TABLE` got a
  false `different` next to a `not-compared` entry, and a bundle derived from such a
  script expected the wrong catalog values.
- No tool recorded source acceptance, extraction, replay or comparison, so every
  case stayed in `design`.
- The supply-chain example failed `lint`, and its tracked `plan.json` held a local
  absolute path because `ddl.py plan` wrote absolute paths.
- The catalog comparator had no seeded-defect test.

## Sources reviewed

HTML topics retrieved on 2026-10-10 through a summarizing reader; quotations are
short, and catalog declarations were confirmed by a second request.

- `ibm-alter-table`, ON DELETE description: "If T1 and T2 are the same table, CASCADE
  or NO ACTION must be specified." The default delete rule follows `CURRENT RULES`:
  `RESTRICT` under `'DB2'`, `NO ACTION` otherwise. This became checker rule
  `table.fk-self-reference-delete-rule`.
- `ibm-alter-table`, clause list: `DATA CAPTURE NONE|CHANGES`, `AUDIT NONE|CHANGES|ALL`,
  `VOLATILE` and `NOT VOLATILE` with the optional `CARDINALITY` ("an optional keyword
  that currently has no effect"), `APPEND NO|YES`, `VALIDPROC program-name|NULL`,
  `ADD RESTRICT ON DROP` and `DROP RESTRICT ON DROP`. Their descriptions match the
  CREATE TABLE options. `ADD RESTRICT ON DROP` "Restricts dropping the table and the
  database and table space that contain the table." A new validation procedure "is not
  used to validate existing table rows." "Do not specify DATA CAPTURE CHANGES for
  tables that reside in table spaces that specify NOT LOGGED." Pending definition
  changes and advisory REORG states are described for column alterations, not for
  these clauses. "The same clause must not be specified more than one time, except
  for the ADD COLUMN or ALTER COLUMN clauses." The flattened HTML diagram did not show
  the exact `VOLATILE CARDINALITY` arrangement; the parser accepts the same forms as
  for CREATE TABLE.
- `ibm-create-table`, REFERENCES: "T1 and T2 cannot be the same table" (the existing
  `table.fk-self-reference` rule), and the same `CURRENT RULES` default delete rule.
- `ibm-catalog-sysroutines`, `ibm-catalog-sysparms`, `ibm-catalog-syspackage` and
  `ibm-catalog-systriggers`: declared types of the columns the procedure and trigger
  models select or filter on, added to `kb/data/db2z13-catalog-columns.json` with a
  `columns_scope` note, because those entries list only some columns of each table.

## Findings fixed

| Finding | Change |
|---|---|
| The exemplar added its self-reference `LINE_PARENT_FK` with `ON DELETE SET NULL`, which the ALTER TABLE rule forbids | `ON DELETE NO ACTION`; the exemplar now uses all four delete rules. The regenerated fixture follows |
| The supply-chain generator put three self-references inside CREATE TABLE with `ON DELETE RESTRICT` | `ALTER TABLE ... ADD CONSTRAINT ... ON DELETE NO ACTION` after the table's enforcing index; the generator now fails unless `lint` passes |
| Campaign-model catalog queries were never checked against the verified catalog columns | Each query names its `table`; every selected column must have a declared type, and computed fields declare `expression_types` |
| Bundle cleanup dropped a table with `RESTRICT ON DROP` directly | `ALTER TABLE ... DROP RESTRICT ON DROP` comes first |
| `ddl.py plan` wrote absolute paths into argv and the environment profile | Paths inside the repository are written relative to its root |

## Rules

| Behavior | Rule |
|---|---|
| `ALTER TABLE` option clauses listed above | `lint` applies them to the altered table and reports a repeated clause or an undocumented value; `bundle` expectations, cleanup and `diff` read the altered definition |
| Other `ALTER` statements | Unchanged: a notice in `lint` and `not-compared` in `diff` |
| Snapshot value types | From the declared catalog type in the contract: integer families become JSON integers; character, date and time families stay text, exactly as exported. Other declared types are refused |
| Snapshot NULL | An unquoted empty field, or the `--null` text, is NULL in a nullable column; in a NOT NULL column it is text (or an error for an integer) |
| `compare` | Rejects a value whose JSON type contradicts the declared type, NULL in a NOT NULL column, and a snapshot converted for another contract |
| Case outcomes | Attempts per phase in the case's `outcomes`; the status is derived: `fail` or `blocked` from any required phase, `pass` when all required phases pass, otherwise `in_progress`. The comparison result is computed, never typed |

## Limits

- Not modeled: `ALTER TABLE ... ADD COLUMN`, `ALTER COLUMN` (including `RESTART WITH`),
  `ADD PERIOD`, versioning, access-control activation, partition alterations, and
  every `ALTER TABLESPACE` and `ALTER INDEX`. They stay `not-compared`.
- `lint` does not yet reject `DATA CAPTURE CHANGES` on a table in a `NOT LOGGED` table
  space.
- `tests/fixtures/varied-schema-catalog/` imitates client exports. It meets all 80
  expectations of the exemplar's bundle contract; columns without an expectation
  hold plausible values, not observed ones.
- Exported rows cannot prove which side they came from, and `FOR BIT DATA` columns
  compare as the client wrote them.
- `record` trusts the person who records source, extraction, replay and probe
  results; only the comparison result is computed. It checks evidence presence and
  hashes, not content.

## Validation performed

New tests: the self-reference delete rule and its fixture; ALTER TABLE option folding
in `lint`, `diff` and `bundle`; CSV reading, typing and refusals; 25 seeded
single-field catalog defects reported against their result set, identical wrong
values on both sides caught by expectations, lost and renamed rows, and malformed
evidence refused; outcome recording, prerequisites, derived statuses, probes,
negative cases, changed evidence, and relative plan paths. The full suite and the
repository checks pass. No Db2 subsystem or administration product was used.
