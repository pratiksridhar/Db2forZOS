-- IBM Db2 13 for z/OS basic-trigger template.
-- Replace every {{TOKEN}}. Configure the SQL processor to use ! as the outer
-- terminator so the semicolons inside BEGIN ATOMIC do not end CREATE TRIGGER.
-- Prerequisites: subject, audit, and aggregate tables already exist locally.

CREATE TRIGGER {{TRIGGER_SCHEMA}}.{{BASIC_TRIGGER}}
  AFTER UPDATE OF {{WATCH_COLUMN}}
  ON {{SUBJECT_SCHEMA}}.{{SUBJECT_TABLE}}
  REFERENCING OLD ROW AS OLDROW NEW ROW AS NEWROW
  FOR EACH ROW
  MODE DB2SQL
  WHEN ({{WHEN_CONDITION_USING_OLDROW_AND_NEWROW}})
  BEGIN ATOMIC
    INSERT INTO {{AUDIT_SCHEMA}}.{{AUDIT_TABLE}}
      ({{AUDIT_KEY_COLUMN}}, {{AUDIT_OLD_COLUMN}}, {{AUDIT_NEW_COLUMN}})
      VALUES
      (NEWROW.{{SUBJECT_KEY_COLUMN}},
       OLDROW.{{WATCH_COLUMN}},
       NEWROW.{{WATCH_COLUMN}});

    UPDATE {{SUMMARY_SCHEMA}}.{{SUMMARY_TABLE}}
       SET {{SUMMARY_COUNT_COLUMN}} = {{SUMMARY_COUNT_COLUMN}} + 1
     WHERE {{SUMMARY_KEY_COLUMN}} = NEWROW.{{SUBJECT_KEY_COLUMN}};
  END!

-- Verification targets:
--   SYSIBM.SYSTRIGGERS.SQLPL is blank.
--   SYSIBM.SYSPACKAGE.TYPE = 'T' for the trigger package.
--   Trigger text retains MODE DB2SQL, transition names, WHEN, and statement order.
