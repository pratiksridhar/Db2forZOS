# Documentation

How to work in this repository. Start with [AGENTS.md](../AGENTS.md) for the rules and
the [README](../README.md) for the overview.

## Workflows

| Need | Read |
|---|---|
| A business-domain schema (most requests) | [Domain schemas: SQL-first](workflows/domain-schema.md) |
| Requirements turned into exact model selections | [Requests and plans](workflows/requests-and-plans.md) |
| Cases from a bounded modeled family | [Modeled campaigns](workflows/campaign.md) |
| Judging product-generated DDL and catalog evidence | [Product verification](workflows/product-verification.md) |
| A new clause, object family or checker rule | [Extending](workflows/extending.md) |

## Reference

| Need | Read |
|---|---|
| Every command, option and exit code | [Command reference](commands.md) |
| Subsystem settings and profiles | [Environment and profiles](environment.md) |
| A prompt to give an agent for a common task | [Reusable prompts](prompts.md) |
| Code layout and where to add a checker rule | [Tool code map](../tools/README.md), [test map](../tests/README.md) |

## Test design

| Need | Read |
|---|---|
| Coverage axes and the comparison policy | [Coverage model](test-design/coverage-model.md) |
| The ordinary foreign-key case suite | [FK case design](test-design/create-table-foreign-key-test-cases.md) |

## Planning and history

Dated records describe the repository when they were written; paths in them may have moved.

| Need | Read |
|---|---|
| Planned gaps and priorities | [Roadmap](roadmap.md) |
| Path moves and change chronology | [Changelog](history/CHANGELOG.md) |
| The original campaign source baseline | [Campaign source review](history/source-review.md) |
| Compiler, cleanup and SQL-processor audit | [Compiler review](history/reviews/compiler.md) |
| Static checker, diff and bundle sources | [Checker review](history/reviews/ddl-checker.md) |
| Trigger and procedure source review | [Routine review](history/reviews/routines.md) |
| Parent/child table model source review | [Relational table review](history/reviews/table-relational.md) |
