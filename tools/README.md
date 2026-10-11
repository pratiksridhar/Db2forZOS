# Tool code map

Run every tool from the repository root. Options and exit codes are in the
[command reference](../docs/commands.md). Functions are named rather than linked by line,
so search for them with `grep -n 'def NAME' tools/FILE`.

## Modules

| Module | Role | Main entry points | Reads | Tests |
|---|---|---|---|---|
| [ddl.py](ddl.py) | CLI: `plan`, `context`, `lint`, `coverage`, `diff`, `bundle`, `levels` | `make_plan`, `main` | [request schema](../qa/schemas/request.schema.json), [object registry](../qa/legacy-agent/object-registry.json), profiles, baselines | [test_ddl.py](../tests/test_ddl.py), [test_db2check.py](../tests/test_db2check.py) |
| [qa.py](qa.py) | CLI: `inventory`, `validate`, `models`, `context`, `validate-case`, `build`, `snapshot`, `compare`, `record`, `status` | `validate_model`, `make_case`, `write_campaign`, `snapshot`, `compare`, `record_outcome`, `case_status`, `context_pack` | [models](../qa/models), [KB](../kb/data/db2z13-create-ddl.json), [catalog columns](../kb/data/db2z13-catalog-columns.json), [trigger-body matrix](../kb/data/db2z13-trigger-body-statements.json), [case schema](../qa/schemas/test-case.schema.json), profiles | [test_qa.py](../tests/test_qa.py), [test_relational.py](../tests/test_relational.py), [test_routine_models.py](../tests/test_routine_models.py), [test_evidence.py](../tests/test_evidence.py) |
| [kb.py](kb.py) | CLI: `objects`, `clauses`, `show`, `rules`, `dimensions`, `search`, `sources`, `trigger-statements` | `build_parser`, `main` | [KB](../kb/data/db2z13-create-ddl.json), [trigger-body matrix](../kb/data/db2z13-trigger-body-statements.json) | [test_kb.py](../tests/test_kb.py) |
| [agent.py](agent.py) | CLI: `registry`, `spec`, `recipes`, `show-recipe`, `fixtures`, `validate` | `command_validate`, `build_parser` | [legacy agent layer](../qa/legacy-agent/README.md) | [test_kb.py](../tests/test_kb.py) |
| [db2check.py](db2check.py) | Library: static rules, variety coverage, semantic diff, bundles | `analyze`, `coverage`, `check_baseline`, `diff`, `bundle` | [checks](../kb/data/db2z13-ddl-checks.json), [KB](../kb/data/db2z13-create-ddl.json), [function levels](../kb/data/db2z13-function-levels.json), [catalog columns](../kb/data/db2z13-catalog-columns.json), [variety baseline](../qa/variety-baseline.json) | [test_db2check.py](../tests/test_db2check.py) |
| [db2sql.py](db2sql.py) | Library: statement splitting, tokens, structural DDL parsing | `split_script`, `tokenize`, `parse_statement` | nothing | [test_db2check.py](../tests/test_db2check.py) |
| [sqltext.py](sqltext.py) | Library: lossless SQL text framing and terminators | `inspect_sql`, `validate_statement`, `emit_sql` | nothing | [test_sqltext.py](../tests/test_sqltext.py), [test_routine_models.py](../tests/test_routine_models.py) |
| [paths.py](paths.py) | Every repository location, defined once | constants | nothing | [test_layout.py](../tests/test_layout.py) |

## db2check.py sections

Sections in file order, each starting at the named definition.

| Section | Starts at |
|---|---|
| Profiles, findings, options, table/table-space state, report | `level_key`, `Finding`, `Report` |
| Script analysis and parser dispatch | `analyze` |
| Object, dependency, name and function-level rules | `class Checker` (`find`, `apply`) |
| Syntax variety and the baseline gate | `coverage`, `check_baseline` |
| Name mapping, semantic normalization and DDL diff | `class NameMap`, `diff` |
| Catalog queries, bundle files, inventory and cleanup | `bundle` |
| Human-readable coverage output | `coverage_text` |

## db2sql.py sections

| Section | Starts at |
|---|---|
| Statement boundaries and terminator directives | `ParseError`, `split_script` |
| Tokens and literals | `tokenize` |
| Parsed object types, cursor helpers, unsupported clauses | `class Name` |
| Statement dispatch | `parse_statement` |
| Storage group, database and table-space parsing | `_parse_stogroup` |
| Data types, columns, constraints and tables | `_parse_data_type` |
| Auxiliary tables and indexes | `_parse_aux_table` |
| Other CREATE, ALTER, DROP, SET and COMMENT | `_parse_other_create` |

## Add a checker rule

1. Add the rule ID, severity, `kb_rules` and IBM `source_refs` to
   [db2z13-ddl-checks.json](../kb/data/db2z13-ddl-checks.json).
2. If the syntax is not parsed yet, extend `parse_statement` or the object parser in
   `db2sql.py`.
3. Emit the finding from `Checker` in `db2check.py`, usually through `Checker.find`.
4. Add a triggering SQL fixture to `NEGATIVE` in [test_db2check.py](../tests/test_db2check.py);
   `test_every_rule_has_a_triggering_fixture` fails until every rule has one.

The full procedure, including chapters and sources, is in
[Extending](../docs/workflows/extending.md).
