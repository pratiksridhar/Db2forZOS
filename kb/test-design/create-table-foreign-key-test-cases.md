# CREATE TABLE foreign-key DDL test suite

## Objective

Validate Db2 13 for z/OS `CREATE TABLE` DDL that defines ordinary referential constraints, and validate DDL emitted by RC/Query or Object Framework Services (OFS) for the same objects.

Every table that this suite creates must reside in the single database named by `{{DATABASE}}`. Normal cases use `IN DATABASE {{DATABASE}}`, so Db2 implicitly creates one PBG universal table space per table inside that database. The explicit-table-space dependency case also creates its table space inside `{{DATABASE}}`.

The suite treats catalog state and data behavior as the semantic oracle. Text comparison alone is insufficient because a generator can legally make an implicit default explicit.

## KB traceability

This design is derived from the repository's [table chapter](../objects/table.md), [coverage model](coverage-model.md), normalized KB, and [catalog verification SQL](catalog-verification.sql).

| KB clause or rule | Test implication |
|---|---|
| `table.foreign-key` | Cover table-level and column-level syntax, primary and unique parent keys, compatible column descriptions, 64-column maximum, delete rules, and enforcement choices. |
| `table.foreign-key-current-rules` | Run omitted-delete-rule cases under both `CURRENT RULES = 'DB2'` and `CURRENT RULES = 'STD'`. |
| `table.set-null-requires-nullable` | Pair a successful nullable `SET NULL` case with a failing all-`NOT NULL` case. |
| `table.constraint-index-enforcement` | Use implicit table spaces for complete parent definitions, and separately prove that an explicit-space parent without its enforcing unique index cannot be referenced. |
| `table.catalog-multirow-verification` | Verify `SYSTABLES`, every relationship row in `SYSRELS`, every key-column row in `SYSFOREIGNKEYS`, and the parent enforcing index. |

Authoritative source IDs are `ibm-create-table`, `ibm-implicit-index`, `ibm-catalog-systables`, `ibm-catalog-syscolumns`, `ibm-catalog-sysrels`, `ibm-catalog-sysforeignkeys`, and `ibm-catalog-sysindexes`; they resolve in [sources.md](../sources.md).

Useful KB queries:

```text
python3 tools/kb.py show table foreign-key
python3 tools/kb.py show table foreign-key-current-rules
python3 tools/kb.py show table set-null-requires-nullable
python3 tools/kb.py show table constraint-index-enforcement
python3 tools/kb.py show table catalog-multirow-verification
```

## Scope and exclusions

In scope:

- `CREATE TABLE` with single-column and composite foreign keys;
- parent primary keys and parent unique keys;
- table-level and column-level spellings;
- `RESTRICT`, `NO ACTION`, `CASCADE`, and `SET NULL`;
- defaulted versus explicit delete rules and enforcement;
- nullable, informational, duplicate, boundary, dependency, authorization, and malformed definitions;
- DDL generation, clean-name recreation, and semantic comparison through OFS.

Application-period temporal referential constraints are intentionally a separate suite. They add `PERIOD BUSINESS_TIME`, no-overlap index requirements, temporal containment semantics, and cycle restrictions that would obscure the ordinary foreign-key coverage here. A direct self-reference in a dynamically executed `CREATE TABLE` is covered as a negative case; the positive self-referencing path requires a later `ALTER TABLE` or schema-processor orchestration.

## Environment and tokens

Record these values with every run:

- Db2 release, activated function level, and `APPLCOMPAT`;
- `CURRENT RULES` at statement execution time;
- authorization ID and SQLID;
- active table and index buffer pools;
- database default storage group and encoding scheme;
- product/OFS build and DDL-generation options.

Replace these tokens before execution:

| Token | Meaning |
|---|---|
| `{{DATABASE}}` | The only database allowed to contain suite tables; use a valid Db2 database name. |
| `{{SCHEMA}}` | Schema that owns the standard fixtures and test tables. |
| `{{STOGROUP}}` | Existing storage group available for implicit and explicit table spaces. |
| `{{TABLE_BP}}` | Active table-space buffer pool. |
| `{{INDEX_BP}}` | Active index buffer pool. |
| `{{LIMITED_SCHEMA}}` | Schema used only by the authorization-negative case. |
| `{{LIMITED_AUTHID}}` | Authorization ID that can create a table in the database but lacks `REFERENCES` or `ALTER` privilege on the parent. |

Do not use a shared production database. Resolve every token to an exact test identifier before running cleanup.

## Execution protocol

1. Run each case from a clean state. A positive case must not already exist; a negative case must leave no table behind.
2. Capture SQLCODE, SQLSTATE, message text, SQL warnings, authorization ID, SQLID, and `CURRENT RULES` for every statement.
3. Commit successful DDL before asking OFS to discover an object.
4. Treat expected-error DML as an individual probe. A runner that stops on negative SQLCODE must restart at the next probe rather than skipping the rest of the case.
5. Use unique data values per case. Roll back DML probes or delete their rows before moving to another case.
6. For successful DDL, verify catalog rows before testing data behavior.
7. For failed DDL, verify that no row exists in `SYSIBM.SYSTABLES` for the attempted table.
8. Drop dependent tables before parents. Never wildcard-drop a shared schema or database.

