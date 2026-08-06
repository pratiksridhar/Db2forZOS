# CREATE PROCEDURE

## Scope

`CREATE PROCEDURE` registers a stored procedure at the current Db2 server. Db2 13 documents three definition families:

| Family | Defining characteristic | Runtime artifact | Test posture |
|---|---|---|---|
| Native SQL procedure | `LANGUAGE SQL` with an SQL routine body and without `FENCED` or `EXTERNAL` | Db2 implicitly binds a package for every version | Preferred SQL-procedure path |
| External procedure | Host-language program named by `EXTERNAL NAME`; `LANGUAGE` identifies the interface | Separately prepared load module or Java method, normally with a separately bound package | Current external-program path |
| External SQL procedure | `LANGUAGE SQL` plus `FENCED` or `EXTERNAL` | Generated C program and package | Deprecated compatibility surface only |

Native SQL procedures are more fully supported and normally easier to maintain than external SQL procedures. Do not confuse an **external procedure** backed by a current COBOL, C, Java, PL/I, assembler, or REXX program with the deprecated **external SQL procedure** form. Sources: `ibm-create-procedure-overview`, `ibm-create-procedure-native`, `ibm-create-procedure-external`, `ibm-create-procedure-sql-external-deprecated`.

## Hand-written grammar summary

This is a test inventory, not a substitute for the IBM syntax diagrams.

### Native SQL procedure

```text
CREATE [OR REPLACE] PROCEDURE [schema.]procedure-name
  [(parameter-declaration [, ...])]
  [VERSION routine-version-id]
  LANGUAGE SQL
  [SPECIFIC [schema.]specific-name]
  [routine-option ...]
  {SQL-routine-body | WRAPPED obfuscated-statement-text}

parameter-declaration :=
  [IN | OUT | INOUT] parameter-name parameter-type

routine-option includes:
  DETERMINISTIC | NOT DETERMINISTIC
  MODIFIES SQL DATA | READS SQL DATA | CONTAINS SQL
  CALLED ON NULL INPUT
  DYNAMIC RESULT SETS integer
  ALLOW | DISALLOW | DISABLE DEBUG MODE
  PARAMETER CCSID {ASCII | EBCDIC | UNICODE}
  QUALIFIER schema-name
  SQL PATH schema-name [, ...]
  PACKAGE OWNER authorization-name [AS ROLE | AS USER]
  ASUTIME {NO LIMIT | LIMIT integer}
  COMMIT ON RETURN {NO | YES} | AUTONOMOUS
  INHERIT SPECIAL REGISTERS | DEFAULT SPECIAL REGISTERS
  bind and execution options
  APPLCOMPAT applcompat-level
```

The option list is order-independent, and an option can be specified only once. The IBM page contains the complete bind-option inventory; model options separately when a case needs them rather than treating this summary as a parser. Source: `ibm-create-procedure-native`.

### External procedure

```text
CREATE [OR REPLACE] PROCEDURE [schema.]procedure-name
  [(parameter-declaration [, ...])]
  [SPECIFIC [schema.]specific-name]
  [FENCED]
  LANGUAGE {ASSEMBLE | C | COBOL | JAVA | PLI | REXX}
  [EXTERNAL [NAME external-program-name]]
  [MODIFIES SQL DATA | READS SQL DATA | CONTAINS SQL | NO SQL]
  [PARAMETER STYLE {SQL | GENERAL | GENERAL WITH NULLS | JAVA}]
  [DYNAMIC RESULT SETS integer]
  [PACKAGE PATH package-path | NO PACKAGE PATH]
  [COLLID collection-id | NO COLLID]
  [DBINFO | NO DBINFO]
  [WLM ENVIRONMENT {name | (name,*)}]
  [ASUTIME {NO LIMIT | LIMIT integer}]
  [STAY RESIDENT {NO | YES}]
  [PROGRAM TYPE {MAIN | SUB}]
  [SECURITY {DB2 | USER | DEFINER}]
  [failure and run-time options]
  [COMMIT ON RETURN {NO | YES}]
  [INHERIT SPECIAL REGISTERS | DEFAULT SPECIAL REGISTERS]
```

`LANGUAGE` is mandatory. An omitted external name defaults from the procedure name only when that default is valid; specify `EXTERNAL NAME` explicitly in durable test DDL. Source: `ibm-create-procedure-external`.

### External SQL procedure, deprecated

The deprecated form uses `LANGUAGE SQL`, an SQL routine body, and either `FENCED` or `EXTERNAL NAME` to select external SQL procedure processing. IBM states that it must be processed using JCL or DSNTPSMP; issuing it from another context can leave an incomplete definition even when statement processing reports no error. Keep it in compatibility suites, not in new default templates. Sources: `ibm-create-procedure-sql-external-deprecated`, `ibm-procedure-create-external-sql-task`.

## Procedure identity and parameters

