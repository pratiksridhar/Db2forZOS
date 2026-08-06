# OFS DDL coverage model

## Objective

The unit under test is not merely whether Db2 accepts one `CREATE` statement. For RC/Query and Object Framework Services (OFS), a complete test proves that:

1. source DDL creates the intended object under a recorded subsystem context;
2. OFS discovers that definition and emits executable DDL;
3. the emitted DDL creates an equivalent object under clean names; and
4. source and recreated objects have equivalent catalog semantics, including child and implicit objects.

Text comparison remains valuable for spelling, qualification, ordering, and regression review, but catalog equivalence is the primary semantic oracle. IBM statement references and catalog-table descriptions listed in [sources.md](../sources.md) are the authority.

## Durable case shape

Store every reusable case as a JSON record conforming to [test-case.schema.json](../data/test-case.schema.json). A case should have one clearly named **primary variation**. Its companion cases expand that variation systematically:

| Companion | Purpose | Example |
|---|---|---|
| omitted | exercise the documented default | omit table-space `CLOSE` |
| explicit default | distinguish omission from explicit syntax | `CLOSE YES` |
| alternate | cover each legal enum/member | `CLOSE NO` |
| lower boundary | minimum accepted value | `PCTFREE 0` |
| upper boundary | maximum accepted value | `PCTFREE 99` |
| just outside | prove Db2 rejects the boundary violation | `PCTFREE 100` |
| illegal pair | exercise mutual exclusion or context | PBG plus `USING VCAT` |
| dependency | expose deferred or child behavior | valid stogroup followed by failed allocation |
| round trip | detect lost/defaulted/transformed attributes | OFS DDL recreates the same catalog state |

Use identifiers such as `DB2Z13-<OBJECT>-<FEATURE>-<nnn>`, for example `DB2Z13-TABLESPACE-TYPE-001`. Keep a family prefix stable so related cases sort together.

## Test categories

- `positive`: a legal explicit variant.
- `negative`: a syntactic, semantic, authorization, or environment rejection with the expected failure layer recorded.
- `boundary`: minimum, maximum, and one-past-limit behavior.
- `default`: omitted versus explicit-default comparison.
- `interaction`: two or more clauses whose combination changes legality or meaning.
- `round_trip`: OFS extraction, generation, recreation, and semantic comparison.
- `dependency`: parent/child, enforcement, implicit-object, or drop-order behavior.
- `operational`: Db2 accepts the definition but DFSMS, ICSF, allocation, compression hardware, or another external facility later accepts or rejects its use.

Do not label a storage or authorization failure as a syntax failure. Negative cases must state the expected failure phase: prepare/execute, data-set allocation, data change, rebuild, or OFS generation.

## Five-layer validation pipeline

### 1. Context and prerequisites

Record Db2 release, activated function level, package `APPLCOMPAT`, `CURRENT RULES`, data-sharing state, active buffer pools, relevant subsystem parameters, SMS/DFSMS capabilities, and authorization prerequisites. A default case is reproducible only when the parameter that supplies that default is recorded.

### 2. Source execution

Execute the source DDL in dependency order. Capture SQLCODE, SQLSTATE, message text, warnings, and whether an object was left incomplete or in a pending state. Issue `COMMIT` at intentional boundaries so OFS is not observing a transient uncommitted definition.

### 3. OFS generation

Generate DDL for the requested root object and record:

- tool/product build and configuration;
- selected generation options;
- root and dependent objects requested;
- exact output as an immutable artifact;
- any OFS warning or unsupported clause indication.

### 4. Clean-name recreation

Apply a deterministic name map to every identifier, including dependent index, LOB, XML, and constraint names. Execute the generated DDL in a clean database/schema or after proving target names absent. Capture the same execution evidence as for the source.

### 5. Semantic and textual comparison

Run [catalog-verification.sql](catalog-verification.sql) for both name sets. Compare only columns relevant to the feature plus dependency counts and partition rows. Normalize environment-generated values such as OBID, DBID, PSID, timestamps, internal data-set names, creator/owner when deliberately changed, and statistics unless the case targets them.

Keep a second textual assertion set for tokens OFS must emit or omit. Text assertions catch regressions that catalog equality can hide, such as an accepted legacy synonym, a dropped explicit default, lost `ASC`/`DESC`, or a qualified name that resolves differently in another SQLID.

## Coverage axes by object

### STOGROUP