SQLCODEs explicitly cited below are stable primary oracles where the failure is unambiguous. For other DDL-negative cases, first assert the documented failure reason and SQLSTATE class, then baseline the exact SQLCODE for the target subsystem and execution path.

## Single-database fixture

Create `{{DATABASE}}` only when the harness owns the whole disposable database. Otherwise, point the token at a pre-created test database with equivalent defaults.

```sql
CREATE DATABASE {{DATABASE}}
  STOGROUP {{STOGROUP}}
  BUFFERPOOL {{TABLE_BP}}
  INDEXBP {{INDEX_BP}}
  CCSID EBCDIC;

COMMIT;
```

Create the reusable parents. Because each statement uses `IN DATABASE`, Db2 creates the table space and required primary/unique indexes implicitly.

```sql
SET CURRENT RULES = 'DB2';

CREATE TABLE {{SCHEMA}}.FKPMAIN
  (
    PARENT_ID     INTEGER     NOT NULL,
    ALT_CODE      CHAR(8)     NOT NULL,
    REGION_CODE   CHAR(2)     NOT NULL,
    BUSINESS_CODE CHAR(8)     NOT NULL,
    PAIR_A        SMALLINT    NOT NULL,
    PAIR_B        SMALLINT    NOT NULL,
    PARENT_NAME   VARCHAR(64),
    CONSTRAINT PK_FKPMAIN
      PRIMARY KEY (PARENT_ID),
    CONSTRAINT UQ_FKPMAIN_ALT
      UNIQUE (ALT_CODE),
    CONSTRAINT UQ_FKPMAIN_BUS
      UNIQUE (REGION_CODE, BUSINESS_CODE),
    CONSTRAINT UQ_FKPMAIN_PAIR
      UNIQUE (PAIR_A, PAIR_B)
  )
  IN DATABASE {{DATABASE}};

CREATE TABLE {{SCHEMA}}.FKPAUX
  (
    AUX_ID   SMALLINT    NOT NULL,
    AUX_NAME VARCHAR(32) NOT NULL,
    CONSTRAINT PK_FKPAUX
      PRIMARY KEY (AUX_ID)
  )
  IN DATABASE {{DATABASE}};

CREATE TABLE {{SCHEMA}}.FKPNOKE
  (
    NONKEY_ID INTEGER NOT NULL,
    LABEL     VARCHAR(32)
  )
  IN DATABASE {{DATABASE}};

CREATE TABLE {{SCHEMA}}.FKPUONL
  (
    UNIQUE_ID INTEGER NOT NULL,
    LABEL     VARCHAR(32),
    CONSTRAINT UQ_FKPUONL
      UNIQUE (UNIQUE_ID)
  )
  IN DATABASE {{DATABASE}};

CREATE TABLE {{SCHEMA}}.FKP255
  (
    KEY255 CHAR(255) NOT NULL,
    CONSTRAINT PK_FKP255
      PRIMARY KEY (KEY255)
  )
  IN DATABASE {{DATABASE}};

INSERT INTO {{SCHEMA}}.FKPMAIN
  (PARENT_ID, ALT_CODE, REGION_CODE, BUSINESS_CODE,
   PAIR_A, PAIR_B, PARENT_NAME)
VALUES
  (1001, 'ALT00001', 'NA', 'BUS00001', 11, 21, 'PARENT 1001');

INSERT INTO {{SCHEMA}}.FKPMAIN
  (PARENT_ID, ALT_CODE, REGION_CODE, BUSINESS_CODE,
   PAIR_A, PAIR_B, PARENT_NAME)
VALUES
  (1002, 'ALT00002', 'EU', 'BUS00002', 12, 22, 'PARENT 1002');

INSERT INTO {{SCHEMA}}.FKPAUX (AUX_ID, AUX_NAME)
VALUES (10, 'AUXILIARY 10');

COMMIT;
```

Fixture acceptance criteria:

- Every fixture table has `DBNAME = UPPER('{{DATABASE}}')` in `SYSIBM.SYSTABLES`.
- `FKPMAIN`, `FKPAUX`, `FKPUONL`, and `FKP255` are definition-complete.
- The implicit enforcing indexes exist in `SYSIBM.SYSINDEXES`.
- The two fixture rows in `FKPMAIN` and one row in `FKPAUX` are committed.

## Common catalog oracle

Run this for every successfully created child, replacing `{{CHILD_TABLE}}`.

