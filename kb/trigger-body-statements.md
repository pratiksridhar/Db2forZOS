# CREATE TRIGGER body statement reference

This reference answers two separate questions for IBM Db2 13 for z/OS:

1. Which statements can be the trigger's one **direct body**?
2. Which statements can appear **inside an SQL control statement** in an advanced trigger?

Those sets are not interchangeable. The authoritative sources are the basic and advanced CREATE TRIGGER diagrams (`ibm-create-trigger-basic`, `ibm-create-trigger-advanced`) and IBM's SQL-procedure-statement syntax and support matrix (`ibm-sql-procedure-statement`). The companion [JSON inventory](data/db2z13-trigger-body-statements.json) carries the same sets, compact syntax signatures, activation-time filters, and source references for automation.

## How to read the body grammar

```text
Basic body
  one basic triggered-SQL-statement
    or
  BEGIN ATOMIC <one or more basic triggered-SQL-statements> END

Advanced body
  one advanced triggered-SQL-statement
    or
  one SQL-control-statement
      which can contain trigger-supported SQL-procedure-statements
```

Therefore, an advanced body that needs two statements, a local variable, a handler, a loop, dynamic SQL, or supported DDL normally has one outer compound SQL-control statement. Activation-time restrictions apply recursively to statements inside that control statement.

The syntax in this file is deliberately compact. Angle-bracketed terms point to a statement-specific IBM subgrammar; they are not permission to omit required parts. Use the full Db2 13 syntax page or SQL Reference for final SQL construction.

## Basic trigger body

`MODE DB2SQL` is required. The body is one statement below or a `BEGIN ATOMIC ... END` list containing only these same families.

| Family | Compact syntax | Activation time | Important body restriction |
|---|---|---|---|
| `CALL` | `CALL <procedure-name> [(<argument> [, ...])]` | `BEFORE`, `AFTER`, `INSTEAD OF` | The called procedure inherits trigger transaction and side-effect restrictions. |
| searched `DELETE` | `[WITH <cte>] DELETE FROM <target> [WHERE <condition>]` | `AFTER`, `INSTEAD OF` | Not allowed in `BEFORE`. |
| fullselect | `[WITH <cte>] <fullselect>` | all | Basic-only as a stand-alone body statement. |
| `INSERT` | `INSERT INTO <target> [(<columns>)] {VALUES ... | <fullselect> | DEFAULT VALUES}` | `AFTER`, `INSTEAD OF` | Not allowed in `BEFORE`. |
| `MERGE` | `MERGE INTO <target> USING <source> ON <condition> <when-clauses>` | `AFTER`, `INSTEAD OF` | Not allowed in `BEFORE`. |
| `REFRESH TABLE` | `REFRESH TABLE <materialized-query-table>` | `AFTER`, `INSTEAD OF` | Not allowed in `BEFORE`. |
| `SET` assignment | `SET <new-transition-variable> = <expression> [, ...]` | `BEFORE` | Every target must be an assignable `NEW` transition variable. |
| `SIGNAL` | `SIGNAL {SQLSTATE [VALUE] <sqlstate> | <condition-name>} [SET MESSAGE_TEXT = <expression>]` | all | Use for validation and controlled failure. |
| `TRUNCATE` | `TRUNCATE TABLE <table> [<storage/delete-trigger options>] IMMEDIATE` | `AFTER`, `INSTEAD OF` | Not allowed in `BEFORE`. |
| searched `UPDATE` | `[WITH <cte>] UPDATE <target> SET <assignment> [, ...] [WHERE <condition>]` | `AFTER`, `INSTEAD OF` | Not allowed in `BEFORE`. |
| `VALUES` | `VALUES <row-value-expression> [, ...]` | all | Basic-only as a stand-alone body statement. |
| `VALUES INTO` | `VALUES <expression> [, ...] INTO <target> [, ...]` | `BEFORE` | Targets are constrained by basic-trigger variable rules. |

`BEGIN ATOMIC` sequences these statements in source order; it does not turn the basic trigger into an SQL PL body and does not add DDL, cursor declarations, handlers, loops, or dynamic SQL.

## Advanced direct body

An advanced trigger omits `MODE DB2SQL`. Its direct `<triggered-SQL-statement>` set has 11 families:

