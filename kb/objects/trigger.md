# CREATE TRIGGER

This chapter models both IBM Db2 13 for z/OS trigger definitions:

- a **basic trigger**, identified by required `MODE DB2SQL`; and
- an **advanced trigger**, identified by the absence of `MODE DB2SQL` and available at application compatibility `V12R1M500` or later.

The complete statement inventories and compact nested-statement syntax signatures are in [trigger-body-statements.md](../trigger-body-statements.md) and [db2z13-trigger-body-statements.json](../data/db2z13-trigger-body-statements.json). This chapter focuses on the definition around that body. IBM's two CREATE statement references are indexed as `ibm-create-trigger-basic` and `ibm-create-trigger-advanced`.

## Compact statement shapes

The common trigger header is:

```text
CREATE TRIGGER <trigger-name>
  <activation-time> <event>
  ON <subject>
  [REFERENCING <transition declarations>]
  FOR EACH {ROW | STATEMENT}
  [<trigger options>]
  [WHEN (<search-condition>)]
  <body>
```

The trigger kind changes the beginning, options, and body:

```text
-- Basic
CREATE TRIGGER <trigger-name>
  ...
  MODE DB2SQL
  [WHEN (<search-condition>)]
  { <triggered-SQL-statement>
  | BEGIN ATOMIC <triggered-SQL-statement>; [...] END }

-- Advanced
CREATE [OR REPLACE] TRIGGER <trigger-name>
  [VERSION {V1 | <version-id>}]
  ...
  [<advanced bind and execution options>]
  [WHEN (<search-condition>)]
  { <SQL-control-statement> | <triggered-SQL-statement> }
```

These are navigation summaries, not replacements for IBM's railroad diagrams. In particular, option placement and subgrammars must be checked against the linked IBM Db2 13 pages.

## Basic versus advanced

| Property | Basic | Advanced |
|---|---|---|
| Discriminator | `MODE DB2SQL` is required | `MODE DB2SQL` must be omitted |
| Catalog marker | `SYSTRIGGERS.SQLPL` is blank | `SYSTRIGGERS.SQLPL = 'Y'` |
| Minimum application compatibility | no advanced-trigger gate | `V12R1M500` or later |
| Multiple statements | `BEGIN ATOMIC` containing only the 12 basic statement families | one SQL control statement, normally a compound block, containing trigger-supported SQL procedure statements |
| SQL PL variables, conditions, cursors, handlers, loops | not available | available |
| Dynamic SQL and DDL in a body | not available | available where the SQL-procedure-statement matrix permits it |
| Stand-alone fullselect and `VALUES` | allowed | not direct body statements; use `SELECT INTO` or `VALUES INTO` |
| Versions and `OR REPLACE` | no trigger versions | supported under the advanced version rules |
| Trigger package type | `SYSPACKAGE.TYPE = 'T'` | `SYSPACKAGE.TYPE = '1'` |

Conversion is not just deletion of `MODE DB2SQL`: preserve activation attributes, account for trigger versions and packages, and revalidate body syntax. See `ibm-trigger-convert`, `ibm-trigger-packages`, and `ibm-catalog-systriggers`.

## Activation time, event, and subject

```text
<activation-time> ::= [NO CASCADE] BEFORE | AFTER | INSTEAD OF
<event>           ::= INSERT | DELETE | UPDATE [OF <column> [, ...]]
<subject>         ::= ON <table-name> | ON <view-name>
```

The legal combinations are structural:

- `BEFORE` and `AFTER` apply to an eligible local base table.
- `INSTEAD OF` applies to an eligible local view.
- `UPDATE OF` is not allowed for an `INSTEAD OF` trigger.
- `FOR EACH STATEMENT` is an `AFTER`-only form. `BEFORE` and `INSTEAD OF` require `FOR EACH ROW`.
- `WHEN` cannot be specified for an `INSTEAD OF` trigger.
- `NO CASCADE BEFORE` prevents the trigger's own changes from activating additional triggers; deeper trigger cascades originate with `AFTER` actions.

The subject and every directly referenced object or local routine must exist when the trigger is created. A subject table with pending definition changes cannot receive a new trigger.

An eligible table is an existing local base table. IBM excludes materialized query, clone, temporary, auxiliary, real-time statistics, accelerator-only, catalog, and directory tables, as well as aliases and synonyms. The view restrictions are broader: among other exclusions, an `INSTEAD OF` subject cannot participate in the documented symmetric-view relationships, mix encoding schemes or CCSIDs, expose restricted underlying column types or field procedures, have only disallowed catalog/DGTT/clone bases, or have another view dependent on it. Build focused subject-negative fixtures from the full lists in `ibm-create-trigger-basic` and `ibm-create-trigger-advanced`.

## Transition rows and tables

Transition declarations have these compact forms:

```text
REFERENCING
  [OLD [ROW] [AS] <old-row-name>]
  [NEW [ROW] [AS] <new-row-name>]
  [OLD_TABLE [AS] <old-table-name>]
  [NEW_TABLE [AS] <new-table-name>]
```

Availability is determined by event, activation time, and granularity:

