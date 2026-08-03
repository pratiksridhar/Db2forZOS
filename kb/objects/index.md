# INDEX

## Concept and independent characteristics

An index is an ordered key-to-row structure in its own index space. Several characteristics are orthogonal: uniqueness, clustering, physical partitioning, key expression, padding, compression, and storage management. A “partitioning index” is identified by how its leading key matches the table partitioning key; `PARTITIONED` instead requests physical index partitioning.

Sources: `ibm-index-concept`, `ibm-index-names`, `ibm-partitioned-indexes`, `ibm-create-index`.

## Syntax summary

```text
CREATE [ UNIQUE [ WHERE NOT NULL ] ] INDEX <index-name>
  ON {
       <table-name>
         ( <key> [, ...]
           [ , BUSINESS_TIME [ WITH | WITHOUT OVERLAPS ] ] )
     | <aux-table-name>
     }
  [ <xml-index-specification> ]
  [ INCLUDE ( <column-name> [, ...] ) ]
  [ CLUSTER | NOT CLUSTER ]
  [ PARTITIONED ]
  [ NOT PADDED | PADDED ]
  [ <using-specification> ]
  [ <free-specification> ]
  [ GBPCACHE { CHANGED | ALL | NONE } ]
  [ DEFINE { YES | NO } ]
  [ COMPRESS { NO | YES } ]
  [ INCLUDE NULL KEYS | EXCLUDE NULL KEYS ]
  [ PARTITION BY RANGE
      ( PARTITION <integer>
          [ <using-specification> ]
          [ <free-specification> ]
          [ GBPCACHE { CHANGED | ALL | NONE } ]
          [ DSSIZE <integer> G ]
        [, ...] ) ]
  [ BUFFERPOOL <bpname> ]
  [ CLOSE { YES | NO } ]
  [ DEFER { NO | YES } ]
  [ DSSIZE <integer> G ]
  [ PIECESIZE <integer> { K | M | G } ]
  [ COPY { NO | YES } ]

<key> ::=
  { <column-name> | <scalar-key-expression> }
  [ ASC | DESC | RANDOM ]

<using-specification> ::=
  USING VCAT <catalog-name>
| USING STOGROUP <stogroup-name>
    [ PRIQTY <integer> ]
    [ SECQTY <integer> ]
    [ ERASE { NO | YES } ]

<free-specification> ::=
  [ FREEPAGE <integer> ]
  [ PCTFREE <integer> ]
```

An auxiliary index omits an explicit key list because Db2 generates its key. Auxiliary tables and their separate CREATE syntax are outside the core object set, but the index form is retained because LOB tables depend on it.

## Names and target tables

- Index name: SQL identifier up to 128 characters, optionally schema-qualified. The name must be new at the server and absent from pending objects.
- Index-space name: separate eight-character physical name, unique among index/table spaces in the table's database. Db2 derives it for Db2-managed storage; user-managed storage uses the first eight characters of the index identifier.
- A declared temporary-table index must use qualifier `SESSION`.
- Target can be an eligible base table, MQT, declared temporary table, or auxiliary table. It cannot be a clone, created temporary table, accelerator-only table, directory table, or implicit XML table. Expression indexes have additional catalog/DGTT restrictions.

## Key columns and expressions

### Column keys

- At most 64 columns, no duplicate and no qualification.
- LOB columns cannot be direct keys. XML is legal only under `XMLPATTERN`.
- BINARY/VARBINARY, row-change timestamp, time-zone timestamp, and other types have context-specific partitioning/padding restrictions.
- For an EBCDIC table with Unicode columns, all character/graphic key results must use a compatible single encoding family.

Key-length limits use `n` nullable columns, `m` varying columns, and `d` DECFLOAT columns:

| Index form | Maximum length |
|---|---|
| padded, nonpartitioning | `2000 - n` |
| not padded, nonpartitioning | `2000 - n - 2m - 3d` |
| padded, partitioning | `255 - n` |
| not padded, partitioning | `255 - n - 2m - 3d` |

### Expression keys

An expression key must reference at least one target-table column and return a supported scalar type. Its UTF-8 text is limited to 4000 bytes; an extended index supports at most 64 expressions.

