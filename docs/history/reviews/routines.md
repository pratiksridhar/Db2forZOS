# Bounded trigger and native procedure source review

Reviewed on 2026-09-12 against the official [IBM Db2 13 for z/OS SQL
Reference](https://www.ibm.com/docs/en/SSEPEK_13.0.0/pdf/db2z_13_sqlrefbook.pdf),
**Last updated: 2026-09-09**, publication SC28-2773-00. The downloaded PDF SHA-256
is `7caf1abd8c151e1669d1f89d210c85ebff486d689c169664853b6b49b6b70710`.
IBM can update this URL; the reviewed PDF is not vendored. Statement HTML returned
403 errors, so the PDF diagrams were rendered and inspected along with extracted
descriptions, restrictions and catalog entries. The scope below does not certify
the rest of the knowledge base.

## Reviewed syntax and modeled scope

- `ibm-create-trigger-basic`: printed pages 1820–1827, especially diagrams on
  1821–1822 (PDF pages 1849–1850), transition matrix on 1825, and allowable body
  statements on 1827. The model uses `NO CASCADE BEFORE`, INSERT or UPDATE OF,
  NEW AS N, FOR EACH ROW, MODE DB2SQL and optional WHEN, on a newly created local
  base table. Its only body statement assigns the NEW transition variable inside
  BEGIN ATOMIC. This is permitted for BEFORE INSERT/UPDATE. Bare BEFORE is an
  isolated negative candidate, because the basic grammar requires NO CASCADE.
  NOT SECURED requires a subject without row or column access control.
- `ibm-create-procedure-native`: printed pages 1658–1663, including the native
  option and procedure-definition diagrams on 1661–1662 (PDF 1689–1690), plus
  parameter, SPECIFIC and data-access descriptions on 1665–1667. The model has
  one IN INTEGER and one OUT VARCHAR(64), version V1, LANGUAGE SQL, a matching
  SPECIFIC name, PARAMETER CCSID UNICODE, CALLED ON NULL INPUT, zero result sets,
  COMMIT ON RETURN NO, DISABLE DEBUG MODE and profile-derived APPLCOMPAT.
  CONTAINS SQL, READS SQL DATA and MODIFIES SQL DATA all admit this body, which
  only declares a local variable and assigns an output parameter. NO SQL is an
  isolated negative candidate because it is absent from the native grammar.
- `ibm-sqlpl-compound`: printed pages 2279–2283, especially the atomicity
  restriction on 2281. Native procedures cannot specify ATOMIC. The generated
  body uses BEGIN, whose default here is NOT ATOMIC. Basic trigger BEGIN ATOMIC
  follows the distinct basic-trigger grammar, not the native-procedure rule.
- `ibm-sqlpl-if`, printed pages 2290–2291, and `ibm-procedure-body`: one outer compound statement contains
  DECLARE, IF/ELSE and SET assignments. A null input follows ELSE because the IF
  condition is not true. Individual nested statements retain semicolons; the
  outer statement has no internal trailing delimiter.
- `ibm-sql-reference-pdf`: SQL comments, printed pages 1139–1140, permits simple
  and bracketed comments. Nested bracketed comments are supported by Db2 but not
  by SPUFI, DSNTEP2, DSNTEP4 or the command line processor, so these portable
  fixtures deliberately avoid nesting. Comment and literal semicolons are data.

`trigger-basic` has **40 raw combinations and 20 valid combinations**:
two activation spellings, two events, two WHEN forms and five body layouts.
`procedure-native` has **60 raw combinations and 45 valid combinations**:
four access levels, three determinism forms and five body layouts. Each model
supports one isolated negative companion with unspecified SQLCODE/SQLSTATE.
Pairwise coverage measures interactions among those modeled values only.

The five body layouts are compact, multiline, line comments, bracketed comments
and a long bracketed comment. The long comment is 7679 characters before its
brackets, deliberately crossing 6000 characters to expose old catalog-text
truncation assumptions. It is a selected stress value, not a Db2 maximum boundary.
Every layout has the same 24-character payload: two leading spaces, mixed case,
a semicolon, an apostrophe-delimited word, repeated spaces and one trailing space.
The source literal doubles the apostrophes. Body formatting changes leave these
payload characters unchanged.

## Catalog and behavioral evidence

`ibm-catalog-systriggers`, printed pages 2806–2809, supports the selected
TRIGTIME, TRIGEVENT, GRANULARITY, SQLPL, SECURE and VERSION fields. Basic triggers
use SQLPL blank, VERSION empty, and the modeled BEFORE/ROW fields are B/R.
**SYSTRIGGERS.TEXT is unused. SYSTRIGGERS.STATEMENT is the full CLOB(2M) CREATE
statement.** `ibm-catalog-systriggers-stmt` describes its auxiliary LOB table;
query the base STATEMENT column instead of trying to join auxiliary rows.

`ibm-catalog-sysroutines`, printed pages 2710–2723, supports the selected routine
identity/type, language, parameter count, determinism, access, null-call,
result-set, commit, version, active, debug and parameter-CCSID fields.
`ibm-catalog-sysparms`, printed pages 2651–2655, supports ordered parameter rows,
ROWTYPE P/O, type name, length, scale and CCSID. Explicit Unicode fixes the output
parameter CCSID to 1208. `ibm-catalog-syspackage`, printed pages 2594 onward,
supports TYPE T for a basic trigger and N for a native procedure, VERSION and
APPLCOMPAT. Preflight rejects existing routines/triggers and packages using the
planned name, rather than assuming the routine schema is an unused collection.

Routine TEXT and trigger STATEMENT contain full definitions with the source
schema embedded. These CLOBs are **capture-only probes**, not fields in the plain
source/replay equality contract. Preserve the full source, product output, replay
and catalog text; compare body spans with statement-aware processing or direct
review. No regex extraction, global name replacement, whitespace folding or
trimming is authorized by a matching semantic contract. Comments need separate
textual review even if a behavior probe passes.

Trigger behavior probes insert one owned row, update its value to itself, then
read the exact payload and its length. This sequence exercises either modeled
event without overwriting a previous INSERT-trigger result. They finish by
removing that row. This probe checks the positive ID branch; it does not establish
WHEN false/unknown branch behavior or all UPDATE OF activation semantics.
Native procedure probes use `CALL procedure(?, ?)`, bind marker 1 as IN INTEGER
with 1, 0 or NULL, and bind marker 2 as OUT VARCHAR(64) through a driver. They expect the exact payload for 1 and `other` for 0/NULL. CALL
parameter markers and bindings are provided as structured probe data, not SPUFI
scripts. Every probe is offline and must run on both accepted source and replay.

## Execution and limits

Configure the outer delimiter as `@` in the SQL processor. The delimiter is
absent even from literals/comments, and body semicolons remain untouched. Preserve
newlines; for SPUFI use [SQLFORMAT SQLPL](https://www.ibm.com/docs/en/db2-for-zos/13.0.0?topic=defaults-current-spufi-panel)
when executing comment fixtures. The long bodies also require sufficient input
record support. The generated metrics report UTF-8 bytes and character/line
counts; these are not a promise about target EBCDIC encoding or client limits.

The trigger owns a dedicated PBG table space. Cleanup drops the trigger and then
its table space, which removes the fixture table. It does not issue a separate
DROP TABLE followed by a potentially redundant DROP TABLESPACE. Run cleanup only
for objects present in the run's creation ledger.

Uncovered scope includes advanced triggers, OLD/transition tables, statement and
INSTEAD OF triggers, handlers, dynamic SQL, procedure table/array/LOB parameters,
external procedures, multiple versions, security, broad package options,
activation order and exhaustive syntax/length boundaries. Package APPLCOMPAT is
compared across sides, but its source value must also be checked against the
verified profile. Selected catalog equality is never whole-object equivalence.

No Db2 subsystem or administration product executed these statements during this
review. All generated cases remain design; source acceptance, actual extraction,
replay and behavioral/text verification remain separate required evidence.
