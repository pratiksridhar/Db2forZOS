# Reproducible DDL campaigns

Create source objects, extract their definitions using the administration product,
replay that output, and compare the resulting semantics. This is the executable
layer above the existing reference KB and agent recipes.

## First campaign

The command-line tools require Python 3.10+ and use the standard library. Run from
the repository root, or pass the absolute path to `tools/qa.py` from elsewhere.

```sh
python3 tools/qa.py models
python3 tools/qa.py build \
  --model table-core \
  --profile kb/campaigns/profiles/example.json \
  --run T01 --strategy pairwise \
  --out generated/table-demo
```

Open `generated/table-demo/RUN.md`. The example profile is **unverified**, including
its illustrative storage group `QASTG`. The builder executes no SQL and never
overwrites an existing output directory. Choose a new run prefix and output path
for another campaign. Run prefixes are 2–4 uppercase alphanumeric characters,
starting with a letter. Case object names incorporate that prefix.

For work, copy the profile into ignored `local-profiles/`. Record actual subsystem
values there; do not put credentials into this repository. Both activated function
level and APPLCOMPAT are checked against model gates. Current models require
`CURRENT RULES DB2`; database-fixture models additionally require recorded active
4 KB pools, `BP0` through `BP49`.
A verified profile requires verification evidence, but cases still start in `design`.

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
  at least one nullable FK column. See [review](reviews/table-relational.md).
- **trigger-basic:** NO CASCADE BEFORE INSERT/UPDATE OF, optional WHEN, and five
  body layouts, including comments and a body longer than 6,000 characters.
- **procedure-native:** IN/OUT parameters, SQL data-access and determinism choices,
  and five compound-body layouts. Both procedural families include text capture and
  behavioral probe specifications. See [review](reviews/routines.md).

`--set AXIS=VALUE` selects exact modeled options. Repeat the same axis for an OR
subset; different axes are ANDed. Unknown or infeasible values fail before output
creation. Negative companions must remain isolatable within these filters.

```sh
python3 tools/qa.py build --model index-core \
  --profile kb/campaigns/profiles/example.json \
  --run I01 --negative --out generated/index-demo
python3 tools/qa.py build --model tablespace-pbg \
  --profile kb/campaigns/profiles/example.json \
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
and per-case records conforming to `kb/data/test-case.schema.json`.

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
verified separately. See [processor review](reviews/compiler.md).

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

## Catalog evidence protocol

Run the generated catalog queries with your local SQL client or test harness.
An adapter exports each result set under the query ID printed in the SQL file:

```json
{
  "case_id": "DB2Z13-TABLE-T01-001",
  "side": "source",
  "catalog": {
    "table": [{"TYPE": "T", "AUDITING": " ", "DATACAPTURE": " ", "APPEND": "N"}]
  }
}
```

This is a format illustration, not a complete table-case snapshot. Every query in
the case contract must be present. Use uppercase column names, JSON numbers for
numeric values, JSON null for SQL NULL, and lossless strings for text. Do not trim
DEFAULTVALUE or change letter case. Identify the second export with `side: replay`.

```sh
python3 tools/qa.py compare \
  --contract generated/table-demo/cases/DB2Z13-TABLE-T01-001/catalog-contract.json \
  --source source-catalog.json --replay replay-catalog.json
```

Exit codes: **0** selected fields match and encoded expectations hold; **1** semantic
differences or failed expectations; **2** malformed/missing evidence or bad inputs.
Rows are compared by declared keys independent of export order. Missing columns,
duplicate keys and unexpected row counts are rejected. Only explicitly declared
catalog padding fields are right-trimmed; literal defaults retain whitespace.
Case IDs and source/replay sides must agree with the contract.

The comparator checks encoded source expectations as well as source/replay equality.
This prevents identical wrong definitions from passing those assertions. Current
contracts cover only their listed fields. Identity generator options, dependencies,
all partition attributes, and DML behavior need additional contracts/probes before
claiming comprehensive semantic equivalence.

## Evidence needed for a product test pass

Keep these separate in the external harness or case artifacts:

1. Source setup/action acceptance, subsystem identity, effective settings and diagnostics.
2. Source catalog assertions and any required behavioral probes.
3. Product version/options, exact extraction scope, raw generated SQL and name map.
4. Actual replay SQL and statement-level acceptance results in the clean target.
5. Catalog comparison and behavioral probe outcomes, plus cleanup ownership/results.

The offline compiler/comparator does not promote a case to `pass`. Only the harness
that has all required evidence can do so. Negative Db2 syntax cases cannot directly
test product extraction because their target objects should not exist.

## Future agents

```sh
python3 tools/qa.py context table > table-context.json
python3 tools/qa.py inventory
python3 tools/kb.py show table identity-cardinality --json
.venv/bin/python tools/qa.py validate-case path/to/case.json
```

`validate-case` also supports manually/agent-authored records from the wider KB.
It requires `requirements-dev.txt`, checks the full case schema, IBM source IDs
and unresolved placeholders, and does not parse or validate arbitrary Db2 SQL.

See [prompts.md](prompts.md) for reusable requests,
[EXTENDING.md](EXTENDING.md) for model authoring, and
[ROADMAP.md](ROADMAP.md) for the remaining high-value expansion.
