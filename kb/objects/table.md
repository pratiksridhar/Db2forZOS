# TABLE

## Concept and CREATE families

A table is the logical row-and-column object. `CREATE TABLE` can define a base table, a materialized query table, or an accelerator-only table; IBM documents auxiliary and global temporary tables with separate CREATE statements. This chapter concentrates on base/MQT definitions while recording accelerator restrictions that affect the shared grammar.

Four definition families are mutually exclusive:

1. explicit columns, periods, and constraints
2. `LIKE` an existing table or view
3. `AS (fullselect) WITH NO DATA`
4. a materialized query definition with refresh options

Sources: `ibm-table-concept`, `ibm-create-base-table`, `ibm-create-table`.

## Top-level syntax summary

```text
CREATE TABLE <table-name>
  {
    ( <table-element> [, ...] )
  | LIKE { <table-name> | <view-name> } [ <copy-options> ]
  | [ ( <column-name> [, ...] ) ]
      AS ( <fullselect> ) WITH NO DATA [ <copy-options> ]
  | [ ( <column-name> [, ...] ) ]
      AS ( <fullselect> ) <refreshable-table-options>
  }
  [ IN <database-name>.<table-space-name>
  | IN DATABASE <database-name>
  | IN ACCELERATOR <accelerator-name> ]
  [ <partitioning-clause> ]
  [ <deprecated-organization-clause> ]
  [ EDITPROC <program-name> [ WITH | WITHOUT ROW ATTRIBUTES ] ]
  [ VALIDPROC <program-name> ]
  [ AUDIT { NONE | CHANGES | ALL } ]
  [ OBID <integer> ]
  [ DATA CAPTURE { NONE | CHANGES } ]
  [ WITH RESTRICT ON DROP ]
  [ CCSID { ASCII | EBCDIC | UNICODE } ]
  [ { NOT VOLATILE | VOLATILE } CARDINALITY ]
  [ LOGGED | NOT LOGGED ]
  [ COMPRESS { NO | YES [ FIXEDLENGTH | HUFFMAN ] } ]
  [ APPEND { NO | YES } ]
  [ DSSIZE <integer> G ]
  [ BUFFERPOOL <bpname> ]
  [ MEMBER CLUSTER ]
  [ TRACKMOD { YES | NO } ]
  [ PAGENUM { RELATIVE | ABSOLUTE } ]
  [ KEY LABEL <key-label-name> | NO KEY LABEL ]
```

Many physical clauses in the lower half are valid only when Db2 implicitly creates the base table space. See “Placement and physical clauses.”

## Explicit table elements

```text
<table-element> ::=
    <column-definition>
  | <period-definition>
  | <unique-constraint>
  | <referential-constraint>
  | <check-constraint>

<column-definition> ::=
  <column-name> [ <data-type> ]
  [ NOT NULL ]
  [ <generated-clause> ]
  [ <single-column-constraint> ]
  [ WITH DEFAULT | DEFAULT <default-value> ]
  [ FIELDPROC <program-name> [ ( <constant> [, ...] ) ] ]
  [ AS SECURITY LABEL ]
  [ IMPLICITLY HIDDEN ]
  [ INLINE LENGTH <integer> ]
```

The data type can be omitted only for generated timestamp/transaction forms where IBM defines an implicit type. Ordinary columns require a built-in or distinct type.

### Column count and row size

- A normal table can have up to 750 columns; a dependent table can have up to 749.
- Column names are unqualified and unique within the table. A table name is a schema-qualified or unqualified SQL identifier; the ordinary object identifier can be up to 128 characters.
- Maximum record sizes without an edit procedure are 4056, 8138, 16330, and 32714 bytes for 4/8/16/32 KB pages. With `EDITPROC`, subtract 10 bytes from each. Maximum row size is eight bytes below maximum record size.
- For an implicitly created table space, Db2 can select a larger page-size buffer pool when the actual record approaches the documented 90% threshold.

## Built-in data-type inventory

This is a compact CREATE inventory; the IBM data-type reference remains authoritative for value semantics.

