# ALTER TABLE and delete rules checked against the SQL Reference, 2026-10-11

Source: Db2 13 for z/OS SQL Reference SC28-2773-00, 2022-05-18 edition, from the IBM
Publications Center (`c2827730.pdf`, SHA-256 2863d424...eb07d6). Read on 2026-10-10 and
2026-10-11: ALTER TABLE, printed pages 1222-1307; the CREATE TABLE referential diagram
and ON DELETE text, pp. 1643 and 1668-1669; the CREATE INDEX partitioning-index
definition, p. 1525; and the delete-connected definition in the concepts chapter, p. 16.
That edition says later editions are published only on IBM Documentation, and the
current PDF (last updated 2026-08-11) refused automated download, so every statement
rule below was rechecked against the current `ibm-alter-table`, `ibm-create-table` and
`ibm-create-index` topics. The facts are in
[the table chapter](../../../kb/objects/table.md#options-changed-later-by-alter-table).
This supersedes the HTML-only sources of [the evidence review](alter-table-and-evidence.md)
for ALTER TABLE; it does not re-certify other reviews.

## Changes

| Manual | Before | Now |
|---|---|---|
| ADD optional before a first unique or referential constraint | Treated as unmodeled | Parsed; a missing ADD elsewhere is `syntax.alter-add-required` |
| A name may follow FOREIGN KEY in ALTER TABLE only | Parse error | Parsed in ALTER TABLE only, as in IBM's sample `FOREIGN KEY RDD (ADMRDEPT)` |
| ADD and DROP RESTRICT ON DROP are separate clauses; ADD clauses run last | Reported as a repeated clause | Both allowed; ADD wins |
| Catalog, accelerator-only, auxiliary and MQT tables accept only some clauses | Not checked | `table.alter-clause-for-table-kind` |
| No DATA CAPTURE CHANGES in a NOT LOGGED table space | Not checked | `table.data-capture-not-logged` (CREATE and ALTER) |
| An added key needs its unique index first (explicit table space) | Reported at the end of the script, and missed when the index came later | `table.alter-key-needs-index` at the ALTER |
| Constraint names differ from the table's existing ones | Not checked for ALTER | `name.duplicate-constraint` |
| The omitted delete rule follows CURRENT RULES when the ALTER runs | Diff and bundle used the CREATE-time value | Recorded per added key |
| Keys to the same or cascade-linked parents share one rule, not SET NULL | Not checked | `table.fk-delete-paths` (CREATE and ALTER) |
| No cycle that delete-connects a table to itself | Not checked | `table.fk-delete-cycle` |
| No SET NULL on a nullable column in a partitioning-index key | Not checked | `table.fk-set-null-partitioning-key` |
| A partitioning index also matches ASC or DESC | Matched key names only | Names, order and ASC/DESC |

A statement that fails a statement-level check (table kind, NOT LOGGED, missing index)
changes nothing in the model, because Db2 rejects the whole statement.

## Finding in the exemplar

`examples/varied-schema.sql` gave `SALES_ORDER` two foreign keys to `CUSTOMER`, one
RESTRICT and one SET NULL, which CREATE TABLE forbids. `ORDER_CODE_FK` is now RESTRICT
and SET NULL moved to `PRODUCT_DOC.DOC_PRODUCT_FK`, whose column became nullable; the
exemplar still uses all four delete rules and meets the `core` baseline. The regenerated
fixture, the catalog export fixture and their seeded defects follow.

## Interpretation

The manual states the cycle and path rules for "two or more tables" and does not say
how self-references take part, so path analysis leaves self-referencing relationships
out; they have their own rule (CASCADE or NO ACTION). The manual's own ALTER TABLE
example 4, `ALTER TABLE DSN8D10.DEPT FOREIGN KEY(ADMRDEPT) REFERENCES DSN8D10.DEPT ON
DELETE CASCADE` (p. 1307), stays valid beside a SET NULL cycle between two tables. The
delete rules of IBM's sample DEPT and EMP tables were not confirmed. NOT ENFORCED
relationships are included, because the text does not exclude them.

## Not checked

FOREIGN KEY on history or archive tables (versioning and archiving are not modeled);
APPEND in work-file table spaces; whether two ADD constraint clauses count as "the same
clause". No Db2 subsystem or administration product was used.
