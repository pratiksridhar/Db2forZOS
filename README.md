# Db2 for z/OS DDL QA workbench

Generate varied test objects from an IBM-derived knowledge base, extract their DDL
with your administration product, and check that recreation preserves their semantics.
Future agents should start with [AGENTS.md](AGENTS.md).

## Use it with any LLM agent

Describe the objects, clauses, boundaries, formatting and relationships you need.
Ask the agent to follow [the authoring workflow](kb/authoring/README.md), turn the
request into a structured plan, and generate either a supported campaign or a
source-reviewed custom case. No particular LLM vendor, API key or service is required.

```sh
python3 tools/ddl.py plan --request kb/authoring/examples/index-include.json
python3 tools/qa.py models
python3 tools/qa.py context trigger
```

The plan exposes exact choices, IBM references, dependencies and unsupported
requirements. It never treats a matching clause name as proof of complete syntax
coverage. See [the September audit](kb/campaigns/reviews/compiler.md) for the
correctness fixes and validation limits.

## Generate your first campaign

```sh
python3 tools/qa.py build --model table-core \
  --profile kb/campaigns/profiles/example.json \
  --run T01 --out generated/table-demo
```

Open `generated/table-demo/RUN.md`. The bundle includes source and replay setup,
schema-valid case records, catalog queries/assertions, cleanup, source references,
and a report of feasible pairwise coverage. **The example environment is unverified;
no SQL is executed.** Replace its settings before running against a test subsystem.

Six executable families cover table columns, relational parent/child tables,
PBG table spaces, indexes, basic triggers and native SQL procedures.
`--negative` adds isolated violations of each model's encoded constraints.
Reference coverage is wider than compiler support; arbitrary Db2 DDL still needs
IBM research and subsystem validation.

```sh
python3 tools/qa.py build --model table-relational \
  --profile kb/campaigns/profiles/example.json --run R01 \
  --strategy three-way --negative --out generated/relational-demo
python3 tools/qa.py build --model trigger-basic \
  --profile kb/campaigns/profiles/example.json --run G01 \
  --set body=long-comment --out generated/trigger-demo
python3 tools/qa.py build --model procedure-native \
  --profile kb/campaigns/profiles/example.json --run P01 \
  --negative --out generated/procedure-demo
```

Trigger/procedure bundles use `@` as the outer terminator. Set the SQL processor
accordingly and preserve comments/line structure for body-format tests. Generated
text metrics measure UTF-8 artifacts, not target CCSID byte limits.

- [Campaign guide](kb/campaigns/README.md): commands, scope, catalog export format,
  product replay, evidence and cleanup.
- [Reusable agent prompts](kb/campaigns/prompts.md): generation, extension and defect investigation.
- [Expansion roadmap](kb/campaigns/ROADMAP.md): PBR/constraints, LOB/XML/temporal,
  procedures, runtime adapters and coverage of syntax paths.

Use `python3 tools/qa.py inventory` to inspect compiler gaps and
`python3 tools/qa.py context table` to export IBM-linked context for any normalized
object. A catalog `match` is scoped evidence, never an automatic product test pass.

## Reference coverage

This repository is a test-authoring knowledge base for validating DDL that RC/Query and Object Framework Services (OFS) generate for these Db2 objects:

- storage groups (`STOGROUP`)
- databases
- table spaces, including base/work-file table spaces and the separate LOB table-space form
- tables
- indexes
- triggers, including basic and advanced definitions plus their complete body-statement matrix
- procedures, including native SQL, external, and deprecated external SQL compatibility definitions

The baseline is **IBM Db2 13 for z/OS documentation**, reviewed on **2026-09-03** through function level **V13R1M509**. The knowledge base records function-level and application-compatibility gates at the rule where they matter; it does not assume that every Db2 13 subsystem has activated the latest function level.

Only official IBM documentation is used. Every normalized rule has one or more source IDs that resolve in [kb/sources.md](kb/sources.md).

