# TABLESPACE

## Concept and forms

A table space is the physical page-set layer that stores table data in VSAM linear data sets. Its buffer pool determines the page size. The requested object family has four materially different creation paths:

| Form | Creation mechanism | What it stores |
|---|---|---|
| PBG UTS | `CREATE TABLESPACE` or implicit `CREATE TABLE` | One base table; partitions added as data grows |
| PBR UTS | `CREATE TABLESPACE` plus table partitioning, or implicit `CREATE TABLE ... PARTITION BY RANGE` | One base table; partitions selected by range keys |
| Work-file PBG | `CREATE TABLESPACE ... IN <work-file-db>` | Work files and temporary processing |
| LOB | Separate `CREATE LOB TABLESPACE` | LOB data reached through an auxiliary table |

XML table spaces are implicit and do not have an ordinary explicit create form. Deprecated segmented and partitioned non-UTS forms remain available only at lower application compatibility and are isolated below.

Sources: `ibm-tablespace-concept`, `ibm-pbg-concept`, `ibm-pbr-create`, `ibm-create-tablespace`, `ibm-create-lob-tablespace`, `ibm-implicit-tablespace`.

## Base/work-file syntax summary

```text
CREATE TABLESPACE <table-space-name>
  [ IN <database-name> ]
  [ BUFFERPOOL <bpname> ]
  [ <pbg-specification> | <pbr-specification> ]
  [ SEGSIZE <integer> ]
  [ CCSID { ASCII | EBCDIC | UNICODE } ]
  [ CLOSE { YES | NO } ]
  [ COMPRESS { NO | YES [ FIXEDLENGTH | HUFFMAN ] } ]
  [ DEFINE { YES | NO } ]
  [ <free-block> ]
  [ GBPCACHE { CHANGED | ALL | NONE } ]
  [ INSERT ALGORITHM { 0 | 1 | 2 } ]
  [ LOCKMAX { SYSTEM | <integer> } ]
  [ LOCKSIZE { ANY | TABLESPACE | PAGE | ROW } ]
  [ LOGGED | NOT LOGGED ]
  [ MAXROWS <integer> ]
  [ MEMBER CLUSTER ]
  [ TRACKMOD { YES | NO } ]
  [ <using-block> ]
  [ FOR SORT | FOR DGTT ]

<free-block> ::=
  [ FREEPAGE <integer> ]
  [ PCTFREE <smallint> [ FOR UPDATE <smallint> ] ]

<using-block> ::=
  USING VCAT <catalog-name>
| USING STOGROUP <stogroup-name>
    [ PRIQTY <integer> ]
    [ SECQTY <integer> ]
    [ ERASE { NO | YES } ]
```

IBM's shared syntax fragment visually includes `GBPCACHE SYSTEM`; IBM's data-sharing guidance restricts that setting to LOBs. Treat it as a negative base-table-space case and use it only in `CREATE LOB TABLESPACE`. Sources: `ibm-create-tablespace`, `ibm-gbpcache`.

## PBG grammar and behavior

```text
<pbg-specification> ::=
  [ MAXPARTITIONS <integer> ]
  [ NUMPARTS <integer> ]
  [ DSSIZE <integer> G ]
```

- `MAXPARTITIONS` identifies PBG intent and sets the growth ceiling. Valid values are 1–4096, further constrained by page size and `DSSIZE`.
- `NUMPARTS`, when paired with `MAXPARTITIONS`, sets how many partition definitions initially exist. Data sets are allocated for that many unless `DEFINE NO` applies. Range: 1–4096 and not greater than `MAXPARTITIONS`.
- At Db2 13 function level 500 behavior, omitting both PBG/PBR specifications creates PBG with `MAXPARTITIONS 254`. The first/initial partition count defaults to 1.
- PBG `DSSIZE` is a power of two from 1 through 256 GB.
- PBG partitions are Db2-managed; `USING VCAT` is not allowed.
- A table in PBG can have only nonpartitioned indexes.

### PBG `DSSIZE` default

| Page size | `MAXPARTITIONS` 1–254 | `MAXPARTITIONS` 255–4096 |
|---|---:|---:|
| 4 KB | 4 G | 4 G |
| 8 KB | 4 G | 8 G |
| 16 KB | 4 G | 16 G |
| 32 KB | 4 G | 32 G |

Any `DSSIZE` greater than 4 G requires DFSMS extended format and extended addressability.

## PBR grammar and behavior

