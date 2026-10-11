# Db2 for z/OS DDL QA workbench

Generate varied test objects from an IBM-derived knowledge base, extract their DDL
with your administration product, and check that recreation preserves their
semantics. **Variety of catalog states is the goal, not volume.** Agents should
start with [AGENTS.md](AGENTS.md).

No command connects to Db2 or executes SQL, and no particular LLM vendor, API key
or service is required. The tools need Python 3.10+ and the standard library.

## Quick start

Check any DDL script, including agent-written or product-generated SQL:

```sh
python3 tools/ddl.py lint my-schema.sql --profile qa/profiles/example.json
python3 tools/ddl.py coverage my-schema.sql --baseline core
python3 tools/ddl.py bundle my-schema.sql --run QA1 --out generated/qa1 \
  --profile qa/profiles/example.json \
  --replay-schema APP=APPR --replay-database APPDB=APPRDB
python3 tools/ddl.py diff generated/qa1/source.sql product-generated.sql \
  --map generated/qa1/name-map.json --text
```

Or build a campaign from a modeled family:

```sh
python3 tools/qa.py models
python3 tools/qa.py build --model table-core --profile qa/profiles/example.json \
  --run T01 --out generated/table-demo
```

Open `generated/table-demo/RUN.md`. **The example profile is unverified.** Record
real subsystem values first; see [environment and profiles](docs/environment.md).

## Where to go next

| I want to | Read |
|---|---|
| Design a business-domain schema (most requests) | [Domain schemas: SQL-first](docs/workflows/domain-schema.md) |
| Generate cases from a modeled family | [Modeled campaigns](docs/workflows/campaign.md), [requests and plans](docs/workflows/requests-and-plans.md) |
| Judge product-generated DDL and catalog evidence | [Product verification](docs/workflows/product-verification.md) |
| Add a clause, object or checker rule | [Extending](docs/workflows/extending.md) |
| Look up every command and exit code | [Command reference](docs/commands.md) |
| Ask an agent for a common task | [Reusable prompts](docs/prompts.md) |
| Look up IBM syntax, defaults and sources | [IBM-derived reference](kb/README.md) |
| See what is planned or how we got here | [Roadmap](docs/roadmap.md), [changelog](docs/history/CHANGELOG.md) |
| Design cases systematically | [Coverage model](docs/test-design/coverage-model.md), [FK case design](docs/test-design/create-table-foreign-key-test-cases.md) |

## Layout

| Path | Holds | Rule |
|---|---|---|
| [kb/](kb/README.md) | IBM-derived chapters, normalized JSON, source manifest | Only official IBM Db2 13 for z/OS content |
| [qa/](qa/README.md) | Models, profiles, schemas, variety baseline, legacy agent layer | Inputs the tools read |
| [examples/](examples/README.md) | Exemplar SQL, request examples, domain schemas, workloads | Tracked worked examples |
| [docs/](docs/README.md) | Workflows, commands, environment, roadmap, dated reviews | How to work; history under `docs/history/` |
| [tools/](tools/README.md) | `ddl.py`, `qa.py`, `kb.py`, `agent.py` and their libraries | Locations live in `tools/paths.py` |
| [tests/](tests/README.md) | Unit and regression tests | Run before every change |
| `generated/`, `local-profiles/` | Your output and real environment values | Ignored by git |

Repository checks are listed in [the command reference](docs/commands.md#repository-checks).
A passing check is never evidence that Db2 accepts the SQL or that the product
regenerates it correctly; only an executed, recorded case can show that.