| Family | Compact syntax | Activation time |
|---|---|---|
| `CALL` | `CALL <procedure-name> [(<argument> [, ...])]` | all |
| searched `DELETE` | `[WITH <cte>] DELETE FROM <target> [WHERE <condition>]` | `AFTER`, `INSTEAD OF` |
| `GET DIAGNOSTICS` | `GET [CURRENT | STACKED] DIAGNOSTICS <target> = <diagnostic-item> [, ...]` | all |
| `INSERT` | `INSERT INTO <target> [(<columns>)] {VALUES ... | <fullselect> | DEFAULT VALUES}` | `AFTER`, `INSTEAD OF` |
| `MERGE` | `MERGE INTO <target> USING <source> ON <condition> <when-clauses>` | `AFTER`, `INSTEAD OF` |
| `REFRESH TABLE` | `REFRESH TABLE <materialized-query-table>` | `AFTER`, `INSTEAD OF` |
| `SET` assignment | `SET <assignment-target> = <expression> [, ...]` | all |
| `SIGNAL` | `SIGNAL {SQLSTATE [VALUE] <sqlstate> | <condition-name>} [SET MESSAGE_TEXT = <expression>]` | all |
| `TRUNCATE` | `TRUNCATE TABLE <table> [<storage/delete-trigger options>] IMMEDIATE` | `AFTER`, `INSTEAD OF` |
| searched `UPDATE` | `[WITH <cte>] UPDATE <target> SET <assignment> [, ...] [WHERE <condition>]` | `AFTER`, `INSTEAD OF` |
| `VALUES INTO` | `VALUES <expression> [, ...] INTO <target> [, ...]` | all |

A stand-alone fullselect and stand-alone `VALUES` are not advanced direct forms. Use `SELECT ... INTO` and `VALUES ... INTO`, normally with SQL variables declared in a compound block.

## Advanced SQL control statements

IBM's SQL PL overview names 16 SQL control statement families. Fifteen can be used in a trigger; the statement-specific `RETURN` rule prohibits `RETURN` in triggers.

| Control form | Compact syntax | Trigger status |
|---|---|---|
| assignment | `[<label>:] SET <assignment-clause>` | supported |
| `CALL` | `[<label>:] CALL <procedure-name> [(<arguments>)]` | supported |
| `CASE` | `[<label>:] CASE [<expression>] WHEN <expression-or-condition> THEN <statement>; [...] [ELSE <statement>;] END CASE` | supported |
| compound | `[<label>:] BEGIN [ATOMIC | NOT ATOMIC] <declarations>; <statement>; [...] END [<label>]` | supported; outer advanced-trigger block is atomic and cannot be `NOT ATOMIC` |
| `FOR` | `[<label>:] FOR [<loop-name> AS] [<cursor-name> CURSOR ... FOR] <select> DO <statement>; [...] END FOR [<label>]` | supported |
| `GET DIAGNOSTICS` | `GET [CURRENT | STACKED] DIAGNOSTICS <target> = <diagnostic-item> [, ...]` | supported |
| `GOTO` | `[<label>:] GOTO <target-label>` | supported |
| `IF` | `[<label>:] IF <condition> THEN <statement>; [...] [ELSEIF ...] [ELSE ...] END IF` | supported |
| `ITERATE` | `[<label>:] ITERATE <target-loop-label>` | supported |
| `LEAVE` | `[<label>:] LEAVE <target-block-or-loop-label>` | supported |
| `LOOP` | `[<label>:] LOOP <statement>; [...] END LOOP [<label>]` | supported |
| `REPEAT` | `[<label>:] REPEAT <statement>; [...] UNTIL <condition> END REPEAT [<label>]` | supported |
| `RESIGNAL` | `[<label>:] RESIGNAL [<sqlstate-or-condition>] [SET MESSAGE_TEXT = <expression>]` | supported |
| `RETURN` | `[<label>:] RETURN [<expression> | NULL | <fullselect>]` | **prohibited in a trigger** |
| `SIGNAL` | `[<label>:] SIGNAL <sqlstate-or-condition> [SET MESSAGE_TEXT = <expression>]` | supported |
| `WHILE` | `[<label>:] WHILE <condition> DO <statement>; [...] END WHILE [<label>]` | supported |

