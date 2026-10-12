#!/usr/bin/env python3
"""Statement-aware reader for Db2 13 for z/OS DDL scripts.

This is a structural reader for the DDL families the KB normalizes. It is not a
complete Db2 grammar. Anything outside the modeled clause sets is reported as
unsupported instead of being guessed, so callers can tell "checked" from
"not understood".
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


WORD_START = re.compile(r"[A-Za-z$#@]")
WORD_CHARS = re.compile(r"[A-Za-z0-9_$#@]*")
ORDINARY_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_]*")  # Identifiers in SQL: the uppercase ordinary form
NUMBER = re.compile(r"(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][+-]?\d+)?")
PLACEHOLDER = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")
TERMINATOR_DIRECTIVE = re.compile(r"--#SET\s+TERMINATOR\s+(\S)", re.IGNORECASE)


class ParseError(ValueError):
    def __init__(self, message, token=None):
        super().__init__(message)
        self.token = token


@dataclass
class Token:
    kind: str  # word, ident, string, number, op
    value: str  # uppercase for words; literal content for strings/identifiers
    raw: str
    line: int
    prefix: str = ""  # X, G, N, UX, GX, BX for strings

    def is_word(self, *values):
        return self.kind == "word" and (not values or self.value in values)


@dataclass
class Statement:
    sql: str
    line: int
    end_line: int
    terminator: str
    terminated: bool = True
    index: int = 0


@dataclass
class Clause:
    """One parsed clause occurrence: KB clause id, normalized value, line."""
    clause: str
    value: object = True
    line: int = 0


# --------------------------------------------------------------------------- split

def split_script(text, terminator=";"):
    """Split on the active outer terminator, honoring literals, comments and
    `--#SET TERMINATOR x` directives. Text is preserved byte-for-byte."""
    statements, i, n = [], 0, len(text)
    line, start, start_line, quote, depth = 1, None, None, None, 0
    current = terminator
    while i < n:
        ch = text[i]
        pair = text[i:i + 2]
        if depth:
            if pair == "/*":
                depth, i = depth + 1, i + 2
                continue
            if pair == "*/":
                depth, i = depth - 1, i + 2
                continue
        elif quote:
            if ch == quote:
                if text[i + 1:i + 2] == quote:
                    i += 2
                    continue
                quote = None
        elif pair == "--":
            end = text.find("\n", i)
            end = n if end < 0 else end
            directive = TERMINATOR_DIRECTIVE.match(text, i, end)
            if directive and start is None:
                current = directive.group(1)
            i = end
            continue
        elif pair == "/*":
            depth, i = 1, i + 2
            if start is None:
                start, start_line = i - 2, line
            continue
        elif ch == current:
            if start is not None and text[start:i].strip():
                sql = text[start:i]
                statements.append(Statement(sql.strip(), start_line + _leading_newlines(sql), line, current))
            start, start_line = None, None
            i += 1
            continue
        elif ch in "'\"":
            quote = ch
        if ch == "\n":
            line += 1
        elif start is None and not ch.isspace():
            start, start_line = i, line
        i += 1
    if quote or depth:
        raise ParseError("Unclosed string literal, delimited identifier or comment at end of script")
    if start is not None and _has_code(text[start:]):
        sql = text[start:]
        statements.append(Statement(sql.strip(), start_line + _leading_newlines(sql), line, current, terminated=False))
    for index, statement in enumerate(statements, 1):
        statement.index = index
    return statements


def _leading_newlines(sql):
    stripped = sql[:len(sql) - len(sql.lstrip())]
    return stripped.count("\n")


def _has_code(text):
    try:
        return bool(tokenize(text))
    except ParseError:
        return True


# --------------------------------------------------------------------------- tokens

def tokenize(sql, first_line=1):
    tokens, i, n, line = [], 0, len(sql), first_line
    while i < n:
        ch, pair = sql[i], sql[i:i + 2]
        if ch == "\n":
            line += 1
            i += 1
        elif ch.isspace():
            i += 1
        elif pair == "--":
            end = sql.find("\n", i)
            i = n if end < 0 else end
        elif pair == "/*":
            depth, i = 1, i + 2
            while i < n and depth:
                if sql[i:i + 2] == "/*":
                    depth, i = depth + 1, i + 2
                elif sql[i:i + 2] == "*/":
                    depth, i = depth - 1, i + 2
                else:
                    line += sql[i] == "\n"
                    i += 1
            if depth:
                raise ParseError("Unclosed bracketed comment")
        elif ch in "'\"" or (ch.upper() in "XGNUB" and _string_prefix(sql, i)):
            prefix = ""
            if ch not in "'\"":
                prefix = _string_prefix(sql, i)
                i += len(prefix)
                ch = sql[i]
            start, j, parts = i, i + 1, []
            while True:
                if j >= n:
                    raise ParseError("Unclosed string literal or delimited identifier")
                if sql[j] == ch:
                    if sql[j + 1:j + 2] == ch:
                        parts.append(ch)
                        j += 2
                        continue
                    break
                parts.append(sql[j])
                j += 1
            raw = (prefix + sql[start:j + 1])
            kind = "ident" if ch == '"' and not prefix else "string"
            tokens.append(Token(kind, "".join(parts), raw, line, prefix.upper()))
            line += raw.count("\n")
            i = j + 1
        elif pair == "{{" and PLACEHOLDER.match(sql, i):
            match = PLACEHOLDER.match(sql, i)
            tokens.append(Token("word", match.group(0), match.group(0), line))
            i = match.end()
        elif ch.isdigit() or (ch == "." and sql[i + 1:i + 2].isdigit()):
            match = NUMBER.match(sql, i)
            tokens.append(Token("number", match.group(0), match.group(0), line))
            i = match.end()
        elif WORD_START.match(ch):
            match = WORD_CHARS.match(sql, i + 1)
            raw = sql[i:match.end()]
            tokens.append(Token("word", raw.upper(), raw, line))
            i = match.end()
        else:
            for op in ("<>", "<=", ">=", "!=", "¬=", "||", "=>"):
                if sql.startswith(op, i):
                    tokens.append(Token("op", op, op, line))
                    i += len(op)
                    break
            else:
                tokens.append(Token("op", ch, ch, line))
                i += 1
    return tokens


def _string_prefix(sql, i):
    for prefix in ("UX", "GX", "BX", "X", "G", "N"):
        if sql[i:i + len(prefix)].upper() == prefix and sql[i + len(prefix):i + len(prefix) + 1] == "'":
            # A prefix only applies when it is not the tail of a longer word.
            if i == 0 or not re.match(r"[A-Za-z0-9_$#@]", sql[i - 1]):
                return sql[i:i + len(prefix)]
    return ""


def utf8_len(value):
    return len(value.encode("utf-8"))


# --------------------------------------------------------------------------- names

@dataclass(frozen=True)
class Name:
    schema: str | None
    name: str
    delimited: bool = field(default=False, compare=False)
    line: int = field(default=0, compare=False)

    def qualified(self, default_schema=None):
        schema = self.schema or default_schema
        return f"{schema}.{self.name}" if schema else self.name

    def __str__(self):
        return self.qualified()


# --------------------------------------------------------------------------- data types

BUILTIN_TYPES = {
    "SMALLINT", "INTEGER", "INT", "BIGINT", "DECIMAL", "DEC", "NUMERIC", "FLOAT", "REAL", "DOUBLE",
    "DECFLOAT", "CHARACTER", "CHAR", "VARCHAR", "CLOB", "GRAPHIC", "VARGRAPHIC", "DBCLOB", "BINARY",
    "VARBINARY", "BLOB", "DATE", "TIME", "TIMESTAMP", "ROWID", "XML",
}

# Type names that appear in other SQL dialects but not in the Db2 13 for z/OS
# built-in-type diagram (CREATE TABLE, data-type). A distinct type with such a
# name would have to be created first.
FOREIGN_TYPES = {
    "BOOLEAN": "no BOOLEAN built-in type; use SMALLINT/CHAR(1) with a CHECK constraint",
    "BOOL": "no BOOL built-in type; use SMALLINT/CHAR(1) with a CHECK constraint",
    "NCHAR": "no NCHAR type; use GRAPHIC(n) or CHAR(n) in a Unicode table",
    "NVARCHAR": "no NVARCHAR type; use VARGRAPHIC(n) or VARCHAR(n) in a Unicode table",
    "NATIONAL": "no NATIONAL CHARACTER type; use GRAPHIC/VARGRAPHIC",
    "NCLOB": "no NCLOB type; use DBCLOB",
    "NTEXT": "no NTEXT type; use DBCLOB or VARGRAPHIC",
    "TEXT": "no TEXT type; use VARCHAR(n) or CLOB(n)",
    "LONGTEXT": "no LONGTEXT type; use CLOB(n)",
    "MEDIUMTEXT": "no MEDIUMTEXT type; use CLOB(n)",
    "TINYTEXT": "no TINYTEXT type; use VARCHAR(n)",
    "VARCHAR2": "no VARCHAR2 type; use VARCHAR(n)",
    "NVARCHAR2": "no NVARCHAR2 type; use VARGRAPHIC(n)",
    "NUMBER": "no NUMBER type; use DECIMAL(p,s), INTEGER or BIGINT",
    "TINYINT": "no TINYINT type; use SMALLINT",
    "MEDIUMINT": "no MEDIUMINT type; use INTEGER",
    "SERIAL": "no SERIAL type; use INTEGER GENERATED ... AS IDENTITY",
    "BIGSERIAL": "no BIGSERIAL type; use BIGINT GENERATED ... AS IDENTITY",
    "SMALLSERIAL": "no SMALLSERIAL type; use SMALLINT GENERATED ... AS IDENTITY",
    "BYTEA": "no BYTEA type; use VARBINARY(n) or BLOB(n)",
    "IMAGE": "no IMAGE type; use BLOB(n)",
    "DATETIME": "no DATETIME type; use TIMESTAMP(p)",
    "DATETIME2": "no DATETIME2 type; use TIMESTAMP(p)",
    "SMALLDATETIME": "no SMALLDATETIME type; use TIMESTAMP(0)",
    "DATETIMEOFFSET": "no DATETIMEOFFSET type; use TIMESTAMP(p) WITH TIME ZONE",
    "TIMESTAMPTZ": "no TIMESTAMPTZ type; use TIMESTAMP(p) WITH TIME ZONE",
    "INTERVAL": "no INTERVAL type",
    "MONEY": "no MONEY type; use DECIMAL(p,s)",
    "SMALLMONEY": "no SMALLMONEY type; use DECIMAL(p,s)",
    "UUID": "no UUID type; use CHAR(16) FOR BIT DATA or BINARY(16)",
    "UNIQUEIDENTIFIER": "no UNIQUEIDENTIFIER type; use BINARY(16)",
    "JSON": "no JSON type; use CLOB/BLOB or VARCHAR",
    "JSONB": "no JSONB type; use BLOB",
    "BIT": "no BIT type; use CHAR(n) FOR BIT DATA or BINARY(n)",
    "VARBIT": "no VARBIT type; use VARBINARY(n)",
    "YEAR": "no YEAR type; use SMALLINT or DATE",
    "ENUM": "no ENUM type; use VARCHAR with a CHECK constraint",
    "LONG": "LONG VARCHAR/LONG VARGRAPHIC are not in the Db2 13 built-in-type diagram; use VARCHAR/VARGRAPHIC or a LOB",
    "STRING": "no STRING type; use VARCHAR(n)",
}

FAMILY = {
    "SMALLINT": "SMALLINT", "INTEGER": "INTEGER", "INT": "INTEGER", "BIGINT": "BIGINT",
    "DECIMAL": "DECIMAL", "DEC": "DECIMAL", "NUMERIC": "DECIMAL", "DECFLOAT": "DECFLOAT",
    "REAL": "FLOAT", "DOUBLE": "FLOAT", "FLOAT": "FLOAT",
    "CHAR": "CHAR", "CHARACTER": "CHAR", "VARCHAR": "VARCHAR", "CLOB": "CLOB",
    "GRAPHIC": "GRAPHIC", "VARGRAPHIC": "VARGRAPHIC", "DBCLOB": "DBCLOB",
    "BINARY": "BINARY", "VARBINARY": "VARBINARY", "BLOB": "BLOB",
    "DATE": "DATE", "TIME": "TIME", "TIMESTAMP": "TIMESTAMP", "ROWID": "ROWID", "XML": "XML",
}
LOB_FAMILIES = {"CLOB", "BLOB", "DBCLOB"}
VARYING_FAMILIES = {"VARCHAR", "VARGRAPHIC", "VARBINARY"}
STRING_FAMILIES = {"CHAR", "VARCHAR", "CLOB", "GRAPHIC", "VARGRAPHIC", "DBCLOB"}
LOB_UNITS = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}


@dataclass
class DataType:
    family: str | None  # None for distinct/unknown
    name: str  # spelled name, e.g. "CHARACTER VARYING" or "SCHEMA.MONEY_T"
    length: int | None = None  # characters/bytes/precision as declared
    scale: int | None = None
    time_zone: bool = False
    subtype: str | None = None  # SBCS, MIXED, BIT
    ccsid: str | None = None
    distinct: Name | None = None
    foreign: str | None = None
    explicit_length: bool = False
    raw: str = ""

    def signature(self):
        """Description compared for FK identity (type, length, scale, subtype/CCSID)."""
        if self.family is None:
            return ("DISTINCT", str(self.distinct or self.name))
        return (self.family, self.length, self.scale, self.time_zone, self.subtype or "", self.ccsid or "")

    def storage_bytes(self):
        """Approximate stored data bytes for a record-length estimate."""
        f, n = self.family, self.length or 0
        if f is None:
            return None
        if f == "SMALLINT":
            return 2
        if f == "INTEGER":
            return 4
        if f == "BIGINT":
            return 8
        if f == "DECIMAL":
            return (self.length or 5) // 2 + 1
        if f == "DECFLOAT":
            return 8 if self.length == 16 else 16
        if f == "FLOAT":
            return 4 if self.length and self.length <= 21 else 8
        if f in ("CHAR", "VARCHAR", "BINARY", "VARBINARY"):
            return n
        if f in ("GRAPHIC", "VARGRAPHIC"):
            return 2 * n
        if f == "DATE":
            return 4
        if f == "TIME":
            return 3
        if f == "TIMESTAMP":
            precision = 6 if self.length is None else self.length
            return 7 + (precision + 1) // 2 + (2 if self.time_zone else 0)
        if f == "ROWID":
            return 17
        return 0  # LOB and XML values are stored outside the base row.


# --------------------------------------------------------------------------- objects

@dataclass
class Column:
    name: str
    type: DataType | None
    line: int
    not_null: bool = False
    default: str | None = None  # None=omitted; otherwise form label
    default_raw: str | None = None
    generated: str | None = None  # identity, row-change-timestamp, rowid, row-begin, row-end, transaction-start-id, expression
    generated_mode: str | None = None  # ALWAYS, BY DEFAULT
    generated_expression: tuple = ()  # tokens inside GENERATED ... AS (expression)
    identity_options: dict = field(default_factory=dict)
    hidden: bool = False
    inline_length: int | None = None
    fieldproc: str | None = None
    fieldproc_parameters: tuple = ()  # tokens inside FIELDPROC name (...)
    security_label: bool = False

    @property
    def nullable(self):
        return not self.not_null and self.generated not in ("identity", "row-change-timestamp", "rowid", "row-begin", "row-end")


@dataclass
class Constraint:
    kind: str  # primary, unique, foreign, check
    name: str | None
    columns: list
    line: int
    parent: Name | None = None
    parent_columns: list | None = None
    delete_rule: str | None = None  # None = omitted
    enforced: bool = True
    query_optimization: bool = False
    condition: str | None = None
    condition_tokens: tuple = ()
    period: str | None = None  # BUSINESS_TIME WITHOUT OVERLAPS / PERIOD BUSINESS_TIME
    parent_period: bool = False  # PERIOD BUSINESS_TIME in the REFERENCES list
    column_level: bool = False
    rules: str | None = None  # CURRENT RULES of the ALTER TABLE that added it; None = the table's CREATE


@dataclass
class Obj:
    kind: str
    name: Name
    statement: int
    line: int
    clauses: list = field(default_factory=list)
    attrs: dict = field(default_factory=dict)


@dataclass
class Parsed:
    """Result of parsing one statement."""
    statement: Statement
    verb: str  # CREATE, ALTER, DROP, SET, COMMIT, COMMENT, ...
    kind: str | None  # object kind for CREATE/ALTER/DROP
    obj: Obj | None = None
    issues: list = field(default_factory=list)  # (code, message, line, extra)
    tokens: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- parser

class Cursor:
    def __init__(self, tokens):
        self.t, self.i = tokens, 0

    def peek(self, offset=0):
        j = self.i + offset
        return self.t[j] if 0 <= j < len(self.t) else None

    def at_end(self):
        return self.i >= len(self.t)

    def next(self):
        token = self.peek()
        if token is None:
            raise ParseError("Unexpected end of statement", self.t[-1] if self.t else None)
        self.i += 1
        return token

    def line(self):
        token = self.peek() or (self.t[-1] if self.t else None)
        return token.line if token else 0

    def is_word(self, *values, offset=0):
        token = self.peek(offset)
        return token is not None and token.is_word(*values)

    def is_op(self, value, offset=0):
        token = self.peek(offset)
        return token is not None and token.kind == "op" and token.value == value

    def accept(self, *words):
        """Consume an exact word sequence; ops may be given as single characters."""
        for k, word in enumerate(words):
            token = self.peek(k)
            if token is None:
                return False
            if len(word) == 1 and not word.isalnum():
                if not (token.kind == "op" and token.value == word):
                    return False
            elif not token.is_word(word):
                return False
        self.i += len(words)
        return True

    def expect(self, *words):
        if not self.accept(*words):
            got = self.peek()
            raise ParseError(f"Expected {' '.join(words)} but found {got.raw if got else 'end of statement'}", got)

    def expect_op(self, value):
        if not self.is_op(value):
            got = self.peek()
            raise ParseError(f"Expected '{value}' but found {got.raw if got else 'end of statement'}", got)
        self.i += 1

    def identifier(self):
        token = self.next()
        if token.kind not in ("word", "ident"):
            raise ParseError(f"Expected an identifier but found {token.raw}", token)
        return token

    def name(self, parts=2):
        first = self.identifier()
        names = [first]
        while len(names) < parts and self.is_op("."):
            self.i += 1
            names.append(self.identifier())
        last = names[-1]
        schema = names[-2].value if len(names) > 1 else None
        return Name(schema, last.value, last.kind == "ident", first.line)

    def integer(self, allow_negative=False):
        negative = False
        if allow_negative and self.is_op("-"):
            self.i += 1
            negative = True
        token = self.next()
        if token.kind != "number" or not token.value.isdigit():
            raise ParseError(f"Expected an integer but found {token.raw}", token)
        return -int(token.value) if negative else int(token.value)

    def group(self):
        """Consume a balanced parenthesized group and return its inner tokens."""
        self.expect_op("(")
        depth, start = 1, self.i
        while depth:
            token = self.next()
            if token.kind == "op" and token.value == "(":
                depth += 1
            elif token.kind == "op" and token.value == ")":
                depth -= 1
        return self.t[start:self.i - 1]


def split_commas(tokens):
    """Split on top-level commas. An empty element (", ," or a trailing comma) is kept as []
    so callers can reject it instead of silently accepting invalid lists."""
    parts, depth, current, saw_comma = [], 0, [], False
    for token in tokens:
        if token.kind == "op" and token.value == "(":
            depth += 1
        elif token.kind == "op" and token.value == ")":
            depth -= 1
        if depth == 0 and token.kind == "op" and token.value == ",":
            parts.append(current)
            current = []
            saw_comma = True
        else:
            current.append(token)
    if current or saw_comma:
        parts.append(current)
    return parts


def render_tokens(tokens, text=None):
    """Readable token text: no space inside parentheses or before commas."""
    out = []
    for token in tokens:
        if out and not (token.kind == "op" and token.value in ",)." or out[-1] in ("(", ".")):
            out.append(" ")
        out.append(text(token) if text else token.raw)
    return "".join(out)


def normalized_text(token):
    """Token text for comparison: keywords in uppercase, and a delimited identifier that spells an
    ordinary identifier ("NAME") written as that identifier. Literals keep their exact text."""
    if token.kind == "word" or (token.kind == "ident" and ORDINARY_IDENTIFIER.fullmatch(token.value)):
        return token.value
    return token.raw


class Unsupported(Exception):
    """A clause/construct outside the modeled diagram subset."""

    def __init__(self, code, message, token=None):
        super().__init__(message)
        self.code, self.token = code, token


# Words that start a LUW/other-dialect clause, with a z/OS-specific message.
DIALECT_CLAUSES = {
    "ORGANIZE": "ORGANIZE BY ROW/COLUMN is not Db2 for z/OS syntax (z/OS has only deprecated ORGANIZE BY HASH)",
    "DISTRIBUTE": "DISTRIBUTE BY is not Db2 for z/OS syntax",
    "INDEX": "INDEX IN <tablespace> is not Db2 for z/OS syntax; indexes get their own index spaces",
    "LONG": "LONG IN <tablespace> is not Db2 for z/OS syntax; LOBs use LOB table spaces/auxiliary tables",
    "MANAGED": "MANAGED BY is not Db2 for z/OS syntax; use USING STOGROUP/VCAT",
    "EXTENTSIZE": "EXTENTSIZE is not Db2 for z/OS syntax; use PRIQTY/SECQTY",
    "PREFETCHSIZE": "PREFETCHSIZE is not Db2 for z/OS syntax",
    "PAGESIZE": "PAGESIZE is not Db2 for z/OS syntax; the BUFFERPOOL determines page size",
    "AUTORESIZE": "AUTORESIZE is not Db2 for z/OS syntax",
    "ENGINE": "ENGINE= is not Db2 SQL",
    "TABLESPACE": "TABLESPACE <name> in CREATE TABLE/INDEX is not Db2 for z/OS syntax; use IN database.tablespace",
    "ALLOW": "ALLOW REVERSE SCANS is not Db2 for z/OS syntax",
    "DISALLOW": "DISALLOW REVERSE SCANS is not Db2 for z/OS syntax",
    "COLLECT": "COLLECT STATISTICS is not Db2 for z/OS CREATE INDEX syntax",
    "MINPCTUSED": "MINPCTUSED is not Db2 for z/OS syntax",
    "LEVEL2": "LEVEL2 PCTFREE is not Db2 for z/OS syntax",
    "PAGE": "PAGE SPLIT is not Db2 for z/OS syntax",
    "WITH": "Unsupported WITH option",
    "PARTITIONING": "PARTITIONING KEY is not Db2 for z/OS syntax; use PARTITION BY RANGE",
    "STORAGE": "STORAGE(...) is not Db2 for z/OS syntax; use USING STOGROUP ... PRIQTY/SECQTY",
    "TABLESPACES": "Not Db2 for z/OS syntax",
    "COMMENT": "COMMENT clauses inside CREATE are not Db2 for z/OS syntax; use COMMENT ON",
    "CHARSET": "Character-set clauses are not Db2 for z/OS syntax; use CCSID",
    "CHARACTER": "CHARACTER SET is not Db2 for z/OS syntax; use CCSID",
    "COLLATE": "COLLATE is not Db2 for z/OS syntax",
    "AUTO_INCREMENT": "AUTO_INCREMENT is not Db2 syntax; use GENERATED ... AS IDENTITY",
    "IDENTITY": "IDENTITY(seed, increment) is not Db2 syntax; use GENERATED ... AS IDENTITY (START WITH n, INCREMENT BY m)",
    "UNSIGNED": "UNSIGNED is not Db2 syntax",
    "ZEROFILL": "ZEROFILL is not Db2 syntax",
    "DEFERRABLE": "DEFERRABLE constraints are not Db2 for z/OS syntax; consider NOT ENFORCED",
    "INITIALLY": "INITIALLY DEFERRED/IMMEDIATE is not Db2 for z/OS syntax",
    "MATCH": "MATCH FULL/PARTIAL/SIMPLE is not Db2 for z/OS syntax",
    "NOLOGGING": "NOLOGGING is not Db2 syntax; use NOT LOGGED on the table space",
    "INCLUDING": "INCLUDING is only valid in LIKE/AS copy options",
    "SECURITY": "Unsupported SECURITY clause in this context",
}


def parse_statement(statement, state):
    """Parse one statement. `state` carries SET CURRENT SCHEMA/RULES context."""
    try:
        tokens = tokenize(statement.sql, statement.line)
    except ParseError as error:
        return Parsed(statement, "UNKNOWN", None, issues=[("script.parse-error", str(error), statement.line, {})])
    result = Parsed(statement, tokens[0].value if tokens and tokens[0].kind == "word" else "UNKNOWN", None, tokens=tokens)
    cur = Cursor(tokens)
    try:
        if cur.is_word("CREATE"):
            _parse_create(cur, result, state)
        elif cur.is_word("ALTER"):
            _parse_alter(cur, result, state)
        elif cur.is_word("DROP"):
            _parse_drop(cur, result)
        elif cur.is_word("SET"):
            _parse_set(cur, result, state)
        elif cur.is_word("COMMENT", "LABEL"):
            _parse_comment_label(cur, result)
        elif cur.is_word("COMMIT", "ROLLBACK", "GRANT", "REVOKE", "INSERT", "UPDATE", "DELETE", "MERGE",
                         "SELECT", "VALUES", "CALL", "RENAME", "EXPLAIN", "DECLARE", "LOCK", "REFRESH",
                         "TRUNCATE", "EXCHANGE", "RELEASE", "SAVEPOINT", "CONNECT", "TRANSFER"):
            result.kind = None
        else:
            result.issues.append(("script.unrecognized-statement", f"Unrecognized statement starting with {tokens[0].raw if tokens else '?'}", statement.line, {}))
    except Unsupported as error:
        line = error.token.line if error.token else cur.line()
        result.issues.append((error.code, str(error), line, {}))
        _mark_partial(result)
    except ParseError as error:
        line = error.token.line if error.token else cur.line()
        result.issues.append(("script.parse-error", str(error), line, {}))
        _mark_partial(result)
    except IndexError:
        result.issues.append(("script.parse-error", "Empty list element or incomplete clause", cur.line(), {}))
        _mark_partial(result)
    return result


def _mark_partial(result):
    """An aborted statement leaves an incomplete object that later checks must not trust."""
    if result.obj is not None:
        result.obj.attrs["partial"] = True
    else:
        result.detail["partial"] = True  # an aborted ALTER changes nothing


def _dialect(cur, context):
    token = cur.peek()
    if token is None:
        return
    if token.kind == "word" and token.value in DIALECT_CLAUSES and token.value not in ("WITH", "SECURITY", "INCLUDING"):
        raise Unsupported("dialect.clause", f"{DIALECT_CLAUSES[token.value]} ({context}).", token)
    raise Unsupported("syntax.unrecognized-clause",
                      f"'{token.raw}' is not a clause this checker models for {context}. It is either outside the Db2 13 "
                      "for z/OS diagram or outside the checker's modeled subset; verify in IBM documentation.", token)


def _parse_create(cur, result, state):
    cur.expect("CREATE")
    replace = cur.accept("OR", "REPLACE")
    line = cur.line()
    if cur.is_word("STOGROUP"):
        kind = "stogroup"
    elif cur.is_word("DATABASE"):
        kind = "database"
    elif cur.is_word("TABLESPACE") or cur.accept("LOB") and cur.is_word("TABLESPACE"):
        kind = "lob-tablespace" if cur.peek(-1).is_word("LOB") else "tablespace"
    elif cur.is_word("LARGE") and cur.is_word("TABLESPACE", offset=1):
        cur.next()
        kind = "tablespace"
        result.issues.append(("deprecated.large", "CREATE LARGE TABLESPACE is a deprecated compatibility form; use DSSIZE.", line, {}))
    elif cur.is_word("TABLE"):
        kind = "table"
    elif cur.is_word("AUXILIARY", "AUX") and cur.is_word("TABLE", offset=1):
        cur.next()
        kind = "auxiliary-table"
    elif cur.is_word("GLOBAL") and cur.is_word("TEMPORARY", offset=1):
        kind = "global-temporary-table"
    elif cur.is_word("UNIQUE", "INDEX"):
        kind = "index"
    elif cur.is_word("VIEW", "ALIAS", "SYNONYM", "SEQUENCE", "TYPE", "DISTINCT", "FUNCTION", "PROCEDURE", "TRIGGER",
                     "ROLE", "MASK", "PERMISSION", "TRUSTED", "VARIABLE", "SCHEMA"):
        kind = cur.peek().value.lower()
    else:
        raise Unsupported("script.unrecognized-statement", f"Unrecognized CREATE {cur.peek().raw if cur.peek() else ''}", cur.peek())
    result.kind = kind
    if cur.is_word("IF") or (cur.is_word(kind.upper()) and cur.is_word("IF", offset=1)):
        token = cur.peek() if cur.is_word("IF") else cur.peek(1)
        raise Unsupported("dialect.if-not-exists", "IF NOT EXISTS is not in the Db2 13 for z/OS CREATE diagrams.", token)
    if replace and kind not in ("procedure", "function", "trigger"):
        result.issues.append(("dialect.or-replace", f"CREATE OR REPLACE is not in the Db2 13 for z/OS CREATE {kind.upper()} diagram.", line, {}))
    parser = {
        "stogroup": _parse_stogroup, "database": _parse_database, "tablespace": _parse_tablespace,
        "lob-tablespace": _parse_tablespace, "table": _parse_table, "auxiliary-table": _parse_aux_table,
        "index": _parse_index,
    }.get(kind)
    if parser is None:
        _parse_other_create(cur, result, kind, state)
        return
    parser(cur, result, state)


def _new_obj(result, kind, name, line):
    result.obj = Obj(kind, name, result.statement.index, line)
    return result.obj


def _clause(obj, clause, value=True, line=0, seen=None, key=None):
    obj.clauses.append(Clause(clause, value, line))
    if seen is not None:
        k = key or clause
        if k in seen:
            obj.attrs.setdefault("duplicate_clauses", []).append((k, line))
        seen.add(k)


# ---- STOGROUP / DATABASE

def _parse_stogroup(cur, result, state):
    cur.expect("STOGROUP")
    line = cur.line()
    obj = _new_obj(result, "stogroup", cur.name(1), line)
    seen = set()
    while not cur.at_end():
        line = cur.line()
        if cur.accept("VOLUMES"):
            values = [t for t in cur.group() if t.kind == "string"]
            wildcard = [v for v in values if v.value == "*"]
            specific = [v for v in values if v.value != "*"]
            obj.attrs["volumes"] = [v.value for v in values]
            if wildcard:
                _clause(obj, "volumes-wildcard", len(wildcard), line, seen, "volumes")
            if specific:
                _clause(obj, "volumes-specific", len(specific), line, seen if not wildcard else None, "volumes")
        elif cur.accept("VCAT"):
            obj.attrs["vcat"] = cur.identifier().value
            _clause(obj, "vcat", True, line, seen)
        elif cur.is_word("DATACLAS", "MGMTCLAS", "STORCLAS"):
            word = cur.next().value
            obj.attrs[word.lower()] = cur.identifier().value
            _clause(obj, word.lower(), True, line, seen)
        elif cur.accept("KEY", "LABEL"):
            obj.attrs["key_label"] = cur.identifier().value
            _clause(obj, "key-label", True, line, seen)
        elif cur.accept("NO", "KEY", "LABEL"):
            _clause(obj, "no-key-label", True, line, seen, "key-label")
        else:
            _dialect(cur, "CREATE STOGROUP")


def _parse_database(cur, result, state):
    cur.expect("DATABASE")
    line = cur.line()
    obj = _new_obj(result, "database", cur.name(1), line)
    seen = set()
    while not cur.at_end():
        line = cur.line()
        if cur.accept("BUFFERPOOL"):
            obj.attrs["bufferpool"] = cur.identifier().value
            _clause(obj, "bufferpool", obj.attrs["bufferpool"], line, seen)
        elif cur.accept("INDEXBP"):
            obj.attrs["indexbp"] = cur.identifier().value
            _clause(obj, "indexbp", obj.attrs["indexbp"], line, seen)
        elif cur.accept("AS", "WORKFILE"):
            obj.attrs["workfile"] = True
            _clause(obj, "as-workfile", True, line, seen)
            if cur.accept("FOR"):
                obj.attrs["member"] = cur.identifier().value
                _clause(obj, "for-member", True, line, seen)
        elif cur.accept("STOGROUP"):
            obj.attrs["stogroup"] = cur.identifier().value
            _clause(obj, "stogroup", True, line, seen)
        elif cur.accept("CCSID"):
            obj.attrs["ccsid"] = cur.identifier().value
            _clause(obj, "ccsid", obj.attrs["ccsid"], line, seen)
        else:
            _dialect(cur, "CREATE DATABASE")


# ---- TABLESPACE

def _parse_using(cur, obj, seen, line, target):
    if cur.accept("VCAT"):
        target["vcat"] = cur.identifier().value
        _clause(obj, "using-vcat", True, line, seen, "using")
        return
    cur.expect("STOGROUP")
    target["stogroup"] = cur.identifier().value
    _clause(obj, "using-stogroup", True, line, seen, "using")
    while True:
        line = cur.line()
        if cur.accept("PRIQTY"):
            target["priqty"] = cur.integer(True)
            _clause(obj, "priqty", target["priqty"], line)
        elif cur.accept("SECQTY"):
            target["secqty"] = cur.integer(True)
            _clause(obj, "secqty", target["secqty"], line)
        elif cur.accept("ERASE"):
            target["erase"] = cur.next().value
            _clause(obj, "erase", target["erase"], line)
        else:
            return


def _parse_free_gbp(cur, obj, seen, target, line, allow_for_update=True):
    if cur.accept("FREEPAGE"):
        target["freepage"] = cur.integer(True)
        _clause(obj, "freepage", target["freepage"], line, seen)
        return True
    if cur.accept("PCTFREE"):
        target["pctfree"] = cur.integer(True)
        _clause(obj, "pctfree", target["pctfree"], line, seen)
        if allow_for_update and cur.accept("FOR", "UPDATE"):
            target["pctfree_for_update"] = cur.integer(True)
            _clause(obj, "pctfree-for-update", target["pctfree_for_update"], line)
        return True
    if cur.accept("GBPCACHE"):
        target["gbpcache"] = cur.next().value
        _clause(obj, "gbpcache", target["gbpcache"], line, seen)
        return True
    return False


def _parse_tablespace(cur, result, state):
    lob = result.kind == "lob-tablespace"
    cur.expect("TABLESPACE")
    line = cur.line()
    obj = _new_obj(result, result.kind, cur.name(1), line)
    a, seen = obj.attrs, set()
    a["partitions"] = []
    context = "CREATE LOB TABLESPACE" if lob else "CREATE TABLESPACE"
    while not cur.at_end():
        line = cur.line()
        if cur.accept("IN"):
            a["database"] = cur.identifier().value
            _clause(obj, "in-database", True, line, seen)
        elif cur.accept("BUFFERPOOL"):
            a["bufferpool"] = cur.identifier().value
            _clause(obj, "bufferpool", a["bufferpool"], line, seen)
        elif not lob and cur.accept("MAXPARTITIONS"):
            a["maxpartitions"] = cur.integer()
            _clause(obj, "maxpartitions", a["maxpartitions"], line, seen)
        elif not lob and cur.accept("NUMPARTS"):
            a["numparts"] = cur.integer()
            _clause(obj, "numparts", a["numparts"], line, seen)
            if cur.is_op("("):
                for part in split_commas(cur.group()):
                    a["partitions"].append(_parse_ts_partition(part, obj))
                _clause(obj, "partition-block", len(a["partitions"]), line)
        elif cur.accept("DSSIZE"):
            a["dssize"] = cur.integer()
            cur.accept("G")
            _clause(obj, "dssize", a["dssize"], line, seen)
        elif not lob and cur.accept("SEGSIZE"):
            a["segsize"] = cur.integer()
            _clause(obj, "segsize", a["segsize"], line, seen)
        elif not lob and cur.accept("CCSID"):
            a["ccsid"] = cur.identifier().value
            _clause(obj, "ccsid", a["ccsid"], line, seen)
        elif cur.accept("CLOSE"):
            a["close"] = cur.next().value
            _clause(obj, "close", a["close"], line, seen)
        elif cur.accept("COMPRESS"):
            value = cur.next().value
            if value == "YES" and cur.is_word("FIXEDLENGTH", "HUFFMAN"):
                value += " " + cur.next().value
            a["compress"] = value
            _clause(obj, "compress", value, line, seen)
        elif cur.accept("DEFINE"):
            a["define"] = cur.next().value
            _clause(obj, "define", a["define"], line, seen)
        elif not lob and cur.is_word("FREEPAGE", "PCTFREE"):
            _parse_free_gbp(cur, obj, seen, a, line)
        elif cur.is_word("GBPCACHE"):
            _parse_free_gbp(cur, obj, seen, a, line)
        elif not lob and cur.accept("INSERT", "ALGORITHM"):
            a["insert_algorithm"] = cur.integer()
            _clause(obj, "insert-algorithm", a["insert_algorithm"], line, seen)
        elif cur.accept("LOCKMAX"):
            a["lockmax"] = "SYSTEM" if cur.accept("SYSTEM") else cur.integer()
            _clause(obj, "lockmax", a["lockmax"], line, seen)
        elif cur.accept("LOCKSIZE"):
            a["locksize"] = cur.next().value
            _clause(obj, "locksize", a["locksize"], line, seen)
        elif cur.accept("LOGGED"):
            a["logged"] = "LOGGED"
            _clause(obj, "logging", "LOGGED", line, seen)
        elif cur.accept("NOT", "LOGGED"):
            a["logged"] = "NOT LOGGED"
            _clause(obj, "logging", "NOT LOGGED", line, seen)
        elif not lob and cur.accept("MAXROWS"):
            a["maxrows"] = cur.integer()
            _clause(obj, "maxrows", a["maxrows"], line, seen)
        elif not lob and cur.accept("MEMBER", "CLUSTER"):
            a["member_cluster"] = True
            _clause(obj, "member-cluster", True, line, seen)
        elif not lob and cur.accept("TRACKMOD"):
            a["trackmod"] = cur.next().value
            _clause(obj, "trackmod", a["trackmod"], line, seen)
        elif cur.accept("USING"):
            _parse_using(cur, obj, seen, line, a)
        elif not lob and cur.accept("PAGENUM"):
            a["pagenum"] = cur.next().value
            _clause(obj, "pagenum", a["pagenum"], line, seen)
        elif not lob and cur.accept("FOR", "SORT"):
            a["usage"] = "SORT"
            _clause(obj, "for-sort", True, line, seen, "usage")
        elif not lob and cur.accept("FOR", "DGTT"):
            a["usage"] = "DGTT"
            _clause(obj, "for-dgtt", True, line, seen, "usage")
        elif cur.is_word("SEGMENTED", "LOCKPART", "LARGE"):
            raise Unsupported("deprecated.clause", f"{cur.peek().raw} is a deprecated/removed table-space option outside the current UTS model.", cur.peek())
        else:
            _dialect(cur, context)
    if lob:
        a["type"] = "LOB"
    elif "maxpartitions" in a or "numparts" not in a:
        a["type"] = "PBG"
    else:
        a["type"] = "PBR"


def _parse_ts_partition(tokens, obj):
    cur = Cursor(tokens)
    line = cur.line()
    cur.expect("PARTITION")
    part = {"number": cur.integer(), "line": line}
    seen = set()
    while not cur.at_end():
        line = cur.line()
        if cur.accept("USING"):
            _parse_using(cur, obj, seen, line, part)
        elif cur.is_word("FREEPAGE", "PCTFREE", "GBPCACHE"):
            _parse_free_gbp(cur, obj, seen, part, line)
        elif cur.accept("COMPRESS"):
            value = cur.next().value
            if value == "YES" and cur.is_word("FIXEDLENGTH", "HUFFMAN"):
                value += " " + cur.next().value
            part["compress"] = value
            _clause(obj, "compress", value, line, seen)
        elif cur.accept("TRACKMOD"):
            part["trackmod"] = cur.next().value
            _clause(obj, "trackmod", part["trackmod"], line, seen)
        elif cur.accept("DSSIZE"):
            part["dssize"] = cur.integer()
            cur.accept("G")
            _clause(obj, "dssize", part["dssize"], line, seen)
        else:
            _dialect(cur, "a table-space PARTITION clause")
    return part


# ---- TABLE

DEFAULT_KEYWORDS = {"NOT", "GENERATED", "PRIMARY", "UNIQUE", "REFERENCES", "CHECK", "CONSTRAINT", "FIELDPROC",
                    "AS", "IMPLICITLY", "INLINE", "WITH", "DEFAULT"}


def _parse_data_type(cur, state):
    start = cur.i
    token = cur.peek()
    if token is None:
        raise ParseError("Missing data type")
    if token.kind not in ("word", "ident"):
        raise ParseError(f"Expected a data type but found {token.raw}", token)
    # SYSIBM.<built-in> or a qualified distinct type.
    if cur.is_op(".", offset=1):
        qualified = cur.name()
        if qualified.schema == "SYSIBM" and qualified.name in BUILTIN_TYPES:
            cur.i = start + 2
            return _parse_builtin(cur, start)
        return DataType(None, str(qualified), distinct=qualified, raw=render_tokens(cur.t[start:cur.i]))
    word = token.value
    if token.kind == "word" and word in BUILTIN_TYPES:
        return _parse_builtin(cur, start)
    if token.kind == "word" and word in FOREIGN_TYPES:
        cur.next()
        if cur.is_op("("):
            cur.group()
        if word in ("NATIONAL", "LONG", "CHARACTER"):
            while cur.is_word("CHARACTER", "CHAR", "VARYING", "VARCHAR", "VARGRAPHIC"):
                cur.next()
            if cur.is_op("("):
                cur.group()
        return DataType(None, word, foreign=FOREIGN_TYPES[word], raw=render_tokens(cur.t[start:cur.i]))
    cur.next()
    return DataType(None, token.value, distinct=Name(None, token.value, token.kind == "ident", token.line),
                    raw=render_tokens(cur.t[start:cur.i]))


def _lob_length(cur):
    inner = cur.group()
    if not inner or inner[0].kind != "number":
        raise ParseError("LOB length must be an integer with optional K, M or G", inner[0] if inner else None)
    value = int(inner[0].value)
    if len(inner) > 1:
        unit = inner[1].value.upper()
        if unit not in LOB_UNITS:
            raise ParseError(f"Unknown LOB length unit {inner[1].raw}", inner[1])
        value *= LOB_UNITS[unit]
    return value


def _parse_builtin(cur, start):
    word = cur.next().value
    dt = DataType(FAMILY[word], word)
    if word in ("CHARACTER", "CHAR"):
        if cur.accept("VARYING"):
            dt.family, dt.name = "VARCHAR", word + " VARYING"
        elif cur.accept("LARGE", "OBJECT"):
            dt.family, dt.name = "CLOB", word + " LARGE OBJECT"
    elif word == "BINARY":
        if cur.accept("VARYING"):
            dt.family, dt.name = "VARBINARY", "BINARY VARYING"
        elif cur.accept("LARGE", "OBJECT"):
            dt.family, dt.name = "BLOB", "BINARY LARGE OBJECT"
    elif word == "DOUBLE":
        cur.accept("PRECISION")
        dt.length = 53
    elif word == "REAL":
        dt.length = 21
    if cur.is_op("("):
        if dt.family in LOB_FAMILIES:
            dt.length = _lob_length(cur)
        else:
            inner = [t for t in cur.group() if not (t.kind == "op" and t.value == ",")]
            numbers = [int(t.value) for t in inner if t.kind == "number" and t.value.isdigit()]
            if dt.family == "XML":
                raise Unsupported("syntax.unmodeled-xml-modifier", "XML type modifiers are recognized but not checked.", inner[0] if inner else None)
            if len(numbers) != len(inner) or not numbers:
                raise ParseError(f"Invalid length/precision for {dt.name}", inner[0] if inner else None)
            dt.length = numbers[0]
            dt.explicit_length = True
            if len(numbers) > 1:
                dt.scale = numbers[1]
            if len(numbers) > 2:
                raise ParseError(f"Too many attributes for {dt.name}")
    # Omitted-length defaults documented in the built-in-type diagram.
    if dt.length is None:
        dt.length = {"DECIMAL": 5, "CHAR": 1, "GRAPHIC": 1, "BINARY": 1, "DECFLOAT": 34, "FLOAT": 53,
                     "CLOB": 1024 ** 2, "BLOB": 1024 ** 2, "DBCLOB": 1024 ** 2}.get(dt.family)
        if dt.family == "TIMESTAMP":
            dt.length = 6
    if dt.family == "DECIMAL" and dt.scale is None:
        dt.scale = 0
    if dt.family == "TIMESTAMP":
        if cur.accept("WITH", "TIME", "ZONE"):
            dt.time_zone = True
        else:
            cur.accept("WITHOUT", "TIME", "ZONE")
    if dt.family in STRING_FAMILIES:
        while True:
            if cur.accept("FOR"):
                dt.subtype = cur.next().value
                cur.expect("DATA")
            elif cur.is_word("CCSID") and cur.peek(1) is not None and cur.peek(1).kind == "number":
                cur.next()
                dt.ccsid = cur.next().value
            else:
                break
    dt.raw = render_tokens(cur.t[start:cur.i])
    return dt


def _parse_default_value(cur, column):
    """Parse WITH DEFAULT / DEFAULT value forms from the column-definition diagram."""
    token = cur.peek()
    if token is None or (token.kind == "word" and token.value in DEFAULT_KEYWORDS) or (token.kind == "op" and token.value == ","):
        column.default, column.default_raw = "type-default", ""
        return None
    start = cur.i
    if token.kind == "string":
        cur.next()
        column.default = "constant"
    elif token.kind == "number" or (token.kind == "op" and token.value in "+-" and cur.peek(1) is not None and cur.peek(1).kind == "number"):
        if token.kind == "op":
            cur.next()
        cur.next()
        column.default = "constant"
    elif cur.accept("NULL"):
        column.default = "null"
    elif cur.accept("USER") or cur.accept("SESSION_USER"):
        column.default = "user"
    elif cur.accept("CURRENT", "SQLID"):
        column.default = "current-sqlid"
    elif token.kind in ("word", "ident") and cur.is_op("(", offset=1):
        name = token.value
        cur.next()
        inner = cur.group()
        column.default = "cast-function"
        if name in ("NOW", "CURRENT_TIMESTAMP", "CURRENT_DATE", "SYSDATE", "GETDATE", "SYSDATETIME", "UUID", "NEWID"):
            column.default = "invalid"
            column.default_raw = render_tokens(cur.t[start:cur.i])
            return f"{column.default_raw} is not a valid DEFAULT form"
        if len(inner) != 1 and not (len(inner) == 2 and inner[0].is_word("CURRENT")):
            column.default = "invalid"
            column.default_raw = render_tokens(cur.t[start:cur.i])
            return "A cast-function DEFAULT takes a single constant, USER, SESSION_USER, CURRENT SQLID or NULL"
    else:
        # Consume a plausible special register/expression for the error message.
        cur.next()
        while cur.peek() is not None and not (cur.peek().kind == "word" and cur.peek().value in DEFAULT_KEYWORDS) and not cur.is_op(","):
            if cur.is_op("("):
                cur.group()
            else:
                cur.next()
            if cur.i - start > 6:
                break
        column.default = "invalid"
        column.default_raw = render_tokens(cur.t[start:cur.i])
        return (f"DEFAULT {column.default_raw} is not a Db2 13 for z/OS default form. Allowed: constant, USER, "
                "SESSION_USER, CURRENT SQLID, NULL, or cast-function(...) for distinct types. A value-less "
                "WITH DEFAULT on DATE/TIME/TIMESTAMP gives the current date/time/timestamp")
    column.default_raw = render_tokens(cur.t[start:cur.i])
    return None


def _parse_identity_options(tokens):
    options, cur = {}, Cursor(tokens)
    while not cur.at_end():
        if cur.accept(","):
            continue
        if cur.accept("START", "WITH"):
            options["START WITH"] = _signed_number(cur)
        elif cur.accept("INCREMENT", "BY"):
            options["INCREMENT BY"] = _signed_number(cur)
        elif cur.accept("NO", "MINVALUE"):
            options["MINVALUE"] = None
        elif cur.accept("MINVALUE"):
            options["MINVALUE"] = _signed_number(cur)
        elif cur.accept("NO", "MAXVALUE"):
            options["MAXVALUE"] = None
        elif cur.accept("MAXVALUE"):
            options["MAXVALUE"] = _signed_number(cur)
        elif cur.accept("NO", "CYCLE"):
            options["CYCLE"] = False
        elif cur.accept("CYCLE"):
            options["CYCLE"] = True
        elif cur.accept("NO", "CACHE"):
            options["CACHE"] = None
        elif cur.accept("CACHE"):
            options["CACHE"] = _signed_number(cur)
        elif cur.accept("NO", "ORDER"):
            options["ORDER"] = False
        elif cur.accept("ORDER"):
            options["ORDER"] = True
        else:
            raise Unsupported("syntax.unrecognized-clause", f"'{cur.peek().raw}' is not an identity option.", cur.peek())
    return options


def _signed_number(cur):
    sign = ""
    if cur.is_op("-") or cur.is_op("+"):
        sign = cur.next().value
    token = cur.next()
    if token.kind != "number":
        raise ParseError(f"Expected a number but found {token.raw}", token)
    return sign + token.value if sign == "-" else token.value


def _parse_references(cur, constraint):
    constraint.parent = cur.name()
    if cur.is_op("("):
        cols = split_commas(cur.group())
        constraint.parent_columns = []
        for col in cols:
            if len(col) == 2 and col[0].is_word("PERIOD") and col[1].is_word("BUSINESS_TIME"):
                constraint.parent_period = True
            else:
                constraint.parent_columns.append(col[0].value)
    while not cur.at_end():
        if cur.accept("ON", "DELETE"):
            if cur.accept("NO", "ACTION"):
                constraint.delete_rule = "NO ACTION"
            elif cur.accept("SET", "NULL"):
                constraint.delete_rule = "SET NULL"
            elif cur.is_word("RESTRICT", "CASCADE"):
                constraint.delete_rule = cur.next().value
            elif cur.is_word("SET") and cur.is_word("DEFAULT", offset=1):
                raise Unsupported("dialect.referential-action", "ON DELETE SET DEFAULT is not Db2 for z/OS syntax; "
                                  "the delete rules are RESTRICT, NO ACTION, CASCADE and SET NULL.", cur.peek())
            else:
                raise ParseError("Expected RESTRICT, NO ACTION, CASCADE or SET NULL", cur.peek())
        elif cur.is_word("ON") and cur.is_word("UPDATE", offset=1):
            raise Unsupported("dialect.referential-on-update", "Db2 13 for z/OS referential constraints have no ON UPDATE "
                              "rule; the references clause supports only ON DELETE.", cur.peek())
        elif cur.accept("NOT", "ENFORCED"):
            constraint.enforced = False
        elif cur.accept("ENFORCED"):
            constraint.enforced = True
        elif cur.accept("ENABLE", "QUERY", "OPTIMIZATION"):
            constraint.query_optimization = True
        else:
            return


def _parse_table_constraint(cur, line, name, legacy_name=False):
    kind = "primary" if cur.accept("PRIMARY", "KEY") else "unique" if cur.accept("UNIQUE") else None
    if kind:
        constraint = Constraint(kind, name, [], line)
        for col in split_commas(cur.group()):
            if len(col) >= 2 and col[0].is_word("BUSINESS_TIME"):
                constraint.period = "BUSINESS_TIME WITHOUT OVERLAPS"
            else:
                if len(col) != 1:
                    raise ParseError(f"Constraint keys must be column names: {render_tokens(col)}", col[0])
                constraint.columns.append(col[0].value)
        return constraint
    if cur.accept("FOREIGN", "KEY"):
        if legacy_name and not cur.is_op("("):
            # ALTER TABLE only: "For compatibility with prior releases, when the CONSTRAINT clause ... is not
            # specified, a constraint-name can be specified following FOREIGN KEY" (ibm-alter-table).
            token = cur.identifier()
            if name is not None:
                raise ParseError("A name after FOREIGN KEY is allowed only when CONSTRAINT is omitted", token)
            name = token.value
        constraint = Constraint("foreign", name, [], line)
        for col in split_commas(cur.group()):
            if len(col) == 2 and col[0].is_word("PERIOD"):
                constraint.period = "PERIOD BUSINESS_TIME"
            else:
                constraint.columns.append(col[0].value)
        cur.expect("REFERENCES")
        _parse_references(cur, constraint)
        return constraint
    if cur.accept("CHECK"):
        inner = cur.group()
        return Constraint("check", name, [], line, condition=render_tokens(inner), condition_tokens=tuple(inner))
    raise ParseError("Expected PRIMARY KEY, UNIQUE, FOREIGN KEY or CHECK", cur.peek())


def _parse_column(tokens, table, state):
    cur = Cursor(tokens)
    name_token = cur.identifier()
    column = Column(name_token.value, None, name_token.line)
    issues = []
    if not cur.at_end() and not cur.is_word("GENERATED", "NOT", "WITH", "DEFAULT", "CONSTRAINT", "PRIMARY", "UNIQUE",
                                             "REFERENCES", "CHECK", "IMPLICITLY"):
        column.type = _parse_data_type(cur, state)
    seen = set()

    def once(key, line):
        if key in seen:
            issues.append(("table.column-clause-repeated", f"Column {column.name}: {key} is specified more than once.", line, {}))
        seen.add(key)

    while not cur.at_end():
        line = cur.line()
        if cur.accept("NOT", "NULL"):
            once("NOT NULL", line)
            column.not_null = True
        elif cur.is_word("NULL"):
            raise Unsupported("dialect.null-attribute", f"Column {column.name}: Db2 13 for z/OS column definitions have no "
                              "NULL attribute. Omit NOT NULL to make a column nullable.", cur.peek())
        elif cur.accept("WITH", "DEFAULT") or cur.accept("DEFAULT"):
            once("DEFAULT", line)
            problem = _parse_default_value(cur, column)
            if problem:
                issues.append(("table.default-value-form", f"Column {column.name}: {problem}.", line, {}))
        elif cur.accept("GENERATED"):
            once("GENERATED", line)
            if cur.accept("ALWAYS"):
                column.generated_mode = "ALWAYS"
            elif cur.accept("BY", "DEFAULT"):
                column.generated_mode = "BY DEFAULT"
            if cur.accept("AS", "IDENTITY"):
                column.generated = "identity"
                if cur.is_op("("):
                    column.identity_options = _parse_identity_options(cur.group())
            elif cur.accept("FOR", "EACH", "ROW", "ON", "UPDATE", "AS", "ROW", "CHANGE", "TIMESTAMP"):
                column.generated = "row-change-timestamp"
            elif cur.accept("AS", "ROW", "BEGIN") or cur.accept("AS", "ROW", "START"):
                column.generated = "row-begin"
            elif cur.accept("AS", "ROW", "END"):
                column.generated = "row-end"
            elif cur.accept("AS", "TRANSACTION", "START", "ID"):
                column.generated = "transaction-start-id"
            elif cur.is_word("AS") and cur.is_op("(", offset=1):
                cur.next()
                column.generated_expression = tuple(cur.group())
                column.generated = "expression"
            elif column.type is not None and column.type.family == "ROWID":
                column.generated = "rowid"
            else:
                raise ParseError(f"Column {column.name}: unrecognized GENERATED clause", cur.peek())
            if column.type is not None and column.type.family == "ROWID":
                column.generated = "rowid" if column.generated in (None, "rowid") else column.generated
        elif cur.is_word("CONSTRAINT", "PRIMARY", "UNIQUE", "REFERENCES", "CHECK"):
            cname = None
            if cur.accept("CONSTRAINT"):
                cname = cur.identifier().value
            cline = cur.line()
            if cur.accept("PRIMARY", "KEY"):
                constraint = Constraint("primary", cname, [column.name], cline, column_level=True)
            elif cur.accept("UNIQUE"):
                constraint = Constraint("unique", cname, [column.name], cline, column_level=True)
            elif cur.accept("REFERENCES"):
                constraint = Constraint("foreign", cname, [column.name], cline, column_level=True)
                _parse_references(cur, constraint)
            elif cur.accept("CHECK"):
                inner = cur.group()
                constraint = Constraint("check", cname, [], cline, condition=render_tokens(inner),
                                        condition_tokens=tuple(inner), column_level=True)
            else:
                raise ParseError("Expected a column constraint", cur.peek())
            table.attrs["constraints"].append(constraint)
        elif cur.accept("FIELDPROC"):
            once("FIELDPROC", line)
            column.fieldproc = cur.name().qualified()
            if cur.is_op("("):
                column.fieldproc_parameters = tuple(cur.group())
        elif cur.accept("AS", "SECURITY", "LABEL"):
            once("AS SECURITY LABEL", line)
            column.security_label = True
        elif cur.accept("IMPLICITLY", "HIDDEN"):
            once("IMPLICITLY HIDDEN", line)
            column.hidden = True
        elif cur.accept("INLINE", "LENGTH"):
            once("INLINE LENGTH", line)
            column.inline_length = cur.integer()
        elif cur.is_word("ON") and cur.is_word("UPDATE", offset=1):
            raise Unsupported("dialect.clause", f"Column {column.name}: ON UPDATE <value> is not Db2 syntax; use "
                              "GENERATED ALWAYS FOR EACH ROW ON UPDATE AS ROW CHANGE TIMESTAMP.", cur.peek())
        else:
            _dialect(cur, f"column {column.name}")
    if column.type is None and column.generated not in ("row-change-timestamp", "row-begin", "row-end", "transaction-start-id"):
        issues.append(("table.column-type-required", f"Column {column.name}: a data type is required except for the "
                       "documented generated timestamp forms.", column.line, {}))
    if column.type is None:
        implied = DataType("TIMESTAMP", "TIMESTAMP", 12 if column.generated != "row-change-timestamp" else 6)
        column.type = implied
    return column, issues


def _parse_partition_by_range(cur, obj, line):
    cur.accept("RANGE")
    keys, nulls_last = [], []
    for part in split_commas(cur.group()):
        k = Cursor(part)
        name = k.identifier().value
        if k.accept("NULLS", "LAST"):
            nulls_last.append(name)
        order = "ASC"
        if k.is_word("ASC", "DESC"):
            order = k.next().value
        if not k.at_end():
            _dialect(k, "a partitioning key")
        keys.append((name, order))
    partitions = []
    for part in split_commas(cur.group()):
        p = Cursor(part)
        pline = p.line()
        p.expect("PARTITION")
        number = p.integer()
        p.expect("ENDING")
        p.accept("AT")
        values = [render_tokens(v, normalized_text) for v in split_commas(p.group())]
        inclusive = p.accept("INCLUSIVE")
        if p.accept("HASH", "SPACE"):
            p.integer()
            p.next()
        if not p.at_end():
            _dialect(p, "a table PARTITION element")
        partitions.append({"number": number, "values": values, "inclusive": inclusive, "line": pline})
    obj.attrs["partition_keys"] = keys
    obj.attrs["partition_nulls_last"] = nulls_last
    obj.attrs["range_partitions"] = partitions
    _clause(obj, "partition-by-range", len(partitions), line)


def _parse_table(cur, result, state):
    cur.expect("TABLE")
    line = cur.line()
    obj = _new_obj(result, "table", cur.name(), line)
    a = obj.attrs
    a.update(columns=[], constraints=[], periods=[], placement="omitted")
    seen = set()
    if cur.accept("LIKE"):
        a["definition"] = "like"
        a["source"] = cur.name()
        _clause(obj, "like", True, line)
        while cur.is_word("INCLUDING", "EXCLUDING", "USING"):
            words = []
            while cur.is_word("INCLUDING", "EXCLUDING", "USING", "IDENTITY", "COLUMN", "ATTRIBUTES", "ROW", "CHANGE",
                              "TIMESTAMP", "XML", "TYPE", "MODIFIERS", "DEFAULTS"):
                words.append(cur.next().value)
            a.setdefault("copy_options", []).append(" ".join(words))
            _clause(obj, "copy-options", " ".join(words), line)
    elif cur.is_op("("):
        elements = split_commas(cur.group())
        if cur.is_word("AS") and cur.is_op("(", offset=1):
            a["definition"] = "as-result"
            a["column_list"] = [e[0].value for e in elements if e]
        else:
            a["definition"] = "explicit"
            _clause(obj, "explicit-elements", len(elements), line)
            for element in elements:
                _parse_element(element, obj, result, state)
    if cur.is_word("AS") and cur.is_op("(", offset=1):
        cur.next()
        cur.group()
        if cur.accept("WITH", "NO", "DATA"):
            a["definition"] = "as-no-data"
            _clause(obj, "as-no-data", True, line)
            while cur.is_word("INCLUDING", "EXCLUDING", "USING"):
                words = []
                while cur.is_word("INCLUDING", "EXCLUDING", "USING", "IDENTITY", "COLUMN", "ATTRIBUTES", "ROW",
                                  "CHANGE", "TIMESTAMP", "XML", "TYPE", "MODIFIERS", "DEFAULTS"):
                    words.append(cur.next().value)
                _clause(obj, "copy-options", " ".join(words), line)
        else:
            a["definition"] = "mqt"
            _clause(obj, "mqt", True, line)
            while cur.is_word("DATA", "REFRESH", "MAINTAINED", "ENABLE", "DISABLE", "INITIALLY", "DEFERRED", "BY",
                              "SYSTEM", "USER", "QUERY", "OPTIMIZATION"):
                cur.next()
    if "definition" not in a:
        raise ParseError("Expected a table element list, LIKE, or AS (fullselect)", cur.peek())
    while not cur.at_end():
        line = cur.line()
        if cur.accept("IN", "DATABASE"):
            a["placement"] = "database"
            a["database"] = cur.identifier().value
            _clause(obj, "in-database", True, line, seen, "in")
        elif cur.accept("IN", "ACCELERATOR"):
            a["placement"] = "accelerator"
            cur.identifier()
            _clause(obj, "in-accelerator", True, line, seen, "in")
        elif cur.accept("IN"):
            first = cur.identifier().value
            if cur.accept("."):
                a["database"], a["tablespace"] = first, cur.identifier().value
            else:
                a["database"], a["tablespace"] = None, first
            a["placement"] = "tablespace"
            _clause(obj, "in-explicit-tablespace", True, line, seen, "in")
        elif cur.accept("PARTITION", "BY", "SIZE"):
            a["partition_by_size"] = None
            if cur.accept("EVERY"):
                a["partition_by_size"] = cur.integer()
                cur.accept("G")
            _clause(obj, "partition-by-size", a["partition_by_size"] or True, line, seen, "partitioning")
        elif cur.accept("PARTITION", "BY"):
            if "partitioning" in seen:
                obj.attrs.setdefault("duplicate_clauses", []).append(("partitioning", line))
            seen.add("partitioning")
            _parse_partition_by_range(cur, obj, line)
        elif cur.accept("ORGANIZE", "BY", "HASH"):
            a["hash"] = True
            cur.accept("UNIQUE")
            cur.group()
            if cur.accept("HASH", "SPACE"):
                cur.integer()
                cur.next()
            _clause(obj, "organization-by-hash", True, line, seen)
        elif cur.accept("EDITPROC"):
            a["editproc"] = cur.name().qualified()
            for form in (("WITH", "ROW", "ATTRIBUTES"), ("WITHOUT", "ROW", "ATTRIBUTES")):
                if cur.accept(*form):
                    a["editproc_row_attributes"] = form[0]
            _clause(obj, "editproc", True, line, seen)
        elif cur.accept("VALIDPROC"):
            a["validproc"] = cur.name().qualified()
            _clause(obj, "validproc", True, line, seen)
        elif cur.accept("AUDIT"):
            a["audit"] = cur.next().value
            _clause(obj, "audit", a["audit"], line, seen)
        elif cur.accept("OBID"):
            a["obid"] = cur.integer()
            _clause(obj, "obid", True, line, seen)
        elif cur.accept("DATA", "CAPTURE"):
            a["data_capture"] = cur.next().value
            _clause(obj, "data-capture", a["data_capture"], line, seen)
        elif cur.accept("WITH", "RESTRICT", "ON", "DROP"):
            a["restrict_on_drop"] = True
            _clause(obj, "restrict-on-drop", True, line, seen)
        elif cur.accept("CCSID"):
            a["ccsid"] = cur.identifier().value
            _clause(obj, "ccsid", a["ccsid"], line, seen)
        elif cur.accept("NOT", "VOLATILE"):
            cur.accept("CARDINALITY")
            a["volatile"] = "NOT VOLATILE"
            _clause(obj, "volatile", "NOT VOLATILE", line, seen)
        elif cur.accept("VOLATILE"):
            cur.accept("CARDINALITY")
            a["volatile"] = "VOLATILE"
            _clause(obj, "volatile", "VOLATILE", line, seen)
        elif cur.accept("APPEND"):
            a["append"] = cur.next().value
            _clause(obj, "append", a["append"], line, seen)
        elif cur.accept("LOGGED"):
            a["logged"] = "LOGGED"
            _clause(obj, "logged", "LOGGED", line, seen)
        elif cur.accept("NOT", "LOGGED"):
            a["logged"] = "NOT LOGGED"
            _clause(obj, "logged", "NOT LOGGED", line, seen)
        elif cur.accept("COMPRESS"):
            value = cur.next().value
            if value == "YES" and cur.is_word("FIXEDLENGTH", "HUFFMAN"):
                value += " " + cur.next().value
            a["compress"] = value
            _clause(obj, "compress", value, line, seen)
        elif cur.accept("DSSIZE"):
            a["dssize"] = cur.integer()
            cur.accept("G")
            _clause(obj, "dssize", a["dssize"], line, seen)
        elif cur.accept("BUFFERPOOL"):
            a["bufferpool"] = cur.identifier().value
            _clause(obj, "bufferpool", a["bufferpool"], line, seen)
        elif cur.accept("MEMBER", "CLUSTER"):
            a["member_cluster"] = True
            _clause(obj, "member-cluster", True, line, seen)
        elif cur.accept("TRACKMOD"):
            a["trackmod"] = cur.next().value
            _clause(obj, "trackmod", a["trackmod"], line, seen)
        elif cur.accept("PAGENUM"):
            a["pagenum"] = cur.next().value
            _clause(obj, "pagenum", a["pagenum"], line, seen)
        elif cur.accept("KEY", "LABEL"):
            a["key_label"] = cur.identifier().value
            _clause(obj, "key-label", True, line, seen)
        elif cur.accept("NO", "KEY", "LABEL"):
            a["key_label"] = None
            _clause(obj, "key-label", "NO KEY LABEL", line, seen)
        else:
            _dialect(cur, "CREATE TABLE")


def _parse_element(tokens, obj, result, state):
    cur = Cursor(tokens)
    line = cur.line()
    if not tokens:
        raise ParseError("Empty table element", None)
    if cur.is_word("CONSTRAINT") or cur.is_word("PRIMARY") and cur.is_word("KEY", offset=1) or \
            cur.is_word("UNIQUE") and cur.is_op("(", offset=1) or \
            cur.is_word("FOREIGN") and cur.is_word("KEY", offset=1) or cur.is_word("CHECK") and cur.is_op("(", offset=1):
        name = None
        if cur.accept("CONSTRAINT"):
            name = cur.identifier().value
        constraint = _parse_table_constraint(cur, line, name)
        if not cur.at_end():
            _dialect(cur, f"constraint {name or ''}".strip())
        obj.attrs["constraints"].append(constraint)
        return
    if cur.is_word("PERIOD") and cur.is_word("FOR", offset=1):
        cur.next()
        cur.next()
        period = cur.identifier().value
        cols = [c[0].value for c in split_commas(cur.group())]
        mode = None
        if cur.is_word("EXCLUSIVE", "INCLUSIVE"):
            mode = cur.next().value
        obj.attrs["periods"].append({"name": period, "columns": cols, "mode": mode, "line": line})
        _clause(obj, "system-period" if period == "SYSTEM_TIME" else "business-period", mode or True, line)
        return
    column, issues = _parse_column(tokens, obj, state)
    result.issues.extend(issues)
    obj.attrs["columns"].append(column)


# ---- AUXILIARY TABLE

def _parse_aux_table(cur, result, state):
    cur.expect("TABLE")
    line = cur.line()
    obj = _new_obj(result, "auxiliary-table", cur.name(), line)
    cur.expect("IN")
    first = cur.identifier().value
    if cur.accept("."):
        obj.attrs["database"], obj.attrs["tablespace"] = first, cur.identifier().value
    else:
        obj.attrs["database"], obj.attrs["tablespace"] = None, first
    cur.expect("STORES")
    obj.attrs["base"] = cur.name()
    if cur.accept("APPEND"):
        obj.attrs["append"] = cur.next().value
    cur.expect("COLUMN")
    obj.attrs["column"] = cur.identifier().value
    if cur.accept("PART"):
        obj.attrs["part"] = cur.integer()
    if not cur.at_end():
        _dialect(cur, "CREATE AUXILIARY TABLE")


# ---- INDEX

def _parse_index(cur, result, state):
    unique, where_not_null = False, False
    line = cur.line()
    if cur.accept("UNIQUE"):
        unique = True
        if cur.accept("WHERE", "NOT", "NULL"):
            where_not_null = True
    cur.expect("INDEX")
    obj = _new_obj(result, "index", cur.name(), line)
    a, seen = obj.attrs, set()
    a.update(unique=unique, where_not_null=where_not_null, keys=[], include=[], expression=False, xmlpattern=False,
             partitions=[])
    if unique:
        _clause(obj, "unique", "UNIQUE WHERE NOT NULL" if where_not_null else "UNIQUE", line)
    if where_not_null:
        _clause(obj, "where-not-null", True, line)
    cur.expect("ON")
    a["table"] = cur.name()
    if cur.is_op("("):
        for part in split_commas(cur.group()):
            k = Cursor(part)
            if k.is_word("BUSINESS_TIME") and len(part) >= 3:
                a["business_time"] = render_tokens(part[1:])
                _clause(obj, "business-time", a["business_time"], part[0].line)
                continue
            order = None
            if part and part[-1].is_word("ASC", "DESC", "RANDOM") and len(part) > 1:
                order = part[-1].value
                part = part[:-1]
            if len(part) == 1 and part[0].kind in ("word", "ident"):
                a["keys"].append((part[0].value, order))
            else:
                a["expression"] = True
                a["keys"].append((render_tokens(part, normalized_text), order))
            _clause(obj, "key-order", order or "<omitted>", part[0].line if part else line)
        _clause(obj, "expression-key" if a["expression"] else "key-list", len(a["keys"]), line)
    else:
        a["auxiliary"] = True
    while not cur.at_end():
        line = cur.line()
        if cur.accept("GENERATE"):
            cur.accept("KEY") or cur.accept("KEYS")
            cur.expect("USING", "XMLPATTERN")
            cur.next()
            cur.expect("AS", "SQL")
            _parse_data_type(cur, state)
            a["xmlpattern"] = True
            _clause(obj, "xmlpattern", True, line, seen)
        elif cur.is_word("INCLUDE") and cur.is_op("(", offset=1):
            cur.next()
            a["include"] = [c[0].value for c in split_commas(cur.group())]
            _clause(obj, "include", len(a["include"]), line, seen)
        elif cur.accept("INCLUDE", "NULL", "KEYS"):
            a["null_keys"] = "INCLUDE"
            _clause(obj, "null-keys", "INCLUDE NULL KEYS", line, seen)
        elif cur.accept("EXCLUDE", "NULL", "KEYS"):
            a["null_keys"] = "EXCLUDE"
            _clause(obj, "null-keys", "EXCLUDE NULL KEYS", line, seen)
        elif cur.accept("NOT", "CLUSTER"):
            a["cluster"] = False
            _clause(obj, "cluster", "NOT CLUSTER", line, seen)
        elif cur.accept("CLUSTER"):
            a["cluster"] = True
            _clause(obj, "cluster", "CLUSTER", line, seen)
        elif cur.accept("PARTITIONED"):
            a["partitioned"] = True
            _clause(obj, "partitioned", True, line, seen)
        elif cur.accept("NOT", "PADDED"):
            a["padded"] = False
            _clause(obj, "padding", "NOT PADDED", line, seen)
        elif cur.accept("PADDED"):
            a["padded"] = True
            _clause(obj, "padding", "PADDED", line, seen)
        elif cur.accept("USING"):
            _parse_using(cur, obj, seen, line, a)
        elif cur.is_word("FREEPAGE", "PCTFREE", "GBPCACHE"):
            _parse_free_gbp(cur, obj, seen, a, line, allow_for_update=False)
        elif cur.accept("DEFINE"):
            a["define"] = cur.next().value
            _clause(obj, "define", a["define"], line, seen)
        elif cur.accept("COMPRESS"):
            a["compress"] = cur.next().value
            _clause(obj, "compress", a["compress"], line, seen)
        elif cur.accept("PARTITION", "BY", "RANGE") or cur.is_word("PARTITION") and cur.is_op("(", offset=1) and cur.accept("PARTITION"):
            for part in split_commas(cur.group()):
                p = Cursor(part)
                p.expect("PARTITION")
                entry = {"number": p.integer()}
                pseen = set()
                while not p.at_end():
                    pline = p.line()
                    if p.accept("USING"):
                        _parse_using(p, obj, pseen, pline, entry)
                    elif p.is_word("FREEPAGE", "PCTFREE", "GBPCACHE"):
                        _parse_free_gbp(p, obj, pseen, entry, pline, allow_for_update=False)
                    elif p.accept("DSSIZE"):
                        entry["dssize"] = p.integer()
                        p.accept("G")
                    elif p.accept("ENDING"):
                        raise Unsupported("deprecated.index-controlled-partitioning", "ENDING AT in CREATE INDEX is the "
                                          "deprecated index-controlled partitioning form.", p.peek(-1))
                    else:
                        _dialect(p, "an index PARTITION clause")
                a["partitions"].append(entry)
            _clause(obj, "partition-attributes", len(a["partitions"]), line, seen)
        elif cur.accept("BUFFERPOOL"):
            a["bufferpool"] = cur.identifier().value
            _clause(obj, "bufferpool", a["bufferpool"], line, seen)
        elif cur.accept("CLOSE"):
            a["close"] = cur.next().value
            _clause(obj, "close", a["close"], line, seen)
        elif cur.accept("DEFER"):
            a["defer"] = cur.next().value
            _clause(obj, "defer", a["defer"], line, seen)
        elif cur.accept("DSSIZE"):
            a["dssize"] = cur.integer()
            cur.accept("G")
            _clause(obj, "dssize", a["dssize"], line, seen)
        elif cur.accept("PIECESIZE"):
            a["piecesize"] = f"{cur.integer()} {cur.next().value}"
            _clause(obj, "piecesize", a["piecesize"], line, seen)
        elif cur.accept("COPY"):
            a["copy"] = cur.next().value
            _clause(obj, "copy", a["copy"], line, seen)
        elif cur.is_word("WHERE"):
            raise Unsupported("dialect.partial-index", "Partial indexes (WHERE <predicate>) are not Db2 for z/OS syntax; "
                              "only UNIQUE WHERE NOT NULL exists.", cur.peek())
        else:
            _dialect(cur, "CREATE INDEX")


# ---- other CREATE statements (recognized for dependencies only)

def _parse_other_create(cur, result, kind, state):
    cur.next()
    if kind == "global-temporary-table":
        cur.next()
        cur.expect("TABLE")
    elif kind == "distinct":
        cur.expect("TYPE")
        kind = result.kind = "type"
    elif kind == "trusted":
        cur.expect("CONTEXT")
    if cur.is_word("PUBLIC") and kind in ("alias", "synonym"):
        cur.next()
    token = cur.peek()
    name = cur.name() if token is not None and token.kind in ("word", "ident") else Name(None, "?")
    obj = _new_obj(result, kind, name, result.statement.line)
    rest = cur.t[cur.i:]
    words = [t for t in rest if t.kind in ("word", "ident")]
    if kind == "trigger":
        for k, t in enumerate(rest):
            if t.is_word("ON") and k + 1 < len(rest):
                sub = Cursor(rest[k + 1:])
                try:
                    obj.attrs["subject"] = sub.name()
                except ParseError:
                    pass
                break
        depth = sum(1 for t in rest if t.is_word("BEGIN")) - sum(1 for t in rest if t.is_word("END"))
        obj.attrs["unbalanced_begin"] = depth > 0
        obj.attrs["sqlpl"] = any(t.is_word("BEGIN") for t in rest)
    elif kind == "procedure":
        depth = sum(1 for t in rest if t.is_word("BEGIN")) - sum(1 for t in rest if t.is_word("END"))
        obj.attrs["unbalanced_begin"] = depth > 0
        obj.attrs["sqlpl"] = any(t.is_word("BEGIN") for t in rest)
    elif kind in ("alias", "synonym"):
        for k, t in enumerate(rest):
            if t.is_word("FOR") and k + 1 < len(rest):
                try:
                    obj.attrs["target"] = Cursor(rest[k + 1:]).name()
                except ParseError:
                    pass
                break
    elif kind == "type":
        for k, t in enumerate(rest):
            if t.is_word("AS") and k + 1 < len(rest):
                try:
                    obj.attrs["source_type"] = _parse_data_type(Cursor(rest[k + 1:]), state)
                except (ParseError, Unsupported):
                    pass
                break
    elif kind == "view":
        refs = []
        for k, t in enumerate(rest):
            if t.is_word("FROM", "JOIN") and k + 1 < len(rest) and rest[k + 1].kind in ("word", "ident"):
                try:
                    refs.append(Cursor(rest[k + 1:]).name())
                except ParseError:
                    pass
        obj.attrs["references"] = refs
    obj.attrs["words"] = len(words)


# ---- ALTER / DROP / SET / COMMENT

def _parse_alter(cur, result, state):
    cur.expect("ALTER")
    if not cur.is_word("TABLE"):
        result.kind = (cur.peek().value.lower() if cur.peek() else None)
        result.detail["unmodeled"] = True
        return
    cur.next()
    result.kind = "table"
    table = cur.name()
    result.detail["table"] = table
    result.detail["constraints"] = []
    result.detail["options"] = {}
    result.detail["unmodeled"] = False
    options, seen, first = result.detail["options"], set(), True

    def option(clause, attribute, value):
        # "The same clause must not be specified more than one time" (ibm-alter-table)
        if clause in seen:
            result.detail.setdefault("duplicate_clauses", []).append((clause, line))
        seen.add(clause)
        options[attribute] = value

    def choice(clause, allowed):
        token = cur.next()
        if token.value not in allowed:
            raise ParseError(f"{clause} takes {' or '.join(allowed)}", token)
        return token.value

    while not cur.at_end():
        line = cur.line()
        if cur.accept("ADD", "RESTRICT", "ON", "DROP"):
            option("add-restrict-on-drop", "restrict_on_drop", True)
        elif cur.accept("DROP", "RESTRICT", "ON", "DROP"):
            option("drop-restrict-on-drop", "restrict_on_drop", False)
        elif cur.is_word("ADD", "CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK"):
            added = cur.accept("ADD")
            if not cur.is_word("CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK"):
                result.detail["unmodeled"] = True
                return
            start, name = cur.peek(), None
            if cur.accept("CONSTRAINT"):
                name = cur.identifier().value
            if not added and (not first or cur.is_word("CHECK")):
                # "The ADD keyword is optional for referential-constraint or unique-constraint if it is the first
                # clause specified in the statement. Otherwise, ADD is required." (ibm-alter-table)
                result.issues.append(("syntax.alter-add-required", "ADD can be omitted only before a unique or "
                                      "referential constraint that is the first clause of ALTER TABLE.", start.line, {}))
            result.detail["constraints"].append(_parse_table_constraint(cur, line, name, legacy_name=True))
        elif cur.accept("DATA", "CAPTURE"):
            option("data-capture", "data_capture", choice("DATA CAPTURE", ("NONE", "CHANGES")))
        elif cur.accept("AUDIT"):
            option("audit", "audit", choice("AUDIT", ("NONE", "CHANGES", "ALL")))
        elif cur.accept("APPEND"):
            option("append", "append", choice("APPEND", ("NO", "YES")))
        elif cur.accept("NOT", "VOLATILE"):
            cur.accept("CARDINALITY")
            option("volatile", "volatile", "NOT VOLATILE")
        elif cur.accept("VOLATILE"):
            cur.accept("CARDINALITY")
            option("volatile", "volatile", "VOLATILE")
        elif cur.accept("VALIDPROC"):
            option("validproc", "validproc", None if cur.accept("NULL") else cur.name().qualified())
        else:
            result.detail["unmodeled"] = True
            return
        first = False
    if "add-restrict-on-drop" in seen:
        options["restrict_on_drop"] = True  # ADD clauses are processed after DROP clauses (ibm-alter-table notes)


def _parse_drop(cur, result):
    cur.expect("DROP")
    token = cur.peek()
    if token is None:
        raise ParseError("DROP requires an object type")
    kind = token.value.lower()
    cur.next()
    if kind == "lob":
        cur.expect("TABLESPACE")
        kind = "tablespace"
    if kind in ("specific",):
        kind = cur.next().value.lower()
    result.kind = kind
    if cur.is_word("IF"):
        raise Unsupported("dialect.if-exists", "DROP ... IF EXISTS is not in the Db2 13 for z/OS DROP diagram.", cur.peek())
    if not cur.at_end():
        result.detail["name"] = cur.name()


def _parse_set(cur, result, state):
    cur.expect("SET")
    result.kind = None
    if cur.accept("CURRENT", "RULES") or cur.accept("CURRENT_RULES"):
        cur.accept("=")
        token = cur.next()
        state["rules"] = token.value.upper()
        result.detail["rules"] = state["rules"]
    elif cur.accept("CURRENT", "SCHEMA") or cur.accept("SCHEMA") or cur.accept("CURRENT_SCHEMA"):
        cur.accept("=")
        token = cur.next()
        state["schema"] = token.value if token.kind in ("string", "ident") else token.value.upper()
        result.detail["schema"] = state["schema"]
    elif cur.accept("CURRENT", "SQLID") or cur.accept("CURRENT_SQLID"):
        cur.accept("=")
        token = cur.next()
        state["sqlid"] = token.value if token.kind in ("string", "ident") else token.value.upper()
        result.detail["sqlid"] = state["sqlid"]
    elif cur.accept("CURRENT", "APPLICATION", "COMPATIBILITY"):
        cur.accept("=")
        state["applcompat"] = cur.next().value


def _parse_comment_label(cur, result):
    verb = cur.next().value
    cur.expect("ON")
    result.kind = None
    if cur.is_word("TABLE", "INDEX", "COLUMN", "TABLESPACE", "ALIAS", "SEQUENCE", "TRIGGER", "PROCEDURE", "FUNCTION",
                   "TYPE", "DISTINCT", "VIEW", "PACKAGE", "PLAN", "ROLE", "TRUSTED", "MASK", "PERMISSION", "VARIABLE"):
        result.detail["target_kind"] = cur.next().value.lower()
        if result.detail["target_kind"] == "column":
            name = cur.name(3)
            result.detail["target"] = name
        else:
            result.detail["target"] = cur.name()
    else:
        # COMMENT ON table (col IS ..., ...) form
        result.detail["target_kind"] = "table"
        result.detail["target"] = cur.name()
    result.detail["verb"] = verb