- explicit single/multiple volumes, nonspecific `'*'`, and SMS-class-only allocation;
- required `VCAT`, name boundaries, all SMS class combinations, and encryption label states;
- specific/nonspecific mixing and duplicate-volume negatives;
- DDL-time success versus allocation-time failure;
- parent default propagation to table and index spaces.

### DATABASE

- every regular default omitted and explicitly named;
- 1/8-character, reserved, implicit-pattern, delimited, and duplicate names;
- ASCII/EBCDIC/UNICODE and buffer-pool page sizes;
- regular versus data-sharing work-file form, member qualification, and forbidden CCSID/page sizes;
- inherited defaults versus child overrides.

### TABLESPACE

- PBG type resolution: no partition specification, `MAXPARTITIONS`, and `MAXPARTITIONS` plus `NUMPARTS`;
- PBR type resolution: `NUMPARTS` without `MAXPARTITIONS`, RPN versus deprecated absolute page numbers;
- page size × `DSSIZE` × partition-count boundaries;
- table-space values, one partition override, and a second inheriting partition;
- Db2-managed omitted storage, `USING STOGROUP`, and legal/illegal `USING VCAT`;
- base, work-file `FOR SORT`/`FOR DGTT`, and separate LOB grammar;
- compression, logging, allocation, free space, locking, group-buffer caching, and tracking defaults/interactions;
- current UTS behavior versus explicitly tagged lower-`APPLCOMPAT` compatibility cases.

### TABLE

- explicit elements, `LIKE`, `AS ... WITH NO DATA`, and MQT definition families;
- data-type aliases, defaulted parameters, every documented minimum/maximum, and page-size row fit;
- nullable/not-null and omitted, `DEFAULT`, `WITH DEFAULT`, valued, and forbidden defaults;
- each generated-column form with omitted/explicit `ALWAYS`, legal `BY DEFAULT`, correct ROWID token order, required type, nullability, and forbidden-default companions;
- column/table forms of primary, unique, foreign, temporal, and check constraints;
- explicit table-space placement, implicit space in an existing database, and fully implicit placement;
- PBG/PBR, composite mixed-direction partitions, null placement, partial keys, extrema, and out-of-range values;
- `LIKE` versus AS-result copy-option legality, option permutations, and duplicate-option negatives;
- LOB and XML implicit/supporting objects, including every XML schema-specification branch;
- table attributes such as audit, capture, volatility, append, procedures, hidden columns, restrict-on-drop, and key labels;
- top-level, column, identity, and MQT option permutations plus duplicate-clause negatives;
- accelerator-only syntax and restriction negatives in an accelerator-enabled environment; and
- compatibility synonyms and deprecated hash/non-UTS paths only under a recorded compatible environment.

### INDEX

- ordinary, unique, `UNIQUE WHERE NOT NULL`, expression, XML, auxiliary, and temporal forms;
- 1/64 keys, duplicate keys, direct/key-expression length formula boundaries, and order choices;
- null-bearing uniqueness and include/exclude-all-null behavior;
- partitioning index, DPSI, and NPI on one PBR table; nonpartitioned-only indexes on PBG;
- `PADDED`/`NOT PADDED`, subsystem default, varying/nonvarying, and prohibited data types;
- storage and per-partition override precedence, free space, compression/page size, `DSSIZE`, `PIECESIZE`, defer, copy, and define;
- explicit enforcing index, implicit enforcing index, and incomplete-definition sequencing.

### TRIGGER

- basic (`MODE DB2SQL`) versus advanced (no `MODE DB2SQL`) and their catalog/package discriminators;
- `BEFORE`, `AFTER`, and `INSTEAD OF` crossed with `INSERT`, `DELETE`, `UPDATE`, and legal `UPDATE OF` lists;
- row versus statement granularity, including zero-row statement activation and every legal/illegal transition row/table declaration;
- omitted/true/false/unknown/subquery `WHEN` conditions and the `INSTEAD OF` prohibition;
- every one of the 12 basic direct and 11 advanced direct body families at its allowed activation times;
- all 15 trigger-usable SQL control forms and the prohibited `RETURN` companion;
- all 35 supported and 34 excluded nested SQL-procedure-statement rows from [the body matrix](../trigger-body-statements.md);
- complex advanced blocks with declarations, handlers, cursor flow, loops, diagnostics, and dynamic SQL;
- permitted nested `CREATE TABLE` (without LOB/XML), `CREATE INDEX`, and `CREATE VIEW`, plus prohibited `CREATE STOGROUP`, `CREATE DATABASE`, `CREATE TABLESPACE`, and `CREATE TRIGGER` cases;
- RCAC-driven `SECURED`, advanced versions, active version, `OR REPLACE`, trigger package options, dependencies, and both recorded `APPLCOMPAT` values;
- same-event activation order and cascade-depth boundaries at valid level 16 and rejected level 17; and
- outer statement-terminator handling for compound bodies.

