# Legacy agent layer

**Legacy.** New work should use the [SQL-first route](../../docs/workflows/domain-schema.md)
or a [modeled campaign](../../docs/workflows/campaign.md). This layer is kept because
it holds the only view scaffold, the object registry that `ddl.py context` and
`ddl.py plan` read, and SQL templates for manual authoring.

For executable campaigns, start with [the campaign guide](../../docs/workflows/campaign.md)
and `python3 tools/qa.py context <object>`. This directory retains the broader
planning recipes and scaffolds; its `agent_ready_from_normalized_kb` labels describe
authoring readiness, not successful compilation or execution on Db2.

This directory is the machine-oriented layer above the IBM-derived Db2 for z/OS
knowledge base. The files here tell an AI agent how to plan, compose, and verify
DDL test cases without scraping long prose chapters.

Use this layer as a planner, not as a replacement for IBM-derived truth. The
[task protocol](TASKS.md) gives the step-by-step agent procedure.

1. Load `object-registry.json` to identify whether an object is normalized or an
   `extension_candidate` scaffold.
2. Load `dependency-graph.json` to resolve required capabilities and create/drop
   ordering.
3. Load `specs/<object>.json` for the generation flow and required rule sets.
4. Load `dimensions/<object>.json` to choose systematic variations.
5. Load `rules/<object>.json` to validate positive and negative combinations.
6. Choose a recipe from `recipes/<object>/` and its fixtures.
7. Fill the referenced SQL template and emit a durable JSON test case conforming
   to `qa/schemas/test-case.schema.json`.
8. Keep generated cases in `status: design` until executed on a recorded Db2
   subsystem and validated with catalog/behavior assertions.

`view` is included as an `extension_candidate_agent_scaffold` because future test
generation should cover views. Do not treat view syntax as normalized KB truth
until `kb/objects/view.md`, source IDs, and normalized JSON rules are added.

## Template-based manual cases

To create a durable test:

1. Choose one primary semantic variation from [the coverage model](../../docs/test-design/coverage-model.md).
2. Add boundary, explicit-default/omitted-default, and illegal-pair companions.
3. Copy the closest SQL template from [templates/](templates/) and replace every `{{TOKEN}}`.
4. Record the subsystem context, source IDs, expected outcome, and OFS comparison policy in a JSON case that conforms to the test-case schema.
5. Execute the source DDL, generate DDL through OFS, recreate the object under a clean name, and compare catalog semantics with the supplied queries.

## Templates

| Template | Purpose |
|---|---|
| [object-stack](templates/object-stack.template.sql) | Parameterized explicit storage-group-to-index object stack |
| [pbg-table](templates/pbg-table.template.sql) | PBG-focused table and index template |
| [pbr-table](templates/pbr-table.template.sql) | PBR/RPN-focused table and index template |
| [basic-trigger](templates/basic-trigger.template.sql) | Multi-statement basic-trigger template |
| [basic-before-validation](templates/basic-before-validation.template.sql) | BEFORE validation trigger used by its recipe |
| [advanced-trigger](templates/advanced-trigger.template.sql) | SQL PL variables, handler, condition, diagnostics, and DML template |
| [advanced-trigger-ddl-body](templates/advanced-trigger-ddl-body.template.sql) | Advanced compound body with supported `CREATE TABLE`, `CREATE INDEX`, and `CREATE VIEW` |
| [native-sql-procedure](templates/native-sql-procedure.template.sql) | Versioned native SQL procedure with parameters, handler, diagnostics, and package options |
| [external-procedure](templates/external-procedure.template.sql) | Current COBOL external-procedure registration with linkage, package, and WLM inputs |
| [simple-view](templates/simple-view.template.sql), [view-check-option](templates/view-check-option.template.sql) | View scaffolds; not normalized IBM truth |

Templates with a `.manifest.json` list their required tokens and must-include text;
`tools/agent.py validate` and the tests check them.