```sql
SELECT C.DBNAME AS CHILD_DB,
       P.DBNAME AS PARENT_DB,
       R.CREATOR,
       R.TBNAME,
       R.RELNAME,
       R.REFTBCREATOR,
       R.REFTBNAME,
       R.COLCOUNT,
       R.DELETERULE,
       R.ENFORCED,
       R.CHECKEXISTINGDATA,
       R.IXOWNER,
       R.IXNAME
  FROM SYSIBM.SYSRELS R
  JOIN SYSIBM.SYSTABLES C
    ON C.CREATOR = R.CREATOR
   AND C.NAME = R.TBNAME
  JOIN SYSIBM.SYSTABLES P
    ON P.CREATOR = R.REFTBCREATOR
   AND P.NAME = R.REFTBNAME
 WHERE R.CREATOR = UPPER('{{SCHEMA}}')
   AND R.TBNAME = UPPER('{{CHILD_TABLE}}')
 ORDER BY R.RELNAME;

SELECT RELNAME, COLNAME, COLNO, COLSEQ
  FROM SYSIBM.SYSFOREIGNKEYS
 WHERE CREATOR = UPPER('{{SCHEMA}}')
   AND TBNAME = UPPER('{{CHILD_TABLE}}')
 ORDER BY RELNAME, COLSEQ;
```

For every returned relationship:

- `CHILD_DB` and `PARENT_DB` must both equal `UPPER('{{DATABASE}}')`;
- the parent schema/table, column count, delete-rule code, and enforcement flag must match the case;
- `SYSFOREIGNKEYS.COLSEQ` must preserve the declared composite-key order;
- the parent key must have its expected enforcing index;
- generated identifiers, timestamps, OBIDs, and implicit table-space names are not compared literally unless the case targets them.

Delete-rule catalog codes are `R` = `RESTRICT`, `A` = `NO ACTION`, `C` = `CASCADE`, and `N` = `SET NULL`.

## Case inventory

| ID | Category | Primary variation | Expected CREATE result |
|---|---|---|---|
| DB2Z13-TABLE-FK-001 | positive | Named table-level FK to primary key | Success |
| DB2Z13-TABLE-FK-002 | default | Parent column list and delete rule omitted under Db2 rules | Success; `RESTRICT` |
| DB2Z13-TABLE-FK-003 | default | Delete rule omitted under standard rules | Success; `NO ACTION` |
| DB2Z13-TABLE-FK-004 | positive | Column-level `REFERENCES` | Success |
| DB2Z13-TABLE-FK-005 | positive | Composite FK to non-primary unique key | Success |
| DB2Z13-TABLE-FK-006 | interaction | Two FKs from one child | Success; two relationships |
| DB2Z13-TABLE-FK-007 | interaction | `ON DELETE CASCADE` | Success; child deletion propagates |
| DB2Z13-TABLE-FK-008 | interaction | Nullable FK with `ON DELETE SET NULL` | Success; FK becomes null |
| DB2Z13-TABLE-FK-009 | interaction | Informational `NOT ENFORCED` FK | Success; orphan insert allowed |
| DB2Z13-TABLE-FK-010 | interaction | Duplicate ordinary FK specification | Success with warning; duplicate ignored |
| DB2Z13-TABLE-FK-011 | boundary | Nonnullable FK length exactly 255 | Success |
| DB2Z13-TABLE-FK-012 | default | Constraint name omitted | Success; generated name |
| DB2Z13-TABLE-FK-013 | negative | Parent table does not exist | Failure |
| DB2Z13-TABLE-FK-014 | negative | Parent list omitted but parent has no primary key | Failure, normally `-538` / `42830` |
| DB2Z13-TABLE-FK-015 | negative | Referenced parent columns are not unique | Failure, normally `-538` / `42830` |
| DB2Z13-TABLE-FK-016 | negative | Child and parent key counts differ | Failure, normally `-538` / `42830` |
| DB2Z13-TABLE-FK-017 | negative | Composite parent columns are reversed | Failure, normally `-538` / `42830` |
| DB2Z13-TABLE-FK-018 | negative | Numeric data types differ | Failure, normally `-538` / `42830` |
| DB2Z13-TABLE-FK-019 | negative | Character length attributes differ | Failure, normally `-538` / `42830` |
| DB2Z13-TABLE-FK-020 | negative | `SET NULL` but every FK column is `NOT NULL` | Failure |
| DB2Z13-TABLE-FK-021 | negative | Prohibited `DECFLOAT` FK column | Failure |
| DB2Z13-TABLE-FK-022 | boundary | Nullable FK length 255 exceeds `255 - n` | Failure |
| DB2Z13-TABLE-FK-023 | negative | Same child column repeated in one FK | Failure |
| DB2Z13-TABLE-FK-024 | negative | Constraint name duplicated within table | Failure |
| DB2Z13-TABLE-FK-025 | negative | Direct self-reference in dynamic `CREATE TABLE` | Failure |
| DB2Z13-TABLE-FK-026 | dependency | Parent primary index is missing | Child failure `-540` / `57001` |
| DB2Z13-TABLE-FK-027 | negative | Creator lacks parent `REFERENCES`/`ALTER` privilege | Authorization failure |
| DB2Z13-TABLE-FK-028 | boundary | 64-column composite FK | Success; 64 catalog key rows |
| DB2Z13-TABLE-FK-029 | boundary | 65-column composite FK | Failure |
| DB2Z13-TABLE-FK-030 | round_trip | OFS generation and clean-name recreation | Semantic equivalence |

