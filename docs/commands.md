# Command reference

Every tool runs from the repository root with Python 3.10+ and the standard library.
`qa.py validate-case` and the test suite also need `requirements-dev.txt`. **No
command connects to Db2 or executes SQL.** Each tool prints full options with
`--help`; this page says which tool owns which job.

| Tool | Owns |
|---|---|
| `tools/ddl.py` | Any DDL script: request plans, lint, variety coverage, product diff, QA bundles |
| `tools/qa.py` | Modeled campaign families and case evidence: build, validate, convert and compare catalog exports, record outcomes, validate cases |
| `tools/kb.py` | Queries over the normalized IBM-derived reference in `kb/data/` |
| `tools/agent.py` | The legacy recipe layer in `qa/legacy-agent/` |

## ddl.py: plan, check and bundle any DDL

| Command | Does | Exit codes |
|---|---|---|
| `plan --request R [--out F] [--require-modeled]` | Turns a structured request into an IBM-linked plan with build argv per family | 0 plan; 1 gaps with `--require-modeled`; 2 bad input |
| `lint SQL [--profile P] [--max-line 72] [--assume KIND:NAME] [--json]` | Static checks against [IBM-sourced rules](../kb/data/db2z13-ddl-checks.json); reports minimum APPLCOMPAT | 0 pass; 1 findings; 2 bad input |
| `coverage SQL [--baseline core\|extended\|FILE] [--json]` | Counts KB clauses and values exercised; gates on a [variety baseline](../qa/variety-baseline.json) | 0; 1 baseline unmet |
| `bundle SQL --run R --out DIR --profile P --replay-schema S=T --replay-database D=E` | Catalog queries/expectations, cleanup, name map, inventory and case from a lint-clean script | 0; 2 bad input |
| `diff SOURCE TARGET [--map name-map.json] [--profile P] [--text]` | Semantic diff of source and product-generated DDL; `--text` lists only entries to review | 0 match; 1 mismatch; 3 unresolved; 2 bad input |
| `levels [--applcompat V13R1M500] [--json]` | Function levels, or syntax gated above an APPLCOMPAT | 0 |
| `context OBJECT` | Full IBM-linked context for a normalized object: clauses, rules, sources, campaign models and coverage | 0 |

