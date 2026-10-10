# Examples

Worked inputs and outputs that are worth tracking. Day-to-day output goes to the
git-ignored `generated/<id>/` instead.

| Path | What it shows | Offline result |
|---|---|---|
| [varied-schema.sql](varied-schema.sql) | Five tables that exercise the whole `core` baseline; CI checks it | `lint` PASS; `coverage --baseline core` 43/43 |
| [requests/index-include.json](requests/index-include.json) | A fully modeled request for `ddl.py plan` | `plan --require-modeled` exits 0 |
| [requests/bespoke-schema.json](requests/bespoke-schema.json) | A request with explicit gaps that need authoring | `plan` exits 0; `--require-modeled` exits 1 by design |
| [sample-case.json](sample-case.json) | A test-case record conforming to [the case schema](../qa/schemas/test-case.schema.json) | `qa.py validate-case` OK |
| [workloads/1000-table/](workloads/1000-table) | The legacy 1,000-table positive workload and its generator; load coverage, not semantic variety | `lint --allow-placeholders` PASS; `core` 28/43 |
| [domains/supply-chain-logistics/](domains/supply-chain-logistics/design.md) | A 68-table domain design with generator, request, plan and case | Generated SQL fails `lint` (3 self-referencing foreign keys inside `CREATE TABLE`); `core` 11/43; `plan.json` predates the current KB and tools |

Commands are in [the command reference](../docs/commands.md); results were last checked
2026-10-10 and none of them involves Db2.

A tracked domain schema gets its own `domains/<id>/` directory holding `design.md`,
`request.json`, the case record, and either `source.sql` or a `generate.py` that
writes `generated/<id>/source.sql`.
