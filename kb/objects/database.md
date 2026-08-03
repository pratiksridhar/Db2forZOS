# DATABASE

## Concept

A Db2 for z/OS database groups table spaces and the indexes on their tables for administration, authorization, commands, and recovery. Its storage group, buffer pools, and encoding scheme are child defaults; a table space or index can override the relevant default.

IBM recommends grouping related objects while keeping the number of tables in a database reasonably small for concurrency and control-block considerations. Treat that as design guidance, not CREATE syntax. Sources: `ibm-database-concept`, `ibm-create-database`.

## Preferred syntax summary

```text
CREATE DATABASE <database-name>
  [ BUFFERPOOL <bpname> ]
  [ INDEXBP <bpname> ]
  [ AS WORKFILE [ FOR <member-name> ] ]
  [ STOGROUP <stogroup-name> ]
  [ CCSID { ASCII | EBCDIC | UNICODE } ]
```

The optional clauses can be supplied in the order allowed by IBM's repeatable syntax path, but the same clause cannot occur more than once. Omission of `STOGROUP` means `SYSDEFLT`. Source: `ibm-create-database`.

## Clause reference

| Clause | Semantics, limits, and defaults |
|---|---|
| `<database-name>` | Required unqualified identifier of up to 8 characters. It must be unique, cannot start with `DSNDB`, and cannot have the reserved implicit form `DSN` plus exactly five digits. `DSNDB07` is a special allowed work-file name in the documented data-sharing case. |
| `BUFFERPOOL <bpname>` | Default buffer pool for child table spaces. Omission uses the `TBSBPOOL` subsystem parameter. A work-file database cannot specify an 8 KB or 16 KB buffer pool. |
| `INDEXBP <bpname>` | Default buffer pool for child indexes; 4/8/16/32 KB pools are allowed for a regular database. Omission uses the installation default for user indexes (whose IBM-supplied default is `BP0`). |
| `AS WORKFILE` | Creates a work-file database. Valid only in data sharing; one work-file database per Db2 subsystem/member. Used for work files, temporary tables, and sensitive static scrollable cursors. Requires `SYSADM`. |
| `FOR <member-name>` | Associates the work-file database with a data-sharing member. Only valid in data sharing and under `AS WORKFILE`; omission selects the executing member. |
| `STOGROUP <name>` | Default storage group for child table/index spaces. The omitted default is `SYSDEFLT`. |
| `CCSID` | Default encoding scheme for data in child table spaces: `ASCII`, `EBCDIC`, or `UNICODE`. Omission uses the installation `DEF ENCODING SCHEME`. Not valid with `AS WORKFILE`. |

## Default propagation

```text
DATABASE.STOGROUP  -> TABLESPACE/INDEX storage default
DATABASE.BUFFERPOOL -> TABLESPACE page size default
DATABASE.INDEXBP    -> INDEX buffer-pool default
DATABASE.CCSID      -> TABLESPACE/TABLE encoding default
```

The generated DDL for a child can explicitly spell an inherited value without changing semantics. A robust OFS comparison records both source text and effective catalog value.

## Work-file database restrictions

`AS WORKFILE` is not a decorative subtype. Test it as a separate grammar context:

- data sharing is required;
- `CCSID` is forbidden;
- `BUFFERPOOL` cannot name an 8 KB or 16 KB pool;
- only one work-file database can be created for each subsystem/member;
- `FOR` is meaningful only in data sharing;
- PUBLIC receives an implicit, non-revocable `CREATETAB` privilege for declared temporary tables;
- child table spaces have their own work-file restrictions described in [tablespace.md](tablespace.md).

## Authorization surface

Regular creation accepts the documented database-creation privileges/authorities (`CREATEDBA`, `CREATEDBC`, `SYSADM`, `SYSCTRL`, System DBADM, or eligible installation `SYSOPR`). Work-file creation specifically requires `SYSADM`. The creator can acquire DBADM or DBCTRL depending on whether creation occurred under `CREATEDBA` or only `CREATEDBC`; that ownership effect is a catalog/authorization case, not a syntax case.

## High-value OFS cases

| Family | Positive variants | Negative/boundary companions |
|---|---|---|
| Name | 1 and 8 characters; delimited identifier | 9 characters; `DSNDB...`; `DSN00001`; duplicate |
| Defaults | all clauses omitted; every default explicitly named | duplicate clause; nonexistent/inactive child resource |
| Encoding | ASCII, EBCDIC, UNICODE, omitted | invalid value; `CCSID` with `AS WORKFILE` |
| Buffer pools | each page-size family for regular DB | work-file DB with 8/16 KB table BP |
| Storage | omitted (`SYSDEFLT`); explicit custom group | nonexistent group; missing USE privilege exercised by child allocation |
| Work file | implicit executing member; explicit `FOR member` | non-data-sharing subsystem; second work-file DB; `FOR` outside work-file form |
| Clause order | valid permutations and IBM-preferred order | repeated clause in otherwise valid statement |

## Catalog assertions

`SYSIBM.SYSDATABASE` records one row per database, including type, data-sharing member, storage-group and buffer-pool defaults, and encoding scheme.

```sql
SELECT *
  FROM SYSIBM.SYSDATABASE
 WHERE NAME = UPPER('{{DATABASE}}');
```

For default inheritance tests, query the child `SYSTABLESPACE` or `SYSINDEXES` row as well; the database row alone proves only the configured default.