| Family | Forms and CREATE limits/defaults |
|---|---|
| Exact integers | `SMALLINT`, `INTEGER`/`INT`, `BIGINT` |
| Decimal | `DECIMAL`/`DEC`/`NUMERIC(p,s)`; `p` 1–31, `s` 0–`p`; omitted form is `(5,0)` |
| Decimal float | `DECFLOAT(16|34)`; omitted precision is 34 |
| Binary float | `FLOAT(n)` with `n` 1–21 single precision, 22–53 double; omitted/`DOUBLE [PRECISION]` is 53; `REAL` is single |
| Fixed character | `CHARACTER`/`CHAR(n)`, 1–255; omitted length 1; optional `FOR SBCS|MIXED|BIT DATA`; EBCDIC tables can define Unicode columns with `CCSID 1208` where allowed |
| Varying character | `VARCHAR(n)`, `CHAR VARYING(n)`, `CHARACTER VARYING(n)`; 1 through maximum-record-dependent limit |
| Character LOB | `CLOB(n [K|M|G])` and long names; 1–2147483647 bytes; default 1M; `G` maximum 2 with the top value reduced by one byte |
| Fixed graphic | `GRAPHIC(n)`, 1–127; omitted length 1; Unicode column form uses `CCSID 1200` where allowed |
| Varying graphic | `VARGRAPHIC(n)`, bounded by half the available row bytes |
| Graphic LOB | `DBCLOB(n [K|M|G])`, 1–1073741823 double-byte characters; default 1M |
| Fixed binary | `BINARY(n)`, 1–255; omitted length 1 |
| Varying binary | `VARBINARY(n)`/`BINARY VARYING(n)`, 1–32704 and page-size constrained |
| Binary LOB | `BLOB(n [K|M|G])`, 1–2147483647 bytes; default 1M |
| Date/time | `DATE`, `TIME`, `TIMESTAMP(p) [WITHOUT|WITH TIME ZONE]`; `p` 0–12, default 6 |
| Row identifier | `ROWID`; must be `NOT NULL`; at most two when one is implicit and one explicit in the documented FL 506 case |
| XML | `XML` optionally constrained by registered `XMLSCHEMA` specifications and a global `ELEMENT` |
| User-defined | `<distinct-type-name>`; restrictions of the source type continue to apply |

High-value type cases include each alias spelling, omitted versus explicit defaults, every min/max, overflow by one, mixed/Unicode subtype behavior, page-size-sensitive varying strings, inline versus out-of-line LOBs, XML modifiers, distinct types, and unsupported types in accelerator-only tables.

## Nullability and defaults

Omitting `NOT NULL` makes a normal column nullable. For a non-identity column, omission of both `NOT NULL` and `DEFAULT` is effectively `DEFAULT NULL`. Identity columns are implicitly not null.

`DEFAULT` can use a compatible constant, `SESSION_USER`/`USER`, `CURRENT SQLID`, `NULL`, or an eligible cast-function form. A value-less `WITH DEFAULT` selects the type default:

| Type family | Type default |
|---|---|
| numeric | zero |
| fixed character/graphic | blanks |
| fixed binary | hexadecimal zeros |
| varying string | zero-length string |
| inline BLOB | hexadecimal zeros |
| inline CLOB/DBCLOB | blanks |
| DATE/TIME | current date/time |
| TIMESTAMP | current timestamp of matching precision and time-zone form |
| distinct type | source-type default |

Do not specify `DEFAULT` for identity, ROWID, row-change timestamp, row-begin, row-end, transaction-start-ID, or XML columns. Accelerator-only tables also reject column defaults.

## Generated columns

```text
<generated-clause> ::=
    GENERATED { ALWAYS | BY DEFAULT } AS IDENTITY [ ( <identity-options> ) ]
  | GENERATED { ALWAYS | BY DEFAULT }
      FOR EACH ROW ON UPDATE AS ROW CHANGE TIMESTAMP
  | GENERATED { ALWAYS | BY DEFAULT } ROWID
  | GENERATED ALWAYS AS TRANSACTION START ID
  | GENERATED ALWAYS AS ROW { BEGIN | START | END }
  | GENERATED ALWAYS AS ( <non-deterministic-expression> )
```

`ALWAYS` is the default/recommended general choice. `BY DEFAULT` permits a supplied value for identity and eligible ROWID/row-change forms, with extra uniqueness/index implications.

### Identity

```text
AS IDENTITY (
  [ START WITH <numeric-constant> ]
  [ INCREMENT BY <numeric-constant> ]
  [ NO MINVALUE | MINVALUE <numeric-constant> ]
  [ NO MAXVALUE | MAXVALUE <numeric-constant> ]
  [ NO CYCLE | CYCLE ]
  [ CACHE <integer-constant> | NO CACHE ]
  [ NO ORDER | ORDER ]
)
```