```text
<pbr-specification> ::=
  NUMPARTS <integer>
  [ (
      PARTITION <partition-number>
        [ <using-block> ]
        [ <free-block> ]
        [ GBPCACHE { CHANGED | ALL | NONE } ]
        [ COMPRESS { NO | YES [ FIXEDLENGTH | HUFFMAN ] } ]
        [ TRACKMOD { YES | NO } ]
        [ DSSIZE <integer> G ]
      [, ...]
    ) ]
  [ PAGENUM { RELATIVE | ABSOLUTE } ]
  [ DSSIZE <integer> G ]
```

- `NUMPARTS` without `MAXPARTITIONS` identifies PBR and defines 1–4096 partitions.
- A `PARTITION n` block overrides table-space-level storage, free-space, group-buffer, compression, tracking, and—in RPN only—`DSSIZE` attributes for that partition. Repeating a partition number causes the last specification to win.
- `PAGENUM RELATIVE` (RPN) is IBM's recommended form. The subsystem parameter `PAGESET_PAGENUM` controls omission and defaults to `RELATIVE` in IBM's documented setup.
- RPN supports any integer `DSSIZE` from 1–1024 G at table-space or partition level; default 4 G; maximum 4096 partitions. It requires extended-format and extended-addressability data sets.
- `PAGENUM ABSOLUTE` is deprecated. Its `DSSIZE` is a power of two from 1–256 G and controls the partition/page bit split.
- `CREATE TABLESPACE` defines the physical partitions; `CREATE TABLE ... PARTITION BY RANGE` defines the data partitioning key and limits. A PBR table is not usable until its partitioning scheme is complete.

### PBR absolute-page-number `DSSIZE` default

| `NUMPARTS` | Default |
|---:|---:|
| 1–16 | 4 G |
| 17–32 | 2 G |
| 33–64 | 1 G |
| 65–254 | 4 G |
| 255–4096 | 4/8/16/32 G for 4/8/16/32 KB page sizes |

## Type selection by application compatibility

This matrix is one of the highest-value grammar tests for OFS.

| Resulting type | `APPLCOMPAT >= V12R1M504` | `APPLCOMPAT <= V12R1M503` |
|---|---|---|
| PBG UTS | `MAXPARTITIONS` with/without `NUMPARTS`, or omit both | `MAXPARTITIONS` with `NUMPARTS`, with nonzero `SEGSIZE`, or alone |
| PBR UTS | `NUMPARTS` without `MAXPARTITIONS` | `NUMPARTS` plus nonzero `SEGSIZE` |
| segmented non-UTS | unsupported | nonzero `SEGSIZE`, or omit `MAXPARTITIONS`/`NUMPARTS`/`SEGSIZE` |
| partitioned non-UTS | unsupported | `NUMPARTS` plus `SEGSIZE 0` |

At V12R1M504 and above, a base table cannot be created in an existing non-UTS table space. Deprecated forms belong in explicit compatibility suites, not in the main templates.

## Common clause reference

### Identity, location, and pages

| Clause | Rules and effective default |
|---|---|
| `<table-space-name>` | Required; qualified by the explicit/implicit database; traditionally up to 8 characters; cannot collide with an existing/pending table, index, or LOB space name in that database. |
| `IN <database>` | Database must exist; cannot be DSNDB06, TEMP, or implicitly created. Default is `DSNDB04`. A work-file database forces PBG. |
| `BUFFERPOOL` | Active 4/8/16/32 KB pool and required USE/authority; determines page size. Defaults from the database. Work-file table spaces cannot use 8/16 KB. |
| `SEGSIZE` | Multiple of 4 from 4–64. Omission uses `DPSEGSZ`; if that parameter is 0, Db2 uses 32. Work-file spaces always use 16 and cannot specify the clause. |
| `CCSID` | ASCII/EBCDIC/UNICODE; omission inherits the database (or installation default for DSNDB04). All data in a non-work-file table space uses one encoding scheme. |

### Space, compression, and allocation

| Clause | Range/default and interactions |
|---|---|
| `CLOSE` | `YES` default; work-file behavior is always `NO`. |
| `COMPRESS` | `NO` unless inherited/explicitly selected for the scope. `YES` uses the subsystem-selected algorithm unless `FIXEDLENGTH` or `HUFFMAN` is named. Partition setting overrides table-space setting. |
| `DEFINE` | `YES` default. `NO` defers Db2-managed data-set allocation; ignored with `USING VCAT`; can make pre-allocation point-in-time recovery and out-of-Db2 tooling unsafe. |
| `FREEPAGE` | 0–255, default 0. Effective free-page interval cannot reach the segment size; Db2 reduces an excessive value to one below it. |
| `PCTFREE` | 0–99, default 5. |
| `FOR UPDATE` | -1–99; omission is controlled by `PCTFREE_UPD`. `-1` requests automatic behavior with an initial 5%. `PCTFREE + FOR UPDATE` must not exceed 99. |
| `MAXROWS` | 1–255 rows considered per data page; default 255. |
| `MEMBER CLUSTER` | Places inserts by available space rather than clustering-index order. |
| `INSERT ALGORITHM` | 0 default: consult `DEFAULT_INSERT_ALGORITHM` at insert time; 1: basic; 2: algorithm 2. Used where applicable with `MEMBER CLUSTER`. |

