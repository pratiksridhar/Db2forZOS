# STOGROUP

## Concept

A Db2 storage group describes the storage from which Db2 can allocate and manage table-space and index-space data sets. Its definition names an ICF catalog and describes volume selection directly or through SMS classes. It is distinct from a DFSMS storage group even when SMS participates in allocation.

The catalog representation is split across `SYSIBM.SYSSTOGROUP` (one row per group) and `SYSIBM.SYSVOLUMES` (one row per volume entry). Source cluster: `ibm-stogroup-concept`, `ibm-create-stogroup`, `ibm-catalog-sysstogroup`, `ibm-catalog-sysvolumes`.

## Preferred syntax summary

```text
CREATE STOGROUP <stogroup-name>
  [ VOLUMES ( <volume-id> [, ...] )
  | VOLUMES ( '*' [, ...] ) ]
  VCAT <catalog-name>
  [ DATACLAS <dc-name> ]
  [ MGMTCLAS <mc-name> ]
  [ STORCLAS <sc-name> ]
  [ KEY LABEL <key-label-name> | NO KEY LABEL ]
```

`VCAT` is required. `VOLUMES` is conditionally required: omit it only when SMS controls selection through at least one of `DATACLAS`, `MGMTCLAS`, or `STORCLAS`. Source: `ibm-create-stogroup`.

## Clause reference

| Clause | Semantics, limits, and defaults |
|---|---|
| `<stogroup-name>` | Required unqualified identifier; up to 128 characters; must be unique at the server. |
| `VOLUMES(<volume-id>,...)` | Each serial is an identifier or string constant of at most 6 characters. The same ID cannot repeat. Required for non-SMS allocation. |
| `VOLUMES('*',...)` | Non-specific volume selection recognized only by SMS. Do not mix `'*'` with specific IDs in one storage group. |
| `VCAT <catalog-name>` | ICF catalog in which Db2-created VSAM linear data sets are cataloged. Use a single-level catalog/alias name; the documented installation constraint is 1–8 characters. Avoid an alias shared in a way that lets different Db2 subsystems derive colliding data-set names. |
| `DATACLAS` | SMS data class, 1–8 characters; at most once. |
| `MGMTCLAS` | SMS management class, 1–8 characters; at most once. |
| `STORCLAS` | SMS storage class, 1–8 characters; at most once. |
| `KEY LABEL` | Default encryption key label for data sets allocated through the group. It must exist in ICSF, must not be an archived decryption-only key, and the Db2 address-space identity must have RACF access. |
| `NO KEY LABEL` | Records that no key label is supplied at storage-group level. |

## Rules that are easy to miss

- Db2 does not validate volume/class existence, device type, or SMS activation during `CREATE STOGROUP`. A syntactically successful case can fail only when a child object allocates a data set.
- A group must use either specific volume IDs or non-specific IDs; mixing them is invalid.
- All volumes used for one data set and its extensions must have compatible device types.
- IBM documents no statement-level limit on listed volumes, but Db2 can manage at most 133 for a storage group. The z/OS per-data-set volume limit is a separate, potentially changing restriction.
- To use an encryption key label, page-set VSAM data sets need an SMS data class with extended-format capability.
- A table-level key label is supplied for all of that table's associated base, LOB, XML, index, and clone spaces ahead of the storage-group label. RACF data-set profiles and other DFSMS inputs can still override the label Db2 supplies.
- `SYSDEFLT` is installed as the default storage group; it is not created by application test DDL.

## Authorization surface

The privilege set needs `CREATESG`, `SYSADM`, `SYSCTRL`, or eligible installation `SYSOPR`. Ownership differs for embedded and dynamically prepared SQL. Authorization failures should be separate from syntax tests because they do not validate OFS clause generation.

## High-value OFS cases

| Family | Positive variants | Negative/boundary companions |
|---|---|---|
| Name | ordinary and 128-character identifier | duplicate name; identifier beyond supported length |
| Volume selection | explicit single/multiple volumes; `VOLUMES('*')`; SMS-class-only omission | duplicate volume; mixed specific and `'*'`; no volumes and no SMS class |
| VCAT | valid local alias | missing `VCAT`; invalid/unavailable catalog exposed at allocation time |
| SMS classes | each independently; all three; classes plus `VOLUMES('*')` | duplicate class clause; 0/9-character class names |
| Encryption | omitted; `NO KEY LABEL`; `KEY LABEL` | inaccessible, missing, archived, or non-EF-compatible key setup |
| Deferred operational validation | create group, then allocate table space/index | class or volume accepted by DDL but rejected by DFSMS during allocation |

For every defaultable choice, pair an omitted-clause case with an explicitly spelled equivalent. OFS should preserve semantics even if it chooses a different textual form.

## Catalog assertions

After creation, verify the group row and its volume rows. Do not treat catalog success alone as proof that the named volumes/classes are operational; force a child allocation for that assertion.

```sql
SELECT *
  FROM SYSIBM.SYSSTOGROUP
 WHERE NAME = UPPER('{{STOGROUP}}');

SELECT *
  FROM SYSIBM.SYSVOLUMES
 WHERE SGNAME = UPPER('{{STOGROUP}}')
 ORDER BY VOLID;
```

See [catalog-verification.sql](../test-design/catalog-verification.sql) for the consolidated query set.
