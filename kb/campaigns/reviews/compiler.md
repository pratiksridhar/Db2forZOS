# Worker utility audit, 2026-09-12

The repository now routes a structured QA request to IBM-linked context, exact
modeled choices, explicit gaps and a reproducible campaign. The compiler supports
six bounded families. It is neither a complete Db2 grammar nor a guarantee that
arbitrary agent-written SQL is valid.

## Changes with practical impact

- `tools/ddl.py plan` preserves the original request, validates its structure and
  dependencies, lists source-linked research gaps and emits build arguments only
  for the supported scope. Every plan still requires agent review of the intent.
- `--set` filters exact dimension values. `three-way` extends coverage to feasible
  triples; reports retain omitted interactions and both filtered/full denominators.
- Relational cases create the parent enforcing indexes before child foreign keys.
  Basic trigger and native procedure cases exercise compact, multiline, line-comment,
  bracketed-comment and long-comment bodies. See the adjacent source reviews.
- Standalone native procedure cases create no unrelated database. They use their
  own routine/package collision checks and routine cleanup; storage/pool profile
  fields are required only for models that actually use database fixtures.
- SQL statement arrays are preserved without splitting bodies, folding case or
  rewriting literals. File delimiters, text hashes and artifact length metrics are
  explicit. Source and replay behavior/CLOB probes are retained independently of
  selected catalog-field comparisons.

## Corrected existing knowledge and cleanup

The column-definition inventory now preserves the dependent-table boundary:
749 named columns when the table is a dependent, 750 otherwise, still subject to
row-size and implicit/hidden-column limits. The existing chapter already contained
this distinction. Source: [CREATE TABLE](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-table),
column-name description, SQL Reference printed page 1712.

For native and current external procedures, SPECIFIC repeats the procedure name
and schema. The prior prose suggested overload disambiguation and both templates
accepted an independent name. The templates now reuse PROCEDURE_NAME and the
normalized rule `procedure.specific-name-matches-procedure` records the restriction.
Sources: [native CREATE PROCEDURE](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-procedure-sql-native)
and [external CREATE PROCEDURE](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-procedure-external),
SPECIFIC descriptions, reviewed 2026-09-12.

SQL procedure compound statements cannot specify ATOMIC. The chapter and normalized
rule `procedure.native-compound-not-atomic` now distinguish this from trigger bodies.
Source: [SQL PL compound statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-compound-statement),
ATOMIC/NOT ATOMIC description. The SQL Reference edition updated 2026-09-09 covers
native SPECIFIC on printed pages 1666-1667 and compound atomicity on page 2281.

Cleanup formerly emitted DROP TABLE followed by DROP TABLESPACE for explicit UTS
fixtures. DROP TABLE also removes the UTS, making the second DROP redundant. Direct
DROP INDEX is also prohibited for indexes enforcing primary/unique constraints.
Models now name a cleanup owner and drop each dedicated space once, child before
parent for relational cases. Sources: [DROP statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-drop),
INDEX, TABLE and TABLESPACE descriptions, SQL Reference printed pages 1945-1949;
[implications of dropping a table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=table-implications-dropping).
The historical FL506 change belonged to Db2 12; no Db2 13 FL506 gate is asserted here.

## SQL processor boundary

IBM documents internal semicolons and the need for a distinct outer delimiter in
[SQL procedure bodies](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=procedures-sql-procedure-body).
The emitted routine bundles use `@` consistently in every SQL file. Configure the
processor before submission; the files do not assume a particular client directive.

[SPUFI defaults](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=defaults-current-spufi-panel),
SQL TERMINATOR and SQL FORMAT, explain that SQL mode removes comments and collapses
lines. SQLPL preserves comments and line structure, so it is the documented SPUFI
choice for these format tests. This does not establish DSNTEP2, CLP or JDBC behavior.

[SQL comments](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-sql-comments)
documents line/bracketed comments and notes that common processors do not support
nested bracketed comments. The generator therefore rejects nested comments in its
portable subset, although Db2 SQL itself supports them. Quotes and doubled quote
escapes are tracked without altering text. Alternate delimiters are conservatively
excluded even from literals/comments, following the processor's input caution.

The framing checks catch unclosed comments/quotes and delimiter mistakes. They do
not validate grammar, name resolution, data-type compatibility or authorization.
Character and UTF-8 byte metrics are not target-CCSID byte counts or Db2 limits.

## Evidence and remaining scope

The live official SQL Reference download used for this extension has edition date
2026-09-09 and SHA-256
`7caf1abd8c151e1669d1f89d210c85ebff486d689c169664853b6b49b6b70710`.
The PDF is not vendored; exact diagram/catalog sections are in the adjacent reviews.
The wider KB retains its older review baseline. New review dates apply only to
the explicitly examined rules, fixtures and catalog fields.

Local tests exercise feasible combinations, constrained negatives, dependency and
cleanup ownership, case schemas, exact body framing, request gaps and corrupted
catalog evidence. No Db2 subsystem or administration-product execution occurred.
Cases remain `design`; expected success is an assertion to test, not a measured result.

Validation recorded for this extension: 98 unit tests passed, `tools/qa.py validate`
and `tools/agent.py validate` passed, and `git diff --check` passed. The six local
example bundles contain 173 schema-validated cases: 56 table-core, 11 tablespace-pbg,
14 index-core, 65 table-relational, 11 trigger-basic and 16 procedure-native.
Relational examples use three-way coverage, the others pairwise; totals include
five isolated negative cases. Every requested feasible design interaction was
covered within those modeled families. Generated examples are under ignored
`generated/worker-utility-demo-20260912/`; the models and generation instructions
are durable repository files.

Remaining compiler gaps include PBR overrides, arbitrary dependency graphs,
LOB/XML/temporal/MQT families, view normalization, advanced triggers, richer routine
parameters/handlers/versioning, and additional object types. Use the authoring plan's
research tasks and the extension guide instead of inventing unsupported syntax.
Live acceptance, extraction, replay and behavioral evidence require a target profile
and a separate execution harness.
