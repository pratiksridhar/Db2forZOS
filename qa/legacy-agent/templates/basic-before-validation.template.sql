-- IBM Db2 13 for z/OS basic BEFORE trigger validation template.
-- Replace every {{TOKEN}}. Configure ! as the outer terminator.
-- This is intentionally basic: MODE DB2SQL is required and SQL PL declarations are unavailable.

CREATE TRIGGER {{TRIGGER_SCHEMA}}.{{TRIGGER_NAME}}
  NO CASCADE BEFORE UPDATE OF STATUS
  ON {{SUBJECT_SCHEMA}}.{{SUBJECT_TABLE}}
  REFERENCING OLD AS O NEW AS N
  FOR EACH ROW
  MODE DB2SQL
  WHEN (N.STATUS NOT IN ('A', 'I', 'X'))
  SIGNAL SQLSTATE '75001'
    SET MESSAGE_TEXT = 'invalid generated status transition'!