The detailed control statement pages are indexed as `ibm-sqlpl-compound`, `ibm-sqlpl-case`, `ibm-sqlpl-for`, `ibm-sqlpl-if`, `ibm-sqlpl-loop`, `ibm-sqlpl-repeat`, `ibm-sqlpl-resignal`, `ibm-sqlpl-return`, `ibm-sqlpl-signal`, and `ibm-sqlpl-while`. The general grammar is `ibm-sqlpl`.

### Compound declarations

A compound block can declare SQL variables, conditions, cursors, and condition handlers before its executable SQL procedure statements. Declaration order follows the IBM compound-statement diagram. Handler actions are themselves SQL procedure statements and remain subject to the trigger matrix and activation-time rules.

The outermost advanced-trigger compound block defaults to `ATOMIC` and cannot specify `NOT ATOMIC`. Nested blocks default to `NOT ATOMIC`; an `ATOMIC` block cannot be nested within an atomic block. Design handler and rollback expectations around those semantics.

## Advanced nested SQL procedure statements

The IBM SQL-procedure-statement table contains 69 rows. Its SQL-trigger-body column supports the following 35 rows. “All” means the matrix does not attach the `BEFORE` prohibition to that row; every other statement-specific trigger restriction still applies.

| Supported row | Compact syntax | Activation time | Trigger-specific note |
|---|---|---|---|
| SQL control statement | one of the supported control forms above | all | Nested content inherits all restrictions. |
| `ALLOCATE CURSOR` | `ALLOCATE <cursor> CURSOR FOR RESULT SET <locator-variable>` | all | Used with procedure result-set locators. |
| `ALTER FUNCTION` | `ALTER FUNCTION <function-designator> <allowed alter form>` | `AFTER`, `INSTEAD OF` | IBM lists external scalar/table, sourced, SQL scalar, and SQL table forms. |
| `ASSOCIATE LOCATORS` | `ASSOCIATE RESULT SET LOCATORS (<locator> [, ...]) WITH PROCEDURE <procedure>` | all | Pair with `CALL`/result sets. |
| `CALL` | `CALL <procedure> [(<arguments>)]` | all | Called routine restrictions still apply. |
| `CLOSE` | `CLOSE <cursor>` | all | Cursor must be in scope. |
| `COMMENT` | `COMMENT ON <object-designator> IS {<string> | NULL}` | `AFTER`, `INSTEAD OF` | DDL side effect. |
| `CREATE INDEX` | `CREATE [UNIQUE [WHERE NOT NULL]] INDEX <name> ON <table> <keys> [<options>]` | `AFTER`, `INSTEAD OF` | Nested only; full syntax is `ibm-create-index`. |
| `CREATE TABLE` | `CREATE TABLE <name> <table-definition> [<placement/options>]` | all | No LOB or XML columns; nested only; full syntax is `ibm-create-table`. |
| `CREATE VIEW` | `CREATE VIEW <name> [(<columns>)] AS [WITH <CTE> [, ...]] <fullselect> [WITH [CASCADED \| LOCAL] CHECK OPTION]` | `AFTER`, `INSTEAD OF` | Nested only; an omitted check-option qualifier defaults to `CASCADED`. |
| `DECLARE CURSOR` | `DECLARE <cursor> [<attributes>] CURSOR ... FOR {<select> | <statement-name>}` | all | Declaration placement follows compound grammar. |
| searched `DELETE` | `[WITH <cte>] DELETE FROM <target> [WHERE <condition>]` | `AFTER`, `INSTEAD OF` | `BEFORE` prohibition applies indirectly through called routines too. |
| `DROP` | `DROP {TABLE <name> | VIEW <name> | INDEX <name>} [<options>]` | all | Only these three DROP forms are supported. |
| `EXECUTE` | `EXECUTE <statement-name> [INTO <targets>] [USING <inputs>]` | all | Dynamic SQL statement must satisfy trigger context. |
| `EXECUTE IMMEDIATE` | `EXECUTE IMMEDIATE <string-expression>` | all | Dynamic SQL does not expand the permitted trigger context. |
| `EXPLAIN` | `EXPLAIN <explainable-statement-or-cache-form>` | all | Use the statement-specific syntax. |
| `FETCH` | `FETCH <cursor> INTO <targets>` | all | No orientation, multiple-row fetch, `WITH CONTINUE`, or `CURRENT CONTINUE`. |
| `GET DIAGNOSTICS` | `GET [CURRENT | STACKED] DIAGNOSTICS <target> = <item> [, ...]` | all | Full item grammar is `ibm-get-diagnostics`. |
| `GRANT` | `GRANT <privileges/authorities> [ON <object>] TO <grantees> [<options>]` | `AFTER`, `INSTEAD OF` | Use the applicable statement-specific privilege form. |
| `INSERT` | `INSERT INTO <target> [(<columns>)] {VALUES ... | <fullselect> | DEFAULT VALUES}` | `AFTER`, `INSTEAD OF` | `BEFORE` prohibition applies indirectly through called routines too. |
| `LABEL` | `LABEL ON <object-designator> IS <string>` | `AFTER`, `INSTEAD OF` | DDL side effect. |
| `LOCK TABLE` | `LOCK TABLE <table> [PART <n>] IN {SHARE | EXCLUSIVE} MODE` | `AFTER`, `INSTEAD OF` | Explicit lock side effect. |
| `MERGE` | `MERGE INTO <target> USING <source> ON <condition> <when-clauses>` | `AFTER`, `INSTEAD OF` | `BEFORE` prohibition applies indirectly through called routines too. |
| `OPEN` | `OPEN <cursor> [USING <inputs>]` | all | Cursor must be declared/prepared as applicable. |
| `PREPARE` | `PREPARE <statement-name> [ATTRIBUTES <string>] FROM <statement-string>` | all | Enables dynamic `EXECUTE` or cursor use. |
| `REFRESH TABLE` | `REFRESH TABLE <materialized-query-table>` | `AFTER`, `INSTEAD OF` | `BEFORE` prohibition applies indirectly through called routines too. |
| `RENAME` | `RENAME {TABLE <old> TO <new> | INDEX <old> TO <new>}` | all | Db2 13 `RENAME` covers table and index forms. |
| `REVOKE` | `REVOKE <privileges/authorities> [ON <object>] FROM <grantees> [<options>]` | all | Use the applicable statement-specific privilege form. |
| `SAVEPOINT` | `SAVEPOINT <name> [UNIQUE] ON ROLLBACK RETAIN CURSORS [ON ROLLBACK RETAIN LOCKS]` | `AFTER`, `INSTEAD OF` | Not allowed in `BEFORE`; transaction restrictions remain. |
| `SELECT INTO` | `SELECT <select-list> INTO <targets> <table-expression>` | all | Advanced replacement for a result-producing stand-alone fullselect. |
| `SET` assignment | `SET <assignment-target> = <expression> [, ...]` | all | Target legality depends on scope and transition mutability. |
| `SET` special register | `SET <settable-special-register> = <value>` | all | Excludes `CURRENT PACKAGE PATH` and `CURRENT PACKAGESET`. |
| `TRUNCATE` | `TRUNCATE TABLE <table> [<storage/delete-trigger options>] IMMEDIATE` | `AFTER`, `INSTEAD OF` | `BEFORE` prohibition applies indirectly through called routines too. |
| searched `UPDATE` | `[WITH <cte>] UPDATE <target> SET <assignment> [, ...] [WHERE <condition>]` | `AFTER`, `INSTEAD OF` | `BEFORE` prohibition applies indirectly through called routines too. |
| `VALUES INTO` | `VALUES <expressions> INTO <targets>` | all | Targets can be SQL variables or other legal assignment targets. |