`lint` covers identifier limits, data types and defaults, keys and foreign keys,
enforcing indexes, table-space/index ranges, LOB support objects,
[dialect traps](../kb/dialect-traps.md) and
[function-level/APPLCOMPAT gates](../kb/function-levels.md). `diff` separates real
differences from documented defaults and subsystem-dependent defaults, and marks what
it cannot read as `not-compared`; [product verification](workflows/product-verification.md#first-look-at-product-output)
explains each status. See [the checker review](history/reviews/ddl-checker.md) and
[the diff review](history/reviews/diff-product-output.md) for sources and limits.

```sh
python3 tools/ddl.py lint my-schema.sql --profile qa/profiles/example.json
python3 tools/ddl.py coverage my-schema.sql --baseline core
python3 tools/ddl.py bundle my-schema.sql --run QA1 --out generated/qa1 \
  --profile qa/profiles/example.json \
  --replay-schema APP=APPR --replay-database APPDB=APPRDB
python3 tools/ddl.py diff generated/qa1/source.sql product-generated.sql \
  --map generated/qa1/name-map.json --profile qa/profiles/example.json --text
python3 tools/ddl.py plan --request examples/requests/index-include.json --require-modeled
python3 tools/ddl.py levels --applcompat V13R1M500
```

## qa.py: modeled campaigns and catalog evidence

| Command | Does | Exit codes |
|---|---|---|
| `models` | Lists compilable campaign models in [qa/models](../qa/models) as JSON | 0 |
| `build --model M --profile P --run R --out DIR [--strategy S] [--set AXIS=VALUE] [--budget N] [--negative]` | Writes an offline campaign bundle; never overwrites output | 0; 2 bad input |
| `snapshot --contract C --side source\|replay --csv-dir DIR [--result ID=FILE] [--null TEXT] [--delimiter D] [--encoding E] [--out F]` | Turns one CSV export per catalog result set into a typed snapshot | 0 written; 2 malformed export or bad input |
| `compare --contract C --source S.json --replay R.json` | Compares selected catalog fields and encoded expectations | 0 match; 1 differences; 2 malformed/missing evidence |
| `record CASE --phase P [--result R] [--evidence F] [--sqlcode N] [--sqlstate S] [--note T] [--product N --product-version V] [--option K=V] [--source S --replay R] [--at T]` | Appends a source, extraction, replay, comparison, probes or cleanup result with its evidence to a case and derives the status | 0 recorded; 2 refused |
| `status PATH... [--json]` | Each case's status, phase results, next phase and evidence integrity | 0 all pass; 1 some not passed; 2 evidence missing/changed or inconsistent |
| `validate-case CASE.json` | Checks a case against the [case schema](../qa/schemas/test-case.schema.json) IBM source IDs and unresolved placeholders; not SQL legality | 0 valid; nonzero invalid |
| `validate` | Checks model references, constraints, rendering and dependency graphs | 0; 2 invalid |
| `inventory` | Normalized clauses with and without a compiler path | 0 |
| `context OBJECT` | Self-contained IBM-linked object context pack | 0 |

Strategies are `pairwise` (default), `three-way`, `each-choice` and `exhaustive`.
See [the campaign workflow](workflows/campaign.md) for what each covers, and
[product verification](workflows/product-verification.md#catalog-evidence-protocol)
for snapshots and outcome records.

```sh
python3 tools/qa.py build --model table-core --profile qa/profiles/example.json \
  --run T01 --out generated/table-demo
python3 tools/qa.py build --model table-relational --profile qa/profiles/example.json \
  --run R01 --strategy three-way --negative --out generated/relational-demo
python3 tools/qa.py build --model trigger-basic --profile qa/profiles/example.json \
  --run G01 --set body=long-comment --out generated/trigger-demo
.venv/bin/python tools/qa.py validate-case generated/qa1/case.json
python3 tools/qa.py snapshot --contract generated/qa1/catalog-contract.json --side source \
  --csv-dir exports/source --out generated/qa1/source.json
python3 tools/qa.py record generated/qa1 --phase comparison \
  --source generated/qa1/source.json --replay generated/qa1/replay.json
python3 tools/qa.py status generated/qa1
```

## kb.py: query the IBM-derived reference

| Command | Does |
|---|---|
| `objects` | Normalized objects |
| `clauses OBJECT` | Clause IDs for an object |
| `show OBJECT ID [--json]` | One clause or rule |
| `rules OBJECT [--tag TAG]` | Cross-clause rules |
| `dimensions OBJECT` | Suggested coverage dimensions |
| `search TEXT` | Clauses, rules, dimensions and sources |
| `sources` | Official IBM sources |
| `trigger-statements basic\|direct\|nested\|excluded\|controls\|ddl\|syntax [--statement S] [--activation A] [--json]` | Trigger-body statement matrix |

```sh
python3 tools/kb.py clauses tablespace
python3 tools/kb.py show table identity-cardinality --json
python3 tools/kb.py rules table --tag implicit
python3 tools/kb.py trigger-statements nested --activation BEFORE
python3 tools/kb.py search "WITHOUT OVERLAPS"
```

## agent.py: legacy recipe layer

`registry`, `spec OBJECT`, `recipes [--object O]`, `show-recipe ID`, `fixtures` and
`validate`. See [qa/legacy-agent](../qa/legacy-agent/README.md). New work should
use `ddl.py` or `qa.py`.

## Example generators

```sh
python3 examples/workloads/1000-table/generate.py         # rewrites the tracked workload
python3 examples/domains/supply-chain-logistics/generate.py  # writes generated/supply-chain-logistics/source.sql
```

## Repository checks

The same commands run in [CI](../.github/workflows/validate.yml):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
python3 tools/qa.py validate
python3 tools/agent.py validate
python3 tools/ddl.py lint examples/varied-schema.sql --profile qa/profiles/example.json
python3 tools/ddl.py coverage examples/varied-schema.sql --baseline core
python3 tools/ddl.py lint examples/workloads/1000-table/create-1000-table-qa-workload.sql --allow-placeholders
git diff --check
```

These check the repository, not Db2 acceptance. Templates and workloads still
need execution under a recorded environment before they become product evidence.
