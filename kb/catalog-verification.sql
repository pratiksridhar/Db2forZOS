-- Db2 13 for z/OS catalog evidence for OFS CREATE DDL tests.
-- Replace every {{TOKEN}}. Run once for the source names and once for the
-- recreated names. SELECT * is intentional: catalog columns can be added at a
-- later catalog level. Compare only case-relevant general-use columns.
-- Catalog definitions: ibm-catalog-* entries in ../sources.md.

-- STOGROUP
SELECT *
  FROM SYSIBM.SYSSTOGROUP
 WHERE NAME = UPPER('{{STOGROUP}}');

SELECT *
  FROM SYSIBM.SYSVOLUMES
 WHERE SGNAME = UPPER('{{STOGROUP}}')
 ORDER BY VOLID;

-- DATABASE
SELECT *
  FROM SYSIBM.SYSDATABASE
 WHERE NAME = UPPER('{{DATABASE}}');

-- TABLESPACE and every partition/data set
SELECT *
  FROM SYSIBM.SYSTABLESPACE
 WHERE DBNAME = UPPER('{{DATABASE}}')
   AND NAME   = UPPER('{{TABLESPACE}}');

SELECT *
  FROM SYSIBM.SYSTABLEPART
 WHERE DBNAME = UPPER('{{DATABASE}}')
   AND TSNAME = UPPER('{{TABLESPACE}}')
 ORDER BY PARTITION;

-- TABLE and columns. SYSTABLES/SYSCOLUMNS also contain period and temporal
-- attributes; Db2 for z/OS does not require a separate period catalog query.
SELECT *
  FROM SYSIBM.SYSTABLES
 WHERE CREATOR = UPPER('{{SCHEMA}}')
   AND NAME    = UPPER('{{TABLE}}');

SELECT *
  FROM SYSIBM.SYSCOLUMNS
 WHERE TBCREATOR = UPPER('{{SCHEMA}}')
   AND TBNAME    = UPPER('{{TABLE}}')
 ORDER BY COLNO;

-- Check-constraint text and table-level relationships.
SELECT *
  FROM SYSIBM.SYSCHECKS
 WHERE TBOWNER = UPPER('{{SCHEMA}}')
   AND TBNAME  = UPPER('{{TABLE}}')
 ORDER BY CHECKNAME;

SELECT *
  FROM SYSIBM.SYSRELS
 WHERE CREATOR = UPPER('{{SCHEMA}}')
   AND TBNAME  = UPPER('{{TABLE}}')
 ORDER BY RELNAME;

SELECT *
  FROM SYSIBM.SYSFOREIGNKEYS
 WHERE CREATOR = UPPER('{{SCHEMA}}')
   AND TBNAME  = UPPER('{{TABLE}}')
 ORDER BY RELNAME, COLSEQ;

-- INDEX and its physical partitions.
SELECT *
  FROM SYSIBM.SYSINDEXES
 WHERE CREATOR = UPPER('{{INDEX_SCHEMA}}')
   AND NAME    = UPPER('{{INDEX}}');

SELECT *
  FROM SYSIBM.SYSINDEXPART
 WHERE IXCREATOR = UPPER('{{INDEX_SCHEMA}}')
   AND IXNAME    = UPPER('{{INDEX}}')
 ORDER BY PARTITION;

-- Ordinary index columns. Expression and XML key targets are in
-- SYSKEYTARGETS instead of, or in addition to, ordinary SYSKEYS rows.
SELECT *
  FROM SYSIBM.SYSKEYS
 WHERE IXCREATOR = UPPER('{{INDEX_SCHEMA}}')
   AND IXNAME    = UPPER('{{INDEX}}')
 ORDER BY COLSEQ;

SELECT *
  FROM SYSIBM.SYSKEYTARGETS
 WHERE IXSCHEMA = UPPER('{{INDEX_SCHEMA}}')
   AND IXNAME   = UPPER('{{INDEX}}')
 ORDER BY KEYSEQ;

-- Discover all indexes belonging to the table, including implicit enforcing,
-- LOB auxiliary, XML, and generated-name indexes. Feed each returned creator
-- and name back into the index queries above.
SELECT *
  FROM SYSIBM.SYSINDEXES
 WHERE TBCREATOR = UPPER('{{SCHEMA}}')
   AND TBNAME    = UPPER('{{TABLE}}')
 ORDER BY CREATOR, NAME;

-- Discover base, LOB, XML, and history-related table rows in the same database.
-- Narrow the result using case-specific type/relationship columns after
-- consulting the current IBM catalog-table descriptions.
SELECT *
  FROM SYSIBM.SYSTABLES
 WHERE DBNAME = UPPER('{{DATABASE}}')
 ORDER BY CREATOR, NAME;

SELECT *
  FROM SYSIBM.SYSTABLESPACE
 WHERE DBNAME = UPPER('{{DATABASE}}')
 ORDER BY NAME;

-- TRIGGER definition and every version. SQLPL is blank for a basic trigger
-- and Y for an advanced trigger. ACTIVE is blank for a basic trigger; for
-- versioned advanced triggers it identifies the active version.
SELECT *
  FROM SYSIBM.SYSTRIGGERS
 WHERE SCHEMA = UPPER('{{TRIGGER_SCHEMA}}')
   AND NAME   = UPPER('{{TRIGGER}}')
 ORDER BY VERSION;