The PDF text extraction places both note 4 (`BEFORE` prohibition) and note 7 (`CREATE TABLE` LOB/XML restriction) beside `GRANT`. Because note 7's prose is explicitly scoped to CREATE TABLE, this KB records the marker for provenance but does not invent a GRANT restriction from it.

## Excluded nested rows

The remaining 34 rows in the same 69-row matrix have no support mark in the SQL-trigger-body column:

| Family | Excluded rows |
|---|---|
| `ALTER` | `ALTER DATABASE`; `ALTER INDEX`; `ALTER MASK`; `ALTER PERMISSION`; `ALTER PROCEDURE` (external, SQL external, or SQL native); `ALTER SEQUENCE`; `ALTER STOGROUP`; `ALTER TABLE`; `ALTER TABLESPACE`; `ALTER TRIGGER`; `ALTER TRUSTED CONTEXT`; `ALTER VIEW` |
| transaction/connection | `COMMIT`; `CONNECT`; `RELEASE` connection; `RELEASE SAVEPOINT`; `ROLLBACK` with `TO SAVEPOINT`; `ROLLBACK` without `TO SAVEPOINT`; `SET CONNECTION` |
| `CREATE` | `CREATE ALIAS`; `CREATE DATABASE`; `CREATE FUNCTION`; `CREATE GLOBAL TEMPORARY TABLE`; `CREATE PROCEDURE` (external); `CREATE ROLE`; `CREATE SEQUENCE`; `CREATE STOGROUP`; `CREATE TABLESPACE`; `CREATE TRUSTED CONTEXT`; `CREATE TYPE` (array); `CREATE TYPE` (distinct); `CREATE VARIABLE` |
| declaration/utility | `DECLARE GLOBAL TEMPORARY TABLE`; `EXCHANGE` |

