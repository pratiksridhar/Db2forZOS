# Db2 for z/OS object DDL knowledge base

This repository is a test-authoring knowledge base for validating DDL that RC/Query and Object Framework Services (OFS) generate for these Db2 objects:

- storage groups (`STOGROUP`)
- databases
- table spaces, including base/work-file table spaces and the separate LOB table-space form
- tables
- indexes
- triggers, including basic and advanced definitions plus their complete body-statement matrix

The baseline is **IBM Db2 13 for z/OS documentation**, reviewed on **2026-07-19**. The knowledge base records function-level and application-compatibility gates at the rule where they matter; it does not assume that every Db2 13 subsystem has activated the latest function level.

Only official IBM documentation is used. Every normalized rule has one or more source IDs that resolve in [kb/sources.md](kb/sources.md).

## Why the knowledge base has two layers

IBM syntax diagrams are the authority, but diagrams alone are a poor test inventory. Important behavior also appears in clause descriptions and notes: defaults controlled by subsystem parameters, mutually exclusive clauses, implicit object creation, function-level gates, and rules that depend on table-space type.

This KB therefore stores the same subject in two complementary forms:

1. **Reference chapters** explain concepts, grammar, defaults, restrictions, and high-yield OFS test ideas for a person.
2. **Normalized JSON** indexes clauses and cross-clause rules for scripts, searches, coverage tracking, and future case generation.

The JSON is deliberately a normalized test model, not a replacement SQL parser. When it and IBM documentation disagree, the IBM statement reference wins and the KB should be corrected.

## Repository map

| Path | Purpose |
|---|---|
| [kb/object-model.md](kb/object-model.md) | Physical/logical hierarchy, dependency order, and implicit creation paths |
| [kb/syntax-notation.md](kb/syntax-notation.md) | Notation used in the hand-written grammar summaries |
| [kb/objects/stogroup.md](kb/objects/stogroup.md) | `CREATE STOGROUP` concepts and syntax |
| [kb/objects/database.md](kb/objects/database.md) | `CREATE DATABASE` concepts and syntax |
| [kb/objects/tablespace.md](kb/objects/tablespace.md) | PBG, PBR, work-file, LOB, and implicit table spaces |
| [kb/objects/table.md](kb/objects/table.md) | `CREATE TABLE` definition forms, columns, constraints, periods, and physical clauses |
| [kb/objects/index.md](kb/objects/index.md) | Ordinary, unique, expression, XML, temporal, partitioned, DPSI, and NPI indexes |
| [kb/objects/trigger.md](kb/objects/trigger.md) | Basic/advanced `CREATE TRIGGER`, transition data, options, restrictions, packages, versions, and verification |
| [kb/trigger-body-statements.md](kb/trigger-body-statements.md) | Direct-body, SQL control, 35 supported nested, and 34 excluded nested statement families with compact syntax |
| [kb/test-design/coverage-model.md](kb/test-design/coverage-model.md) | A systematic model for deriving positive, negative, boundary, default, and round-trip cases |
| [kb/test-design/catalog-verification.sql](kb/test-design/catalog-verification.sql) | Catalog queries for semantic validation after DDL execution |
| [kb/templates/object-stack.template.sql](kb/templates/object-stack.template.sql) | Parameterized explicit storage-group-to-index object stack |
| [kb/templates/pbg-table.template.sql](kb/templates/pbg-table.template.sql) | PBG-focused table and index template |
| [kb/templates/pbr-table.template.sql](kb/templates/pbr-table.template.sql) | PBR/RPN-focused table and index template |
| [kb/templates/basic-trigger.template.sql](kb/templates/basic-trigger.template.sql) | Multi-statement basic-trigger template |
| [kb/templates/advanced-trigger.template.sql](kb/templates/advanced-trigger.template.sql) | SQL PL variables, handler, condition, diagnostics, and DML template |
| [kb/templates/advanced-trigger-ddl-body.template.sql](kb/templates/advanced-trigger-ddl-body.template.sql) | Advanced compound body with supported `CREATE TABLE`, `CREATE INDEX`, and `CREATE VIEW` |
| [kb/data/db2z13-create-ddl.json](kb/data/db2z13-create-ddl.json) | Machine-readable clause, rule, dimension, and source index |
| [kb/data/db2z13-trigger-body-statements.json](kb/data/db2z13-trigger-body-statements.json) | Machine-readable trigger statement syntax and support matrix |
| [kb/data/test-case.schema.json](kb/data/test-case.schema.json) | JSON Schema for persistent OFS test-case records |
| [kb/test-design/sample-case.json](kb/test-design/sample-case.json) | Example test-case record |
| [tools/kb.py](tools/kb.py) | Dependency-free command-line query tool |

