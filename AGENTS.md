# Working in this Db2 for z/OS QA repository

This repository helps a Broadcom administration-product QA engineer create diverse
catalog objects, extract their DDL with the product, recreate them, and detect lost
semantics. **Variety of catalog states is the goal, not volume.** Ninety tables that
repeat one option set exercise the product less than eight tables that each differ.
Realistic domain models are welcome, but spread syntax variants across them.

## Route the request

| Request | Path |
|---|---|
| A bounded family the compiler models (`python3 tools/qa.py models`) | Write a request, run `tools/ddl.py plan`, then `tools/qa.py build` with the plan's argv |
| A domain or bespoke schema (most requests) | SQL-first workflow below |
| Product-generated DDL to assess | `tools/ddl.py diff`, then catalog comparison (see Product verification) |
| A clause or object nothing models yet | IBM research, then `kb/campaigns/EXTENDING.md` and new checker rules with fixtures |

## SQL-first workflow for domain schemas

1. Read `kb/dialect-traps.md` and the object chapters you need under `kb/objects/`.
   Read `kb/function-levels.md` when a level is named or newer syntax is used.
2. Record the request in `kb/authoring/requests/<id>.json` (see
   `kb/authoring/README.md`). Unknown environment values stay explicit and unverified.
3. Plan variety before writing SQL. Map tables to the requirements of the `core`
   baseline in `kb/authoring/variety-baseline.json` (PBG and PBR, partition
   overrides, several SEGSIZE/LOCKSIZE/COMPRESS/free-space values, many type
   families, identity ALWAYS and BY DEFAULT, hidden and row-change columns, several
   delete rules, NOT ENFORCED, INCLUDE, DESC, PADDED/NOT PADDED, partitioned
   indexes, implicit and explicit placement, LOB support). Study
   `kb/authoring/examples/varied-schema.sql`.
4. Write the SQL, or a small generator, under `generated/<id>/` (ignored by git)
   unless the user asks for a tracked file. Name every constraint. Create each
   enforcing unique index (same columns, same order) right after its table and
   before any child references it. Add self-references with `ALTER TABLE`.
5. **Gate 1, static checks:** `python3 tools/ddl.py lint generated/<id>/source.sql
   --profile <profile>` must print PASS. Fix findings; do not reword around them.
   `--allow-unsupported` is acceptable only with a per-finding explanation in the
   report and IBM evidence that the construct is valid.
6. **Gate 2, variety:** `python3 tools/ddl.py coverage <sql> --baseline core` must
   report every requirement met, unless the user narrowed the scope. Report any
   unmet requirement and why.
7. **Gate 3, QA bundle:** `python3 tools/ddl.py bundle <sql> --run <RUN>
   --out generated/<id>/bundle --profile <profile> --replay-schema S=T
   --replay-database D=E` derives catalog queries and expectations, cleanup, name
   map, inventory and a schema-valid case. Run `qa.py validate-case` on the case.
8. Report the deliverables, gate results, `compatibility.minimum_applcompat` from
   lint, unmet requirements, and that no Db2 or product execution occurred.

## Authority and uncertainty

- Use only official **IBM Db2 13 for z/OS** documentation for syntax and catalog
  semantics. Db2 LUW, Db2 for i, older releases, and plausible SQL are not substitutes.
- Read the relevant syntax diagram, clause descriptions, restrictions, defaults,
  and catalog definitions. Use the official SQL Reference PDF if HTML fails.
- Record source IDs and the exact reviewed edition/section. Never mark a whole
  object reviewed because one clause was checked.
- Normalized JSON is a test model, and `ddl.py lint` is a rule checker, not a
  complete grammar. A PASS never proves Db2 acceptance. Statements it reports as
  not checked (views, routines, triggers, GRANT, COMMENT) still need IBM review.
- Views remain scaffolded. Other unmodeled objects must be researched and normalized
  before their syntax can be treated as source-derived truth.
- Ask for the real function level, APPLCOMPAT, CURRENT RULES, subsystem settings
  (including TABLE_COL_NAME_EXPANSION, DPSEGSZ, PADIX, PAGESET_PAGENUM), storage
  group, pool sizes, and privileges when execution depends on them. Continue offline
  work with an explicitly unverified profile if those are unknown.

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
- First offline check: `python3 tools/ddl.py diff source.sql product-generated.sql
  --map name-map.json --profile <profile>`. `different` entries are candidate
  defects; `environment-dependent` entries need recorded subsystem values or
  catalog evidence; `equivalent-default` entries are not defects.
- Recreate actual product output under clean names. A reference script produced by
  this repository does not prove that the product generated correct DDL.
- Compare selected semantic catalog fields (`tools/qa.py compare` with the bundle
  contract) and add behavioral probes where catalogs are insufficient. Preserve
  case, literal whitespace, ordered keys/parameters, and object relationships.
  Never normalize SQL with blanket string replacement.
- Missing or empty evidence is not a pass. A catalog `match` is only a scoped result,
  not the case lifecycle state. Keep source acceptance, extraction, replay, and
  semantic verification as separate outcomes.
- Offline generation does not authorize running SQL. Cleanup targets only objects
  this run created. Dedicated database cleanup drops their entire contents.

## Extending and checking

Use `kb/campaigns/EXTENDING.md`. Preserve existing chapters, rule IDs, user changes,
and the legacy 1,000-table workload. New normalized features need matching chapters,
sources, rule references, catalog oracles, and regression coverage. A new checker
rule needs an entry in `kb/data/db2z13-ddl-checks.json` with IBM sources and a
triggering fixture in `tests/test_db2check.py`; the tests fail otherwise.

Run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
python3 tools/qa.py validate
python3 tools/agent.py validate
python3 tools/ddl.py lint kb/authoring/examples/varied-schema.sql
git diff --check
```

Report what changed, checks performed, uncovered scope, and whether any live Db2 or
product execution actually occurred. Keep chat updates short and decision-focused.