## Detailed cases

### DB2Z13-TABLE-FK-001 — named table-level FK to a primary key

```sql
CREATE TABLE {{SCHEMA}}.FKC001
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    PAYLOAD   VARCHAR(64),
    CONSTRAINT PK_FKC001
      PRIMARY KEY (CHILD_ID),
    CONSTRAINT FK_FKC001_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
      ON DELETE RESTRICT
      ENFORCED
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Expected:

- CREATE succeeds with SQLCODE 0.
- One `SYSRELS` row names `FK_FKC001_P`, the parent is `FKPMAIN`, `COLCOUNT = 1`, `DELETERULE = 'R'`, and `ENFORCED = 'Y'`.
- One `SYSFOREIGNKEYS` row names `PARENT_ID` with `COLSEQ = 1`.
- A valid child insert succeeds; an orphan insert fails with SQLCODE `-530`, SQLSTATE `23503`.
- Deleting a referenced parent fails with SQLCODE `-532`, SQLSTATE `23504`.

```sql
INSERT INTO {{SCHEMA}}.FKC001 VALUES (1, 1001, 'VALID');
INSERT INTO {{SCHEMA}}.FKC001 VALUES (2, 9999, 'EXPECT -530');
DELETE FROM {{SCHEMA}}.FKPMAIN WHERE PARENT_ID = 1001;
ROLLBACK;
```

### DB2Z13-TABLE-FK-002 — omitted parent list and delete rule under Db2 rules

```sql
SET CURRENT RULES = 'DB2';

CREATE TABLE {{SCHEMA}}.FKC002
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT PK_FKC002
      PRIMARY KEY (CHILD_ID),
    CONSTRAINT FK_FKC002_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Expected: CREATE succeeds, omission selects the parent's primary key, and `SYSRELS.DELETERULE = 'R'`.

### DB2Z13-TABLE-FK-003 — omitted delete rule under standard rules

```sql
SET CURRENT RULES = 'STD';

CREATE TABLE {{SCHEMA}}.FKC003
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT PK_FKC003
      PRIMARY KEY (CHILD_ID),
    CONSTRAINT FK_FKC003_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
  )
  IN DATABASE {{DATABASE}};

COMMIT;
SET CURRENT RULES = 'DB2';
```

Expected: CREATE succeeds and `SYSRELS.DELETERULE = 'A'`. Confirm that the harness restores `CURRENT RULES` even if the case fails.

### DB2Z13-TABLE-FK-004 — column-level REFERENCES