- One identity column per table; exact numeric type with scale zero.
- Defaults: increment 1, `NO MINVALUE`, `NO MAXVALUE`, `NO CYCLE`, `CACHE 20`, `NO ORDER`; start resolves from direction and endpoints.
- `CACHE n` has minimum 2. `CYCLE` can generate duplicates; identity itself does not imply uniqueness.
- In data sharing, `ORDER` effectively disables caching to preserve request order.

### System-generated timestamp and provenance forms

| Form | Required type/rules |
|---|---|
| row-change timestamp | one per table; `TIMESTAMP(6) WITHOUT TIME ZONE`, `NOT NULL`, no default |
| transaction-start ID | one per table; implicit `TIMESTAMP(12) WITHOUT TIME ZONE` or explicit precision-12 with/without time zone; no default; not updatable |
| row begin | one; precision-12 timestamp with/without time zone; `NOT NULL`; no default; not updatable |
| row end | one; same type rules as begin; `NOT NULL`; no default; assigned end-of-time value |
| `DATA CHANGE OPERATION` | one; `CHAR(1)`, nullable, no default; generates `I`, `U`, or `D` |
| client/server special register | exact required VARCHAR/CHAR type documented for the selected register; nullable, no default |
| package session variable | exact documented VARCHAR type; nullable, no default |

Non-deterministic generated-expression sources are limited to the IBM-listed client/server special registers and `SYSIBM.PACKAGE_NAME`, `PACKAGE_SCHEMA`, or `PACKAGE_VERSION` session variables. These columns cannot use `CCSID 1200`, `CCSID 1208`, or `FIELDPROC`.

## Column attributes

| Attribute | Core restrictions |
|---|---|
| `FIELDPROC` | Built-in character/graphic string with encoded length no more than 255; not LOB, security label, row-change timestamp, time-zone timestamp, certain Unicode/EBCDIC combinations, or accelerator-only. Parameter text is limited to 254 bytes. |
| `AS SECURITY LABEL` | One per table; EBCDIC `CHAR(8) FOR SBCS DATA NOT NULL WITH DEFAULT`; active RACF security-label setup; no field/check/referential constraint on the column. |
| `IMPLICITLY HIDDEN` | Excluded from `SELECT *` unless named; cannot hide every column; not ROWID/distinct ROWID or accelerator-only. |
| `INLINE LENGTH` | LOB/distinct LOB in UTS only. BLOB/CLOB 0–32680 bytes; DBCLOB 0–16340 double-byte characters; not above the LOB maximum. Omission uses the distinct-type attribute or `LOB_INLINE_LENGTH` behavior. |

## Constraints

### Primary and unique keys

```text
[ CONSTRAINT <name> ] PRIMARY KEY
  ( <column-name> [, ...] [ , BUSINESS_TIME WITHOUT OVERLAPS ] )

[ CONSTRAINT <name> ] UNIQUE
  ( <column-name> [, ...] [ , BUSINESS_TIME WITHOUT OVERLAPS ] )
```

- Primary key: at most one per table. Every key column must be `NOT NULL`.
- Unique key columns also must be `NOT NULL` in this table-constraint form.
- At most 64 columns; no duplicate column; no LOB, ROWID, XML, row-change timestamp, or related prohibited distinct types.
- Key length must not exceed `2000 - n - 2m - 3d`, using IBM's `m` varying-column and `d` DECFLOAT counts (for these nonnullable keys, `n` is normally zero).
- Character/graphic key columns use one encoding scheme.
- An explicit table space plus ordinary dynamic SQL can leave the table unavailable until matching enforcing unique indexes are created. The schema processor or an implicit table space can create them implicitly.
- `BUSINESS_TIME WITHOUT OVERLAPS` adds end then begin columns to the enforcement key and makes the non-period portion unique over time.

Single-column `PRIMARY KEY`, `UNIQUE`, `REFERENCES`, and `CHECK` forms can be written inside the column definition under the same semantic restrictions.

### Referential constraints

