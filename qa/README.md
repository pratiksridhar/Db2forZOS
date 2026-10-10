# QA inputs

Files the tools read to generate and judge test cases. They cite the IBM-derived
reference in [kb/](../kb/README.md) but are repository-authored test design, not
IBM truth. Locations are defined once in [tools/paths.py](../tools/paths.py).

| Path | Read by | Purpose |
|---|---|---|
| [models/](models) | `qa.py build`, `ddl.py plan` | Bounded campaign families: dimensions, constraints, nodes, catalog oracles ([extending](../docs/workflows/extending.md)) |
| [profiles/example.json](profiles/example.json) | `lint`, `diff`, `bundle`, `build` | Unverified example environment ([environment](../docs/environment.md)) |
| [variety-baseline.json](variety-baseline.json) | `ddl.py coverage --baseline` | `core` and `extended` syntax-variety requirements for QA schemas |
| [schemas/request.schema.json](schemas/request.schema.json) | `ddl.py plan` | Structured authoring requests ([requests and plans](../docs/workflows/requests-and-plans.md)) |
| [schemas/test-case.schema.json](schemas/test-case.schema.json) | `qa.py validate-case`, tests | Persistent test-case records, including those `build` and `bundle` write |
| [legacy-agent/](legacy-agent/README.md) | `agent.py`, `ddl.py context` | Earlier recipe layer, fixtures and SQL templates; kept for the view scaffold and manual authoring |

Put real environment values in the git-ignored `local-profiles/`, never here.