Do not confuse matrix exclusion with dynamic SQL permission. `PREPARE`, `EXECUTE`, and `EXECUTE IMMEDIATE` being supported does not waive trigger-context rules for the statement being prepared or executed.

## DDL subset for this repository

For complex bodies that exercise the repository's existing DDL object set:

```text
Advanced compound trigger body
  CREATE TABLE       yes; BEFORE/AFTER/INSTEAD OF; no LOB or XML columns
  CREATE INDEX       yes; AFTER/INSTEAD OF only
  CREATE STOGROUP    no
  CREATE DATABASE    no
  CREATE TABLESPACE  no
  CREATE TRIGGER     no; it is not listed in SQL-procedure-statement grammar
```

`CREATE TABLE` and `CREATE INDEX` must be nested within an SQL control statement because they are not in the advanced direct-body list. Use [advanced-trigger-ddl-body.template.sql](templates/advanced-trigger-ddl-body.template.sql) as a focused test skeleton. Creating fixed-name objects on every activation introduces repeat-activation and authorization concerns; isolate the subject data and clean up exact names between runs.

## Cross-cutting restrictions checklist

Before accepting any body composed from the tables above, verify:

- activation time permits every statement, including handler and nested-loop actions;
- row/table transition references exist for the event and granularity;
- only `NEW` variables of `BEFORE INSERT`/`UPDATE` are assigned;
- no XML transition value is referenced;
- no host variable or declared temporary table is referenced;
- no parameter marker appears in a basic trigger body;
- every directly referenced object and local routine exists at create time and is at the current server;
- no body statement modifies a `BUSINESS_TIME` period column;
- no table-locator-reference element or hexadecimal graphic string (`GX`) constant is used;
- a `BEFORE` path neither contains nor indirectly invokes prohibited side effects;
- called procedures contain no prohibited transaction/connection statements and are not `COMMIT ON RETURN`;
- dynamic SQL does not attempt to bypass a trigger restriction;
- `RETURN` is absent; and
- the SQL processor uses an outer terminator other than the semicolons inside the body.

## Suggested matrix execution order

1. Prove each basic direct family once at every allowed activation time.
2. Prove each advanced direct family the same way.
3. Prove each of the 15 usable control families with a minimal nested `SET`, `VALUES INTO`, or `SIGNAL` action.
4. Prove all 35 supported SQL-procedure-statement rows, using dedicated fixtures for cursor, dynamic SQL, DDL, privilege, and diagnostic families.
5. Prove focused negatives for all 34 excluded rows.
6. Add interaction cases: handler plus diagnostics, cursor plus loop, dynamic DDL plus condition, DDL plus repeat activation, and cascading depth.
7. Round-trip through OFS and compare `SYSTRIGGERS`, `SYSTRIGGERS_STMT`, trigger package attributes, dependencies, active version, and activation timestamp.

The matrix itself is queryable with `python3 tools/kb.py trigger-statements ...`; see the repository README for examples.