```text
[ CONSTRAINT <name> ]
FOREIGN KEY ( <column-name> [, ...] [ , PERIOD BUSINESS_TIME ] )
REFERENCES <parent-table>
  [ ( <column-name> [, ...] [ , PERIOD BUSINESS_TIME ] ) ]
[ ON DELETE { RESTRICT | NO ACTION | CASCADE | SET NULL } ]
[ ENFORCED
| NOT ENFORCED [ ENABLE QUERY OPTIMIZATION ] ]
```

- Up to 64 columns including implicit period columns; key length no more than `255 - n`, where `n` is the number of nullable columns.
- Parent columns must match a primary/unique key in number, order, and compatible definition; omission of the parent list selects its primary key.
- LOB, ROWID, DECFLOAT, XML, row-change timestamp, security-label, and accelerator-only columns cannot participate.
- `SET NULL` requires at least one nullable foreign-key column.
- Delete-rule omission depends on `CURRENT RULES`: Db2 rules default to `RESTRICT`; standard rules default to `NO ACTION`.
- `ENFORCED` is default. `NOT ENFORCED` shifts correctness outside Db2; query optimization is enabled by default.
- Temporal referential constraints require `PERIOD BUSINESS_TIME` on both sides, matching no-overlap indexes, and `ON DELETE RESTRICT`.

### Check constraints

```text
[ CONSTRAINT <name> ] CHECK ( <check-condition> )
```

The condition must be true or unknown for every row. IBM limits it to 3800 bytes and restricts it to the table's columns and a constrained predicate language: no subselects, general functions, host/parameter markers, special/global variables, CASE/OLAP/sequence constructs, or CCSID conversion. Create dedicated negative cases for each forbidden expression family rather than treating `CHECK` as arbitrary SQL search syntax.

## Periods and temporal foundations

```text
PERIOD FOR SYSTEM_TIME ( <row-begin-column>, <row-end-column> )

PERIOD FOR BUSINESS_TIME
  ( <begin-column>, <end-column> [ EXCLUSIVE | INCLUSIVE ] )
```

- `SYSTEM_TIME` requires `AS ROW BEGIN` and `AS ROW END` columns with matching precision/type. Defining the period does not itself enable system-versioned history; the history-table relationship/versioning is established later with `ALTER TABLE`.
- `BUSINESS_TIME` begin/end columns are `DATE` or `TIMESTAMP(6) WITHOUT TIME ZONE`, matching, `NOT NULL`, and not generated.
- Business time defaults to inclusive-exclusive (`EXCLUSIVE`). `INCLUSIVE` makes the end inclusive.
- Db2 creates a check constraint enforcing end > begin for exclusive or end >= begin for inclusive.
- A table can have one period of each kind, making bitemporal foundations possible.

## LIKE, AS-result, and MQT forms

### LIKE

`LIKE table-or-view` copies column names and descriptions but not the table's keys, indexes, table-space placement, or most generated semantics. Important selectable copy options are:

- `INCLUDING` or `EXCLUDING IDENTITY COLUMN ATTRIBUTES` (default excludes)
- `INCLUDING` or `EXCLUDING ROW CHANGE TIMESTAMP COLUMN ATTRIBUTES` (default excludes)
- `EXCLUDING COLUMN DEFAULTS`, `INCLUDING COLUMN DEFAULTS`, or `USING TYPE DEFAULTS`
- `EXCLUDING XML TYPE MODIFIERS`

Test source table versus source view, hidden columns, identity/timestamp/default options, inline LOB inheritance, ROWID behavior, and fields/procedures. A source cannot be an auxiliary or clone table; accelerator-only sources are excluded.

### AS-result table

```text
[ ( <new-column-name> [, ...] ) ]
AS ( <fullselect> )
WITH NO DATA
[ <copy-options> ]
```

The result determines column name/type/length/precision/scale/nullability. Provide a name list when the result contains duplicates or unnamed expressions. Keys and other table attributes are not inherited. Generated attributes are not inherited. This form creates no rows.

### Materialized query table

```text
[ ( <new-column-name> [, ...] ) ]
AS ( <fullselect> )
DATA INITIALLY DEFERRED
REFRESH DEFERRED
[ MAINTAINED BY { SYSTEM | USER } ]
[ ENABLE | DISABLE QUERY OPTIMIZATION ]
```

System maintenance and query optimization are defaults. User-maintained MQTs permit supported data-change/LOAD/REFRESH paths. The fullselect has substantial IBM restrictions; use the CREATE statement source for exhaustive MQT query legality.

## Placement and physical clauses