### Locking, logging, caching, and tracking

| Clause | Range/default and interactions |
|---|---|
| `LOCKMAX` | 0–2147483647 or `SYSTEM`. Zero disables escalation counting. Omission with `LOCKSIZE ANY` gives `SYSTEM`; omission with TABLESPACE/PAGE/ROW gives 0. TABLESPACE requires omitted/zero `LOCKMAX`. |
| `LOCKSIZE` | `ANY`, `TABLESPACE`, `PAGE`, or `ROW`. `ANY` usually behaves as page locking plus system lock maximum. |
| `LOGGED` / `NOT LOGGED` | `LOGGED` default. Applies to the table and indexes; XML and auxiliary spaces inherit relevant logging. Not allowed for DSNDB06. |
| `GBPCACHE` | `CHANGED` default; `ALL` or `NONE` are base-space alternatives in data sharing. Ignored outside data sharing. `SYSTEM` is LOB-only. Not allowed in work-file spaces. |
| `TRACKMOD` | YES/NO; omission uses `IMPTKMOD`. Can be overridden per PBR partition. |

### Storage management

| Clause | Rules and effective default |
|---|---|
| omitted `USING` | Db2 manages data sets using the database's default storage group and normal `PRIQTY`, `SECQTY`, and `ERASE` defaults. |
| `USING VCAT` | User-managed data sets. Not valid for PBG. `DEFINE NO` is ignored. |
| `USING STOGROUP` | Db2-managed data sets in an existing group; requires USE/authority. Can be table-space-level or PBR-partition-level. |
| `PRIQTY` | Positive KB or `-1` for Db2 calculation. Minimum positive allocations are normalized by 4/8/16/32 KB page size to at least 12/24/48/96 KB. FL 507 caps the effective request at 1,073,741,824 KB. |
| `SECQTY` | Positive KB, zero, or `-1` for Db2 calculation. FL 507 caps the effective value at 209,715,200 KB. IBM recommends allowing Db2 to calculate it. |
| `ERASE` | `NO` default; `YES` overwrites deleted data sets with zeros. |

Partition-level values override table-space-level values, which override database/default behavior. That precedence should be tested independently from clause spelling.

## Maximum PBG/PBR-absolute partition counts

For PBG and PBR with absolute page numbering, page size and `DSSIZE` constrain the partition count:

| `DSSIZE` | 4 KB | 8 KB | 16 KB | 32 KB |
|---:|---:|---:|---:|---:|
| 1–4 G | 4096 | 4096 | 4096 | 4096 |
| 8 G | 2048 | 4096 | 4096 | 4096 |
| 16 G | 1024 | 2048 | 4096 | 4096 |
| 32 G | 512 | 1024 | 2048 | 4096 |
| 64 G | 256 | 512 | 1024 | 2048 |
| 128 G | 128 | 256 | 512 | 1024 |
| 256 G | 64 | 128 | 256 | 512 |

PBR RPN instead supports up to 4096 partitions and `DSSIZE` up to 1024 G per partition.

## Work-file table spaces

A table space in a work-file database must be PBG. Db2 13 FL 508 adds mutually exclusive usage qualifiers:

- `FOR SORT`: sort, join, created global temporary tables, parallelism, transition tables, and related non-DGTT work.
- `FOR DGTT`: declared global temporary tables and internal temporary-table processing such as scrollable cursors.

The following ordinary clauses are forbidden: `CCSID`, `COMPRESS`, `DEFINE NO`, `FREEPAGE`, `GBPCACHE`, `LARGE`, `LOCKPART`, `LOCKSIZE`, `LOGGED`, `NOT LOGGED`, `MAXROWS`, `MEMBER CLUSTER`, `PAGENUM`, `PCTFREE`, `SEGSIZE`, and `TRACKMOD`. Db2 uses `SEGSIZE 16` and `CLOSE NO` behavior. At least one 32 KB work-file table space is required before declared temporary tables or sensitive static scrollable cursors can use that capacity.

## LOB table-space syntax

```text
CREATE LOB TABLESPACE <table-space-name>
  [ IN <database-name> ]
  [ BUFFERPOOL <bpname> ]
  [ CLOSE { YES | NO } ]
  [ COMPRESS { YES | NO } ]
  [ DEFINE { YES | NO } ]
  [ DSSIZE <integer> G ]
  [ GBPCACHE { CHANGED | ALL | SYSTEM | NONE } ]
  [ LOCKMAX { SYSTEM | <integer> } ]
  [ LOCKSIZE { ANY | LOB } ]
  [ LOGGED | NOT LOGGED ]
  [ <using-block> ]
```

