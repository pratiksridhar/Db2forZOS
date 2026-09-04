# Official IBM source manifest

All research in this knowledge base is derived from IBM documentation. `source_id` values in the normalized JSON resolve here.

Reviewed: **2026-09-03**. Product path: **Db2 13 for z/OS** unless noted.

## Release and compatibility

- `ibm-fl509` — [Function level 509 (PH70028 - April 2026)](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=levels-function-level-509)
- `ibm-sql-statements` — [SQL statements in Db2 for z/OS](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=sql-statements)

## Storage groups

- `ibm-create-stogroup` — [CREATE STOGROUP statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-stogroup)
- `ibm-stogroup-concept` — [Db2 storage groups](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=structures-db2-storage-groups)
- `ibm-stogroup-create-task` — [Creating Db2 storage groups](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=groups-creating-db2-storage)
- `ibm-catalog-sysstogroup` — [SYSIBM.SYSSTOGROUP catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-sysstogroup)
- `ibm-catalog-sysvolumes` — [SYSIBM.SYSVOLUMES catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-sysvolumes)

## Databases

- `ibm-create-database` — [CREATE DATABASE statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-database)
- `ibm-database-concept` — [Creation of databases](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=objects-creation-databases)
- `ibm-catalog-sysdatabase` — [SYSIBM.SYSDATABASE catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-sysdatabase)

## Table spaces

- `ibm-create-tablespace` — [CREATE TABLESPACE statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-tablespace)
- `ibm-create-lob-tablespace` — [CREATE LOB TABLESPACE](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-lob-tablespace)
- `ibm-tablespace-concept` — [Db2 table spaces](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=structures-db2-table-spaces)
- `ibm-pbg-concept` — [Partition-by-growth table spaces](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=zos-partition-by-growth-table-spaces)
- `ibm-pbr-create` — [Creating partition-by-range table spaces](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-creating-partition-by-range-table)
- `ibm-implicit-tablespace` — [Implicitly defined table spaces](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-implicitly-defined-table)
- `ibm-ea-spaces` — [EA-enabled table spaces and index spaces](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-ea-enabled-table-index)
- `ibm-gbpcache` — [How the GBPCACHE option affects write operations](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=operations-how-gbpcache-option-affects-write)
- `ibm-catalog-systablespace` — [SYSIBM.SYSTABLESPACE catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-systablespace)
- `ibm-catalog-systablepart` — [SYSIBM.SYSTABLEPART catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-systablepart)

## Tables

- `ibm-create-table` — [CREATE TABLE statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-table)
- `ibm-table-concept` — [Db2 tables](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=concepts-db2-tables)
- `ibm-create-base-table` — [Creating base tables](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-creating-base)
- `ibm-temporal-concept` — [Temporal tables and data versioning](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-temporal-data-versioning)
- `ibm-catalog-systables` — [SYSIBM.SYSTABLES catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-systables)
- `ibm-catalog-syscolumns` — [SYSIBM.SYSCOLUMNS catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-syscolumns)
- `ibm-catalog-sysrels` — [SYSIBM.SYSRELS catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-sysrels)
- `ibm-catalog-sysforeignkeys` — [SYSIBM.SYSFOREIGNKEYS catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-sysforeignkeys)
- `ibm-catalog-syschecks` — [SYSIBM.SYSCHECKS catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-syschecks)

## Views

- `ibm-create-view` — [CREATE VIEW statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-view)

## Indexes

- `ibm-create-index` — [CREATE INDEX statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-index)
- `ibm-index-concept` — [Db2 indexes](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-db2-indexes)
- `ibm-index-names` — [Index names and guidelines](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=indexes-index-names-guidelines)
- `ibm-partitioned-indexes` — [Indexes on partitioned tables](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=indexes-partitioned-tables)
- `ibm-implicit-index` — [How Db2 implicitly creates an index](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=indexes-how-db2-implicitly-creates-index)
- `ibm-catalog-sysindexes` — [SYSIBM.SYSINDEXES catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-sysindexes)
- `ibm-catalog-sysindexpart` — [SYSIBM.SYSINDEXPART catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-sysindexpart)
- `ibm-catalog-syskeys` — [SYSIBM.SYSKEYS catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-syskeys)
- `ibm-catalog-syskeytargets` — [SYSIBM.SYSKEYTARGETS catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-syskeytargets)

## Triggers