### Existing explicit table space

```text
IN <database-name>.<table-space-name>
```

The database and UTS must exist and match; the space cannot be implicit, LOB, XML, non-UTS, or an already occupied partitioned space. The table inherits physical attributes from that space. Do **not** also specify `LOGGED`, `NOT LOGGED`, `COMPRESS`, `DSSIZE`, `BUFFERPOOL`, `MEMBER CLUSTER`, `TRACKMOD`, or `PAGENUM`.

### Implicit table space in an existing database

```text
IN DATABASE <database-name>
```

Db2 derives a table-space name and creates it. Eligible physical clauses on `CREATE TABLE` describe the implicit space.

### Fully implicit database and table space

Omitting `IN` creates/chooses an implicit database named `DSNnnnnn` and creates a table space. The database and table space are owned by `SYSIBM` under the documented implicit-creation behavior.

### Accelerator-only

`IN ACCELERATOR` stores rows only in the accelerator and leaves definitions in the Db2 catalog. It forbids many shared clauses and data types. Because execution depends on accelerator configuration, keep these cases in a separately tagged environment suite.

## Partitioning clause

### PBG

```text
PARTITION BY SIZE [ EVERY <integer> G ]
```

This is the default when Db2 implicitly creates a space and no partition clause is present. `EVERY` cannot exceed 256 G and must equal an existing PBG table space's effective `DSSIZE` when one is named.

### PBR

```text
PARTITION BY [ RANGE ]
  ( <partition-expression> [, ...] )
  ( <partition-element> [, ...] )

<partition-expression> ::=
  <column-name> [ NULLS LAST ] [ ASC | DESC ]

<partition-element> ::=
  PARTITION <physical-number>
  ENDING AT ( <constant> | MAXVALUE | MINVALUE [, ...] )
  [ INCLUSIVE ]
```

- `RANGE` is optional in current syntax.
- Up to 64 partitioning columns; no duplicates; total length `<= 255 - n` for `n` nullable columns.
- LOB, binary/varbinary, DECFLOAT, and XML columns are not allowed. A time-zone timestamp can appear only last. Character/graphic columns share one encoding scheme.
- Default direction is `ASC`. `NULLS LAST` treats null as positive infinity for partition comparison.
- Every physical table-space partition needs a `PARTITION` element.
- Each boundary supplies one or more constants/`MAXVALUE`/`MINVALUE`; omitted trailing key components resolve to the direction-dependent extreme.
- Boundaries must progress in key order. The last boundary is enforced; values beyond it are out of range.
- `MAXVALUE`/`MINVALUE` propagation and nullable-key rules depend on ASC/DESC as documented. Pair every mixed-direction positive case with boundary-order and illegal-extreme negatives.
- `INCLUSIVE` includes the specified boundary. Omission follows the statement's documented ending semantics.

## Table and implicit-space options

| Clause | Meaning/default and legality |
|---|---|
| `EDITPROC` | Whole-row transformation exit; optional row attributes. Numerous generated/LOB/XML/security restrictions. |
| `VALIDPROC` | Row validation exit; one at a time; not accelerator-only. |
| `AUDIT` | `NONE` default, `CHANGES`, or `ALL`; effective only with appropriate traces. |
| `OBID` | Explicit internal object identifier greater than 1 and never previously used in the database; normally omit. |
| `DATA CAPTURE` | `NONE` default or `CHANGES` for replication logging; `CHANGES` conflicts with `NOT LOGGED`. |
| `WITH RESTRICT ON DROP` | Prevents ordinary drop of the table and containing objects until altered/repair handling. |
| `CCSID` | ASCII/EBCDIC/UNICODE; must match a named table space. With implicit placement it selects the new space's encoding. |
| `VOLATILE` | Tells optimization to prefer index access where possible; `NOT VOLATILE` default. `CARDINALITY` is compatibility syntax with no independent effect. |
| `APPEND` | `NO` default; `YES` disregards clustering for insert/LOAD placement. Not for work-file table spaces. |
| `KEY LABEL` | Table-level encryption label for all Db2-managed associated spaces. Requires UTS/eligible partitioned space and proper ICSF/RACF/DFSMS setup; not accelerator/auxiliary. |

The following options describe only an **implicitly created** base table space:

