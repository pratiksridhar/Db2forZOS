# Examples

Worked inputs and outputs that are worth tracking. Day-to-day output goes to the
git-ignored `generated/<id>/` instead.

| Path | What it shows |
|---|---|
| [varied-schema.sql](varied-schema.sql) | Five tables that pass `ddl.py lint` and meet the `core` variety baseline; CI checks it |
| [requests/index-include.json](requests/index-include.json) | A fully modeled request for `ddl.py plan` |
| [requests/bespoke-schema.json](requests/bespoke-schema.json) | A request with explicit gaps that need authoring |
| [sample-case.json](sample-case.json) | A test-case record conforming to [the case schema](../qa/schemas/test-case.schema.json) |
| [workloads/1000-table/](workloads/1000-table) | The legacy 1,000-table positive workload and its generator; load coverage, not semantic variety |
| [domains/supply-chain-logistics/](domains/supply-chain-logistics/design.md) | A 68-table domain design with generator, request, plan and case; currently fails `lint` |

A tracked domain schema gets its own `domains/<id>/` directory holding `design.md`,
`request.json`, the case record, and either `source.sql` or a `generate.py` that
writes `generated/<id>/source.sql`.
