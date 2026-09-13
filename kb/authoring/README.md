# A daily utility for a QA engineer and an LLM

Describe the objects you need, let the agent map your requirements to exact model
values, then generate a reproducible campaign or author the missing source-reviewed
case. The repository needs no particular LLM, service account or network API.
Its Python command-line utilities use the standard library.

## Start from the use case

Give an agent this prompt from the repository root:

> Read AGENTS.md and kb/authoring/README.md. Create DDL for this use case: [describe
> objects, clauses, column types, relationships, body text, formatting and boundaries].
> Write a structured request and run tools/ddl.py plan. Inspect the exact model
> values and source references; report every unmet requirement. Use only IBM Db2
> 13 for z/OS documentation to resolve gaps, recording the reviewed edition and
> section. Produce the SQL and persistent design cases with dependencies, cleanup,
> catalog expectations and behavioral checks. Keep unknown subsystem settings
> explicit. Do not execute SQL. Validate the artifacts and tell me which requested
> dimensions remain uncovered.

The request is the agreement about what to generate. The agent translates natural
language into this structure; `ddl.py` does not call an LLM or parse prose. Its
`intent` stays verbatim for review. A requirement hidden only in `intent` cannot be
checked automatically, so record each requirement as exact selections or an entry
in `requirements`.

```sh
python3 tools/qa.py models
python3 tools/ddl.py context index
python3 tools/ddl.py plan \
  --request kb/authoring/examples/index-include.json \
  --out /tmp/index-include-plan.json --require-modeled
```

The example requests unique indexes with INCLUDE, and crosses the remaining
modeled key-order, padding and free-space choices. The plan lists the exact
selected combinations, SQL fragments, constraint predicates, filtered coverage
denominator, full model denominator and a concrete `offline_build_argv` for each
independent object family. Execute that argument list through a process API,
or quote it correctly for your shell, after reviewing the plan. It calls
`tools/qa.py build`, which writes the DDL bundle and executes no SQL.

Every plan has `status: design` and `review_status: agent_review_required`, even
when `structured_scope_has_gaps` is false. A clause ID means a compiler path is
tagged with that clause; it does not prove all its syntax branches are implemented
or that it satisfies a prose request. Read the selected SQL fragments and the
linked IBM syntax diagrams, descriptions, restrictions, defaults and catalog
definitions. Existing links do not constitute a new source review.

## Request fields and exact selections

Use [request.schema.json](request.schema.json) and the
[index example](examples/index-include.json). Root fields are:

- `schema_version`, `id`, `intent`, `objects`: required. Each object has a unique
  instance `id`, an object type such as `table`, and an optional exact `model` ID.
- `profile`: a profile path relative to the repository root, or an absolute path.
  Missing or incompatible profiles leave a gap. The example profile permits
  offline design and remains explicitly unverified.
- `strategy`: `pairwise` by default; also `three-way`, `each-choice`, `exhaustive`.
  `budget` is an optional limit from 1 through 999 positive cases per family.
  `negative: true` requests isolated companions for each encoded constraint.
- `run_prefix`: one or two uppercase alphanumeric characters, starting with a
  letter; defaults to `QA`. Object position supplies two more digits, such as
  `QA01`. `output_root` defaults to `generated/<request-id>`. Use new values for
  another run; campaign generation refuses to overwrite existing output.

Each object's `select` maps exact dimension names to nonempty lists of exact
model values. Values on the same axis are OR choices; axes are combined with AND.
An omitted axis retains all its modeled values. For example:

```json
"select": {
  "column": ["decimal-min", "decimal-max", "varchar-default"],
  "audit": ["omitted", "none"],
  "append": ["no"]
}
```

This is a `table-core` selection. It exercises omitted AUDIT and explicit
`AUDIT NONE` separately. It does not request an arbitrary DECIMAL precision or
every VARCHAR length. Unknown axes/values and infeasible combinations stay
explicit gaps; the planner never silently substitutes a nearby value.

