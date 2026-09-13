# Campaign source review, 2026-09-04

Later scoped reviews: [relational tables](reviews/table-relational.md),
[basic triggers and native procedures](reviews/routines.md), and
[compiler, cleanup and procedure corrections](reviews/compiler.md), 2026-09-12.
They do not replace the historical scope/edition record below.

The new compiler families were checked against the official
[IBM Db2 13 for z/OS SQL Reference](https://www.ibm.com/docs/en/SSEPEK_13.0.0/pdf/db2z_13_sqlrefbook.pdf),
downloaded on 2026-09-04. The retrieved edition says **Last updated: 2026-09-03**.
Its SHA-256 was
`35b65a3d7267e638b9680592a05a19bc41f264ac5c5e7e64161cbde700beb1da`.
The PDF is not vendored. IBM can update the file at the same URL.

HTML statement pages returned access errors during this review. The PDF diagrams
were rendered for inspection and the descriptions/catalog entries were extracted
for field-level checks. This review applies only to the new bounded campaign
models; it does not re-certify every existing chapter, recipe or workload.

## Statements and scope

- `ibm-create-table`: printed page 1701 onward (PDF page 1729), top-level diagram;
  column/data-type diagrams on printed pages 1702–1704; descriptions for defaults,
  identity, hidden and row-change columns. Checked the campaign's explicit logged
  PBG placement, audit, data capture and append branches. No LOB, XML, temporal,
  generated provenance, constraint or copy-family compiler coverage is claimed.
- `ibm-create-tablespace`: printed page 1769 onward (PDF page 1797), PBG specification,
  segment size, selected partition ceilings and DSSIZE values, lock size and storage
  clauses. Selected values fit 4 KB pools. PBR and compatibility forms remain outside
  the executable family.
- `ibm-create-index`: printed pages 1571–1574, diagram; descriptions around pages
  1575–1584 for uniqueness, INCLUDE, padding, PBG restrictions and storage options.
  The key contains VARCHAR to make padding meaningful. INCLUDE needs UNIQUE;
  PARTITIONED is not a positive path for the fixed PBG fixture.
- Bootstrap CREATE DATABASE uses the existing normalized database clauses and
  existing object-stack template pattern. It references an existing storage group;
  the campaign does not create or drop that storage group.

## Catalog contract checks

- `ibm-catalog-syscolumns`: printed pages 2450 onward, column identity/order,
  type/precision/scale, nullability, default discriminator, default literal and
  hidden state. DECIMAL LENGTH is precision. Identity ALWAYS/BY DEFAULT use I/J;
  the selected row-change form uses E. Literal DEFAULTVALUE is not trimmed.
- `ibm-catalog-sysindexes`: printed pages 2533 onward, uniqueness, column count,
  VARCHAR padding and creation-time FREEPAGE/PCTFREE fields.
- `ibm-catalog-syskeys`: printed page 2571 onward, ordered column keys and INCLUDE
  column rows. Included columns have blank ordering.
- `ibm-catalog-systables`: printed pages 2767 onward, table identity, audit, data
  capture and append flags. Only the contract's explicit field list is compared.
- `ibm-catalog-systablespace`: printed pages 2781 onward, lock rule, pool, segment
  size, maximum partitions and DSSIZE. Catalog DSSIZE is in KB, so 1/4 GB choices
  assert 1,048,576/4,194,304 respectively.

All IDs resolve through [the source manifest](../sources.md) and normalized JSON.
Models retain minimum Db2 13 gates as a conservative compiler baseline. They are
not statements of when every constituent feature was first introduced.

## Validation boundary

Syntax-source review and local compiler tests are complete for this change's
modeled scope. No target subsystem, active pools, storage configuration, Db2
acceptance, product extraction or replay was available for live verification.
Negative SQLCODE/SQLSTATE values therefore remain unspecified.
