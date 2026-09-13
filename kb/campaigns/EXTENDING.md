# Add a compiler family without teaching the agent guesses

1. Choose one bounded semantic family. Confirm the object is normalized in
   `kb/data/db2z13-create-ddl.json`. For new objects, add its IBM source manifest,
   chapter, normalized clauses/rules, registry entry and case-schema support first.
2. Review exact Db2 13 syntax diagrams plus descriptions/restrictions and catalog
   tables. Record the edition, pages/topics and scope in SOURCE-REVIEW.md. Model
   individual diagram paths; do not flatten context-specific copy/generated forms.
3. Add `models/<id>.json`. `dimensions` map named values to SQL fragments, clause
   references and optional catalog assertions. SQL fragments are repository-authored
   code, not arbitrary user input. Fragments cannot contain further placeholders.
4. Add constraints as `when` implies `requires`. Conditions map axis names to one
   value or a list of accepted values; keys in a condition are ANDed. A negative
   companion must violate exactly one predicate. Keep nonexpressible conditions
   as explicit prerequisites or split the model instead of pretending they are checked.
5. Define `nodes` with IDs, dependencies, role (`setup` or `action`), SQL and DROP SQL.
   The engine sorts actual dependencies, rejects missing nodes/cycles, and reverses
   that order for cleanup. Current models require one terminal action. A node owned
   by a cascading cleanup operation uses `drop: null` and `cleanup_via` naming a
   droppable ancestor, for example a table's explicit UTS. Never directly drop an
   enforcing index. SQL PL nodes use `kind: sql_pl` and a model-level alternate
   `statement_terminator`, with internal semicolons and no outer delimiter in the node.
6. Define catalog queries with selected fields, stable keys, row-count bounds and
   explicit padding fields. Exclude relocated identities from selected fields or add
   a field-aware mapping mechanism. Do not normalize arbitrary SQL text or literals.
   Each assertion names a query, a row predicate (`where`) and exact expected fields
   (`equals`). An assertion must select exactly one row on both sides.
   Option `catalog_row_counts` can specialize exact expected row counts, such as
   two index keys versus two keys plus one INCLUDE column.
7. Give every model source references, qualified normalized clause/rule references,
   compatibility gates, and a review record. Source links show provenance; they do
   not prove all IBM restrictions have been encoded.
8. Add behavioral tests for selection completeness against an independent oracle,
   forbidden combinations, isolated negatives, correct dependency order, missing
   evidence, and a deliberately corrupted catalog. Validate emitted cases against
   the existing JSON Schema. Run the commands in AGENTS.md.

Optional model `object_names` lists tokenized qualified identities for field-aware
source/replay name mapping. Add `preflight` SQL templates for every additional
namespace/name and `prerequisites` for model-specific environment or execution
conditions. `probes` entries have IDs, SQL, expectations and a `mutates` flag;
the compiler renders both sides into manual/harness specifications without execution.
Keep each probe to a single statement and document order, client bindings and cleanup.

Set `uses_database: false` for a standalone model with no database/storage fixture.
This removes generic database bootstrap, table/index collision checks and database
cleanup, while retaining the model's own preflight and per-case cleanup. Its profile
does not require storage-group or pool fields. Such a model must supply its own
complete object/package collision checks and authority prerequisites.

Every new source/template fragment must be tested after rendering. SQL framing checks
are lexical only: a `sql_pl` label is not proof that multiple SQL statements form a
valid routine. Read IBM's diagrams and restrictions before adding the fragment.

Prefer multiple small models to a giant Cartesian product. Pairwise testing does
not cover every three-way or higher interaction. Add explicit targeted families
for known interactions, environment-dependent defaults, implicit objects, physical
partition overrides, security, and procedural behavior.
