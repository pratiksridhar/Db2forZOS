-- Db2 for z/OS CREATE VIEW LOCAL CHECK OPTION template.
-- Agent scaffold: promote after CREATE VIEW is normalized from IBM documentation.
-- Replace every {{TOKEN}}.

CREATE VIEW {{VIEW_SCHEMA}}.{{VIEW_NAME}}
  (ID, STATUS, AMOUNT)
AS
  SELECT ID, STATUS, AMOUNT
    FROM {{BASE_SCHEMA}}.{{BASE_TABLE}}
   WHERE STATUS <> 'X'
WITH LOCAL CHECK OPTION
!
