# Db2 13 function levels and APPLCOMPAT gates for DDL

Use this chapter when a request names a function level (FL), when a profile records
one, or when generated DDL uses newer syntax. The machine-readable source is
[db2z13-function-levels.json](data/db2z13-function-levels.json); `tools/ddl.py lint`
uses it to report the minimum APPLCOMPAT and FL that a script needs and to fail
gated syntax that the recorded profile cannot run. Reviewed **2026-10-10** against
`ibm-db2-function-levels`, `ibm-applcompat-v13`, `ibm-applcompat-v12`,
`ibm-applcompat-incompatible`, `ibm-db2-13-incompatible` and `ibm-db2-13-deprecated`.

Quick lookup: `python3 tools/ddl.py levels --applcompat V13R1M500` lists the gated
syntax that is not available at that APPLCOMPAT and the default changes in effect.

## How the levels interact

- **Function level** activates capabilities for the subsystem or data sharing group.
  Activating a level activates all lower levels. Db2 13 levels are V13R1M100 and
  V13R1M500 through V13R1M509 on the review date.
- **APPLCOMPAT** is the application compatibility level of the package that runs a
  statement (for DDL scripts, the SPUFI/DSNTEP2/DSNTIAD or client package). New SQL
  syntax and behavior generally needs an APPLCOMPAT level at least equal to the FL
  that introduced it; otherwise Db2 returns an error such as SQLCODE -4743 or keeps
  the previous behavior. APPLCOMPAT cannot exceed the activated FL.
- Db2 13 still runs packages at V10R1, V11R1 and V12R1Mnnn APPLCOMPAT levels.
  Several DDL rules changed across the Db2 12 levels, so a Db2 13 subsystem can
  still produce Db2 12 behavior for a low-APPLCOMPAT package.
- Catalog level (CATMAINT) can differ from FL. FL 508 changes catalog column types
  (SYSINDEXES.DSSIZE becomes BIGINT) at catalog level V13R1M508.

Record `function_level`, `applcompat` and relevant subsystem parameters in the
profile's `product_context`. Without them the linter only reports requirements.

## DDL-relevant changes by function level

### FL 100 (V13R1M100, 2022-05)

Catalog level V13R1M100; enabling APAR none; source `ibm-fl100`.

IBM capability list: Index look-aside optimization; Sort optimization; Expanded SORTL usage with learning from execution (IBM z15); Improved locking and cross-partition search for INSERT to PBG table spaces; Reduced ECSA storage for IFI buffers; Column names longer than 30 bytes; Relative page numbering for new PBR table spaces (PAGESET_PAGENUM default RELATIVE); Improved default statistics collection granularity; Enhanced space-level recovery with the RECOVER utility.

- **fl100-long-column-names**: Column names can be up to 128 bytes when the TABLE_COL_NAME_EXPANSION subsystem parameter is ON (the limits page spells it TABLE_COLUMN_NAME_EXPANSION); otherwise 30 bytes. Names over 30 bytes can be truncated in SQLDA-based APIs. Checker: `name.length`, `name.column-expansion`.
- **fl100-pagenum-default**: The PAGESET_PAGENUM default changed to RELATIVE, so an omitted PAGENUM on a new PBR table space uses relative page numbering unless the installation overrides it.
- **fl100-key-label-archived**: A KEY LABEL on CREATE/ALTER STOGROUP or CREATE/ALTER TABLE cannot name an ICSF key archived for decryption only.

### FL 500 (V13R1M500, 2022-05)

Catalog level V13R1M100; enabling APAR none; source `ibm-fl500`.

IBM capability list: Increased flexibility for package ownership; Page sampling for inline statistics; SQL Data Insights; Reduced ECSA storage for IFI buffers; Online conversion of tables from growth-based (PBG) to range-based (PBR) partitions; Fast index traversal (FTB) support for larger index keys; Increased control for applications over how long to wait for a lock; Profile table enhancements for application environment settings; Ability to delete an active log data set from the BSDS while Db2 is running; SPT01 and SYSLGRNX table spaces are converted to DSSIZE 256 GB; Improved concurrency for altering tables for DATA CAPTURE; Change REORG INDEX SHRLEVEL REFERENCE or CHANGE so the NOSYSUT1 keyword is the default; CREATE TABLESPACE uses MAXPARTITIONS 254 by default; Long names support for timeout and deadlock messages in IRLM.

