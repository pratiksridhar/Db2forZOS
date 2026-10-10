# IBM-derived reference

Everything under `kb/` comes from official IBM Db2 13 for z/OS documentation:
chapters for people, normalized JSON for tools, and the source manifest that
every rule cites. Test machinery lives in [qa/](../qa/README.md); workflows in
[docs/](../docs/README.md).

## Coverage

This repository is a test-authoring knowledge base for validating DDL that RC/Query and Object Framework Services (OFS) generate for these Db2 objects:

- storage groups (`STOGROUP`)
- databases
- table spaces, including base/work-file table spaces and the separate LOB table-space form
- tables
- indexes
- triggers, including basic and advanced definitions plus their complete body-statement matrix
- procedures, including native SQL, external, and deprecated external SQL compatibility definitions

The baseline is **IBM Db2 13 for z/OS documentation**, reviewed on **2026-09-03** through function level **V13R1M509**. The knowledge base records function-level and application-compatibility gates at the rule where they matter; it does not assume that every Db2 13 subsystem has activated the latest function level.

Only official IBM documentation is used. Every normalized rule has one or more source IDs that resolve in [sources.md](sources.md).

## Reference and executable layers

IBM syntax diagrams are the authority, but diagrams alone are a poor test inventory. Important behavior also appears in clause descriptions and notes: defaults controlled by subsystem parameters, mutually exclusive clauses, implicit object creation, function-level gates, and rules that depend on table-space type.

This repository connects three complementary layers:

1. **Reference chapters** explain concepts, grammar, defaults, restrictions, and high-yield OFS test ideas for a person.
2. **Normalized JSON** indexes clauses and cross-clause rules for scripts, searches and coverage tracking.
3. **Campaign models and compiler** turn bounded dimensions and constraints into
   deterministic SQL bundles with semantic comparison contracts. The existing
   agent recipes remain available for broader manual/LLM authoring.

The JSON is deliberately a normalized test model, not a replacement SQL parser. When it and IBM documentation disagree, the IBM statement reference wins and the KB should be corrected.

## Contents

| Path | Purpose |
|---|---|
| [sources.md](sources.md) | Source IDs, URLs and citation policy |
| [object-model.md](object-model.md) | Physical/logical hierarchy, dependency order, and implicit creation paths |
| [syntax-notation.md](syntax-notation.md) | Notation used in the hand-written grammar summaries |
| [objects/stogroup.md](objects/stogroup.md) | `CREATE STOGROUP` concepts and syntax |
| [objects/database.md](objects/database.md) | `CREATE DATABASE` concepts and syntax |
| [objects/tablespace.md](objects/tablespace.md) | PBG, PBR, work-file, LOB, and implicit table spaces |
| [objects/table.md](objects/table.md) | `CREATE TABLE` definition forms, columns, constraints, periods, and physical clauses |
| [objects/table-relational.md](objects/table-relational.md) | Parent/child fixtures with composite referential integrity and enforcing indexes |
| [objects/index.md](objects/index.md) | Ordinary, unique, expression, XML, temporal, partitioned, DPSI, and NPI indexes |
| [objects/trigger.md](objects/trigger.md) | Basic/advanced `CREATE TRIGGER`, transition data, options, restrictions, packages, versions, and verification |
| [objects/procedure.md](objects/procedure.md) | Native SQL, external, and deprecated external SQL `CREATE PROCEDURE` forms |
| [trigger-body-statements.md](trigger-body-statements.md) | Direct-body, SQL control, 35 supported nested, and 34 excluded nested statement families |
| [dialect-traps.md](dialect-traps.md) | Other-dialect habits that produce invalid Db2 for z/OS DDL, with the checker rule for each |
| [function-levels.md](function-levels.md) | Db2 13 function levels 100 and 500-509, APPLCOMPAT gates, default changes and deprecations |
| [catalog-verification.sql](catalog-verification.sql) | Catalog queries for semantic validation after DDL execution |
| [data/db2z13-create-ddl.json](data/db2z13-create-ddl.json) | Normalized clause, rule, dimension, and source index |
| [data/db2z13-trigger-body-statements.json](data/db2z13-trigger-body-statements.json) | Trigger statement syntax and support matrix |
| [data/db2z13-ddl-checks.json](data/db2z13-ddl-checks.json) | Static check rules with severities, KB rule references and IBM sources |
| [data/db2z13-function-levels.json](data/db2z13-function-levels.json) | Function-level and APPLCOMPAT gate data used by `lint` and `diff` |
| [data/db2z13-catalog-columns.json](data/db2z13-catalog-columns.json) | Verified catalog column names/types that generated queries may select |