High-yield restrictions:

- no subquery, aggregate, nondeterministic/external-action function, UDF, sequence, host variable, parameter marker, global variable, special register, CASE, or OLAP expression;
- referenced columns cannot have `FIELDPROC`, security-label, or implicitly hidden attributes;
- output cannot be LOB, XML, DECFLOAT, or array, although limited intermediate LOB/DECFLOAT use is documented;
- `LOWER`/`UPPER` needs locale and non-bit input; `TRANSLATE` needs the target string;
- LOB references are limited to documented `SUBSTR`/`JSON_VAL` inline cases;
- no `INCLUDE` or XML key-generation clause with expression keys;
- `DESC` is not legal when the ON list contains a key expression; test implicit/explicit ascending behavior.

Do not reduce expression-index validation to SQL text parsing. Execute against populated and empty tables: expression errors can surface at CREATE time when existing rows are evaluated or later during data change/rebuild.

## Key ordering

| Choice | Meaning and restrictions |
|---|---|
| omitted / `ASC` | Ascending; default. Not valid with XML key generation. |
| `DESC` | Descending; not with XML generation or expression keys. |
| `RANDOM` | Randomized key order. Not with nonpadded varying keys, time-zone timestamp, DECFLOAT, XML, partitioning key, or expression index. |

Use mixed ASC/DESC cases on composite column indexes, but compare semantic order in `SYSKEYS`, not only emitted tokens.

## Uniqueness and null semantics

| Form | Semantics |
|---|---|
| no `UNIQUE` | Duplicate key values allowed |
| `UNIQUE` | Duplicate keys prohibited; null values compare equal for uniqueness, so an all-null single key occurs at most once |
| `UNIQUE WHERE NOT NULL` | Duplicate non-null keys prohibited while multiple null-bearing keys are allowed; it does **not** enforce a table primary/unique constraint |

Creation fails if populated data already violates the selected uniqueness rule.

`INCLUDE (columns)` adds non-enforcing columns to a **unique** index for index-only access. Included columns count toward the 64-column and length limits, cannot duplicate key/include columns, and cannot be LOB or DECFLOAT. `INCLUDE` is not legal for nonunique, auxiliary, XML, extended/expression, or legacy index-controlled partitioning-index forms.

## Temporal index keys

```text
( <ordinary-key> [, ...], BUSINESS_TIME WITH OVERLAPS )
( <ordinary-key> [, ...], BUSINESS_TIME WITHOUT OVERLAPS )
```

Db2 appends business-time end then begin columns in ascending order.

- `WITHOUT OVERLAPS` enforces uniqueness of the ordinary key over time and is used for application-period primary/unique constraints.
- `WITH OVERLAPS` is intended for the child/foreign-key side of a temporal referential constraint and cannot be `UNIQUE`.
- Business-period columns must not already be listed or be part of the partitioning key in forbidden combinations.
- An index satisfying a temporal foreign key can become a dependency and cannot then be dropped independently.

## XML index form

```text
ON <table-name> ( <xml-column> )
GENERATE { KEY | KEYS } USING
XMLPATTERN [ <namespace-prolog> ] <pattern-expression>
AS SQL {
    VARCHAR ( <integer> )
  | DECFLOAT [ (34) ]
  | DATE
  | TIMESTAMP (12)
}
```

- Pattern UTF-8 text: nonempty and at most 4000 bytes.
- Namespace prolog supports declared prefixes and a default element namespace.
- Pattern paths support the documented child, descendant, self, descendant-or-self axes; element/attribute wildcards; text nodes; and restricted `fn:upper-case(.)`/`fn:exists(...)` steps.
- `VARCHAR` length is 1–1000. Timestamp precision is exactly 12. Date/timestamp values normalize to UTC. `DECFLOAT` stores normalized numeric values.
- Values that cannot be cast can be omitted from the index without rejecting the XML document in the documented cases; out-of-range values can error. A VARCHAR length violation can fail insert or CREATE.
- Uniqueness applies after conversion/rounding, which can turn distinct XML lexical values into duplicate SQL keys.
- XML indexes cannot be partitioned, padded, clustered, or combined with expression/INCLUDE forms as prohibited by the statement reference.

