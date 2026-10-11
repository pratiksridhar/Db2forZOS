# Environment and profiles

DDL legality, effective defaults and generated text depend on more than the Db2
release. Without the target's real values, an omitted clause is not a stable
expected value, and a negative test can fail for the wrong reason. This page is
the single checklist; other documents link here instead of restating it.

## Record before execution

- Db2 release and activated function level; see [function levels](../kb/function-levels.md)
  for syntax gates and defaults that change with APPLCOMPAT
- package/application `APPLCOMPAT`; for advanced triggers, record definition-processing
  and body/package values separately
- procedure kind; for native SQL, routine/package version and body `APPLCOMPAT`;
  for external procedures, program, package, WLM and external-security context
- `CURRENT RULES`
- data sharing versus non-data-sharing
- subsystem parameters, especially `DPSEGSZ`, `IMPDSSIZE`, `IMPTKMOD`, `IMPTSCMP`,
  `IMPDSDEF`, `PADIX`, `PAGESET_PAGENUM`, `PCTFREE_UPD`, `DEFAULT_INSERT_ALGORITHM`,
  `TABLE_COL_NAME_EXPANSION`, `TBSBPLOB` and compression defaults
- `MIXED` (field MIXED DATA on panel DSNTIPF, `YES` or `NO`) and the default encoding
  scheme: with a table's encoding they decide whether an omitted `FOR subtype DATA`
  means SBCS or MIXED, which product-generated DDL often states explicitly
- storage group, active buffer pools and their sizes
- SMS/DFSMS capabilities, extended-format/extended-addressability settings and
  available storage classes
- authorities: database, table-space and table creation, `REFERENCES`, and `USE`
  of storage groups and buffer pools
- for product tests: administration-product version, extraction options and scope

Ask for missing values. Continue offline work with an explicitly unverified profile
rather than guessing.

## Profiles

A profile is the JSON form of this checklist, read by `ddl.py lint|diff|bundle`
and `qa.py build`. [qa/profiles/example.json](../qa/profiles/example.json) is
**unverified**, including its illustrative storage group `QASTG`. It permits
offline design only.

For real work, copy it into the git-ignored `local-profiles/` and record the actual
subsystem values there. Never put credentials into this repository. Both activated
function level and APPLCOMPAT are checked against model gates. Current models
require `CURRENT RULES DB2`; database-fixture models also require recorded active
4 KB pools `BP0` through `BP49`. A verified profile requires verification evidence,
but generated cases still start in `design`.

## SQL processor

Record the client's outer terminator and verify its formatting and CCSID
conversion before body-text tests. Trigger and procedure bundles use `@`. For SPUFI,
SQLFORMAT SQLPL retains comments and line structure. A 72-column source limit is a
client/workload constraint (`lint --max-line 72`), not a universal Db2 limit.
Generated text metrics count UTF-8 artifacts, not target-CCSID bytes.