- **fl500-maxpartitions-254**: At APPLCOMPAT V13R1M500 or higher an omitted MAXPARTITIONS gives 254 (previously 256 from V12R1M504); the calculated default DSSIZE is 4 G. IBM lists this as an incompatible change. Checker: `fl.behavior-change`.
- **fl500-package-owner-type**: CREATE/ALTER PROCEDURE (SQL native) and CREATE/ALTER FUNCTION (compiled SQL scalar) accept AS ROLE or AS USER on PACKAGE OWNER at APPLCOMPAT V13R1M500. Checker: `fl.applcompat-gate`.
- **fl500-pbg-to-pbr**: ALTER TABLE ... ALTER PARTITIONING TO PARTITION BY RANGE converts PBG to PBR (pending change, materialized by REORG; result uses relative page numbering). Checker: `fl.applcompat-gate`.
- **fl500-lock-timeout**: CURRENT LOCK TIMEOUT special register and SET CURRENT LOCK TIMEOUT statement. Checker: `fl.applcompat-gate`.

### FL 501 (V13R1M501, 2022-05)

Catalog level V13R1M501; enabling APAR none; source `ibm-fl501`.

IBM capability list: Allow applications to specify a deadlock resolution priority; DEADLOCK_RESOLUTION_PRIORITY global variable; Real-time statistics scalability; Collection of real-time and historical information about utility execution; Real-time statistics support for index splits.

- **fl501-deadlock-priority**: SYSIBMADM.DEADLOCK_RESOLUTION_PRIORITY built-in global variable (APPLCOMPAT V13R1M501). No CREATE-statement syntax changes. Checker: `fl.applcompat-gate`.

### FL 502 (V13R1M502, 2022-10)

Catalog level V13R1M501; enabling APAR PH47891; source `ibm-fl502`.

IBM capability list: Db2 controlled sysplex workload balancing (PH48253); Record dependencies and validity at the statement level for packages (PH47560).

- **fl502-statement-deps**: DEPLEVEL(STATEMENT) bind option; SYSPACKAGE.VALID can be 'S'. Affects routine/trigger package verification queries, not CREATE syntax.

### FL 503 (V13R1M503, 2023-02)

Catalog level V13R1M501; enabling APAR PH51469; source `ibm-fl503`.

IBM capability list: New default values in existing rows for added ROW CHANGE TIMESTAMP columns (PH51185); Accelerator-only support for more than 32K elements in an IN list (PH50756); SELECT INTO statement support for OPTIMIZE FOR n ROWS (PH50010).

- **fl503-rct-add-column**: At APPLCOMPAT V13R1M503, ALTER TABLE ADD COLUMN for a ROW CHANGE TIMESTAMP column sets SYSCOLUMNS.DEFAULTVALUE to the ALTER timestamp (incompatible change). CREATE TABLE does not set DEFAULTVALUE.

### FL 504 (V13R1M504, 2023-10)

Catalog level V13R1M504; enabling APAR PH54919; source `ibm-fl504`.

IBM capability list: Minimized impact of invalidated packages with statement-level invalidation (PH55497); Db2 trace capacity: More OP buffers (PH55622); Utility object-level history (PH55476, PH55914, PH55915, PH55916); Enhancements to SQL Data Insights (PH55212); ORDER BY support for a fullselect that invokes LISTAGG (PH55596).

- **fl504-listagg-order-by**: A fullselect that invokes LISTAGG can specify ORDER BY at APPLCOMPAT V13R1M504 (relevant to view and MQT definitions).

### FL 505 (V13R1M505, 2024-04)

