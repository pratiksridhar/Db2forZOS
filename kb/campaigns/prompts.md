# Reusable agent requests

## Generate a campaign

> Read AGENTS.md. Generate a pairwise table-core campaign using my profile at
> local-profiles/work.json, run prefix Q02, and output generated/q02. Keep cases
> in design. Report selected cases, the valid-combination denominator, missing
> coverage, and execution prerequisites. Do not execute SQL.

## Extend one syntax family

> Read AGENTS.md and kb/campaigns/EXTENDING.md. Add a source-reviewed PBR table
> campaign using only official IBM Db2 13 documentation. Model complete range
> partitions, ascending/descending keys, relative page numbering, and required
> enforcing indexes. Encode cross-clause exclusions, isolated negatives and catalog
> oracles. Keep the existing PBG family intact and report any unsupported branches.

## Investigate a product discrepancy

> Read the case record, contract, source/replay catalogs and actual product-generated
> SQL in the supplied case directory. Identify whether the failure belongs to setup,
> Db2 acceptance, product extraction, name mapping, replay, or semantic comparison.
> Show the smallest relevant difference with IBM source references. Do not infer
> success from missing evidence. Propose a smaller reproducer preserving the same
> dependency and effective environment.

## Fill a coverage gap

> Run tools/qa.py inventory. For CREATE TABLE, rank the unmodeled features by likely
> DDL regeneration defect yield, required infrastructure, and dependency complexity.
> Implement one bounded family with IBM evidence, positive and negative cases,
> catalog/behavior assertions and regression checks. State the exact new coverage
> denominator and what remains unmodeled.
