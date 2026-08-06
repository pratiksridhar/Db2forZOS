# Object model and DDL dependency graph

## The seven objects at a glance

Db2 separates logical data design from physical storage, but the boundaries are intentionally permeable: defaults flow downward, and a `CREATE TABLE` can cause several physical objects to appear implicitly.

```text
Db2 storage group
  -> supplies volumes/SMS classes and an ICF catalog for Db2-managed data sets

Database
  -> administrative and recovery grouping
  -> carries default storage group, table-space buffer pool, index buffer pool, CCSID

Table space
  -> VSAM linear data sets divided into pages
  -> contains one base table for supported UTS forms
  -> PBG: partitions appear as data grows
  -> PBR: rows map to partitions by range keys

Table
  -> logical rows, columns, constraints, periods, and optional partitioning definition

Index
  -> ordered pointers/keys in a separate index space
  -> can enforce a primary/unique key, cluster rows, or provide an access path

Trigger
  -> belongs to a local subject table (BEFORE/AFTER) or view (INSTEAD OF)
  -> owns an implicitly created trigger package and dependencies on body objects
  -> can read transition rows/tables and run a basic or advanced triggered action

Procedure
  -> is invoked explicitly with CALL or from another routine/trigger
  -> is native SQL with an implicitly bound versioned package, or external with a separately prepared program
  -> owns parameters, execution attributes, privileges, and dependencies on body/program artifacts
```

Official IBM concepts behind this model are indexed as `ibm-stogroup-concept`, `ibm-database-concept`, `ibm-tablespace-concept`, `ibm-table-concept`, `ibm-index-concept`, `ibm-trigger-concept`, and `ibm-procedure-concept` in [sources.md](sources.md).

## Storage group

A Db2 storage group is a cataloged description of storage, not a data container itself. It identifies an ICF catalog and either explicit volumes, SMS selection, or SMS class names. When a table space or index says `USING STOGROUP`, Db2 defines and manages its VSAM linear data sets. `USING VCAT` instead means that the user manages the data sets.

`SYSDEFLT` is installed as the default storage group. A database can name another default, and a table space or index can override the database default. A key label at the table level takes precedence over a storage-group key label when Db2 supplies a key label to DFSMS; DFSMS and RACF can still apply their own precedence.

## Database

A Db2 database is primarily an administrative grouping for related table spaces and their indexes. It supports database-level start, stop, display, authorization, and recovery operations. It is not the same concept as a distributed-platform Db2 database.

The database definition supplies defaults rather than permanently fixing child attributes:

- `STOGROUP` is the default storage group for table and index spaces.
- `BUFFERPOOL` is the default for table spaces.
- `INDEXBP` is the default for indexes.
- `CCSID` is the default encoding scheme for table spaces.

A regular database and an `AS WORKFILE` database have materially different clause rules. Work-file databases are data-sharing-specific and support temporary/work processing rather than ordinary base-table storage.

## Table space

A table space is the physical page-set layer. Its assigned buffer pool determines a 4 KB, 8 KB, 16 KB, or 32 KB page size. The supported base-table forms at application compatibility V12R1M504 and higher are universal table spaces (UTS):

| Form | Partition creation | Data placement | Index implications |
|---|---|---|---|
| PBG | Db2 adds partitions as the object grows, bounded by `MAXPARTITIONS` | Growth/space driven | Only nonpartitioned indexes |
| PBR | All partitions are defined; the table carries range keys and limit values | Range-key driven | Partitioning indexes, DPSIs, and NPIs are possible |

Both PBG and PBR UTS contain one base table and have segmented space management. PBR with relative page numbering (RPN) is IBM's recommended PBR form. Absolute page numbering remains a deprecated compatibility surface.

LOB table spaces use the separate `CREATE LOB TABLESPACE` statement. A LOB column needs an auxiliary table in a LOB table space and an auxiliary index. For a partitioned base table, each LOB column requires that supporting set for every base partition. Db2 can create the supporting objects implicitly in eligible cases.

XML table spaces are created implicitly when a table gains XML columns; they are not created with ordinary `CREATE TABLESPACE` syntax.

## Table

A table is the logical data structure. `CREATE TABLE` has four major definition families:

1. explicit column/constraint definitions
2. `LIKE` another table or view
3. `AS (fullselect) WITH NO DATA`
4. a materialized query definition

Physical-placement clauses on `CREATE TABLE` have two different meanings:

- With `IN database.table-space`, the named explicit table space already owns most physical attributes; clauses such as `BUFFERPOOL`, `COMPRESS`, `DSSIZE`, `LOGGED`, `MEMBER CLUSTER`, and `TRACKMOD` are not legal there.
- With no explicit table-space name, Db2 creates a PBG or PBR UTS implicitly and eligible physical clauses describe that new space.

A table with primary or unique constraints might remain definition-incomplete until enforcing unique indexes exist. Under the schema processor or when the table space is implicit, Db2 can create those indexes automatically.

## Index

An index has its own index space and storage attributes. Its semantic roles are independent and can overlap:

- **unique**: enforces key uniqueness
- **primary**: a unique index selected to enforce the table primary key
- **clustering**: controls preferred physical row order
- **partitioning**: key begins with the PBR partitioning key in the required order and direction
- **DPSI**: a physically partitioned secondary index aligned with data partitions
- **NPI/NPSI**: one physical index across all data partitions
- **expression-based**: one or more keys are scalar expressions
- **XML**: indexes values matching an `XMLPATTERN`
- **temporal**: adds business-time begin/end columns with overlap semantics

Partitioning and clustering are not synonyms. Partitioning chooses the data partition; clustering influences row order within the space.

## Trigger

A trigger is executable behavior attached to a data-change event. `BEFORE` and `AFTER` definitions depend on a local base table; `INSTEAD OF` definitions depend on a local view. The trigger also creates a package whose collection and name derive from the trigger schema and name. Body references add package dependencies that must be preserved and compared during OFS round trips.

The body relationship is deliberately asymmetric. An advanced trigger can contain supported `CREATE TABLE`, `CREATE INDEX`, or `CREATE VIEW` statements inside an SQL control block, but it cannot contain `CREATE STOGROUP`, `CREATE DATABASE`, `CREATE TABLESPACE`, or `CREATE TRIGGER`. Those runtime-created objects are effects of firing the trigger, not children in the trigger catalog hierarchy. Keep them in isolated fixtures and collect both trigger-package evidence and the created-object catalog rows.

## Procedure

A procedure is an executable routine registered at the current server. A native SQL procedure contains an SQL PL body and Db2 implicitly binds a package for each version. A current external procedure instead points to a separately prepared host-language load module or Java method and runs in an external WLM-managed address space. The older external SQL procedure form is deprecated and remains only a compatibility target.

Procedure dependencies are behavioral rather than containment relationships. A native body can depend on tables, views, routines, and other objects through its package; an external definition depends operationally on its program, WLM environment, external package, and security configuration. A trigger can invoke an eligible procedure, and a procedure with a table-locator parameter can be invoked only from a trigger action. Drop procedures before dropping body dependencies in a clean OFS fixture so package invalidation and restrictive dependencies do not obscure the target test.

## Explicit creation path

The most controlled OFS test stack is:

```text
CREATE STOGROUP
CREATE DATABASE ... STOGROUP ...
CREATE TABLESPACE ... IN database ... USING STOGROUP ...
CREATE TABLE ... IN database.table-space
CREATE [UNIQUE] INDEX ... ON table ... USING STOGROUP ...
CREATE TRIGGER ... ON table ...
CREATE PROCEDURE ... LANGUAGE SQL ...
```

This isolates inheritance and makes every object independently retrievable for generated-DDL comparison.

## Implicit creation paths

Implicit behavior deserves its own test family because generated DDL can legitimately be textually different while describing the same catalog state.

| `CREATE TABLE` placement | Result |
|---|---|
| `IN database.table-space` | Uses an existing explicit table space |
| `IN DATABASE database` | Db2 implicitly creates a table space in that database |
| no `IN` clause | Db2 chooses or creates a `DSNnnnnn` implicit database and creates a table space |
| `PARTITION BY SIZE` or no partition clause | The implicit base table space is PBG |
| `PARTITION BY RANGE ...` | The implicit base table space is PBR |

An implicit base table space can bring along enforcing primary/unique indexes, a generated-`BY DEFAULT` ROWID index, LOB table spaces/auxiliary objects, and XML table spaces. Capture both requested DDL and resulting catalog rows; a string-only assertion is insufficient.

## Drop-order implication for disposable tests

For a clean explicit stack, dependency order is the reverse of creation order: procedures, triggers, indexes, table, table space, database, then storage group. A table drop can remove dependent triggers and indexes and invalidate dependent packages; a database or table-space drop can cascade through contained objects depending on the statement used. Test harness cleanup should resolve exact names first and avoid broad wildcard drops. A trigger-body DDL case must first drop the exact view/index/table created by activation, then drop the trigger and its ordinary subject stack.