## Reference and executable layers

IBM syntax diagrams are the authority, but diagrams alone are a poor test inventory. Important behavior also appears in clause descriptions and notes: defaults controlled by subsystem parameters, mutually exclusive clauses, implicit object creation, function-level gates, and rules that depend on table-space type.

This repository connects three complementary layers:

1. **Reference chapters** explain concepts, grammar, defaults, restrictions, and high-yield OFS test ideas for a person.
2. **Normalized JSON** indexes clauses and cross-clause rules for scripts, searches and coverage tracking.
3. **Campaign models and compiler** turn bounded dimensions and constraints into
   deterministic SQL bundles with semantic comparison contracts. The existing
   agent recipes remain available for broader manual/LLM authoring.

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
| [kb/objects/procedure.md](kb/objects/procedure.md) | Native SQL, external, and deprecated external SQL `CREATE PROCEDURE` forms, parameters, versions, packages, WLM, and verification |
| [kb/trigger-body-statements.md](kb/trigger-body-statements.md) | Direct-body, SQL control, 35 supported nested, and 34 excluded nested statement families with compact syntax |
| [kb/test-design/coverage-model.md](kb/test-design/coverage-model.md) | A systematic model for deriving positive, negative, boundary, default, and round-trip cases |
| [kb/test-design/catalog-verification.sql](kb/test-design/catalog-verification.sql) | Catalog queries for semantic validation after DDL execution |
| [kb/test-design/create-1000-table-qa-workload.sql](kb/test-design/create-1000-table-qa-workload.sql) | Generated positive workload: one storage group/database, 1,000 dedicated table spaces, 1,000 varied tables, indexes, and seed data |
| [kb/templates/object-stack.template.sql](kb/templates/object-stack.template.sql) | Parameterized explicit storage-group-to-index object stack |
| [kb/templates/pbg-table.template.sql](kb/templates/pbg-table.template.sql) | PBG-focused table and index template |
| [kb/templates/pbr-table.template.sql](kb/templates/pbr-table.template.sql) | PBR/RPN-focused table and index template |
| [kb/templates/basic-trigger.template.sql](kb/templates/basic-trigger.template.sql) | Multi-statement basic-trigger template |
| [kb/templates/advanced-trigger.template.sql](kb/templates/advanced-trigger.template.sql) | SQL PL variables, handler, condition, diagnostics, and DML template |
| [kb/templates/advanced-trigger-ddl-body.template.sql](kb/templates/advanced-trigger-ddl-body.template.sql) | Advanced compound body with supported `CREATE TABLE`, `CREATE INDEX`, and `CREATE VIEW` |
| [kb/templates/native-sql-procedure.template.sql](kb/templates/native-sql-procedure.template.sql) | Versioned native SQL procedure with parameters, handler, diagnostics, and package options |
| [kb/templates/external-procedure.template.sql](kb/templates/external-procedure.template.sql) | Current COBOL external-procedure registration with linkage, package, and WLM inputs |
| [kb/data/db2z13-create-ddl.json](kb/data/db2z13-create-ddl.json) | Machine-readable clause, rule, dimension, and source index |
| [kb/data/db2z13-trigger-body-statements.json](kb/data/db2z13-trigger-body-statements.json) | Machine-readable trigger statement syntax and support matrix |
| [kb/data/test-case.schema.json](kb/data/test-case.schema.json) | JSON Schema for persistent OFS test-case records |
| [kb/test-design/sample-case.json](kb/test-design/sample-case.json) | Example test-case record |
| [kb/agent/README.md](kb/agent/README.md) | Agent-first planning layer: object registry, specs, rules, dimensions, fixtures, and recipes |
| [tools/kb.py](tools/kb.py) | Dependency-free command-line query tool for the normalized IBM-derived KB |
| [tools/agent.py](tools/agent.py) | Dependency-free command-line query and validation tool for the agent generation layer |
| [tools/generate_1000_table_qa_sql.py](tools/generate_1000_table_qa_sql.py) | Deterministically regenerates and validates the 1,000-table SQL workload |

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
python3 tools/kb.py clauses procedure
python3 tools/kb.py show procedure kind-discriminator
python3 tools/kb.py rules procedure --tag versioning
python3 tools/kb.py dimensions procedure
python3 tools/kb.py trigger-statements basic
python3 tools/kb.py trigger-statements nested --activation BEFORE
python3 tools/kb.py trigger-statements ddl
python3 tools/kb.py trigger-statements controls --statement return
python3 tools/kb.py trigger-statements syntax --statement create-table --json
python3 tools/kb.py search "WITHOUT OVERLAPS"
python3 tools/kb.py sources
```

For AI/agent-driven generation, start with the agent layer instead of the prose chapters:

```text
python3 tools/agent.py registry
python3 tools/agent.py spec trigger
python3 tools/agent.py recipes --object trigger
python3 tools/agent.py show-recipe trigger_basic_before_validation
python3 tools/agent.py fixtures
python3 tools/agent.py validate
```

The agent layer under [kb/agent](kb/agent/README.md) provides object routing, dependency/capability graphs, structured constraints, coverage dimensions, fixtures, recipes, and template manifests. Objects marked `normalized` are backed by the IBM-derived KB. Objects marked `extension_candidate`, such as the initial `view` scaffold, are planning aids until their IBM syntax chapter and normalized JSON rules are added.

To create a durable test:

1. Choose one primary semantic variation from [the coverage model](kb/test-design/coverage-model.md).
2. Add boundary, explicit-default/omitted-default, and illegal-pair companions.
3. Copy the closest SQL template and replace every `{{TOKEN}}`.
4. Record the subsystem context, source IDs, expected outcome, and OFS comparison policy in a JSON case that conforms to the test-case schema.
5. Execute the source DDL, generate DDL through OFS, recreate the object under a clean name, and compare catalog semantics with the supplied queries.

## Verify the KB itself

The repository checks normalized IDs and sources, existing templates, command-line
queries, feasible pair coverage, constraint isolation, dependency ordering, all
generated case schemas, and catalog-comparison failure detection. Test dependencies
are separate from the standard-library command-line tools:

```text
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
python3 tools/qa.py validate
python3 tools/agent.py validate
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
- procedure kind; for native SQL record routine/package version and body `APPLCOMPAT`, and for external procedures record program, package, WLM, and external-security context
- `CURRENT RULES`
- data sharing versus non-data-sharing
- relevant subsystem parameters, especially `DPSEGSZ`, `IMPDSSIZE`, `IMPTKMOD`, `IMPTSCMP`, `PADIX`, `PAGESET_PAGENUM`, `PCTFREE_UPD`, `DEFAULT_INSERT_ALGORITHM`, and compression defaults
- active buffer-pool sizes
- SMS/DFSMS capabilities, extended-format/extended-addressability settings, and available storage classes

Without this context, an omitted clause is not a stable expected value and a negative test might fail for the wrong reason.

## Scope boundary

The core chapters cover the requested object set and the syntax that directly changes their definitions. The following related statements are identified where they affect the seven objects but are not independently modeled as top-level object chapters in this edition: `ALTER`, `DROP`, `CREATE AUXILIARY TABLE`, `CREATE GLOBAL TEMPORARY TABLE`, and accelerator administration. The trigger-body inventory still classifies every `ALTER`, `CREATE`, `DROP`, transaction, and utility row that IBM includes in the SQL-procedure-statement matrix. XML table spaces are implicit; explicit LOB table spaces use `CREATE LOB TABLESPACE` and are included in the table-space chapter. Deprecated external SQL procedures are documented as compatibility surfaces but intentionally have no default template.

Deprecated non-UTS and index-controlled forms are retained only as compatibility test surfaces. They are clearly marked and should not be used as the default source for new-object cases.