A procedure can have no parameters; both an empty parameter list and omission of the parentheses are documented. Each declared parameter has `IN`, `OUT`, or `INOUT` usage, with `IN` as the default. Parameter position, usage, data type, string subtype, and CCSID are part of the callable signature and the catalog oracle. Sources: `ibm-create-procedure-overview`, `ibm-create-procedure-native`, `ibm-create-procedure-external`, `ibm-catalog-sysparms`.

All character and graphic parameters must use one encoding scheme: ASCII, EBCDIC, or Unicode. Per-parameter CCSID clauses and `PARAMETER CCSID` must agree. Scalar `AS LOCATOR` applies only to LOB values or distinct types based on LOBs and is not allowed for SQL procedures. `TABLE LIKE table-or-view AS LOCATOR` is a separate table-parameter form: it describes a transition table and can be invoked only from a trigger action. Sources: `ibm-create-procedure-overview`, `ibm-create-procedure-native`, `ibm-create-procedure-external`.

`SPECIFIC` gives the routine its unambiguous specific identity. Use it in OFS cases that test overloaded names, table parameters, replacement, grants, or catalog joins; catalog and privilege queries should join by schema plus specific name rather than by unqualified procedure name alone.

## Native SQL procedure behavior

### Body shape and statement terminators

An SQL routine body is one SQL statement. That statement can itself be an SQL control statement, normally a compound statement, that contains declarations, handlers, control flow, cursors, diagnostics, dynamic SQL, and other supported SQL procedure statements. A multiple-statement body therefore needs one outer compound statement. Sources: `ibm-procedure-body`, `ibm-sqlpl`, `ibm-sql-procedure-statement`.

If the body is one non-control SQL procedure statement, it has no trailing semicolon inside the `CREATE PROCEDURE`. For a compound body, semicolons separate nested statements but do not terminate the outermost control statement. SPUFI, DSNTEP2, and similar processors can truncate the definition when semicolon is also their outer SQL terminator; use a distinct outer terminator such as `!`.

The declared data-access level is enforced against local body statements and locally invoked routines:

- `MODIFIES SQL DATA` is the default and permits supported modifying statements.
- `READS SQL DATA` excludes data-changing statements.
- `CONTAINS SQL` excludes statements that read or modify data.

An unhandled SQL condition is returned to the caller. Use focused cases for declared handlers, unhandled errors, diagnostics, and nested routine failures. Sources: `ibm-create-procedure-native`, `ibm-procedure-body`.

### Versions and replacement

The initial native version is `V1`. With `OR REPLACE`, omitting `VERSION` replaces the whole eligible procedure definition; specifying `VERSION` replaces that version if it exists or adds it otherwise. Only one version is active. New versions can change parameter names, procedure options, and the body, but not parameter count, modes, data types, character attributes, or CCSIDs. `AUTONOMOUS` must be consistent across all versions. Table parameters prevent adding or replacing a version with `CREATE PROCEDURE`; drop and recreate instead. Sources: `ibm-create-procedure-native`, `ibm-procedure-multiple-versions`.

Replacement re-applies defaults for omitted options, even if the old definition specified those options explicitly. `DISABLE DEBUG MODE` cannot later be relaxed for that version. A whole-procedure replacement also discards an existing comment while preserving granted procedure privileges. These are high-value OFS round-trip cases because generated DDL that omits an option can change behavior.

### Package, APPLCOMPAT, and dependencies

Db2 implicitly binds one package per native SQL procedure version. Its location, collection, package, and version identity are current server, procedure schema, procedure name, and routine version. `SYSPACKAGE.TYPE='N'` identifies a native SQL routine package, and `SYSPACKDEP.DTYPE='N'` identifies its recorded package dependencies. `APPLCOMPAT` governs static SQL in the procedure body and is stored on the package. Sources: `ibm-procedure-create-native-task`, `ibm-procedure-package-copies`, `ibm-create-procedure-native`, `ibm-catalog-syspackage`, `ibm-catalog-syspackdep`.

A native procedure that issues `CONNECT`, uses a qualifying remote three-part name, or changes `CURRENT PACKAGESET` or `CURRENT PACKAGE PATH` can require explicit package copies. Keep copied-package deployment distinct from the source `CREATE PROCEDURE` case.

### Commit behavior

`COMMIT ON RETURN NO` is the default. `YES` commits both procedure work and caller work after a non-error return and requires returned result-set cursors to be `WITH HOLD` if they are to remain usable. A routine or trigger cannot invoke a procedure defined with `COMMIT ON RETURN YES`.

`AUTONOMOUS` runs the native procedure in an independent unit of work and implies commit-on-return behavior for that unit without committing caller work. It requires `DYNAMIC RESULT SETS 0`, disallows the documented LOB/XML-related parameter forms, cannot assign global variables, and cannot call another autonomous procedure. Sources: `ibm-create-procedure-overview`, `ibm-create-procedure-native`, `ibm-procedure-create-native-task`.