## Quick use

Read an object chapter before composing a case, then query the normalized inventory:

```text
python3 tools/kb.py objects
python3 tools/kb.py clauses tablespace
python3 tools/kb.py show tablespace maxpartitions
python3 tools/kb.py rules table --tag implicit
python3 tools/kb.py dimensions index
python3 tools/kb.py clauses trigger
python3 tools/kb.py show trigger advanced-ddl-subset
python3 tools/kb.py trigger-statements basic
python3 tools/kb.py trigger-statements nested --activation BEFORE
python3 tools/kb.py trigger-statements ddl
python3 tools/kb.py trigger-statements controls --statement return
python3 tools/kb.py trigger-statements syntax --statement create-table --json
python3 tools/kb.py search "WITHOUT OVERLAPS"
python3 tools/kb.py sources
```

To create a durable test:

1. Choose one primary semantic variation from [the coverage model](kb/test-design/coverage-model.md).
2. Add boundary, explicit-default/omitted-default, and illegal-pair companions.
3. Copy the closest SQL template and replace every `{{TOKEN}}`.
4. Record the subsystem context, source IDs, expected outcome, and OFS comparison policy in a JSON case that conforms to the test-case schema.
5. Execute the source DDL, generate DDL through OFS, recreate the object under a clean name, and compare catalog semantics with the supplied queries.

## Verify the KB itself

The repository checks normalized IDs, official-source references, internal links, requested object coverage, template presence, the sample case shape, and command-line queries:

```text
python3 -m unittest discover -s tests -v
python3 -m json.tool kb/data/db2z13-create-ddl.json > /dev/null
python3 -m json.tool kb/data/db2z13-trigger-body-statements.json > /dev/null
python3 -m json.tool kb/data/test-case.schema.json > /dev/null
python3 -m json.tool kb/test-design/sample-case.json > /dev/null
```

These are repository checks, not a substitute for preparing the SQL on a Db2 subsystem. The parameterized templates intentionally require environment values and must be executed under the recorded function level, `APPLCOMPAT`, authority, buffer-pool, and storage context before they become product test evidence.

## Version and environment discipline

DDL legality and generated text can depend on more than the product release. At minimum, capture:

- Db2 release and activated function level
- package/application `APPLCOMPAT`; for advanced triggers, record definition-processing and body/package values separately
- `CURRENT RULES`
- data sharing versus non-data-sharing
- relevant subsystem parameters, especially `DPSEGSZ`, `IMPDSSIZE`, `IMPTKMOD`, `IMPTSCMP`, `PADIX`, `PAGESET_PAGENUM`, `PCTFREE_UPD`, `DEFAULT_INSERT_ALGORITHM`, and compression defaults
- active buffer-pool sizes
- SMS/DFSMS capabilities, extended-format/extended-addressability settings, and available storage classes

Without this context, an omitted clause is not a stable expected value and a negative test might fail for the wrong reason.

## Scope boundary

The core chapters cover the requested object set and the syntax that directly changes their definitions. The following related statements are identified where they affect the six objects but are not independently modeled as top-level object chapters in this edition: `ALTER`, `DROP`, `CREATE AUXILIARY TABLE`, `CREATE GLOBAL TEMPORARY TABLE`, and accelerator administration. The trigger-body inventory still classifies every `ALTER`, `CREATE`, `DROP`, transaction, and utility row that IBM includes in the SQL-procedure-statement matrix. XML table spaces are implicit; explicit LOB table spaces use `CREATE LOB TABLESPACE` and are included in the table-space chapter.

Deprecated non-UTS and index-controlled forms are retained only as compatibility test surfaces. They are clearly marked and should not be used as the default source for new-object cases.
