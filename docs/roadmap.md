# Roadmap

## Current checker gaps

Views, sequences, aliases, routines and triggers are recognized but not checked;
CHECK and generated expressions are not validated; XML modifiers and temporal
versioning (`ALTER TABLE ADD VERSIONING`) are outside the modeled subset. See
[the checker review](history/reviews/ddl-checker.md). How the repository got
here is in [the changelog](history/CHANGELOG.md).

## Next: finish the product feedback loop

Build a thin adapter around the actual work environment: SQL submission, statement
diagnostics, catalog export, product invocation and clean-target replay. Keep the
file protocol independent of the LLM vendor and product invocation mechanism.
Record product version/options and subsystem settings alongside every result.

Acceptance: one case demonstrates source acceptance, product extraction, replay,
and detection of an intentionally removed semantic attribute. Keep approved test
subsystems and execution credentials in the work harness, outside this repository.

## Expand by likely defect yield

Next add PBR plus partition overrides; wider PK/unique/FK graphs beyond the bounded
parent/child model; identity/sequence properties; LIKE versus AS-result copying; and explicit
versus implicit creation. These force regeneration to preserve relationships and
effective defaults across multiple catalog rows.

Next add LOB auxiliary objects, XML support objects, temporal/history pairs and
versioning, MQTs, views/check options, expression/XML indexes, and procedural
objects beyond basic BEFORE triggers and the initial native procedure model, with
versions, packages, dependencies and behavioral probes. Normalize
CREATE VIEW before enabling it. Track standalone sequences, aliases, functions,
distinct types, masks, permissions, trusted contexts and roles as separate candidate
objects requiring their own IBM research and product scope confirmation.

Acceptance for each family: source review, dimensions, executable constraints,
dependency setup, positive/boundary/negative cases, catalog or behavior oracles,
cleanup, regression tests, and a live validated seed before claiming execution support.

## Measure syntax paths, not just clause names

Evolve each normalized clause into explicit branch IDs with choices, omission,
cardinality, ordering, prerequisites, source anchors and lifecycle gates. Clause
presence alone cannot distinguish all identity options or copy forms. Add a report
with separate counts for source-reviewed paths, modeled paths, generated cases,
Db2-accepted cases, extracted cases, replayed cases and semantically verified cases.

Record exclusions with reasons. Sample higher-order interactions deliberately and
cross environments when defaults or function-level gates change the behavior.
Never label an entire syntax diagram covered based on pairwise coverage of a subset.

## Make failures smaller and more valuable

Add dependency-aware reduction that repeatedly removes clauses/objects while an
external harness confirms the same failure signature. Preserve the original case,
seed/model hash, SQL, environment and product output. Use mutation tests to show
that oracles catch missing defaults, reversed keys, wrong referential actions,
truncated routine text and lost partition overrides. The DDL diff has such a test
over the exemplar ([diff review](history/reviews/diff-product-output.md)); the
catalog comparator and routine text checks do not yet. The diff still models no
`ALTER TABLE` form other than an added constraint.

Eventually rank campaign work by uncovered source-reviewed branches, historical
defect yield, risk and execution cost. Thousands of repeated names are load coverage;
they are a separate budget from semantic diversity.
