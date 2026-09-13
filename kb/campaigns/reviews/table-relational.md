# Relational table model source review

Reviewed 2026-09-12 against the official [IBM Db2 13 for z/OS SQL
Reference](https://www.ibm.com/docs/en/SSEPEK_13.0.0/pdf/db2z_13_sqlrefbook.pdf),
SC28-2773-00, **Last updated: 2026-09-09**, 3,186 PDF pages.
SHA-256: `7caf1abd8c151e1669d1f89d210c85ebff486d689c169664853b6b49b6b70710`.
The PDF is not vendored. IBM can replace its content at the same URL. IBM HTML
catalog pages returned 403; the PDF constraint diagrams were rendered and
visually inspected, and the adjoining descriptions and catalog fields reviewed.

This review covers [table-relational.json](../models/table-relational.json), a
bounded two-table campaign. It does not certify arbitrary SQL or the whole KB.
The conservative model baseline is function level/APPLCOMPAT V13R1M500.
No Db2 subsystem or administration product was executed.

## Syntax and restrictions reviewed

- `ibm-create-table`, printed pp. 1708-1709 (PDF 1736-1737): unique, referential,
  references and CHECK diagrams. Named composite PRIMARY KEY and named UNIQUE
  constraints are separate elements. The REFERENCES column order follows the
  nominated parent key; ON DELETE precedes ENFORCED.
- `ibm-create-table`, printed pp. 1730-1733 (PDF 1758-1761): each PRIMARY KEY and
  UNIQUE column is NOT NULL. The explicitly placed parent is incomplete until
  its required ordinary UNIQUE indexes exist. The parent of the FK must exist
  and have a unique index; matching column counts, order and type definitions
  matter. This model uses two INTEGER columns on both sides, and creates both
  parent enforcing indexes before the child action.
- `ibm-create-table`, printed pp. 1733-1734 (PDF 1761-1762): omitted ON DELETE is
  RESTRICT for CURRENT RULES DB2 and NO ACTION for STD. The compiler requires
  DB2. SET NULL requires **at least one** nullable FK column, and changes only
  the nullable FK columns. The model includes all NOT NULL, one nullable, and
  both nullable forms. Only the first is forbidden with SET NULL. Fixed ENFORCED
  avoids informational-constraint behavior.
- `ibm-create-table`, printed pp. 1734-1735 (PDF 1762-1763): CHECK accepts true
  or unknown; its restricted condition language includes the modeled comparisons,
  BETWEEN, IN, IS NULL, AND and OR. Comparisons put a table column first; monetary
  constants fit DECIMAL(15,2), and both compared dates have the same type.
  Functions, casts, subqueries, CASE and several other SQL constructs are excluded.
  The 3,800-byte condition limit excludes redundant blanks; this model's three
  short conditions do not claim that boundary.
- `ibm-create-index`, printed pp. 1571 onward, especially enforcement notes:
  ordinary UNIQUE indexes matching the declared key columns in order enforce the
  parent's PRIMARY KEY and UNIQUE constraint. Neither index is PARTITIONED on
  the PBG fixture.
- `ibm-drop`, printed pp. 1945 and 1949 (PDF 1973 and 1977): an enforcing index
  cannot be explicitly dropped while its constraint requires it. DROP TABLESPACE
  also drops its contained table; dropping a table drops its indexes. Cleanup
  therefore emits only the child's dedicated table-space drop followed by the
  parent's, and declares ownership for the tables/indexes. This also avoids
  redundant DROP TABLE followed by DROP TABLESPACE. Creation ledgers must confirm
  run ownership before either table space is dropped.
- Explicit logged PBG table spaces, INTEGER/CHAR/VARCHAR/DECIMAL/TIMESTAMP data
  types and ordinary defaults reuse the documented paths in
  [the base campaign review](../SOURCE-REVIEW.md). The current PDF column/type
  diagrams and selected data-type descriptions were checked for the new payloads.
  VARCHAR(1) is a length boundary; VARCHAR(1024) is a selected length, not a maximum.
  DECIMAL(31,9) reaches maximum precision, and TIMESTAMP(12) maximum precision.

## Catalog fields and expected semantics

- `ibm-catalog-syscolumns`, printed pp. 2450 onward: COLNO is the column's
  one-based ordinal; COLTYPE, LENGTH, SCALE and NULLS describe its definition.
  DECIMAL LENGTH is precision. TIMESTAMP(12) uses TIMESTMP, LENGTH 13, SCALE 12.
  DEFAULT `1` identifies the explicit character default; DEFAULTVALUE retains
  the two trailing spaces in `MiXeD  `. Numeric default strings are compared
  losslessly but their catalog spelling is not asserted without live evidence.
- `ibm-catalog-sysrels`, printed pp. 2701-2703 (PDF 2729-2731): DELETERULE is
  R/A/C/N for RESTRICT/NO ACTION/CASCADE/SET NULL. ENFORCED is Y, COLCOUNT is 2,
  CHECKEXISTINGDATA is I for the enforced non-temporal FK. A query computes
  PARENT_MATCH against each side's exact schema/name and asserts 1, so an FK
  pointing to an unintended parent cannot pass because both exports are wrong.
- `ibm-catalog-sysforeignkeys`, printed p. 2530 (PDF 2558): COLSEQ is position
  within the FK; COLNO is position in the child. The model asserts the ordered
  mapping `(P_TENANT, P_ID)` to child columns `(2, 3)`.
- `ibm-catalog-sysindexes`, printed p. 2534 (PDF 2562): UNIQUERULE P identifies
  the primary index; C identifies the index enforcing the non-referenced UNIQUE
  constraint. COLCOUNT is 2 and 1 respectively. Queries require the intended
  index names and parent table identity.
- `ibm-catalog-syskeys`, printed p. 2571 (PDF 2599): COLSEQ/COLNO/COLNAME and
  ORDERING assert `(TENANT_ID ASC, PARENT_ID ASC)` for the primary index and
  `(EXTERNAL_CODE ASC)` for the unique index.
- `ibm-catalog-syschecks`, printed pp. 2438-2439 (PDF 2466-2467): CHECKNAME,
  CHECKCONDITION and PERIOD. The contract asserts one CK_VALUE, PERIOD blank,
  and compares raw CHECKCONDITION losslessly. It deliberately does not invent
  a source text canonicalization or equate raw text equality with proof that
  the selected predicate behaves correctly.
- `ibm-catalog-systables`, printed p. 2773 (PDF 2801): STATUS X means a complete
  table with a PRIMARY KEY/UNIQUE constraint; blank means complete with no such
  constraint. The parent expects X and child blank. Both expect TYPE T and a
  computed SPACE_MATCH of 1 for each side's exact database/table-space names.

## Deliberate limits

There are 180 modeled combinations, of which 168 are valid. The 12 exclusions
all combine SET NULL with both FK columns NOT NULL. `--negative` emits one
representative of this single rule violation, after identical valid parent setup.
SQLCODE/SQLSTATE stay null until actual execution supplies evidence.

Catalog comparison checks only the declared fields. CHECK behavior, constraint
name preservation for parent keys, the 64-column/key-byte limits, complex cascade
networks, cycles, alternate parent unique-key references, three or more related
tables, identity generator options, implicit objects, LOB/XML, temporal features,
and statement-format permutations are outside this family's coverage. See
[the working guide](../../objects/table-relational.md) for fixture/probe guidance.