| Trigger form | DELETE | INSERT | UPDATE |
|---|---|---|---|
| `BEFORE ... FOR EACH ROW` | `OLD` | `NEW` | `OLD`, `NEW` |
| `AFTER` or `INSTEAD OF ... FOR EACH ROW` | `OLD`, `OLD_TABLE` | `NEW`, `NEW_TABLE` | `OLD`, `NEW`, `OLD_TABLE`, `NEW_TABLE` |
| `AFTER ... FOR EACH STATEMENT` | `OLD_TABLE` | `NEW_TABLE` | `OLD_TABLE`, `NEW_TABLE` |

Important negative cases follow from this matrix:

- only one declaration of each transition kind is permitted, and all four possible correlation/table names must be mutually unique;
- transition tables are read-only;
- only a `NEW` transition variable in a `BEFORE INSERT` or `BEFORE UPDATE` row trigger can be assigned;
- row transition variables do not exist for statement triggers;
- transition tables do not exist for `BEFORE` triggers; and
- an XML transition variable, or an XML column of a transition table, cannot be referenced by a body SQL procedure statement.

## Granularity and conditions

`FOR EACH ROW` runs once for each affected row. `FOR EACH STATEMENT` runs once for the triggering statement, including when it changes no rows. This changes both the number of activations and which transition data is available.

`WHEN (<search-condition>)` gates the body. A true result runs the body; false or unknown does not. A `BEFORE` condition fullselect cannot reference the subject table. Test true, false, unknown, and subquery conditions separately because a generator can preserve the text but change qualification or transition correlation semantics.

## Basic body

A basic body is either one allowed triggered SQL statement or an atomic list of those same statements:

```text
<triggered-SQL-statement>

BEGIN ATOMIC
  <triggered-SQL-statement>;
  [<triggered-SQL-statement>; ...]
END
```