## Clustering, partitioning, DPSI, and NPI

### Clustering

`CLUSTER` makes this the table's clustering index; `NOT CLUSTER` does not. It is invalid for auxiliary, hash-organized, XML, or expression indexes. Only one index can be the effective clustering index.

### Physical partitioning

`PARTITIONED` creates an index physically aligned to a PBR/range-partitioned table. It is not supported on PBG or XML indexes.

For a PBR table:

- **partitioning index**: leading key columns match the table partitioning columns, order, and ASC/DESC attributes; no special keyword marks this semantic role;
- **DPSI**: `PARTITIONED` index whose key does not match the partitioning key in the required way;
- **NPI/NPSI**: omit `PARTITIONED`; one physical index covers all data partitions.

A unique physically partitioned index must contain a superset of the table partitioning columns in the key itself, not merely in `INCLUDE`.

`PARTITION BY RANGE (PARTITION n ...)` in current table-controlled PBR syntax supplies **per-partition index attributes**. It does not redefine the table's range boundaries. Each partition block can override USING, free space, group-buffer caching, and RPN `DSSIZE`.

## Padding and null-key storage

### Padding

- `PADDED` pads varying strings to maximum length. It is forbidden for VARBINARY and XML indexes.
- `NOT PADDED` stores actual length metadata. Auxiliary indexes remain padded.
- With no varying key, the choice is ignored with a warning and the physical index is padded.
- With a varying key, omission is controlled by the `PADIX` subsystem parameter. Record it in the case context.

### All-null keys

- `INCLUDE NULL KEYS` is default.
- `EXCLUDE NULL KEYS` omits an index entry only when **all** key columns are null.
- `EXCLUDE` conflicts with `UNIQUE`, `BUSINESS_TIME WITHOUT OVERLAPS`, XML, expression keys, `INCLUDE`, or a key set containing a `NOT NULL` column.

## Storage and physical options

### Storage management

| Clause | Rules/defaults |
|---|---|
| omitted `USING` | Db2 manages data sets in the database default storage group; default quantities and `ERASE NO`. |
| `USING VCAT` | User-managed data sets. Not for DGTT; not for a noncatalog PBG table's index. |
| `USING STOGROUP` | Db2-managed in an existing group with USE/authority. |
| `PRIQTY` | Positive KB or `-1`. Positive values below 12 become 12. Effective upper behavior is 4,194,304 KB, with the documented 2,097,152 limit for a nonpartitioned index on a classic non-large space. |
| `SECQTY` | Positive KB, zero, or `-1` for Db2 calculation. |
| `ERASE` | `NO` default; `YES` zeroes deleted data sets. |

For partitioned indexes, a partition-level `USING` overrides the index-level choice; absence at both levels uses the database default. Test one override and one inherited partition together.

### Free space and group-buffer caching

| Clause | Range/default |
|---|---|
| `FREEPAGE` | 0–255; default 0; not DGTT |
| `PCTFREE` | 0–99; default 10; values above 10 reserve at most 10% in nonleaf pages; not DGTT |
| `GBPCACHE` | `CHANGED` default, `ALL`, or `NONE`; ignored outside data sharing; partition override precedence; not DGTT |

### Allocation, compression, and lifecycle

| Clause | Meaning/default and constraints |
|---|---|
| `DEFINE` | Omission inherits the current base-table-space allocation state. `NO` defers Db2-managed allocation, is ignored with VCAT or nonempty tables, and is forbidden for clone-related/DGTT cases. |
| `COMPRESS` | `NO` default. `YES` requires an 8/16/32 KB buffer pool; physical disk page remains 4 KB. Applies to all partitions. |
| `BUFFERPOOL` | Active 4/8/16/32 KB pool with USE/authority. Larger pages suit sequential patterns; smaller can suit random insertion. |
| `CLOSE` | `YES` default; DGTT behavior is `NO`. |
| `DEFER` | `NO` default builds now. `YES` leaves a populated-table index rebuild-pending for `REBUILD INDEX`; not auxiliary/DGTT. Empty table is not put rebuild-pending. |
| `COPY` | `NO` default. `YES` permits index image copy and RECOVER; not DGTT. |

