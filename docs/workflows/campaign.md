# Modeled campaigns

Bounded families the compiler models end to end: dimensions, constraints,
dependency nodes and catalog oracles in [qa/models](../../qa/models). Use a
[request and plan](requests-and-plans.md) to choose exact values, or call
`qa.py build` directly. [Product verification](product-verification.md) covers
what happens after a bundle is executed.

## First campaign

The command-line tools require Python 3.10+ and use the standard library. Run from
the repository root, or pass the absolute path to `tools/qa.py` from elsewhere.

```sh
python3 tools/qa.py models
python3 tools/qa.py build \
  --model table-core \
  --profile qa/profiles/example.json \
  --run T01 --strategy pairwise \
  --out generated/table-demo
```

Open `generated/table-demo/RUN.md`. The example profile is **unverified**, including
its illustrative storage group `QASTG`. The builder executes no SQL and never
overwrites an existing output directory. Choose a new run prefix and output path
for another campaign. Run prefixes are 2–4 uppercase alphanumeric characters,
starting with a letter. Case object names incorporate that prefix.

Profiles, local copies and the environment values models gate on are described
in [environment and profiles](../environment.md).

## Available executable families

- **table-core:** 14 column profiles, including DECIMAL precision boundaries,
  timestamp precision boundaries, identity modes, nullable/default variants,
  hidden columns and row-change timestamps; crossed with audit, data capture and
  append choices. Physical placement is an explicit logged PBG table space.
- **tablespace-pbg:** segment sizes 4/32/64, maximum partitions 1/4, DSSIZE 1/4 GB,
  and ANY/PAGE/ROW lock sizes. These are selected test values, not all Db2 limits.
- **index-core:** uniqueness, INCLUDE, ASC/DESC, padding, FREEPAGE 0/1/255 and
  PCTFREE 0/10/99. Valid generation excludes INCLUDE on nonunique indexes and
  PARTITIONED indexes on PBG tables. `--negative` adds one isolated case for each
  of those two constraints; expected SQLCODE and SQLSTATE remain null.

The 14 column profiles are intentionally independent column definitions, not a full
cross product of data types and column clauses. A boundary in one profile does not
establish coverage of every data-type boundary.

- **table-relational:** composite parent primary key, unique constraint and both
  enforcing indexes before the child table; five delete-clause choices, three FK
  nullability patterns, four payload types and three CHECK shapes. SET NULL requires
  at least one nullable FK column. See [review](../history/reviews/table-relational.md).
- **trigger-basic:** NO CASCADE BEFORE INSERT/UPDATE OF, optional WHEN, and five
  body layouts, including comments and a body longer than 6,000 characters.
- **procedure-native:** IN/OUT parameters, SQL data-access and determinism choices,
  and five compound-body layouts. Both procedural families include text capture and
  behavioral probe specifications. See [review](../history/reviews/routines.md).

`--set AXIS=VALUE` selects exact modeled options. Repeat the same axis for an OR
subset; different axes are ANDed. Unknown or infeasible values fail before output
creation. Negative companions must remain isolatable within these filters.

```sh
python3 tools/qa.py build --model index-core \
  --profile qa/profiles/example.json \
  --run I01 --negative --out generated/index-demo
python3 tools/qa.py build --model tablespace-pbg \
  --profile qa/profiles/example.json \
  --run S01 --out generated/space-demo
```

## What coverage means

`pairwise` uses a deterministic greedy selector over **valid modeled combinations**.
It covers each feasible pair of dimension values and every feasible individual
value. It is not claimed to produce the smallest possible suite. Constraints are
evaluated before selection; combinations with unsupported values do not count in
the valid denominator.

`each-choice` covers each feasible individual value. `exhaustive` selects every
valid modeled combination. `--budget N` limits positive cases; requested negative
companions are additional. Reports retain the uncovered interactions and set
`complete: false` when the budget is insufficient. For exhaustive runs, completeness
also requires every valid combination, even when all individual values are covered.
The engine limits raw products to 100,000 and output to 999 cases per campaign.

`three-way` covers every feasible triple, pair and individual value. After `--set`,
coverage is relative to the filtered family. The report also retains the full
model's raw and valid combination counts. Budgeted results never hide uncovered
interactions.

`coverage.json` measures **design selection**, with runtime passes initially zero.
`tools/qa.py inventory` separately reports which normalized clauses have any
compiler path and which have none. Neither report claims complete IBM syntax,
restriction, behavior, or product coverage. Rule references provide traceability;
they are not all executable constraint predicates.

## Bundle and execution boundary

Each bundle contains the model snapshot, profile, IBM source links, hashes of the
model/KB/compiler, coverage report, preflight SQL, source/replay database bootstrap,
and per-case records conforming to `qa/schemas/test-case.schema.json`.

Each case has setup, action, source, cleanup, source/replay catalog queries and a
catalog contract. Positive cases also have reference replay SQL. Run source setup
before the action and retain statement-level results. If setup fails, the case is
blocked, even if the action returns an expected-looking error.

The two database names end in `SDB` and `RDB`; source and replay use different
schemas. Standalone `procedure-native` uses no campaign database, so its bootstrap
and database-cleanup files contain comments only; its profile needs no storage-group
or buffer-pool fields. Preflight checks must return zero rows, and CREATE errors must stop the
run. Do not continue against preexisting objects. A fresh prefix is the simplest
way to avoid a collision. No automatic suffixing hides a previous test run.

**Replay the actual product-generated SQL to test the product.** Reference replay
only tests the repository's harness. Preserve extraction version/options and use
product name mapping or an SQL-aware adapter. Never rewrite quoted literals or
routine bodies with global replacement. Extract the required table-space and
dependency definitions too; the replay database alone is not a complete fixture.

Cleanup scripts contain destructive DROP statements but are never executed by the
tools. Drop only objects recorded as created in this run. Per-case cleanup may
contain absent targets after negative/failed cases; use the creation ledger.
`cleanup-databases.sql` drops the **entire two dedicated campaign databases**.

Tables in the explicit UTS fixtures are cleaned through their owning table spaces.
This avoids directly dropping enforcing indexes or issuing a redundant space DROP
after DROP TABLE has already removed it. Procedures require their separate case
cleanup even if the campaign databases are dropped.

## Body text and SQL processor settings

Every bundle records its outer terminator; all `.sql` files in that bundle use it.
SQL PL families use `@`, preserving internal semicolons, comments, case and literal
whitespace. JSON statement arrays contain exactly one statement per item without
an outer terminator. Configure the client before submitting these files. For SPUFI,
SQLFORMAT SQLPL retains comments and line structure; other client settings must be
verified separately. See [processor review](../history/reviews/compiler.md).

`catalog-contract.json` includes text hashes, character counts, UTF-8 byte counts
and maximum line length. These describe generated source text; they do not establish
Db2 limits after target-CCSID conversion. The framing checker detects broken quotes,
comments and delimiters, but does not parse or certify arbitrary Db2 grammar.

`behavior-probes.json` supplies manual/harness probe specifications, including
mutation flags, expected results and source/replay SQL. Inspect prerequisites before
running them. Full routine definitions need lossless CLOB capture, not truncating
VARCHAR casts or blanket name replacement. Whole-definition text often contains
relocated names, so raw text capture and behavioral verification remain separate
from the selected-field comparator. A catalog match alone cannot prove body fidelity.

## Related

[Command reference](../commands.md), [prompts](../prompts.md),
[extending a family](extending.md) and the [roadmap](../roadmap.md).