```sql
CREATE TABLE {{SCHEMA}}.FKC004
  (
    CHILD_ID INTEGER NOT NULL
      CONSTRAINT PK_FKC004 PRIMARY KEY,
    PARENT_ID INTEGER
      CONSTRAINT FK_FKC004_P
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
      ON DELETE NO ACTION,
    PAYLOAD VARCHAR(64)
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Expected: CREATE succeeds; one relationship exists with `DELETERULE = 'A'`; a null `PARENT_ID` is accepted; a nonnull orphan fails with `-530` / `23503`.

### DB2Z13-TABLE-FK-005 — composite FK to a non-primary unique key

```sql
CREATE TABLE {{SCHEMA}}.FKC005
  (
    CHILD_ID      INTEGER NOT NULL,
    REGION_CODE   CHAR(2) NOT NULL,
    BUSINESS_CODE CHAR(8) NOT NULL,
    CONSTRAINT PK_FKC005
      PRIMARY KEY (CHILD_ID),
    CONSTRAINT FK_FKC005_BUS
      FOREIGN KEY (REGION_CODE, BUSINESS_CODE)
      REFERENCES {{SCHEMA}}.FKPMAIN
        (REGION_CODE, BUSINESS_CODE)
      ON DELETE RESTRICT
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Expected:

- CREATE succeeds and the relationship identifies the non-primary unique parent key.
- `COLCOUNT = 2`; `SYSFOREIGNKEYS` returns `REGION_CODE` at sequence 1 and `BUSINESS_CODE` at sequence 2.
- `('NA', 'BUS00001')` succeeds; an otherwise valid row with `('NA', 'MISSING1')` fails with `-530` / `23503`.

### DB2Z13-TABLE-FK-006 — two parent relationships from one child

```sql
CREATE TABLE {{SCHEMA}}.FKC006
  (
    CHILD_ID  INTEGER  NOT NULL,
    PARENT_ID INTEGER  NOT NULL,
    AUX_ID    SMALLINT NOT NULL,
    CONSTRAINT PK_FKC006
      PRIMARY KEY (CHILD_ID),
    CONSTRAINT FK_FKC006_MAIN
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
      ON DELETE RESTRICT,
    CONSTRAINT FK_FKC006_AUX
      FOREIGN KEY (AUX_ID)
      REFERENCES {{SCHEMA}}.FKPAUX (AUX_ID)
      ON DELETE RESTRICT
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Expected: CREATE succeeds; two `SYSRELS` rows and two `SYSFOREIGNKEYS` rows exist. Test four DML partitions: both keys valid, only main invalid, only auxiliary invalid, and both invalid. Only the first succeeds.

### DB2Z13-TABLE-FK-007 — cascading delete

```sql
CREATE TABLE {{SCHEMA}}.FKC007
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT PK_FKC007
      PRIMARY KEY (CHILD_ID),
    CONSTRAINT FK_FKC007_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
      ON DELETE CASCADE
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Probe with a case-owned parent value:

```sql
INSERT INTO {{SCHEMA}}.FKPMAIN
  (PARENT_ID, ALT_CODE, REGION_CODE, BUSINESS_CODE,
   PAIR_A, PAIR_B, PARENT_NAME)
VALUES
  (7001, 'ALT07001', 'C7', 'BUS07001', 71, 72, 'CASCADE PARENT');

INSERT INTO {{SCHEMA}}.FKC007 VALUES (7001, 7001);
DELETE FROM {{SCHEMA}}.FKPMAIN WHERE PARENT_ID = 7001;

SELECT COUNT(*) AS EXPECT_ZERO
  FROM {{SCHEMA}}.FKC007
 WHERE CHILD_ID = 7001;

ROLLBACK;
```

Expected: `DELETERULE = 'C'`; parent deletion succeeds; the child count is zero.

### DB2Z13-TABLE-FK-008 — SET NULL and nullable semantics

```sql
CREATE TABLE {{SCHEMA}}.FKC008
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER,
    CONSTRAINT PK_FKC008
      PRIMARY KEY (CHILD_ID),
    CONSTRAINT FK_FKC008_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
      ON DELETE SET NULL
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Expected:

- `DELETERULE = 'N'` and `ENFORCED = 'Y'`.
- An initially null FK succeeds and represents no parent relationship.
- After inserting a case-owned parent and child, deleting the parent succeeds and changes the child's `PARENT_ID` to null without deleting the child.

### DB2Z13-TABLE-FK-009 — informational relationship

```sql
CREATE TABLE {{SCHEMA}}.FKC009
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT PK_FKC009
      PRIMARY KEY (CHILD_ID),
    CONSTRAINT FK_FKC009_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
      ON DELETE RESTRICT
      NOT ENFORCED ENABLE QUERY OPTIMIZATION
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Expected: CREATE succeeds; `SYSRELS.ENFORCED = 'N'` and `CHECKEXISTINGDATA = 'N'`; inserting `(1, 9999)` succeeds. Record this as an informational constraint, not as proof of referential integrity.

### DB2Z13-TABLE-FK-010 — duplicate relationship warning

```sql
CREATE TABLE {{SCHEMA}}.FKC010
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT PK_FKC010
      PRIMARY KEY (CHILD_ID),
    CONSTRAINT FK_FKC010_A
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
      ON DELETE RESTRICT,
    CONSTRAINT FK_FKC010_B
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
      ON DELETE RESTRICT
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Expected: statement succeeds with a warning; the duplicate ordinary relationship is ignored. Assert exactly one effective `SYSRELS` row for this child and preserve the warning as test evidence. Do not require a particular generated/internal identity for the ignored definition.

### DB2Z13-TABLE-FK-011 — maximum nonnullable FK length

```sql
CREATE TABLE {{SCHEMA}}.FKC011
  (
    CHILD_ID INTEGER   NOT NULL,
    KEY255   CHAR(255) NOT NULL,
    CONSTRAINT PK_FKC011
      PRIMARY KEY (CHILD_ID),
    CONSTRAINT FK_FKC011_255
      FOREIGN KEY (KEY255)
      REFERENCES {{SCHEMA}}.FKP255 (KEY255)
      ON DELETE RESTRICT
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Expected: CREATE succeeds at the foreign-key length boundary of 255 bytes when no FK column is nullable.

### DB2Z13-TABLE-FK-012 — generated constraint name

```sql
CREATE TABLE {{SCHEMA}}.FKC012
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT PK_FKC012
      PRIMARY KEY (CHILD_ID),
    FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
      ON DELETE RESTRICT
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

Expected: CREATE succeeds and `SYSRELS.RELNAME` is nonblank. Capture, but do not hard-code, the generated name. In an OFS round trip, either preserve the generated name or apply the recorded deterministic name map.

### DB2Z13-TABLE-FK-013 — missing parent table

```sql
SET CURRENT RULES = 'DB2';

CREATE TABLE {{SCHEMA}}.FKC013
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT FK_FKC013_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKP404 (PARENT_ID)
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails because the parent does not exist; under Db2 rules the normal diagnostic is `-204` / `42704`. Verify that `FKC013` was not created.

### DB2Z13-TABLE-FK-014 — omitted parent list without a primary key

```sql
CREATE TABLE {{SCHEMA}}.FKC014
  (
    CHILD_ID INTEGER NOT NULL,
    UNIQUE_ID INTEGER NOT NULL,
    CONSTRAINT FK_FKC014_P
      FOREIGN KEY (UNIQUE_ID)
      REFERENCES {{SCHEMA}}.FKPUONL
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails, normally with `-538` / `42830`. `FKPUONL` has a unique key but no primary key, and an omitted parent column list selects only a primary key.

### DB2Z13-TABLE-FK-015 — referenced parent columns are not a parent key

```sql
CREATE TABLE {{SCHEMA}}.FKC015
  (
    CHILD_ID INTEGER NOT NULL,
    NONKEY_ID INTEGER NOT NULL,
    CONSTRAINT FK_FKC015_P
      FOREIGN KEY (NONKEY_ID)
      REFERENCES {{SCHEMA}}.FKPNOKE (NONKEY_ID)
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails, normally with `-538` / `42830`, because the nominated parent column is neither a primary nor a unique key.

### DB2Z13-TABLE-FK-016 — mismatched key counts

```sql
CREATE TABLE {{SCHEMA}}.FKC016
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    EXTRA_ID  INTEGER NOT NULL,
    CONSTRAINT FK_FKC016_P
      FOREIGN KEY (PARENT_ID, EXTRA_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails, normally with `-538` / `42830`; the child and nominated parent keys have different column counts.

### DB2Z13-TABLE-FK-017 — composite parent key in the wrong order

```sql
CREATE TABLE {{SCHEMA}}.FKC017
  (
    CHILD_ID      INTEGER NOT NULL,
    BUSINESS_CODE CHAR(8) NOT NULL,
    REGION_CODE   CHAR(2) NOT NULL,
    CONSTRAINT FK_FKC017_P
      FOREIGN KEY (BUSINESS_CODE, REGION_CODE)
      REFERENCES {{SCHEMA}}.FKPMAIN
        (BUSINESS_CODE, REGION_CODE)
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails, normally with `-538` / `42830`; the parent has a unique key in `(REGION_CODE, BUSINESS_CODE)` order, not the reversed order.

### DB2Z13-TABLE-FK-018 — incompatible numeric type

```sql
CREATE TABLE {{SCHEMA}}.FKC018
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID BIGINT  NOT NULL,
    CONSTRAINT FK_FKC018_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails, normally with `-538` / `42830`; `BIGINT` and `INTEGER` are not identical column descriptions for this relationship.

### DB2Z13-TABLE-FK-019 — incompatible character length

```sql
CREATE TABLE {{SCHEMA}}.FKC019
  (
    CHILD_ID INTEGER NOT NULL,
    ALT_CODE CHAR(7) NOT NULL,
    CONSTRAINT FK_FKC019_P
      FOREIGN KEY (ALT_CODE)
      REFERENCES {{SCHEMA}}.FKPMAIN (ALT_CODE)
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails, normally with `-538` / `42830`; the child length is 7 while the parent key length is 8.

### DB2Z13-TABLE-FK-020 — SET NULL without a nullable FK column

```sql
CREATE TABLE {{SCHEMA}}.FKC020
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT FK_FKC020_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
      ON DELETE SET NULL
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails because `SET NULL` requires at least one nullable foreign-key column. Verify no `SYSTABLES` or `SYSRELS` residue.

### DB2Z13-TABLE-FK-021 — prohibited DECFLOAT key column

```sql
CREATE TABLE {{SCHEMA}}.FKC021
  (
    CHILD_ID INTEGER NOT NULL,
    BAD_KEY  DECFLOAT(16) NOT NULL,
    CONSTRAINT FK_FKC021_P
      FOREIGN KEY (BAD_KEY)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails. The primary assertion is rejection of `DECFLOAT` as a foreign-key column; do not misclassify the result merely as a numeric coercion failure.

### DB2Z13-TABLE-FK-022 — nullable key exceeds the reduced length limit

```sql
CREATE TABLE {{SCHEMA}}.FKC022
  (
    CHILD_ID INTEGER NOT NULL,
    KEY255   CHAR(255),
    CONSTRAINT FK_FKC022_255
      FOREIGN KEY (KEY255)
      REFERENCES {{SCHEMA}}.FKP255 (KEY255)
      ON DELETE RESTRICT
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails. One nullable FK column reduces the permitted sum from 255 to `255 - 1 = 254`, while this key has length 255. Compare with successful boundary case FK-011.

### DB2Z13-TABLE-FK-023 — duplicate child column in one FK

```sql
CREATE TABLE {{SCHEMA}}.FKC023
  (
    CHILD_ID INTEGER  NOT NULL,
    PAIR_A   SMALLINT NOT NULL,
    CONSTRAINT FK_FKC023_P
      FOREIGN KEY (PAIR_A, PAIR_A)
      REFERENCES {{SCHEMA}}.FKPMAIN (PAIR_A, PAIR_B)
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails because the same child column is identified twice in one foreign key.

### DB2Z13-TABLE-FK-024 — duplicate constraint name

```sql
CREATE TABLE {{SCHEMA}}.FKC024
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT DUP_FKC024
      CHECK (CHILD_ID > 0),
    CONSTRAINT DUP_FKC024
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
  )
  IN DATABASE {{DATABASE}};
```

Expected: CREATE fails because a referential, check, primary-key, or unique-key constraint name must be unique within the table definition.

### DB2Z13-TABLE-FK-025 — direct self-reference in dynamic CREATE TABLE

```sql
CREATE TABLE {{SCHEMA}}.FKC025
  (
    NODE_ID        INTEGER NOT NULL,
    PARENT_NODE_ID INTEGER,
    CONSTRAINT PK_FKC025
      PRIMARY KEY (NODE_ID),
    CONSTRAINT FK_FKC025_SELF
      FOREIGN KEY (PARENT_NODE_ID)
      REFERENCES {{SCHEMA}}.FKC025 (NODE_ID)
      ON DELETE NO ACTION
  )
  IN DATABASE {{DATABASE}};
```

Expected: ordinary dynamic CREATE fails because the referenced parent must already exist and cannot be the table currently being created. Record schema-processor behavior separately; do not convert this negative case into an `ALTER TABLE` test silently.

### DB2Z13-TABLE-FK-026 — parent lacks its required primary index

This dependency case deliberately uses an explicit table space. All objects remain in `{{DATABASE}}`.

```sql
CREATE TABLESPACE FKTINC
  IN {{DATABASE}}
  BUFFERPOOL {{TABLE_BP}}
  MAXPARTITIONS 1
  SEGSIZE 32
  USING STOGROUP {{STOGROUP}}
    PRIQTY -1
    SECQTY -1;

CREATE TABLE {{SCHEMA}}.FKPINC
  (
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT PK_FKPINC
      PRIMARY KEY (PARENT_ID)
  )
  IN {{DATABASE}}.FKTINC;

CREATE TABLE {{SCHEMA}}.FKC026
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT FK_FKC026_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPINC (PARENT_ID)
  )
  IN DATABASE {{DATABASE}};
```

Expected:

- The parent CREATE succeeds but its definition is incomplete because ordinary dynamic SQL against an explicit table space does not implicitly create the primary index.
- The child CREATE fails with `-540` / `57001`.
- After the negative assertion, create a matching unique primary index in a companion run and prove that the child CREATE then succeeds. Capture the enforcing index identity.

```sql
CREATE UNIQUE INDEX {{SCHEMA}}.IXFKPINC
  ON {{SCHEMA}}.FKPINC (PARENT_ID ASC)
  USING STOGROUP {{STOGROUP}}
  BUFFERPOOL {{INDEX_BP}};

CREATE TABLE {{SCHEMA}}.FKC026
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT FK_FKC026_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPINC (PARENT_ID)
  )
  IN DATABASE {{DATABASE}};

COMMIT;
```

The companion child CREATE must now succeed, and `SYSRELS` must identify the completed parent key.

### DB2Z13-TABLE-FK-027 — missing REFERENCES privilege

Execute this statement as `{{LIMITED_AUTHID}}`, using `{{LIMITED_SCHEMA}}`, after the harness grants only the privileges needed to create an implicit-space table in `{{DATABASE}}`. The ID must have neither `ALTER` nor applicable `REFERENCES` privilege on `{{SCHEMA}}.FKPMAIN`.

```sql
CREATE TABLE {{LIMITED_SCHEMA}}.FKC027
  (
    CHILD_ID  INTEGER NOT NULL,
    PARENT_ID INTEGER NOT NULL,
    CONSTRAINT FK_FKC027_P
      FOREIGN KEY (PARENT_ID)
      REFERENCES {{SCHEMA}}.FKPMAIN (PARENT_ID)
  )
  IN DATABASE {{DATABASE}};
```

Expected: authorization failure, normally SQLSTATE `42501`; no child table remains. Then grant the exact required parent privilege and rerun as a positive companion. Both the limited-schema child and the parent must still report `DBNAME = UPPER('{{DATABASE}}')`.

### DB2Z13-TABLE-FK-028 — 64-column maximum

Generate two tables in `{{DATABASE}}`:

- `FKP064` has columns `K01` through `K64`, each `SMALLINT NOT NULL`, and a primary key containing all 64 columns in numeric order.
- `FKC028` has `CHILD_ID INTEGER NOT NULL`, matching `K01` through `K64`, and a foreign key containing all 64 columns that references the 64-column parent key in the same order.

Use mechanical generation in the harness to avoid transcription defects. The expanded DDL—not an ellipsis—is the executed and retained artifact.

Expected:

- Both CREATE statements succeed.
- `SYSRELS.COLCOUNT = 64`.
- `SYSFOREIGNKEYS` returns exactly 64 rows with continuous `COLSEQ` values 1 through 64.
- A row matching all 64 values succeeds; changing only `K64` produces `-530` / `23503`.
- OFS output preserves every column exactly once and in order.

### DB2Z13-TABLE-FK-029 — one column above the maximum

Reuse the valid 64-column `FKP064` parent from FK-028. Mechanically generate `FKC029` with `K01` through `K65` as `SMALLINT NOT NULL`, and attempt this child definition:

```text
FOREIGN KEY (K01, K02, ... fully expand through K65)
  REFERENCES {{SCHEMA}}.FKP064
```

The omitted parent list resolves to the 64-column primary key. Retain the fully expanded child DDL artifact; the executed SQL must not contain an ellipsis. Place `FKC029` with `IN DATABASE {{DATABASE}}`.

Expected: the child CREATE is rejected and no `FKC029` table or relationship row exists. Because a valid parent primary/unique key is itself limited to 64 columns, this is a coupled ceiling/count case: it proves that 65 columns cannot form a relationship, but it cannot provide an otherwise-valid 65-column parent key. Keep FK-028 as the clean accepted-boundary companion.

### DB2Z13-TABLE-FK-030 — OFS round trip

Use at least these source cases:

- FK-001 for explicit `RESTRICT` and `ENFORCED`;
- FK-002 and FK-003 for environment-dependent omission;
- FK-005 for composite order and a non-primary parent key;
- FK-007 and FK-008 for mutating delete rules;
- FK-009 for `NOT ENFORCED`;
- FK-012 for a generated constraint name;
- FK-028 for the column-count boundary.

Procedure:

1. Commit the source parent and child definitions.
2. Ask OFS to generate the child plus every required parent and enforcing index dependency.
3. Save the exact output and generation options as immutable artifacts.
4. Apply a deterministic map to every table, constraint, index, and implicit-object name. Keep all recreated tables in `{{DATABASE}}`.
5. Execute the generated DDL under the clean names.
6. Compare source and recreated `SYSTABLES`, `SYSCOLUMNS`, `SYSRELS`, `SYSFOREIGNKEYS`, and parent-enforcing-index semantics.
7. Repeat the relevant valid/orphan/delete DML probes against the recreated objects.

Required semantic assertions:

- parents are created before dependent tables;
- both source and target table rows identify `{{DATABASE}}`;
- parent schema/table and nominated key are preserved;
- `COLCOUNT` and every `COLSEQ` are preserved;
- `DELETERULE`, `ENFORCED`, and `CHECKEXISTINGDATA` are preserved;
- `SET NULL` nullability and `CASCADE` behavior are preserved;
- generated names are either preserved or covered by the name map;
- no source-only or recreated-only relationship remains.

Required textual assertions:

- explicit `CASCADE`, `SET NULL`, and `NOT ENFORCED` clauses are not lost;
- every composite column appears once and in the correct order;
- parent identifiers are correctly qualified;
- no unresolved `{{TOKEN}}` remains;
- a default omitted in source may be explicit in output only when catalog and DML semantics remain equivalent under the recorded `CURRENT RULES`.

## Suite-level containment check

Run after setup, after each case batch, and before cleanup:

```sql
SELECT CREATOR, NAME, DBNAME, TSNAME
  FROM SYSIBM.SYSTABLES
 WHERE (CREATOR = UPPER('{{SCHEMA}}')
        OR CREATOR = UPPER('{{LIMITED_SCHEMA}}'))
   AND (NAME LIKE 'FKP%' OR NAME LIKE 'FKC%')
 ORDER BY CREATOR, NAME;
```

Fail the suite immediately if any returned table has a `DBNAME` other than `UPPER('{{DATABASE}}')`.

## Cleanup

Drop successfully created children and recreated OFS children first, then child-side explicit indexes if any, then parents, then explicit table spaces. Use exact resolved names. A database drop is allowed only when the harness created and exclusively owns `{{DATABASE}}`.

Minimum fixture cleanup order:

```text
all FKC* dependent tables
FKPINC, then table space FKTINC
FKP064 when created
FKP255
FKPUONL
FKPNOKE
FKPAUX
FKPMAIN
{{DATABASE}} only if suite-owned
```

Before dropping anything, preserve negative diagnostics, OFS-generated SQL, catalog snapshots, DML probe results, and environment metadata. Cleanup success does not replace a missing test artifact.