| Clause | Rule |
|---|---|
| `LOGGED` / `NOT LOGGED` | `LOGGED` default; inherited by associated spaces/indexes where documented. |
| `COMPRESS` | Omission uses `IMPTSCMP`; explicit YES optionally selects fixed-length or Huffman. |
| `DSSIZE` | Omission uses `IMPDSSIZE`; conflicts with an explicit table-space name and `EVERY n G`. |
| `BUFFERPOOL` | Active 4/8/16/32 KB pool; otherwise Db2 chooses based on row size and subsystem defaults. |
| `MEMBER CLUSTER` | Places by available space rather than clustering order. |
| `TRACKMOD` | YES/NO; omission uses `IMPTKMOD`. |
| `PAGENUM` | Applies to an implicit PBR space; omission uses `PAGESET_PAGENUM`; RPN preferred. |

## LOB and XML side effects

### LOB

A table with CLOB/BLOB/DBCLOB data needs a ROWID, an auxiliary table in a LOB table space for each LOB column, and an auxiliary index. For a partitioned base table, that set is needed per LOB column per partition.

When no explicit ROWID is supplied, Db2 creates an implicitly hidden `GENERATED ALWAYS` ROWID column. In eligible implicit-creation situations, Db2 also creates LOB spaces, auxiliary tables, and auxiliary indexes. Otherwise the definition remains incomplete until the explicit supporting objects exist. This KB models the side effect but leaves the separate `CREATE AUXILIARY TABLE` grammar outside the five-object core.

### XML

The first XML column causes an implicit BIGINT document-ID column. Db2 creates the underlying XML table space implicitly and derives its attributes from the base space according to the documented PBG/PBR rules. XML indexes use the specialized grammar in [index.md](index.md).

## Deprecated hash organization

`ORGANIZE BY HASH (...) HASH SPACE ...` and per-partition hash-space clauses are deprecated. At application compatibility V12R1M504 and higher, creating new hash-organized tables is not supported. Retain the grammar only for low-compatibility recovery/regression tests; do not use it in new-object templates.

## High-value OFS test dimensions

1. All four definition families, with legal and illegal copy-option combinations.
2. Data-type alias/default/min/max matrices across all four page sizes.
3. Nullable versus `NOT NULL`; omitted default, value-less default, explicit type default, explicit constant, and forbidden generated-column default.
4. Every generated-column subtype and its exact type/nullability/default companion negatives.
5. Column-level versus table-level constraint spellings; enforcing-index incomplete versus implicit-index-complete behavior.
6. Simple, composite, self/parent, cascading, nullable, unenforced, and temporal referential constraints.
7. System, business, and bitemporal period foundations; inclusive/exclusive and no-overlap behavior.
8. Existing explicit versus database-implicit versus fully implicit placement, including rejection of implicit-space clauses with an explicit space.
9. PBG versus PBR, mixed ASC/DESC boundaries, nullable keys, partial limit keys, extrema, and out-of-range last partitions.
10. LOB inline/out-of-line and explicit/implicit support objects; XML type modifiers and implicit XML objects.
11. Encoding, hidden, field/security procedures, auditing, capture, volatility, append, key-label, and restrict-on-drop attributes.
12. Deprecated hash/non-UTS cases only under explicitly recorded lower `APPLCOMPAT`.

## Catalog assertions

Use `SYSTABLES` for table attributes and `SYSCOLUMNS` for every column. Constraint and period cases also require their specialized catalog tables; do not infer a complete definition from only `SYSTABLES`.

```sql
SELECT *
  FROM SYSIBM.SYSTABLES
 WHERE CREATOR = UPPER('{{SCHEMA}}')
   AND NAME    = UPPER('{{TABLE}}');

SELECT *
  FROM SYSIBM.SYSCOLUMNS
 WHERE TBCREATOR = UPPER('{{SCHEMA}}')
   AND TBNAME    = UPPER('{{TABLE}}')
 ORDER BY COLNO;
```

Also query `SYSIBM.SYSRELS`, `SYSIBM.SYSFOREIGNKEYS`, `SYSIBM.SYSCHECKS`, the enforcing rows in `SYSIBM.SYSINDEXES`/`SYSIBM.SYSKEYS`, and the base/LOB/XML space rows as appropriate. Period and temporal attributes are represented in `SYSTABLES` and `SYSCOLUMNS`; do not assume a separate period catalog table. The consolidated script uses broad `SELECT *` predicates to remain useful across catalog-level additions.