Catalog level V13R1M505; enabling APAR PH59534; source `ibm-fl505`.

IBM capability list: New token-based authentication capability (PH55599); Temporal support for security-related catalog tables (PH59531); New trace destination for Db2ZAI (PH56369); INTERPRET scalar function (PH59595).

- **fl505-interpret**: INTERPRET built-in function (APPLCOMPAT V13R1M505). No CREATE-statement syntax changes. Checker: `fl.applcompat-gate`.

### FL 506 (V13R1M506, 2024-10)

Catalog level V13R1M505; enabling APAR PH62635; source `ibm-fl506`.

IBM capability list: Non-disruptive clearing of data partitions with LOAD (PH62543); Improved performance for IN-list predicates (PH58750); Db2 trace capacity: More concurrently active traces (PH59020); INSERT with multi-row VALUES clause (PH62561); Add implicitly hidden ROWID columns (PH61629); Lift certain restrictions for column masks (PH62393, PH62690).

- **fl506-hidden-rowid-add**: ALTER TABLE ADD COLUMN can define an IMPLICITLY HIDDEN ROWID column in a UTS table at APPLCOMPAT V13R1M506 (one per table); lower levels return SQLCODE -270. Checker: `fl.applcompat-gate`.
- **fl506-multirow-insert**: INSERT ... VALUES (...), (...) with multiple rows at APPLCOMPAT V13R1M506 (seed data in QA scripts). Checker: `fl.applcompat-gate`.

### FL 507 (V13R1M507, 2025-04)

Catalog level V13R1M507; enabling APAR PH64907; source `ibm-fl507`.

IBM capability list: Online conversion of table partitioning from PBR to PBG (PH64949, PH64950); Enhanced application availability for system temporal tables (PH65039); LASTUSED column support in the SYSIBM.SYSPLAN catalog table (PH64762); Referencing temporal and archive-enabled tables in the same SELECT statement (PH65133); Specify greater than 64 GB primary and secondary space allocation quantities (PH64760).

- **fl507-pbr-to-pbg**: ALTER TABLE ... ALTER PARTITIONING TO PARTITION BY GROWTH at APPLCOMPAT V13R1M507; can be stacked with PBG-to-PBR conversion in one REORG. Checker: `fl.applcompat-gate`.
- **fl507-space-quantities**: CREATE/ALTER TABLESPACE and CREATE LOB TABLESPACE accept PRIQTY up to 1 TB (1073741824 KB) and SECQTY up to 200 GB (209715200 KB) at APPLCOMPAT V13R1M507. Larger values are reduced to those caps; below this level the cap is 64 GB. Checker: `fl.applcompat-gate`.
- **fl507-systime-adjust**: SYSTIME_PERIOD_ADJUST built-in global variable for system-period temporal tables (APPLCOMPAT V13R1M507). Checker: `fl.applcompat-gate`.

### FL 508 (V13R1M508, 2025-10)

Catalog level V13R1M508; enabling APAR PH66983; source `ibm-fl508`.

IBM capability list: BLOCKING_THREADS table function enhancements (PH67082); Increasing the maximum number of active and archive logs (PH67380); Specify sort work or DGTT usage for PBG table spaces in the work file database (PH67418); Generation of UUID values (PH67353); More local applications control with Db2 profile tables (PH67138); Consistent DSSIZE records in Db2 catalog tables for UTS and LOB objects (PH67419); Rebind phase-in for SQL PL and trigger packages (PH67404); Preparation for conversion of non-UTS catalog and directory objects (PH67554).

- **fl508-for-sort-dgtt**: CREATE TABLESPACE ... FOR SORT | FOR DGTT for PBG table spaces in a work file database at APPLCOMPAT V13R1M508 (ALTER TABLESPACE support needs PH71332). SYSTABLESPACE.USAGE records it. Checker: `fl.applcompat-gate`.
- **fl508-uuid**: GENERATE_UUID, GENERATE_UUID_BINARY, VARBINARY_FORMAT and VARCHAR_FORMAT_BINARY built-in functions at APPLCOMPAT V13R1M508; the UUID generators need IBM z14 or later. Checker: `fl.applcompat-gate`.
- **fl508-catalog-dssize**: From catalog level V13R1M508, DSSIZE columns in SYSINDEXES/SYSINDEXPART are BIGINT and DSSIZE/PIECESIZE are populated consistently for UTS and LOB objects. Catalog queries that select SYSINDEXES.DSSIZE need catalog level V13R1M508.

