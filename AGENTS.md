# Working in this Db2 for z/OS QA repository

This repository helps a Broadcom administration-product QA engineer create diverse
catalog objects, extract their DDL with the product, recreate them, and detect lost
semantics. More object names do not establish more syntax coverage.

## Start here

1. Read `README.md` and `kb/campaigns/README.md`.
   For everyday requests, follow `kb/authoring/README.md` and use
   `python3 tools/ddl.py plan --request <request.json>` to expose exact choices,
   source context and gaps before authoring. Free-text intent still needs agent review.
2. Run `python3 tools/qa.py inventory` to see implemented compiler coverage and gaps.
3. Run `python3 tools/qa.py context <object>` for normalized clauses, rules, IBM links,
   and available executable models. Use `tools/kb.py show <object> <rule-id>` for a
   narrower lookup. Trigger context includes the body-statement matrix.
4. For a supported campaign, use `tools/qa.py build`. Otherwise extend a model or
   author a schema-valid case using the existing templates and source references.

## Authority and uncertainty

- Use only official **IBM Db2 13 for z/OS** documentation for syntax and catalog
  semantics. Db2 LUW, Db2 for i, older releases, and plausible SQL are not substitutes.
- Read the relevant syntax diagram, clause descriptions, restrictions, defaults,
  and catalog definitions. Use the official SQL Reference PDF if HTML fails.
- Record source IDs and the exact reviewed edition/section. Never mark a whole
  object reviewed because one clause was checked.
- Normalized JSON is a test model, not a complete SQL grammar or SQL validator.
  The legacy agent recipes are planning aids; a scaffold is not executable support.
- Views remain scaffolded. Other unmodeled objects must be researched and normalized
  before their syntax can be treated as source-derived truth.
- Ask for real function level, APPLCOMPAT, CURRENT RULES, subsystem settings,
  storage group, pool sizes, and privileges when execution depends on them.
  Continue offline work with an explicitly unverified profile if those are unknown.

## Case generation

- Start every generated case in `design`. Static checks never imply Db2 acceptance.
- Keep SQL, environment, selected variations, prerequisites, dependencies, cleanup,
  source/rule references, and catalog/behavior expectations together.
- Exercise omitted clauses separately from explicit defaults. Record environment
  defaults so those two forms are compared meaningfully.
- Prefer valid pairwise combinations within bounded families, then targeted
  higher-order interactions and documented boundaries. Report the denominator and
  uncovered combinations when a budget limits coverage.
- Negative cases must isolate one intended violation after successful setup.
  Unknown SQLCODE/SQLSTATE stays null; do not invent a diagnostic.
- Resolve actual dependencies, including enforcing indexes and implicit objects.
  A global object-type order alone is insufficient for arbitrary object stacks.
- SQL PL bodies need statement-aware handling of the outer terminator. Do not
  split routines or triggers on every semicolon.
- Use repeatable `--set AXIS=VALUE` to select exact modeled options; repeated values
  within one axis are alternatives. `--strategy three-way` covers feasible triples.
  Coverage denominators after filtering do not imply coverage of the whole model.
- Preserve text byte-for-byte in case arrays. Use model `statement_terminator` for
  files and verify SQL-processor formatting/CCSID before body-text tests.
- Cleanup follows ownership as well as dependency order. Do not separately drop
  enforcing indexes or a table space already dropped with its UTS table.

## Product verification

- Preserve actual product-generated SQL, product version/options, name mappings,
  environment, and statement-level execution results.
- Recreate actual product output under clean names. A reference script produced by
  this repository does not prove that the product generated correct DDL.
- Compare selected semantic catalog fields and add behavioral probes where catalogs
  are insufficient. Preserve case, literal whitespace, ordered keys/parameters,
  and object relationships. Never normalize SQL with blanket string replacement.
- Missing or empty evidence is not a pass. A catalog `match` is only a scoped result,
  not the case lifecycle state. Keep source acceptance, extraction, replay, and
  semantic verification as separate outcomes.
- Offline generation does not authorize running SQL. Cleanup targets only objects
  this run created. Dedicated database cleanup drops their entire contents.

## Extending and checking

Use `kb/campaigns/EXTENDING.md`. Preserve existing chapters, rule IDs, user changes,
and the legacy 1,000-table workload. New normalized features need matching chapters,
sources, rule references, catalog oracles, and regression coverage.

Run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
python3 tools/qa.py validate
python3 tools/agent.py validate
git diff --check
```

Report what changed, checks performed, uncovered scope, and whether any live Db2 or
product execution actually occurred. Keep chat updates short and decision-focused.
