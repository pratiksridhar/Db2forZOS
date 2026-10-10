# Changelog

Dated reviews in [reviews/](reviews/) and the [campaign source review](source-review.md)
record exactly what was checked against which IBM edition. They are history: later
changes do not re-certify them.

## 2026-10-10: repository reorganized

`kb/` now holds only IBM-derived reference. Tool inputs moved to `qa/`, examples
and workloads to `examples/`, workflows and history to `docs/`; `tools/paths.py`
owns every location. Root domain scripts (`banking.sql`, `insurance.sql`,
`supply-chain-logistics.sql`) were removed; the supply-chain generator and its
records moved to `examples/domains/supply-chain-logistics/`.

| Old | New |
|---|---|
| `kb/campaigns/models/`, `kb/campaigns/profiles/` | `qa/models/`, `qa/profiles/` |
| `kb/authoring/request.schema.json`, `kb/data/test-case.schema.json` | `qa/schemas/` |
| `kb/authoring/variety-baseline.json` | `qa/variety-baseline.json` |
| `kb/agent/`, `kb/templates/` | `qa/legacy-agent/`, `qa/legacy-agent/templates/` |
| `kb/authoring/examples/` | `examples/varied-schema.sql`, `examples/requests/` |
| `kb/test-design/sample-case.json` | `examples/sample-case.json` |
| `kb/test-design/create-1000-table-qa-workload.sql`, `tools/generate_1000_table_qa_sql.py` | `examples/workloads/1000-table/` |
| `kb/test-design/catalog-verification.sql` | `kb/catalog-verification.sql` |
| `kb/test-design/*.md` | `docs/test-design/` |
| `kb/authoring/README.md` | `docs/workflows/requests-and-plans.md`, `domain-schema.md`, `product-verification.md` |
| `kb/campaigns/README.md` | `docs/workflows/campaign.md`, `product-verification.md` |
| `kb/campaigns/EXTENDING.md`, `prompts.md`, `ROADMAP.md` | `docs/workflows/extending.md`, `docs/prompts.md`, `docs/roadmap.md` |
| `kb/campaigns/SOURCE-REVIEW.md`, `kb/campaigns/reviews/` | `docs/history/source-review.md`, `docs/history/reviews/` |

Recorded artifacts written before this date, such as
`examples/domains/supply-chain-logistics/plan.json`, keep the old paths and hashes.

## 2026-10-10: static checker and SQL-first path

A statically checked SQL-first path for domain schemas: IBM-sourced lint rules,
function-level and APPLCOMPAT gates, a variety baseline, a semantic DDL diff for
product output, and bundle derivation from any lint-clean script. See
[the checker review](reviews/ddl-checker.md).

## 2026-09-12: more campaign families

Added `table-relational`, `trigger-basic`, `procedure-native`, structured request
plans, filtered selections, feasible three-way coverage and lossless SQL PL
framing. See [the compiler audit](reviews/compiler.md). Existing reference chapters
and the legacy workload remain useful for wider manual authoring; they are not
automatically promoted to compiler support.

## 2026-09-04: executable campaign layer

The starting repository had seven normalized objects, useful rule/source records,
templates, a 20-family 1,000-table workload and 22 passing tests. Agent recipes
covered only triggers and scaffolded views. `tools/agent.py validate` checked file
and token references, but did not select combinations, render complete case bundles,
measure design coverage, or compare product recreation evidence. The executable
layer added those foundations for three bounded families. See
[the source review](source-review.md).