## Object cross-reference

C/R/D counts the normalized clauses, cross-clause rules and coverage dimensions of each
object in [db2z13-create-ddl.json](data/db2z13-create-ddl.json). Checker prefixes are IDs in
[db2z13-ddl-checks.json](data/db2z13-ddl-checks.json) that start with the object name or cite
one of its rules in `kb_rules`; generic script checks are omitted, so `—` means no explicit
mapping, not that nothing is checked.

| Chapter | JSON object | C/R/D | Checker prefixes | Most cited sources |
|---|---|---:|---|---|
| [STOGROUP](objects/stogroup.md) | `stogroup` | 9/6/6 | — | `ibm-create-stogroup`, `ibm-stogroup-create-task` |
| [DATABASE](objects/database.md) | `database` | 7/7/7 | `name.` | `ibm-create-database` |
| [TABLESPACE](objects/tablespace.md) | `tablespace` | 31/16/14 | `tablespace.`, `deprecated.`, `fl.` | `ibm-create-tablespace`, `ibm-create-lob-tablespace` |
| [TABLE](objects/table.md) | `table` | 53/36/14 | `table.`, `dialect.`, `syntax.`, `auxtable.`, `fl.` | `ibm-create-table`, `ibm-implicit-tablespace` |
| [Relational tables](objects/table-relational.md) | companion to `table` | — | — | — |
| [INDEX](objects/index.md) | `index` | 27/20/14 | `index.`, `table.`, `cleanup.` | `ibm-create-index`, `ibm-partitioned-indexes` |
| [PROCEDURE](objects/procedure.md) | `procedure` | 23/25/16 | `dialect.` | `ibm-create-procedure-native`, `ibm-create-procedure-external` |
| [TRIGGER](objects/trigger.md) | `trigger` | 26/37/14 | — | `ibm-create-trigger-advanced`, `ibm-create-trigger-basic` |

## Find a rule

From the repository root:

- **By clause name:** `python3 tools/kb.py search LOCKSIZE` gives the object and ID;
  `python3 tools/kb.py show tablespace locksize` prints it; then
  `grep -n -i LOCKSIZE kb/objects/tablespace.md` finds the chapter text.
- **By checker ID:** `grep -n '"id": "table.identity-cardinality"' kb/data/db2z13-ddl-checks.json`,
  then follow its `kb_rules` with `python3 tools/kb.py show table identity-cardinality`.
  Checks with empty `kb_rules` have no chapter mapping; follow their `source_refs`.
- **By source ID:** `python3 tools/kb.py search ibm-create-database` lists the entries
  that cite it; `grep -n ibm-create-database kb/sources.md kb/objects/*.md` finds the
  manifest entry and chapter citations.

Query the normalized data with `tools/kb.py` ([commands](../docs/commands.md#kbpy-query-the-ibm-derived-reference)).

## Scope boundary

The core chapters cover the requested object set and the syntax that directly changes their definitions. The following related statements are identified where they affect the seven objects but are not independently modeled as top-level object chapters in this edition: `ALTER`, `DROP`, `CREATE AUXILIARY TABLE`, `CREATE GLOBAL TEMPORARY TABLE`, and accelerator administration. The trigger-body inventory still classifies every `ALTER`, `CREATE`, `DROP`, transaction, and utility row that IBM includes in the SQL-procedure-statement matrix. XML table spaces are implicit; explicit LOB table spaces use `CREATE LOB TABLESPACE` and are included in the table-space chapter. Deprecated external SQL procedures are documented as compatibility surfaces but intentionally have no default template.

Deprecated non-UTS and index-controlled forms are retained only as compatibility test surfaces. They are clearly marked and should not be used as the default source for new-object cases.