### PROCEDURE

- native SQL versus current external versus deprecated external SQL recognition, with native SQL as the default SQL-procedure generation path;
- zero/one/many parameters; `IN`, `OUT`, and `INOUT`; scalar and table-locator forms; type, subtype, CCSID, and ordinal preservation;
- one-statement and compound SQL PL bodies with declarations, handlers, cursors, control flow, diagnostics, dynamic SQL, and nested routines;
- data-access declarations crossed with actual read/change behavior and local nested-routine behavior;
- omitted and explicit defaults for determinism, result sets, commit behavior, special-register inheritance, qualifier/path, package owner, and bind options;
- native `V1`, added/replaced versions, active-version state, whole-definition replacement, and forbidden signature/table-parameter/autonomous changes;
- native package `TYPE='N'`, version, `APPLCOMPAT`, validity, owner, qualifier/path, and `SYSPACKDEP.DTYPE='N'` dependencies;
- `DYNAMIC RESULT SETS` boundaries, actual returned cursor count, and `WITH HOLD` interaction with commit on return;
- `COMMIT ON RETURN NO/YES`, nested invocation prohibition, and autonomous parameter/result-set/global-variable boundaries;
- COBOL/C external registration with executable name, parameter style, package path/collection, WLM, program type, security, and first-invocation evidence;
- Java and REXX language/linkage option matrices, including prohibited option pairs and REXX output-parameter ordering;
- deprecated external SQL preservation as a compatibility case, without using it as a new-object template; and
- distinct outer SQL terminator handling for compound native bodies.

## Interaction policy

Exhaustive Cartesian products are not useful. Use this rule:

1. Cover every clause/value once in a minimal positive case.
2. Cover each restriction with one focused negative case.
3. Cover all documented pairs that change type, default, or legality.
4. Use pairwise combinations for remaining independent dimensions.
5. Add three-way combinations only for a documented dependency or a past OFS defect.

For a clause controlled by environment, run at least two contexts if practical: one where omission equals the common default and one where it does not. That is how a generator that hard-codes an IBM-supplied default is distinguished from one that preserves effective semantics.

## Comparison policy

Classify fields before comparing:

| Class | Treatment |
|---|---|
| semantic definition | must match; examples: type, key order, partition boundary, compression choice |
| explicitness-sensitive | catalog may match but generated text has an assertion; examples: explicit default, synonym |
| environment-derived | compare only when environments are identical; examples: omitted buffer pool or subsystem-controlled option |
| generated identity | map/ignore; examples: DBID, OBID, PSID, internal data-set name |
| operational state/statistics | normally ignore unless targeted; examples: REORGP, cardinality, space statistics |
| authorization provenance | compare under a dedicated ownership case; examples: creator, owner |

Never compare only the parent row. Table spaces and indexes need partition rows; tables need column and constraint rows; LOB/XML cases need their support objects; unique/primary/ROWID cases need enforcing indexes and key rows. Triggers need definition/version rows, externalized statement text where present, trigger-package attributes, package dependencies, definition environment, and observable activation order when replacement is tested. Procedures need routine/version rows, ordered parameter rows, native package options/dependencies, grants when targeted, and separate first-call evidence for external program/WLM readiness.

## Cleanup and isolation

Cleanup is part of the case, not an ad-hoc shell step. Resolve exact target names, drop in reverse dependency order, and never wildcard a shared database or schema. A typical explicit stack drops procedures and triggers first, then table (and its dependent indexes), table space if still present, database, then storage group. A trigger that creates DDL objects at activation needs exact-name cleanup for those runtime effects before it can fire again. `WITH RESTRICT ON DROP`, temporal dependencies, pending states, and externally managed data sets need dedicated cleanup instructions.

Preserve failed generated DDL and catalog snapshots before cleanup; they are the evidence needed to diagnose whether the defect is discovery, serialization, ordering, or Db2 legality.
