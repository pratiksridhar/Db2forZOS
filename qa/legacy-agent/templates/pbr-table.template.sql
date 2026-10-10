-- PBR with relative page numbering plus three distinct index roles.
-- IBM source IDs: ibm-create-tablespace, ibm-create-table,
-- ibm-create-index, ibm-partitioned-indexes.
-- Required tokens: DATABASE, TABLESPACE, STOGROUP, SCHEMA, TABLE,
-- INDEX_SCHEMA, PART_INDEX, DPSI_INDEX, NPI_INDEX, TABLE_BP, INDEX_BP.
-- The database and storage group must already exist.

CREATE TABLESPACE {{TABLESPACE}}
  IN {{DATABASE}}
  BUFFERPOOL {{TABLE_BP}}
  NUMPARTS 4
  PAGENUM RELATIVE
  DSSIZE 8 G
  SEGSIZE 32
  CCSID EBCDIC
  COMPRESS YES FIXEDLENGTH
  USING STOGROUP {{STOGROUP}}
    PRIQTY -1
    SECQTY -1
    ERASE NO;

CREATE TABLE {{SCHEMA}}.{{TABLE}}
  (
    EVENT_DATE DATE NOT NULL,
    EVENT_ID BIGINT NOT NULL,
    TENANT_ID CHAR(8) NOT NULL,
    EVENT_STATUS CHAR(1) NOT NULL DEFAULT 'N',
    PAYLOAD VARCHAR(512),
    CONSTRAINT {{TABLE}}_CK1
      CHECK (EVENT_STATUS IN ('N', 'P', 'C'))
  )
  IN {{DATABASE}}.{{TABLESPACE}}
  PARTITION BY RANGE (EVENT_DATE ASC)
    (
      PARTITION 1 ENDING AT ('2026-03-31'),
      PARTITION 2 ENDING AT ('2026-06-30'),
      PARTITION 3 ENDING AT ('2026-09-30'),
      PARTITION 4 ENDING AT (MAXVALUE)
    )
  AUDIT NONE
  DATA CAPTURE NONE
  APPEND NO;

-- Partitioning index: the leading key matches the table partitioning key.
CREATE INDEX {{INDEX_SCHEMA}}.{{PART_INDEX}}
  ON {{SCHEMA}}.{{TABLE}}
    (EVENT_DATE ASC, EVENT_ID ASC)
  CLUSTER
  PARTITIONED
  BUFFERPOOL {{INDEX_BP}}
  CLOSE YES;

-- DPSI: physically partitioned, but its leading key is not the partition key.
CREATE INDEX {{INDEX_SCHEMA}}.{{DPSI_INDEX}}
  ON {{SCHEMA}}.{{TABLE}}
    (EVENT_STATUS ASC)
  PARTITIONED
  BUFFERPOOL {{INDEX_BP}}
  CLOSE YES;

-- NPI: one nonpartitioned physical index spans all table partitions.
CREATE INDEX {{INDEX_SCHEMA}}.{{NPI_INDEX}}
  ON {{SCHEMA}}.{{TABLE}}
    (TENANT_ID ASC, EVENT_ID ASC)
  BUFFERPOOL {{INDEX_BP}}
  CLOSE YES;

COMMIT;
