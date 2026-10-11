# DDL diff against product-style output, 2026-10-10

This review covers changes to `tools/ddl.py diff` and the semantic model in
`tools/db2check.py` and `tools/db2sql.py`. It does not re-certify the
[checker review](ddl-checker.md), chapters or models.

## Why

`diff` is the first offline check of product-generated DDL. A hand-written
imitation of extraction-tool output for `examples/varied-schema.sql`
(`tests/fixtures/varied-schema-regenerated.sql`) keeps every definition but uses
delimited names, explicit defaults, keys added by `ALTER TABLE`, every PBR
partition listed, `FOR SBCS DATA`, `INCLUSIVE` boundaries and a name for an
unnamed foreign key. Before this change the diff reported 19 `different` entries
for it (status `mismatch`, exit 1). It also returned `match` when the target held
a clause it could not parse, ignored unmodeled `ALTER` statements, and never
compared generated-column expressions, `FIELDPROC` parameters or `NULLS LAST`.
A noisy oracle gets ignored and a silent one passes defects, so both were fixed.

After the change the same pair has no `different` entry. With the example profile
the status is `unresolved` because of genuine subsystem dependencies; with
`DPSEGSZ`, `IMPTKMOD` and `MIXED` recorded, only index `DEFINE` and one omitted
PBG `DSSIZE` remain environment-dependent. Twenty-one seeded defects in the same
fixture (a lost override, a changed delete rule, reversed keys, a renamed table and
so on) are each reported (`RegeneratedOutputTests`).

## Sources reviewed

HTML topics retrieved on 2026-10-10. Facts used:

- `ibm-create-tablespace`: a partition takes FREEPAGE and PCTFREE, GBPCACHE and
  COMPRESS from its PARTITION clause, else from the clause outside any PARTITION
  clause, else the default; "If the TRACKMOD value is not specified for a partition,
  the TRACKMOD value for the table space is used"; "If the USING clause is not
  specified for a partition, the USING clause specified for the table space is
  used." No inheritance rule is stated for partition-level DSSIZE or for
  PCTFREE ... FOR UPDATE, so those are compared per partition only.
- `ibm-create-index`: the same precedence for USING ("it applies to every PARTITION
  clause that does not include a USING clause"), FREEPAGE/PCTFREE and GBPCACHE.
  Omitted USING uses the database's default storage group.
- `ibm-create-table`: an omitted `FOR subtype DATA` gives SBCS for ASCII or EBCDIC
  data when field MIXED DATA on panel DSNTIPF is NO, MIXED when it is YES, and
  MIXED for Unicode data. `ENDING AT` "Defines the limit key for a partition
  boundary"; the diagram offers only an optional `INCLUSIVE`. An unnamed foreign
  key gets a generated name; an unnamed check constraint gets a name derived from
  its first column. `NULLS LAST` "Specifies that null values are treated as
  positive infinity"; the page does not state the omitted behavior.
- `ibm-partition-boundary`: "The limit key is the highest value of the
  partitioning key for a partition." With the CREATE TABLE text this means an
  omitted `INCLUSIVE` gives the same boundary (recorded in `kb/objects/table.md`).
- `ibm-sql-identifiers`: an ordinary identifier is an uppercase letter followed by
  uppercase letters, digits or underscores, and lowercase letters in an undelimited
  identifier are folded to uppercase. The page has no example equating `"NAME"` with
  `NAME`; the diff already relied on that equivalence for object names and now
  applies it inside CHECK conditions, generated expressions, index expressions and
  limit keys.
- `kb/objects/database.md` (`ibm-create-database`): `INDEXBP` and `STOGROUP` are
  the defaults for child indexes and spaces; omitted `STOGROUP` means `SYSDEFLT`.
- `kb/objects/table.md`: `USER` is a synonym for `SESSION_USER` in generated
  expressions.

## Rules

| Rewrite or loss | Result |
|---|---|
| Delimited identifier spelling an ordinary identifier | Same token as the ordinary identifier |
| Keyword case in limit keys and expression keys | Ignored |
| `INCLUSIVE` on `ENDING AT` | Not compared |
| Attribute stated outside PARTITION clauses versus repeated in each | Compared per partition after IBM's precedence; USING is one block |
| Index buffer pool, storage group, table CCSID left to the script's own database or table space | Resolved before comparison |
| Unnamed source constraint, named in the target | `equivalent-default` |
| Omitted versus explicit `FOR SBCS DATA` or `FOR MIXED DATA` | `equivalent-default`, `different` or `environment-dependent` per encoding and `MIXED` |
| Generated expression, FIELDPROC parameters, `NULLS LAST` | Compared; `USER` equals `SESSION_USER` |
| Partly parsed statement, unmodeled `ALTER`, `RENAME`, view, routine, trigger and other unmodeled objects | `not-compared`; the status cannot be `match` |

## Limits

The diff still does not model `ALTER TABLE` forms other than added constraints, so
a product that sets `DATA CAPTURE` or similar attributes by `ALTER` gets a
`different` entry next to a `not-compared` one. `NULLS LAST` present on one side
only is reported as `different` because IBM does not state the omitted behavior.
Partition-level DSSIZE and FOR UPDATE given on one side only are
`environment-dependent`. Materializing an implicit table space as an explicit one
is still reported as `extra` plus a `different` placement.

## Validation performed

The new tests fail on the previous code and pass now: partition precedence, INCLUSIVE
and delimited identifiers, generated constraint names, subtype defaults, expression,
FIELDPROC and NULLS LAST comparison, `not-compared` statuses, `--text` output, the
regenerated exemplar, and 21 seeded defects. The full suite and repository checks
pass. No Db2 subsystem or administration product was used; the fixture imitates
common extraction formatting and is not product evidence.
