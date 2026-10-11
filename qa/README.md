# QA inputs

Files the tools read to generate and judge test cases. They cite the IBM-derived
reference in [kb/](../kb/README.md) but are repository-authored test design, not
IBM truth. Locations are defined once in [tools/paths.py](../tools/paths.py).

| Path | Read by | Checked by | Purpose |
|---|---|---|---|
| [models/](models) | `qa.py build`, `ddl.py plan` | `test_qa`, `test_relational`, `test_routine_models`; `qa.py validate` | Bounded campaign families: dimensions, constraints, nodes, catalog oracles ([extending](../docs/workflows/extending.md)) |
| [profiles/example.json](profiles/example.json) | `lint`, `diff`, `bundle`, `build` | `test_qa` | Unverified example environment ([environment](../docs/environment.md)) |
| [variety-baseline.json](variety-baseline.json) | `ddl.py coverage --baseline` | `test_db2check` | `core` and `extended` syntax-variety requirements for QA schemas |
| [schemas/request.schema.json](schemas/request.schema.json) | `ddl.py plan` | `test_ddl` | Structured authoring requests ([requests and plans](../docs/workflows/requests-and-plans.md)) |
| [schemas/test-case.schema.json](schemas/test-case.schema.json) | `qa.py validate-case`, tests | `test_kb`, `test_evidence` | Persistent test-case records, including those `build` and `bundle` write and the outcomes `qa.py record` adds |
| [legacy-agent/](legacy-agent/README.md) | `agent.py`, `ddl.py plan` (object registry) | `test_kb`; `agent.py validate` | Earlier recipe layer, fixtures and SQL templates; kept for the view scaffold and manual authoring |

The six models are `table-core`, `table-relational`, `tablespace-pbg`, `index-core`,
`trigger-basic` and `procedure-native`; `python3 tools/qa.py models` lists them with their axes.
`legacy-agent/environments.json` is a manual design input that no tool reads.
`agent.py validate` checks token use only for the four templates that have a
`.manifest.json`; the other seven templates have none.

Put real environment values in the git-ignored `local-profiles/`, never here.