`clause_refs` and `rule_refs` contain fully qualified normalized IDs, for example
`table.identity` and `table.identity-cardinality`. They select relevant knowledge
and check whether the preview has matching compiler paths and rule citations.
They do not add SQL clauses or turn prose rules into executable predicates.
Use `tools/kb.py clauses table`, `tools/kb.py rules table`, and `tools/qa.py models`
to discover exact IDs rather than guessing them.

The plan includes all normalized clauses and rules for relevant objects, IBM
source URLs, and the complete body-statement matrix when triggers are relevant.
Request, KB, model, profile, tool and request-schema hashes support reproducibility.
With the same inputs and repository version the output is deterministic.

## Bespoke schemas and text stress tests

The [bespoke schema example](examples/bespoke-schema.json) preserves requirements
that need authoring rather than claiming a model already satisfies them:

```sh
python3 tools/ddl.py plan \
  --request kb/authoring/examples/bespoke-schema.json \
  --out /tmp/bespoke-schema-plan.json --require-modeled
```

The plan is still written, but the command returns 1 for its explicit gaps.
Return 0 means a plan was produced, and with `--require-modeled` also means no
structured gap was found. Return 2 means invalid input or an I/O error. No return
code proves Db2 syntax acceptance. A plan file supplied with `--out` is created
exclusively, so an existing file is never overwritten.

An object's `depends_on` names other request instances. Missing instances and
cycles are errors; a valid graph gives `dependency_order`. This orders the
authoring task only. Independent campaign bundles do not connect arbitrary
requested objects to each other. Connected instances receive no build command
until their topology is implemented in one model or a manually authored case.
Model-internal prerequisites, including its table and enforcing-index nodes,
remain available in the plan's model dependency list.

Put additional requirements in `requirements`, each with `id`, `kind`, `text` and
the affected instance IDs in `objects`. Kinds are `syntax`, `formatting`, `length`,
`dependency`, `behavior`, `environment` and `coverage`. Every free-form requirement
remains an agent-review gap. Once the agent implements it, replace the requirement
with exact model selections where possible, or preserve the completed review and
evidence alongside a manually authored case. Do not delete an unresolved
requirement merely to get a green exit code.

For body text, state the intended comments, newlines, quotes, embedded semicolons,
case and trailing spaces explicitly. A formatting transformation must preserve
literal contents and statement boundaries. Record the client's outer terminator;
SQL PL bodies must not be split on every semicolon. Length requirements must say
whether they count characters, encoded bytes, source records, or body text, and
which client/encoding applies. A 72-column source requirement is a client/workload
constraint, not an assumed universal Db2 DDL limit.

For unsupported syntax, review official IBM Db2 13 sources and use
[EXTENDING.md](../campaigns/EXTENDING.md) to add a bounded model with source/rule
references, dependency nodes, catalog oracles and regression coverage. For a
one-off case, use [the case schema](../data/test-case.schema.json) and
[sample case](../test-design/sample-case.json), then run:

```sh
.venv/bin/python tools/qa.py validate-case path/to/case.json
```

This validates case structure and references. It is not an SQL parser, and it
cannot establish acceptance by Db2.

## Finish the QA loop

Before executing, record the actual function level, APPLCOMPAT, CURRENT RULES,
subsystem defaults, active buffer pools, storage and privileges. Ask for missing
runtime facts while continuing offline authoring with an explicitly unverified
profile. Preserve negative-case SQLCODE/SQLSTATE as null until sourced or observed;
setup must succeed before an intended action failure counts.

Use [the campaign evidence protocol](../campaigns/README.md) to keep source
acceptance, actual product extraction, replay and semantic verification separate.
Retain the administration-product version/options, actual generated SQL, name
mappings and statement-level results. Compare scoped catalog fields and run
behavioral probes where catalogs cannot capture the requirement. A reference
replay generated by this repository does not establish product correctness.

Deliver the SQL, request/plan, design case records, uncovered scope and static
check results. State plainly whether any live Db2 or product execution occurred.
