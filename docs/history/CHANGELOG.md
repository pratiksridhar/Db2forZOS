# Changelog

Dated reviews in [reviews/](reviews/) and the [campaign source review](source-review.md)
record exactly what was checked against which IBM edition. They are history: later
changes do not re-certify them.

## 2026-10-10: catalog exports, recorded outcomes and ALTER TABLE options

`qa.py snapshot` turns one CSV export per catalog result set into a typed snapshot,
so catalog comparison no longer needs hand-built JSON. Contracts now declare each
field's catalog type; campaign-model queries name their catalog table, and four
routine, trigger and package catalog tables joined the verified column list.
`compare` rejects mistyped values and snapshots converted for another contract.
`qa.py record` appends source, extraction, replay, comparison, probe and cleanup
results with hashed evidence to a case and derives its status, which gains
`in_progress`; `qa.py status` reports progress and changed evidence. Seeded defects
in an imitation catalog export of the exemplar test the comparator. `lint`, `bundle`
and `diff` apply the ALTER TABLE options DATA CAPTURE, AUDIT, VOLATILE, APPEND,
VALIDPROC and RESTRICT ON DROP, and bundle cleanup removes RESTRICT ON DROP first.
New rule `table.fk-self-reference-delete-rule` caught the exemplar's self-reference
with `ON DELETE SET NULL`, now `NO ACTION`. The supply-chain example passes `lint`,
and `ddl.py plan` writes repository-relative paths. See
[the review](reviews/alter-table-and-evidence.md).

## 2026-10-10: diff trusts product-style output and flags what it cannot read

`ddl.py diff` no longer reports common extraction rewrites as differences: delimited
names, explicit defaults, per-partition repetition, `INCLUSIVE` boundaries,
generated constraint names and explicit `FOR SBCS|MIXED DATA` subtypes. It now compares
generated expressions, `FIELDPROC` parameters and `NULLS LAST`, and it reports
partly parsed statements, unmodeled `ALTER` statements and unmodeled objects as
`not-compared` instead of returning `match`. `--text` prints only entries to review.
Campaign `RUN.md` now points to the snapshot format in product verification. See
[the diff review](reviews/diff-product-output.md).

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