LOB-specific rules:

- The LOB space must be in the same database as the base table space and cannot be in DSNDB06, a work-file/TEMP database, or an implicit database.
- Omitted `BUFFERPOOL` uses the installation default for user LOB data.
- `COMPRESS YES` requires configured zEDC and a base table in UTS; a value no larger than the data page is not compressed.
- `DSSIZE` defaults to 4 G; documented sizes are 1, 2, 4, 8, 16, 32, 64, 128, or 256 G. Values above 4 G need extended format/addressability.
- `GBPCACHE SYSTEM` caches changed LOB system/space-map pages, not user LOB data. IBM recommends `CHANGED` for typical LOB use.
- `LOCKSIZE ANY` normally resolves to LOB locking with system lock maximum.
- `LOCKSIZE TABLESPACE`, `PAGE`, and `ROW` are base-table-space forms; the LOB statement accepts only `ANY` or `LOB`.
- For a partitioned base table, each LOB column needs a separate LOB space, auxiliary table, and auxiliary index for every base partition.
- Do not issue this statement when Db2 is implicitly creating the LOB infrastructure.

LOB `PRIQTY` minimums differ from base spaces: positive values below 200/400/800/1600 KB for 4/8/16/32 KB pages are raised to those minimums. FL 507 applies the same large-allocation caps described above.

## Implicit table spaces from `CREATE TABLE`

- `CREATE TABLE ... IN DATABASE db` creates a table space in that database.
- Omitting `IN` also selects or creates an implicit `DSNnnnnn` database.
- No partition clause or `PARTITION BY SIZE` yields PBG; `PARTITION BY RANGE` yields PBR.
- Db2 derives the table-space name from the table name when possible and selects a suitable buffer pool from installation defaults if the row does not fit the database default.
- The `CREATE TABLE` physical clauses (`DSSIZE`, `BUFFERPOOL`, `COMPRESS`, `LOGGED`, `MEMBER CLUSTER`, `TRACKMOD`, `PAGENUM`) apply only to an implicitly created base table space.
- Implicit LOB/XML spaces and enforcing indexes can appear with it. See [table.md](table.md).

## Compatibility spellings

Keep these in a dedicated parser/round-trip suite:

- `PART` for `PARTITION`
- `LOG YES` for `LOGGED`; `LOG NO` for `NOT LOGGED`
- `LOCKPART` is accepted but has no useful effect; all spaces behave as selective-partition locking permits
- `LOCKSIZE TABLE` as a compatibility synonym in the documented context
- `CREATE LARGE TABLESPACE` as a tolerated legacy spelling when `DSSIZE` is absent

The preferred generated form should use current keywords.

## High-value OFS cases

1. Type-resolution quartet: omitted specification (PBG), `MAXPARTITIONS` (PBG), `NUMPARTS` (PBR), both (PBG).
2. PBR RPN versus deprecated absolute page numbering, including non-power-of-two RPN `DSSIZE`.
3. Table-space-level defaults versus one partition override and a second partition inheriting.
4. Page-size × `DSSIZE` × maximum-partition boundary cases from the matrix.
5. `USING STOGROUP`, omitted `USING`, and `USING VCAT`; reject VCAT for PBG.
6. `DEFINE NO` with STOGROUP, VCAT (ignored), populated child behavior, and external-tool warning path.
7. Explicit/omitted compression algorithm, logging, close, tracking, and free-space values.
8. Work-file legal minimum, `FOR SORT`, `FOR DGTT`, and each forbidden ordinary clause.
9. Base versus LOB grammar, especially `GBPCACHE SYSTEM`, LOB lock size, zEDC compression, and LOB allocation minimums.
10. Current syntax versus each accepted legacy synonym at both modern and low application compatibility.

## Catalog assertions

Use `SYSIBM.SYSTABLESPACE` for object-level attributes and `SYSIBM.SYSTABLEPART` for each partition/data set. Inspect both; partition overrides cannot be proven from only the table-space row.

```sql
SELECT *
  FROM SYSIBM.SYSTABLESPACE
 WHERE DBNAME = UPPER('{{DATABASE}}')
   AND NAME   = UPPER('{{TABLESPACE}}');

SELECT *
  FROM SYSIBM.SYSTABLEPART
 WHERE DBNAME = UPPER('{{DATABASE}}')
   AND TSNAME = UPPER('{{TABLESPACE}}')
 ORDER BY PARTITION;
```