-- The full CREATE statement is a CLOB in SYSTRIGGERS.STATEMENT. The physical
-- LOB is backed by SYSIBM.SYSTRIGGERS_STMT, but select it through the base
-- catalog row so trigger identity remains available.
SELECT SCHEMA,
       NAME,
       VERSION,
       ACTIVE,
       STATEMENT
  FROM SYSIBM.SYSTRIGGERS
 WHERE SCHEMA = UPPER('{{TRIGGER_SCHEMA}}')
   AND NAME   = UPPER('{{TRIGGER}}')
 ORDER BY VERSION;

-- Trigger package. COLLID is the trigger schema and NAME is the trigger name.
-- TYPE T identifies basic; TYPE 1 identifies advanced.
SELECT *
  FROM SYSIBM.SYSPACKAGE
 WHERE COLLID = UPPER('{{TRIGGER_SCHEMA}}')
   AND NAME   = UPPER('{{TRIGGER}}')
   AND TYPE IN ('T', '1')
 ORDER BY VERSION;

-- Definition-processing environment. This APPLCOMPAT is distinct from the
-- body APPLCOMPAT stored on the trigger package.
SELECT T.SCHEMA,
       T.NAME,
       T.VERSION,
       T.ACTIVE,
       T.ENVID,
       E.*
  FROM SYSIBM.SYSTRIGGERS T
  JOIN SYSIBM.SYSENVIRONMENT E
    ON E.ENVID = T.ENVID
 WHERE T.SCHEMA = UPPER('{{TRIGGER_SCHEMA}}')
   AND T.NAME   = UPPER('{{TRIGGER}}')
 ORDER BY T.VERSION;

-- Dependencies of every trigger-package version. DTYPE T is basic and 1 is
-- advanced. DCONTOKEN distinguishes package consistency tokens/versions.
SELECT *
  FROM SYSIBM.SYSPACKDEP
 WHERE DCOLLID = UPPER('{{TRIGGER_SCHEMA}}')
   AND DNAME   = UPPER('{{TRIGGER}}')
   AND DTYPE IN ('T', '1')
 ORDER BY DTYPE, DCONTOKEN, BTYPE, BQUALIFIER, BNAME;

-- Observable activation order for all triggers on one subject/event/time.
-- CREATEDTS is the ordering evidence; run a behavioral test as the final oracle.
SELECT TBOWNER,
       TBNAME,
       TRIGTIME,
       TRIGEVENT,
       GRANULARITY,
       SCHEMA,
       NAME,
       VERSION,
       ACTIVE,
       CREATEDTS
  FROM SYSIBM.SYSTRIGGERS
 WHERE TBOWNER  = UPPER('{{SUBJECT_SCHEMA}}')
   AND TBNAME   = UPPER('{{SUBJECT_TABLE_OR_VIEW}}')
   AND TRIGTIME = '{{TRIGTIME_CODE}}'
   AND TRIGEVENT = '{{TRIGEVENT_CODE}}'
 ORDER BY CREATEDTS, SCHEMA, NAME, VERSION;

-- PROCEDURE definition and every version. ROUTINETYPE P identifies a stored
-- procedure. ORIGIN N is native SQL; ORIGIN E is external or external SQL.
SELECT *
  FROM SYSIBM.SYSROUTINES
 WHERE SCHEMA      = UPPER('{{PROCEDURE_SCHEMA}}')
   AND NAME        = UPPER('{{PROCEDURE_NAME}}')
   AND ROUTINETYPE = 'P'
 ORDER BY VERSION, SPECIFICNAME;

-- Native SQL source text, including its body. TEXT is a zero-length string for
-- non-native procedure rows, so preserve that distinction in comparisons.
SELECT SCHEMA,
       NAME,
       SPECIFICNAME,
       ORIGIN,
       VERSION,
       ACTIVE,
       TEXT
  FROM SYSIBM.SYSROUTINES
 WHERE SCHEMA      = UPPER('{{PROCEDURE_SCHEMA}}')
   AND NAME        = UPPER('{{PROCEDURE_NAME}}')
   AND ROUTINETYPE = 'P'
 ORDER BY VERSION, SPECIFICNAME;

-- Ordered scalar/table parameter metadata. ROWTYPE P/O/B means IN/OUT/INOUT.
SELECT *
  FROM SYSIBM.SYSPARMS
 WHERE SCHEMA      = UPPER('{{PROCEDURE_SCHEMA}}')
   AND NAME        = UPPER('{{PROCEDURE_NAME}}')
   AND ROUTINETYPE = 'P'
 ORDER BY SPECIFICNAME, ORDINAL;

-- Native SQL procedure package. Collection/name/version are procedure
-- schema/name/version, and TYPE N identifies a native SQL routine package.
SELECT *
  FROM SYSIBM.SYSPACKAGE
 WHERE COLLID = UPPER('{{PROCEDURE_SCHEMA}}')
   AND NAME   = UPPER('{{PROCEDURE_NAME}}')
   AND TYPE   = 'N'
 ORDER BY VERSION;

-- Dependencies of every native SQL procedure package version.
SELECT *
  FROM SYSIBM.SYSPACKDEP
 WHERE DCOLLID = UPPER('{{PROCEDURE_SCHEMA}}')
   AND DNAME   = UPPER('{{PROCEDURE_NAME}}')
   AND DTYPE   = 'N'
 ORDER BY DCONTOKEN, BTYPE, BQUALIFIER, BNAME;

-- Explicit EXECUTE privileges are recorded by specific routine name.
SELECT *
  FROM SYSIBM.SYSROUTINEAUTH
 WHERE SCHEMA       = UPPER('{{PROCEDURE_SCHEMA}}')
   AND SPECIFICNAME = UPPER('{{PROCEDURE_SPECIFIC_NAME}}')
   AND ROUTINETYPE  = 'P'
 ORDER BY GRANTEETYPE, GRANTEE;