- `ibm-create-trigger-basic` — [CREATE TRIGGER statement (basic trigger)](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-trigger-basic)
- `ibm-create-trigger-advanced` — [CREATE TRIGGER statement (advanced trigger)](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-trigger-advanced)
- `ibm-trigger-concept` — [Triggers](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=concepts-triggers)
- `ibm-trigger-create-task` — [Creating a trigger](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=programs-creating-trigger)
- `ibm-trigger-convert` — [Converting existing triggers to support advanced capabilities](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=trigger-converting-existing-triggers-support-advanced-capabilities)
- `ibm-trigger-cascading` — [Trigger cascading](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=trigger-cascading)
- `ibm-trigger-activation-order` — [Activation order of multiple triggers](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=trigger-activation-order-multiple-triggers)
- `ibm-trigger-packages` — [Trigger packages](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=trigger-packages)

## Procedures

- `ibm-create-procedure-overview` — [CREATE PROCEDURE statement (overview)](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-procedure-overview)
- `ibm-create-procedure-native` — [CREATE PROCEDURE statement (SQL - native procedure)](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-procedure-sql-native)
- `ibm-create-procedure-external` — [CREATE PROCEDURE statement (external procedure)](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-procedure-external)
- `ibm-create-procedure-sql-external-deprecated` — [CREATE PROCEDURE statement (SQL - external procedure) (deprecated)](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-create-procedure-sql-external-deprecated)
- `ibm-procedure-concept` — [Routines in Db2 for z/OS: functions and procedures](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=concepts-routines-functions-procedures)
- `ibm-procedure-create-native-task` — [Creating native SQL procedures](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=procedures-creating-native-sql)
- `ibm-procedure-create-external-task` — [Creating external stored procedures](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=procedures-creating-external-stored)
- `ibm-procedure-create-external-sql-task` — [Creating external SQL procedures (deprecated)](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=procedures-creating-external-sql-deprecated)
- `ibm-procedure-multiple-versions` — [Multiple versions of native SQL procedures](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=procedures-multiple-versions-native-sql)
- `ibm-procedure-package-copies` — [Making copies of a package for a native SQL procedure](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=procedures-making-copies-package-native-sql-procedure)
- `ibm-procedure-body` — [SQL procedure body](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=procedures-sql-procedure-body)
- `ibm-catalog-sysroutines` — [SYSIBM.SYSROUTINES catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-sysroutines)
- `ibm-catalog-sysparms` — [SYSIBM.SYSPARMS catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-sysparms)
- `ibm-catalog-sysroutineauth` — [SYSIBM.SYSROUTINEAUTH catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-sysroutineauth)

## SQL PL and trigger-body statements

- `ibm-sqlpl` — [SQL procedural language (SQL PL)](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=sql-procedural-language-pl)
- `ibm-sql-procedure-statement` — [SQL-procedure-statement (SQL PL)](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-sql-procedure-statement-sql)
- `ibm-sqlpl-compound` — [Compound statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-compound-statement)
- `ibm-sqlpl-case` — [CASE statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-case-statement)
- `ibm-sqlpl-for` — [FOR statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-statement)
- `ibm-sqlpl-if` — [IF statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-if-statement)
- `ibm-sqlpl-loop` — [LOOP statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-loop-statement)
- `ibm-sqlpl-repeat` — [REPEAT statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-repeat-statement)
- `ibm-sqlpl-resignal` — [RESIGNAL statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-resignal-statement)
- `ibm-sqlpl-return` — [RETURN statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-return-statement)
- `ibm-sqlpl-signal` — [SIGNAL statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-signal)
- `ibm-sqlpl-while` — [WHILE statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=pl-while-statement)
- `ibm-get-diagnostics` — [GET DIAGNOSTICS statement](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=statements-get-diagnostics)
- `ibm-sql-reference-pdf` — [Db2 13 for z/OS SQL Reference PDF](https://www.ibm.com/docs/en/SSEPEK_13.0.0/pdf/db2z_13_sqlrefbook.pdf)

## Trigger catalog and package evidence

- `ibm-catalog-systriggers` — [SYSIBM.SYSTRIGGERS catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-systriggers)
- `ibm-catalog-systriggers-stmt` — [SYSIBM.SYSTRIGGERS_STMT catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-systriggers-stmt)
- `ibm-catalog-syspackage` — [SYSIBM.SYSPACKAGE catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-syspackage)
- `ibm-catalog-syspackdep` — [SYSIBM.SYSPACKDEP catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=tables-syspackdep)
- `ibm-catalog-sysenvironment` — [SYSIBM.SYSENVIRONMENT catalog table](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=spaces-sysenvironment)

## Citation policy

Chapters cite source IDs at the section or rule cluster level instead of reproducing IBM prose. Examples in this repository are newly authored and use placeholders; IBM examples are not copied into the templates. Recheck the source manifest before adding a feature introduced after the review date.