### FL 509 (V13R1M509, 2026-04)

Catalog level V13R1M509; enabling APAR PH70028; source `ibm-fl509`.

IBM capability list: Converting Db2 catalog table spaces to UTS (PH70027); Subnet wildcard filtering for resource limit facility (RLF) (PH70071); Online ownership transfer of application objects (PH69677); Utility history for SHRLEVEL information (PH70075); New catalog columns for STMT_HASHID2 (PH70030); I/O counts in real time statistics (PH70074); Reduced false page P-lock contention in data sharing (PH69217).

- **fl509-transfer-ownership**: TRANSFER OWNERSHIP accepts function-designator, PROCEDURE and SEQUENCE at APPLCOMPAT V13R1M509. Checker: `fl.applcompat-gate`.
- **fl509-plock-hash**: Page sets created after FL 509 with DSSIZE above 64 GB (4 KB pages) or 128 GB (8 KB pages) use a new lock hash algorithm; behavioral, not syntax.

### Announced levels

- **V13R1M510**: The V13R1Mnnn APPLCOMPAT table lists CREATE TRIGGER (basic) REFERENCING UNIT_OF_RECOVERY_ID AS ur-identifier at V13R1M510. No function level 510 page was published on the review date. (`ibm-applcompat-v13`)
- **V13R1M511**: The Db2 13 deprecation table lists V13R1M511 as the level at which synonyms, hash-organized tables, non-UTS table spaces for base tables, index-controlled partitioning, basic row format, 6-byte RBA/LRSN page sets and SNA/VTAM can no longer be created or accessed. (`ibm-db2-13-deprecated`)

Treat announced levels as planning information only. Do not mark a profile with a
level that has no published function-level page.

## APPLCOMPAT gates the linter enforces

A gate applies to the APPLCOMPAT of the package that runs the statement. V13R1Mnnn
gates also need at least that function level. V12R1Mnnn gates are available at any
Db2 13 function level.

