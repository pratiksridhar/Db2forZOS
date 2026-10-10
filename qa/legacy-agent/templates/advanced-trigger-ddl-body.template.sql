-- IBM Db2 13 for z/OS advanced-trigger DDL-body template.
-- Replace every {{TOKEN}}. Configure ! as the outer terminator.
-- Use an isolated fixture: the first activation creates fixed-name objects and
-- another activation will fail unless exact-name cleanup has run.
-- CREATE TABLE is permitted here only without LOB or XML columns.
-- CREATE INDEX and CREATE VIEW require AFTER or INSTEAD OF activation.

CREATE TRIGGER {{TRIGGER_SCHEMA}}.{{DDL_TRIGGER}}
  AFTER INSERT
  ON {{SUBJECT_SCHEMA}}.{{SUBJECT_TABLE}}
  FOR EACH STATEMENT
  APPLCOMPAT {{BODY_APPLCOMPAT}}
  BEGIN ATOMIC
    CREATE TABLE {{CREATED_SCHEMA}}.{{CREATED_TABLE}}
      (ID INTEGER NOT NULL,
       TEST_VALUE VARCHAR(100),
       CREATED_AT TIMESTAMP NOT NULL WITH DEFAULT)
      IN {{DATABASE}}.{{TABLESPACE}};

    CREATE UNIQUE INDEX {{CREATED_SCHEMA}}.{{CREATED_INDEX}}
      ON {{CREATED_SCHEMA}}.{{CREATED_TABLE}} (ID ASC);

    CREATE VIEW {{CREATED_SCHEMA}}.{{CREATED_VIEW}}
      (ID, TEST_VALUE)
      AS SELECT ID, TEST_VALUE
           FROM {{CREATED_SCHEMA}}.{{CREATED_TABLE}};
  END!

-- Focused negative companions should replace the body with exactly one of:
--   CREATE STOGROUP ...
--   CREATE DATABASE ...
--   CREATE TABLESPACE ...
--   CREATE TRIGGER ...
-- The first three are excluded matrix rows. CREATE TRIGGER is not listed in
-- SQL-procedure-statement at all, so it is likewise not a trigger-body form.

-- Cleanup order after collecting evidence:
--   DROP VIEW  {{CREATED_SCHEMA}}.{{CREATED_VIEW}};
--   DROP INDEX {{CREATED_SCHEMA}}.{{CREATED_INDEX}};
--   DROP TABLE {{CREATED_SCHEMA}}.{{CREATED_TABLE}};