## External procedure behavior

The host-language program must be prepared outside `CREATE PROCEDURE`. For assembler, C, C++, COBOL, and PL/I, IBM documents precompile/compile/link-edit and package binding before registration. The `EXTERNAL NAME`, package collection/path, parameter style, WLM environment, program type, run options, and external security identity must agree with the prepared artifact and runtime environment. Sources: `ibm-create-procedure-external`, `ibm-procedure-create-external-task`.

Important language interactions include:

- Java requires a valid `EXTERNAL NAME` and `PARAMETER STYLE JAVA`; do not combine Java with `DBINFO`, `PROGRAM TYPE MAIN`, or `RUN OPTIONS`.
- REXX uses `GENERAL` or `GENERAL WITH NULLS`; it cannot default to `PARAMETER STYLE SQL`. Only one REXX parameter can be `OUT` or `INOUT`, and it must be last.
- `DBINFO` requires `PARAMETER STYLE SQL`.
- `PARAMETER STYLE GENERAL` does not accept null arguments; `GENERAL WITH NULLS` supplies an indicator array.
- `PARAMETER VARCHAR` is a C-specific representation option with the documented exclusions; it does not redefine implicit SQL-style parameters.

External procedures execute in a WLM-managed external address space. An omitted `WLM ENVIRONMENT` uses the installation default, but a named environment requires matching external-security authorization. Test the DDL registration and the first invocation separately: catalog success does not prove that the load module, Java method, WLM setup, package, or RACF permissions are runnable.

## Catalog verification

Use [catalog-verification.sql](../test-design/catalog-verification.sql) with these semantic targets:

- `SYSIBM.SYSROUTINES`: one procedure row/version, with `ROUTINETYPE='P'`; `ORIGIN='N'` for native SQL and `ORIGIN='E'` for external or external SQL; compare identity, language, data access, result-set count, commit behavior, version/active state, debug state, WLM fields, and relevant options.
- `SYSIBM.SYSPARMS`: one row per scalar parameter and multiple rows for a table parameter; compare ordinal, `ROWTYPE` (`P`, `O`, or `B`), data type, length/precision/scale, CCSID, locator flag, and table metadata.
- `SYSIBM.SYSPACKAGE`: for native SQL, collection is the procedure schema, name is the procedure name, version is the routine version, and `TYPE='N'`; compare bind options including `APPLCOMPAT`.
- `SYSIBM.SYSPACKDEP`: compare package dependencies for native definitions using `DTYPE='N'`.
- `SYSIBM.SYSROUTINEAUTH`: compare explicit `EXECUTE` grants by specific name when authorization is part of the case.

`SYSROUTINES.TEXT` contains the native SQL routine definition and body but is empty for non-native rows. Compare source text as a textual oracle and catalog columns as the semantic oracle. Sources: `ibm-catalog-sysroutines`, `ibm-catalog-sysparms`, `ibm-catalog-syspackage`, `ibm-catalog-syspackdep`, `ibm-catalog-sysroutineauth`.

## High-yield OFS cases

1. Minimal native SQL procedure with no parameters and one SQL statement.
2. Native compound body with `IN`, `OUT`, and `INOUT`, a handler, diagnostics, and an application error.
3. Omitted versus explicit defaults for determinism, data access, result sets, commit behavior, special registers, and bind options.
4. `V1`, added inactive version, replaced version, activation switch through `ALTER PROCEDURE`, and whole-definition `OR REPLACE`.
5. Legal version body/option changes versus illegal signature, CCSID, mode, table-parameter, and autonomous changes.
6. `DYNAMIC RESULT SETS 0`, one returned `WITH HOLD` cursor, declared count above actual, and count exceeded.
7. `COMMIT ON RETURN NO`, `YES`, nested-call prohibition, and autonomous restrictions.
8. Data-access declarations crossed with read, update, dynamic SQL, and nested routine statements.
9. Native package `TYPE='N'`, version, `APPLCOMPAT`, package owner, qualifier/path, and dependency round trip.
10. External COBOL/C registration crossed with parameter style, WLM, program type, package collection/path, security, and first-call operational failure.
11. Java linkage positives and prohibited Java option pairs; REXX mode/count/order boundaries.
12. Deprecated external SQL recognition and safe preservation without making it the generated default.
13. Compound-body outer terminator preservation through OFS extraction and recreation.
14. Catalog/source comparison for readable versus `WRAPPED` native definitions.

## Source map

All sources are official IBM Db2 13 for z/OS documentation and are indexed in [sources.md](../sources.md). The primary statement pages are `ibm-create-procedure-overview`, `ibm-create-procedure-native`, `ibm-create-procedure-external`, and `ibm-create-procedure-sql-external-deprecated`.