| Gate | APPLCOMPAT | Statements | Syntax or behavior | Source |
|---|---|---|---|---|
| `v12-function-level-500-ddl` | V12R1M500 | CREATE TABLESPACE, CREATE TABLE, CREATE INDEX, CREATE TRIGGER (advanced), CREATE PROCEDURE (SQL native) | CREATE TABLESPACE PAGENUM and INSERT ALGORITHM; CREATE TABLE PAGENUM, column CCSID on CHAR/GRAPHIC/CLOB/DBCLOB, PERIOD BUSINESS_TIME EXCLUSIVE/INCLUSIVE, PERIOD BUSINESS_TIME in constraints; CREATE INDEX DSSIZE; advanced triggers; WRAPPED; CONCENTRATE STATEMENTS. CREATE TABLESPACE/INDEX without USING fail with -204 if the database storage group does not exist. | `ibm-applcompat-v12` |
| `key-label` | V12R1M502 | CREATE STOGROUP, ALTER STOGROUP, CREATE TABLE, ALTER TABLE | KEY LABEL | `ibm-applcompat-v12` |
| `on-delete-add-extra-row` | V12R1M503 | ALTER TABLE | ON DELETE ADD EXTRA ROW (system-period temporal versioning) | `ibm-applcompat-v12` |
| `uts-only-creation` | V12R1M504 | CREATE TABLESPACE, CREATE TABLE, CREATE SYNONYM, CREATE AUXILIARY TABLE | Base table spaces are always PBG or PBR; synonyms and hash-organized tables cannot be created; one table per UTS; CREATE AUX TABLE needs PART when the base table is in a PBG table space. | `ibm-applcompat-incompatible` |
| `decfloat-keys` | V12R1M505 | CREATE TABLE, ALTER TABLE, CREATE INDEX | DECFLOAT columns in PRIMARY KEY, UNIQUE and index keys | `ibm-applcompat-v12` |
| `trigger-when-changed` | V12R1M505 | CREATE TRIGGER (basic), CREATE TRIGGER (advanced) | Changed WHEN search-condition | `ibm-applcompat-v12` |
| `drop-table-explicit-uts` | V12R1M506 | DROP TABLE | DROP TABLE for a table in an explicitly created UTS implicitly drops the table space; dropping an auxiliary table drops its explicit LOB table space. Below this level DROP TABLE of a PBG table fails with SQLCODE -669. | `ibm-applcompat-incompatible` |
| `procedure-or-replace-specific` | V12R1M507 | CREATE PROCEDURE (SQL native), CREATE PROCEDURE (external) | OR REPLACE; SPECIFIC | `ibm-applcompat-v12` |
| `alter-tablespace-move-table` | V12R1M508 | ALTER TABLESPACE | MOVE TABLE | `ibm-applcompat-v12` |
| `compress-algorithm` | V12R1M509 | CREATE TABLESPACE, CREATE TABLE, ALTER TABLESPACE | COMPRESS YES FIXEDLENGTH \| COMPRESS YES HUFFMAN | `ibm-applcompat-v12` |
| `ai-functions` | V13R1M500 | any SQL | AI_ANALOGY, AI_SEMANTIC_CLUSTER, AI_SIMILARITY | `ibm-applcompat-v13` |
| `alter-partitioning-range` | V13R1M500 | ALTER TABLE | ALTER PARTITIONING TO PARTITION BY RANGE | `ibm-applcompat-v13` |
| `lock-timeout` | V13R1M500 | SET CURRENT LOCK TIMEOUT, any SQL | CURRENT LOCK TIMEOUT special register | `ibm-applcompat-v13` |
| `package-owner-type` | V13R1M500 | CREATE PROCEDURE (SQL native), CREATE FUNCTION (compiled SQL scalar) | PACKAGE OWNER ... AS ROLE \| AS USER | `ibm-applcompat-v13` |
| `deadlock-priority` | V13R1M501 | SET assignment | SYSIBMADM.DEADLOCK_RESOLUTION_PRIORITY | `ibm-applcompat-v13` |
| `ai-commonality` | V13R1M504 | any SQL | AI_COMMONALITY | `ibm-applcompat-v13` |
| `interpret-function` | V13R1M505 | any SQL | INTERPRET | `ibm-applcompat-v13` |
| `hidden-rowid-add-column` | V13R1M506 | ALTER TABLE | ADD COLUMN ... ROWID ... IMPLICITLY HIDDEN | `ibm-applcompat-v13` |
| `multirow-insert` | V13R1M506 | INSERT | VALUES (row), (row), ... | `ibm-applcompat-v13` |
| `alter-partitioning-growth` | V13R1M507 | ALTER TABLE | ALTER PARTITIONING TO PARTITION BY GROWTH | `ibm-applcompat-v13` |
| `large-space-quantities` | V13R1M507 | CREATE TABLESPACE, CREATE LOB TABLESPACE, ALTER TABLESPACE | PRIQTY above 64 GB up to 1 TB; SECQTY above 64 GB up to 200 GB | `ibm-applcompat-v13` |
| `systime-period-adjust` | V13R1M507 | SET assignment | SYSTIME_PERIOD_ADJUST | `ibm-applcompat-v13` |
| `uuid-functions` | V13R1M508 | any SQL | GENERATE_UUID, GENERATE_UUID_BINARY, VARBINARY_FORMAT, VARCHAR_FORMAT_BINARY | `ibm-applcompat-v13` |
| `workfile-usage` | V13R1M508 | CREATE TABLESPACE, ALTER TABLESPACE | FOR SORT \| FOR DGTT | `ibm-applcompat-v13` |
| `transfer-ownership-routines` | V13R1M509 | TRANSFER OWNERSHIP | function-designator \| PROCEDURE procedure-name \| SEQUENCE sequence-name | `ibm-applcompat-v13` |
| `trigger-unit-of-recovery-id` | V13R1M510 | CREATE TRIGGER (basic) | REFERENCING UNIT_OF_RECOVERY_ID AS ur-identifier | `ibm-applcompat-v13` |