### `DSSIZE` and `PIECESIZE`

- Index `DSSIZE` is valid only for an index on a PBR table space with relative page numbering. Partition value overrides index value; omission inherits the base space.
- `PIECESIZE` applies to a nonpartitioned index and sets the maximum size of each index data set, not allocation. It accepts power-of-two K/M/G values up to 256 G, further limited by the base table-space size attribute.
- Exercise both smallest legal piece and the largest permitted for each base `DSSIZE`, plus one power-of-two violation and one base-space mismatch.

## Enforcing indexes and incomplete table definitions

A table `PRIMARY KEY`, table `UNIQUE`, or `GENERATED BY DEFAULT ROWID` requires an ordinary `UNIQUE` index—not `UNIQUE WHERE NOT NULL`—with an identical key where required. Db2 implicitly creates it when the schema processor is used or the table space is implicit. Otherwise the table can remain unavailable/incomplete until all required indexes exist.

This is a critical OFS sequence test:

1. create an explicit UTS;
2. create a table with primary and unique constraints;
3. confirm incomplete state;
4. generate/create matching unique indexes one by one;
5. confirm the final index completes the table definition and is classified as primary/constraint-enforcing.

## Deprecated index-controlled partitioning

For a deprecated partitioned non-UTS table without table-controlled boundaries, `CREATE INDEX ... PARTITION BY RANGE` can define partition limit keys with `ENDING AT`. Db2 13 still processes this at eligible low compatibility, but IBM recommends conversion and can prevent new definitions through subsystem policy. Do not confuse this legacy boundary-defining form with current PBR per-partition attribute syntax.

## High-value OFS test dimensions

1. Nonunique, `UNIQUE`, and `UNIQUE WHERE NOT NULL` on nullable and populated data.
2. One through 64 column keys, every length formula boundary, mixed directions, and random-order conflicts.
3. Expression positive cases and each forbidden construct, on empty and populated tables.
4. XML pattern axes/wildcards/namespaces/functions, each SQL cast type, cast failure, length boundary, and post-cast uniqueness.
5. Unique index with included columns and every incompatible index family.
6. Clustering versus nonclustering; implicit first-index behavior versus explicit cluster.
7. PBG NPI only; PBR partitioning index, DPSI, NPI, and illegal unique DPSI missing partition keys.
8. Index-level versus partition-level storage/free/GBP/DSSIZE inheritance.
9. PADIX-dependent omission versus explicit padded/nonpadded; varying versus fixed and VARBINARY negatives.
10. Include/exclude null keys with all-null, partly-null, and not-null keys.
11. Define-now/deferred-build/deferred-allocation combinations on empty and populated tables.
12. Compression × buffer page size, close, copy, piecesize, and storage-management variants.
13. Business-time with/without overlaps and the related table constraint/foreign-key dependency.
14. Implicit enforcing index DDL versus explicitly generated OFS DDL.

## Catalog assertions

Use `SYSINDEXES` for index-level classification, `SYSKEYS`/`SYSKEYTARGETS` for key order and expressions, and `SYSINDEXPART` for per-partition/storage attributes.

```sql
SELECT *
  FROM SYSIBM.SYSINDEXES
 WHERE CREATOR = UPPER('{{SCHEMA}}')
   AND NAME    = UPPER('{{INDEX}}');

SELECT *
  FROM SYSIBM.SYSKEYS
 WHERE IXCREATOR = UPPER('{{SCHEMA}}')
   AND IXNAME    = UPPER('{{INDEX}}')
 ORDER BY COLSEQ;

SELECT *
  FROM SYSIBM.SYSINDEXPART
 WHERE IXCREATOR = UPPER('{{SCHEMA}}')
   AND IXNAME    = UPPER('{{INDEX}}')
 ORDER BY PARTITION;
```

For expression indexes, confirm the current catalog names/columns on the target maintenance level and query `SYSIBM.SYSKEYTARGETS`; catalog shape can gain columns over time even when CREATE semantics remain stable.
