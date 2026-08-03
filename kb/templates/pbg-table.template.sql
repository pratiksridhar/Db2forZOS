-- Implicit PBG table-space case created by CREATE TABLE.
-- IBM source IDs: ibm-create-table, ibm-implicit-tablespace,
-- ibm-create-tablespace, ibm-create-index.
-- Required tokens: DATABASE, SCHEMA, TABLE, INDEX_SCHEMA, INDEX, TABLE_BP,
-- INDEX_BP. The database must already exist and Huffman compression must be
-- enabled for this environment.

CREATE TABLE {{SCHEMA}}.{{TABLE}}
  (
    EVENT_ID BIGINT NOT NULL,
    TENANT_ID VARCHAR(8) NOT NULL,
    EVENT_STATUS CHAR(1) NOT NULL DEFAULT 'N',
    PAYLOAD VARCHAR(512),
    CREATED_AT TIMESTAMP(6) NOT NULL WITH DEFAULT,
    CONSTRAINT {{TABLE}}_CK1
      CHECK (EVENT_STATUS IN ('N', 'P', 'C'))
  )
  IN DATABASE {{DATABASE}}
  PARTITION BY SIZE EVERY 4 G
  CCSID EBCDIC
  LOGGED
  COMPRESS YES HUFFMAN
  BUFFERPOOL {{TABLE_BP}}
  MEMBER CLUSTER
  TRACKMOD YES
  APPEND NO;

-- A PBG table can have only a nonpartitioned index. PARTITIONED is therefore
-- deliberately absent and belongs in this template's negative companion.
CREATE INDEX {{INDEX_SCHEMA}}.{{INDEX}}
  ON {{SCHEMA}}.{{TABLE}}
    (TENANT_ID ASC, CREATED_AT DESC)
  NOT PADDED
  FREEPAGE 0
  PCTFREE 10
  COMPRESS NO
  INCLUDE NULL KEYS
  BUFFERPOOL {{INDEX_BP}}
  CLOSE YES
  COPY NO;

COMMIT;