The list is closed: `CALL`, searched `DELETE`, fullselect, `INSERT`, `MERGE`, `REFRESH TABLE`, transition-variable `SET`, `SIGNAL`, `TRUNCATE`, searched `UPDATE`, `VALUES`, and `VALUES INTO`, with activation-time restrictions. The exact matrix is in [the body statement reference](../trigger-body-statements.md#basic-trigger-body).

## Advanced body

An advanced body is exactly one outer statement:

```text
<SQL-control-statement>
    or
<advanced-triggered-SQL-statement>
```

To execute multiple statements, make that one outer statement a compound SQL PL block:

```text
BEGIN ATOMIC
  <declarations>
  <SQL-procedure-statement>;
  [<SQL-procedure-statement>; ...]
END
```

The outermost advanced-trigger compound block defaults to `ATOMIC` and cannot be `NOT ATOMIC`. A nested compound block defaults to `NOT ATOMIC`; an `ATOMIC` block cannot be nested inside an atomic block. The permitted nested statements are not every Db2 statement. IBM's trigger column in the SQL-procedure-statement matrix yields 35 supported rows and 34 excluded rows, captured without inference in [the body statement reference](../trigger-body-statements.md#advanced-nested-sql-procedure-statements).

For the existing DDL test set, the critical advanced-body result is:

| DDL statement inside a control block | Trigger-body status |
|---|---|
| `CREATE TABLE` | allowed for `BEFORE`, `AFTER`, and `INSTEAD OF`; the created table must not contain LOB or XML columns |
| `CREATE INDEX` | allowed only for `AFTER` or `INSTEAD OF` |
| `CREATE VIEW` | allowed only for `AFTER` or `INSTEAD OF` |
| `CREATE STOGROUP` | excluded |
| `CREATE DATABASE` | excluded |
| `CREATE TABLESPACE` | excluded |
| `CREATE TRIGGER` | not listed in the SQL-procedure-statement grammar and therefore not a body statement |

The DDL forms are nested SQL procedure statements, not members of the 11-statement direct-body list. Use an SQL control statement such as `BEGIN ATOMIC ... END` around them. See `ibm-sql-procedure-statement`, plus `ibm-create-table` and `ibm-create-index` for each nested DDL's full syntax.

## Body restrictions that cut across both kinds

- A `BEFORE` body cannot perform searched `DELETE`, `INSERT`, `MERGE`, `REFRESH TABLE`, `TRUNCATE`, searched `UPDATE`, or select from a data-change statement.
- The corresponding IBM restrictions also prevent a `BEFORE` body from directly or indirectly invoking routines that contain the documented broader side-effect set.
- A body cannot use host variables, an undeclared transition variable, or a declared temporary table.
- Direct references are limited to objects and local routines at the current server.
- A body cannot modify a column that belongs to a `BUSINESS_TIME` period.
- A called procedure cannot use forbidden transaction or connection control, and cannot be defined with `COMMIT ON RETURN`.
- SQL PL lists `RETURN` as a control statement generally, but IBM's `RETURN` statement explicitly prohibits it in a trigger.

Treat these as prepare/execute negatives rather than assuming that a statement's presence in the general SQL PL grammar makes it legal in every trigger context.

## Advanced options and two APPLCOMPAT values

Advanced definitions can carry package-style options such as `QUALIFIER`, `SQL PATH`, debug/WLM controls, isolation and concurrent-access behavior, dynamic rules and encoding, explain/immediate-write behavior, optimization hints, release policy, date/time/decimal formats, rounding, temporal/archive sensitivity, `APPLCOMPAT`, and statement concentration.

IBM defines the option list as order-independent, with each individual option allowed at most once. The normalized JSON groups related options for test navigation; a vertical bar between grouped signatures does not make independent options mutually exclusive.

Two application-compatibility values matter:

1. `CURRENT APPLICATION COMPATIBILITY` governs processing of the trigger definition. `SYSTRIGGERS.ENVID` links to the corresponding `SYSENVIRONMENT.APPLCOMPAT` row.
2. The advanced trigger's `APPLCOMPAT` option governs SQL in the body and is recorded in `SYSPACKAGE.APPLCOMPAT`.

Record and compare both. A round trip can preserve body behavior while silently changing the environment used to process the definition, or the reverse. Sources: `ibm-create-trigger-advanced`, `ibm-catalog-systriggers`, `ibm-catalog-sysenvironment`, and `ibm-catalog-syspackage`.

## Security, versions, and activation order

`NOT SECURED` is the ordinary default. `SECURED` is required when row or column access control applies to the subject table or to an underlying table of a subject view. Treat `SECURED` as an audited assertion, not cosmetic emitted text.

Advanced versions share the trigger's activation time, event, subject, and granularity. Version-specific elements include the transition declarations, body, and applicable options. Exercise initial `V1`, add-version, replace-version, whole-trigger `OR REPLACE`, and active/inactive version catalog state.

When multiple triggers have the same subject, event, and activation time, Db2 uses creation timestamp order. Drop/recreate and `OR REPLACE` can move a trigger later in that sequence. Compare `SYSTRIGGERS.CREATEDTS` and run an observable order test when generated DDL replaces triggers. Source: `ibm-trigger-activation-order`.

Db2 runs all applicable `BEFORE` triggers before the `AFTER` triggers. Within one set of row triggers, the earlier-created trigger processes all affected rows before the next trigger begins its rows. Include a multi-row event when testing activation order; a one-row event cannot expose that batching rule.

## Cascading boundary

An `AFTER` action can activate another trigger. IBM documents a maximum of 16 nested trigger, routine, or function levels. Reaching a 17th level results in SQLCODE `-724` and Db2 changes in the chain are backed out. Cover no cascade, a short valid chain, level 16, and attempted level 17. Source: `ibm-trigger-cascading`.

## Statement terminator

A compound body contains semicolons, which can look like the end of `CREATE TRIGGER` to SPUFI, the Db2 command line processor, or DSNTEP2. Configure an alternative outer terminator before submitting a multi-statement definition. The templates use `!` as a visible placeholder convention; adapt the directive to the actual processor. This submission concern is documented in both CREATE TRIGGER references.

## Catalog verification

Use [catalog-verification.sql](../test-design/catalog-verification.sql) to collect:

- `SYSIBM.SYSTRIGGERS` for event/time/granularity, basic versus advanced marker, version, active state, security/debug attributes, create timestamp, environment ID, and definition text;
- `SYSIBM.SYSTRIGGERS_STMT` where the trigger statement text is externalized;
- `SYSIBM.SYSPACKAGE` for the trigger package and body bind options;
- `SYSIBM.SYSENVIRONMENT` for definition-processing `APPLCOMPAT`; and
- `SYSIBM.SYSPACKDEP` for dependencies (`DTYPE = 'T'` for basic trigger packages and `DTYPE = '1'` for advanced trigger packages).

Catalog sources are `ibm-catalog-systriggers`, `ibm-catalog-systriggers-stmt`, `ibm-catalog-syspackage`, `ibm-catalog-sysenvironment`, and `ibm-catalog-syspackdep`.

## High-yield OFS test families

1. Round-trip equivalent basic and advanced definitions and prove their `SQLPL` and package-type distinction.
2. Cross event, time, and granularity with the transition matrix, including every illegal declaration.
3. Exercise one statement from every basic and advanced-direct body family at every permitted activation time.
4. Exercise all 35 supported nested statement rows, plus focused negatives for the 34 excluded rows.
5. Build complex advanced blocks with variables, conditions, handlers, cursor flow, diagnostics, dynamic SQL, and permitted DDL.
6. Test the existing DDL objects explicitly: nested `CREATE TABLE`, `CREATE INDEX`, and the forbidden `CREATE STOGROUP`, `CREATE DATABASE`, and `CREATE TABLESPACE` forms.
7. Round-trip advanced package options and compare both application-compatibility values.
8. Prove trigger activation order before and after generated `OR REPLACE` or drop/recreate.
9. Exercise secure triggers on RCAC subjects and validate both expected success and missing-`SECURED` failure.
10. Exercise cascade depth and atomic rollback at the 16/17-level boundary.

These tests should compare body text and catalog/package semantics. Text alone does not expose an altered active version, package option, dependency set, or activation timestamp.