## Behavior changes that alter omitted-clause defaults

- **pbg-default-maxpartitions** (V13R1M500, incompatible): Omitted MAXPARTITIONS on CREATE TABLESPACE: 254 at V13R1M500 or higher; 256 (with default DSSIZE 4 G) at V12R1M504 through V13R1M100. (`ibm-applcompat-incompatible`)
- **uts-only** (V12R1M504, incompatible): Statements that create base table spaces always create PBG or PBR; non-UTS, synonyms and hash organization return errors. (`ibm-applcompat-incompatible`)
- **drop-table-uts** (V12R1M506): DROP TABLE in an explicit UTS also drops the table space; DROP of an auxiliary table also drops its explicit LOB table space. (`ibm-applcompat-incompatible`)
- **rct-add-column-default** (V13R1M503, incompatible): ALTER TABLE ADD COLUMN for ROW CHANGE TIMESTAMP records the ALTER timestamp in SYSCOLUMNS.DEFAULTVALUE. (`ibm-applcompat-incompatible`)
- **workfile-display-type** (V13R1M508, incompatible): DISPLAY DATABASE can return WF, WD or WS instead of TS for work file table spaces. (`ibm-db2-13-incompatible`)

These matter for round-trip tests: an omitted clause in source DDL and an explicit
value in product output are equivalent only at the APPLCOMPAT level that defines
that default. `tools/ddl.py diff --profile` resolves MAXPARTITIONS with the
profile's APPLCOMPAT and PAGENUM with `PAGESET_PAGENUM`.

## Deprecated function relevant to DDL

- **Absolute page numbering for PBR table spaces** — use PBR with relative page numbering (PAGENUM RELATIVE). no removal level announced. (`ibm-db2-13-deprecated`)
- **Hash-organized tables** — use ALTER TABLE ... DROP ORGANIZATION and fast index traversal. Cannot be created at APPLCOMPAT V12R1M504+; cannot be created or accessed at V13R1M511. (`ibm-db2-13-deprecated`)
- **Non-UTS table spaces for base tables (segmented, partitioned, simple) and index-controlled partitioning** — use PBG or PBR UTS. Cannot be created at APPLCOMPAT V12R1M504+; cannot be created or accessed at V13R1M511. (`ibm-db2-13-deprecated`)
- **Synonyms** — use Aliases. Cannot be created at APPLCOMPAT V12R1M504+; cannot be created or accessed at V13R1M511. (`ibm-db2-13-deprecated`)
- **External SQL procedures** — use Native SQL procedures. no removal level announced. (`ibm-db2-13-deprecated`)
- **Basic row format table spaces** — use Reordered row format. Cannot be accessed at V13R1M511. (`ibm-db2-13-deprecated`)
- **Page sets with basic 6-byte RBA or LRSN** — use Extended 10-byte RBA/LRSN. Cannot be accessed at V13R1M511. (`ibm-db2-13-deprecated`)

## Using levels in QA cases

1. Keep one baseline profile per environment, with the real FL, catalog level and
   APPLCOMPAT. A script's `lint` output includes `compatibility.minimum_applcompat`.
2. For defaults that depend on APPLCOMPAT, write companion cases: omitted clause,
   explicit value equal to the default, and an explicit non-default value.
3. Generate a lower-APPLCOMPAT variant only when the product must support it; the
   linter then rejects gated syntax for that profile.
4. Do not use deprecated features for new objects unless the case is explicitly a
   compatibility case at a lower APPLCOMPAT, and record that level.
