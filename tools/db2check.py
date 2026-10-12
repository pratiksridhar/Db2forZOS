#!/usr/bin/env python3
"""Static Db2 13 for z/OS checks, syntax-variety coverage, semantic DDL diff and
QA bundle derivation for arbitrary DDL scripts.

Every finding cites a rule in kb/data/db2z13-ddl-checks.json, which in turn
cites official IBM Db2 13 for z/OS sources. Passing these checks never proves
that Db2 accepts a script; only execution on a recorded subsystem does.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

import db2sql as sq
import paths

ROOT = paths.ROOT
CHECKS = paths.DDL_CHECKS
KB = paths.CREATE_DDL
FUNCTION_LEVELS = paths.FUNCTION_LEVELS
LEVEL = re.compile(r"V(10|11|12|13)R1(?:M(\d{3}))?")
UTS_BASELINE = (12, 504)
TOKEN_GATES = {  # identifier tokens that are only valid at a gated APPLCOMPAT level
    "GENERATE_UUID": "uuid-functions", "GENERATE_UUID_BINARY": "uuid-functions", "VARBINARY_FORMAT": "uuid-functions",
    "VARCHAR_FORMAT_BINARY": "uuid-functions", "INTERPRET": "interpret-function", "AI_ANALOGY": "ai-functions",
    "AI_SEMANTIC_CLUSTER": "ai-functions", "AI_SIMILARITY": "ai-functions", "AI_COMMONALITY": "ai-commonality",
    "DEADLOCK_RESOLUTION_PRIORITY": "deadlock-priority", "SYSTIME_PERIOD_ADJUST": "systime-period-adjust",
    "UNIT_OF_RECOVERY_ID": "trigger-unit-of-recovery-id",
}


def level_key(value):
    """V12R1M504 -> (12, 504); V11R1 -> (11, 0); invalid -> None."""
    match = LEVEL.fullmatch(value or "")
    return (int(match.group(1)), int(match.group(2) or 0)) if match else None


def level_name(key):
    return f"V{key[0]}R1" + (f"M{key[1]:03d}" if key[1] else "")


def function_level_data():
    return read_json(FUNCTION_LEVELS)

FAILING = {"error", "unsupported"}
DEFAULT_SCHEMA = "<CURRENT SCHEMA>"
BUFFERPOOL = re.compile(r"BP(?:(?:[0-9]|[1-4][0-9])|8K[0-9]|16K[0-9]|32K[1-9]?)")
SHORT_NAME = re.compile(r"[A-Z][A-Z0-9]*")
SHORT_NAME_EXTENDED = re.compile(r"[A-Z$#@][A-Z0-9_$#@]*")
RECORD_LIMIT = {4: 4056, 8: 8138, 16: 16330, 32: 32714}
VARYING_LIMIT = {"VARCHAR": {4: 4046, 8: 8128, 16: 16320, 32: 32704}, "VARBINARY": {4: 4046, 8: 8128, 16: 16320, 32: 32704},
                 "VARGRAPHIC": {4: 2023, 8: 4064, 16: 8160, 32: 16352}}  # Limits page, string length limits
# MAXPARTITIONS ceilings by DSSIZE (G) and page size (KB), CREATE TABLESPACE Table 1.
MAXPART_CEILING = {
    1: {4: 4096, 8: 4096, 16: 4096, 32: 4096}, 2: {4: 4096, 8: 4096, 16: 4096, 32: 4096},
    4: {4: 4096, 8: 4096, 16: 4096, 32: 4096}, 8: {4: 2048, 8: 4096, 16: 4096, 32: 4096},
    16: {4: 1024, 8: 2048, 16: 4096, 32: 4096}, 32: {4: 512, 8: 1024, 16: 2048, 32: 4096},
    64: {4: 256, 8: 512, 16: 1024, 32: 2048}, 128: {4: 128, 8: 256, 16: 512, 32: 1024},
    256: {4: 64, 8: 128, 16: 256, 32: 512},
}
POWERS_OF_TWO = {1, 2, 4, 8, 16, 32, 64, 128, 256}
TYPE_LIMITS = {  # family: (min, max) for the declared length/precision
    "CHAR": (1, 255), "VARCHAR": (1, 32704), "GRAPHIC": (1, 127), "VARGRAPHIC": (1, 16352),
    "BINARY": (1, 255), "VARBINARY": (1, 32704), "DECIMAL": (1, 31), "FLOAT": (1, 53),
    "TIMESTAMP": (0, 12), "CLOB": (1, 2147483647), "BLOB": (1, 2147483647), "DBCLOB": (1, 1073741823),
}
NOT_CHECKED_KINDS = {"view", "alias", "synonym", "sequence", "type", "function", "procedure", "trigger", "role", "mask",
                     "permission", "trusted", "variable", "schema", "global-temporary-table"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rule_catalog():
    data = read_json(CHECKS)
    return {rule["id"]: rule for rule in data["rules"]}


@dataclass
class Finding:
    rule: str
    severity: str
    message: str
    line: int = 0
    statement: int = 0
    object: str | None = None

    def as_dict(self, rules):
        rule = rules.get(self.rule, {})
        return {"rule": self.rule, "severity": self.severity, "line": self.line, "statement": self.statement,
                "object": self.object, "message": self.message, "kb_rules": rule.get("kb_rules", []),
                "source_refs": rule.get("source_refs", [])}


@dataclass
class Options:
    terminator: str = ";"
    column_name_expansion: bool | None = None  # TABLE_COLUMN_NAME_EXPANSION
    current_rules: str = "DB2"
    max_line: int | None = None
    allow_placeholders: bool = False
    function_level: str | None = None
    applcompat: str | None = None
    assume: list = field(default_factory=list)  # "KIND:NAME"
    subsystem_parameters: dict = field(default_factory=dict)

    @classmethod
    def from_profile(cls, profile, **overrides):
        options = cls(**overrides)
        if profile:
            context = profile.get("product_context", profile)
            params = context.get("subsystem_parameters", {}) or {}
            options.subsystem_parameters = params
            # IBM spells the parameter both ways: TABLE_COL_NAME_EXPANSION (DSN6SPRM) and TABLE_COLUMN_NAME_EXPANSION.
            value = params.get("TABLE_COL_NAME_EXPANSION", params.get("TABLE_COLUMN_NAME_EXPANSION"))
            if isinstance(value, bool):
                options.column_name_expansion = value
            elif isinstance(value, str) and value.upper() in ("YES", "ON", "Y", "NO", "OFF", "N"):
                options.column_name_expansion = value.upper() in ("YES", "ON", "Y")
            if context.get("current_rules") in ("DB2", "STD"):
                options.current_rules = context["current_rules"]
            options.function_level = context.get("function_level") or None
            options.applcompat = context.get("applcompat") or None
        return options


@dataclass
class TableState:
    obj: object
    key: str
    schema_default: str | None
    columns: dict = field(default_factory=dict)
    pk: object = None
    uniques: list = field(default_factory=list)
    fks: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    tablespace: object = None  # TablespaceState or None
    database: str | None = None
    implicit_space: bool = False
    external: bool = False
    aux: bool = False
    enforced_keys: set = field(default_factory=set)  # tuples of columns with unique enforcing index
    aux_tables: dict = field(default_factory=dict)  # (column, part) -> aux table key
    rules: str = "DB2"
    clustering_index: str | None = None
    indexes: list = field(default_factory=list)

    @property
    def partitioned(self):
        return bool(self.tablespace and self.tablespace.obj.attrs.get("type") == "PBR")


def partitioning_index(table, attrs):
    """"An index is considered a partitioning index if the specified index key columns match or comprise a
    superset of the columns specified in the partitioning key, are in the same order, and have the same
    ascending or descending attributes" (ibm-create-index)."""
    partition_keys = [(name, order or "ASC") for name, order in table.obj.attrs.get("partition_keys", [])]
    keys = [(name, order or "ASC") for name, order in attrs.get("keys", [])]
    return bool(partition_keys) and keys[:len(partition_keys)] == partition_keys


def delete_rule(constraint, state):
    """The explicit delete rule, else the CURRENT RULES default of the statement that defined the constraint."""
    return constraint.delete_rule or ("RESTRICT" if (constraint.rules or state.rules) == "DB2" else "NO ACTION")


def not_logged(state):
    """True when the table's table space specifies NOT LOGGED: the explicit space, or the implicit one its CREATE TABLE describes."""
    attrs = state.tablespace.obj.attrs if state.tablespace is not None else state.obj.attrs
    return attrs.get("logged") == "NOT LOGGED"


def _auxiliary(state):
    """an auxiliary table, which accepts only APPEND"""
    return state.aux


def _accelerator_only(state):
    """an accelerator-only table, which accepts only ADD or DROP RESTRICT ON DROP"""
    return state.obj.attrs.get("placement") == "accelerator"


def _materialized_query(state):
    """a materialized query table, which accepts AUDIT, DATA CAPTURE and RESTRICT ON DROP among the modeled clauses"""
    return state.obj.attrs.get("definition") == "mqt"


# ALTER TABLE clauses a kind of table accepts, among those the parser models (ibm-alter-table, table-name).
ALTER_LIMITS = ((_auxiliary, {"append"}), (_accelerator_only, {"restrict_on_drop"}),
                (_materialized_query, {"audit", "data_capture", "restrict_on_drop"}))


@dataclass
class TablespaceState:
    obj: object
    key: str
    database: str
    table: str | None = None
    external: bool = False


class Report:
    def __init__(self, options, rules):
        self.options, self.rules = options, rules
        self.findings, self.parsed, self.objects = [], [], []
        self.tables, self.tablespaces, self.indexes, self.databases = {}, {}, {}, {}
        self.stogroups, self.relations, self.types = {}, {}, {}
        self.not_checked = Counter()
        self.statement_count = 0
        self.drops = []
        self.compatibility = {}

    def add(self, rule, message, line=0, statement=0, obj=None, severity=None):
        if rule not in self.rules:
            raise KeyError(f"Unregistered lint rule {rule}")
        self.findings.append(Finding(rule, severity or self.rules[rule]["severity"], message, line, statement, obj))

    def counts(self):
        return dict(Counter(f.severity for f in self.findings))

    def failed(self, allow_unsupported=False):
        failing = {"error"} if allow_unsupported else FAILING
        return any(f.severity in failing for f in self.findings)

    def as_dict(self, allow_unsupported=False):
        return {"status": "fail" if self.failed(allow_unsupported) else "pass",
                "statements": self.statement_count, "counts": self.counts(),
                "not_checked": dict(self.not_checked), "compatibility": self.compatibility,
                "findings": [f.as_dict(self.rules) for f in sorted(self.findings, key=lambda f: (f.line, f.rule))],
                "scope": "Static checks against encoded IBM Db2 13 for z/OS rules. Not proof of Db2 acceptance."}


# --------------------------------------------------------------------------- helpers

def qualified(name, default):
    return name.qualified(default or DEFAULT_SCHEMA)


OVERLAPS = "BUSINESS_TIME WITHOUT OVERLAPS"


def enforcement_key(constraint):
    """Key an enforcing unique index must match: same columns, same order, plus WITHOUT OVERLAPS when used."""
    return tuple(constraint.columns) + ((OVERLAPS,) if constraint.period == OVERLAPS else ())


def index_key(attrs):
    keys = tuple(k for k, _ in attrs.get("keys", []))
    return keys + ((OVERLAPS,) if "WITHOUT" in (attrs.get("business_time") or "") else ())


def length_attr(dt):
    """Length attribute used in key-length formulas (bytes)."""
    if dt is None or dt.family is None:
        return None
    f = dt.family
    if f in ("GRAPHIC", "VARGRAPHIC"):
        return 2 * (dt.length or 0)
    if f == "DECIMAL":
        return (dt.length or 5) // 2 + 1
    if f == "TIMESTAMP":
        precision = 6 if dt.length is None else dt.length
        return 7 + (precision + 1) // 2 + (2 if dt.time_zone else 0)
    return dt.storage_bytes()


def key_length(columns, padded=True):
    total, nullable, varying, decfloat = 0, 0, 0, 0
    for column in columns:
        size = length_attr(column.type)
        if size is None:
            return None
        total += size
        nullable += column.nullable
        varying += column.type.family in sq.VARYING_FAMILIES
        decfloat += column.type.family == "DECFLOAT"
    return total, nullable, varying, decfloat


def page_size(bufferpool):
    if not bufferpool:
        return None
    for size in (32, 16, 8):
        if bufferpool.startswith(f"BP{size}K"):
            return size
    return 4


def parse_assumptions(values):
    assumed = defaultdict(set)
    for value in values:
        kind, separator, name = value.partition(":")
        if not separator or not name:
            raise ValueError(f"--assume expects KIND:NAME, for example table:SCHEMA.T1 or database:DB1, not {value!r}")
        assumed[kind.strip().lower()].add(name.strip().upper())
    return assumed


# --------------------------------------------------------------------------- analysis

def analyze(text, options=None):
    options = options or Options()
    report = Report(options, rule_catalog())
    assumed = parse_assumptions(options.assume)
    assumed["stogroup"].add("SYSDEFLT")
    assumed["database"].add("DSNDB04")
    try:
        statements = sq.split_script(text, options.terminator)
    except sq.ParseError as error:
        report.add("script.parse-error", str(error))
        return report
    report.statement_count = len(statements)
    if options.max_line:
        for number, line in enumerate(text.splitlines(), 1):
            if len(line) > options.max_line:
                report.add("script.record-length", f"Line has {len(line)} characters; the requested maximum is {options.max_line}.", number)
    state = {"rules": options.current_rules, "schema": None, "sqlid": None}
    parsed = []
    for statement in statements:
        result = sq.parse_statement(statement, state)
        result.detail["schema_default"] = state.get("schema") or state.get("sqlid")
        result.detail["rules"] = state["rules"]
        parsed.append(result)
        if not statement.terminated:
            report.add("script.unterminated-statement", "The final statement has no outer terminator.", statement.line, statement.index)
    report.parsed = parsed
    created_at = {}
    for result in parsed:
        if result.verb == "CREATE" and result.obj is not None:
            created_at.setdefault(_object_key(result), result.statement.index)
    checker = Checker(report, assumed, created_at)
    for result in parsed:
        for code, message, line, _ in result.issues:
            report.add(code, message, line, result.statement.index, _label(result))
        tokens = sorted({t.value for t in result.tokens if t.value.startswith("{{")})
        if tokens:
            report.add("script.placeholder", f"Unresolved placeholder(s) {', '.join(tokens)}.", result.statement.line,
                       result.statement.index, _label(result), "notice" if options.allow_placeholders else None)
        checker.apply(result)
    checker.finish()
    return report


def _label(result):
    if result.obj is not None:
        return f"{result.obj.kind} {result.obj.name}"
    return None


def _object_key(result):
    obj, default = result.obj, result.detail.get("schema_default")
    kind = obj.kind
    if kind in ("tablespace", "lob-tablespace"):
        return ("tablespace", f"{obj.attrs.get('database') or 'DSNDB04'}.{obj.name.name}")
    if kind in ("table", "auxiliary-table", "view", "alias", "synonym", "global-temporary-table"):
        return ("relation", qualified(obj.name, default))
    if kind in ("database", "stogroup"):
        return (kind, obj.name.name)
    return (kind, qualified(obj.name, default))


class Checker:
    def __init__(self, report, assumed, created_at):
        self.r, self.assumed, self.created_at = report, assumed, created_at
        self.padix_dependent = 0
        self.requirements = []  # (gate id, line, statement, detail, severity)
        self.gates = {g["id"]: g for g in function_level_data()["applcompat_gates"]}
        self.default_maxpartitions = 0

    # ---- generic helpers
    def find(self, rule, message, result, line=None, obj=None, severity=None):
        self.r.add(rule, message, line or result.statement.line, result.statement.index, obj or _label(result), severity)

    def require(self, gate, result, detail, line=None, severity=None):
        if gate not in self.gates:
            raise KeyError(f"Unknown APPLCOMPAT gate {gate}")
        self.requirements.append((gate, line or result.statement.line, result.statement.index, detail, severity))

    def scan_tokens(self, result):
        words = [t.value for t in result.tokens if t.kind == "word"]
        for word in set(words) & TOKEN_GATES.keys():
            line = next(t.line for t in result.tokens if t.kind == "word" and t.value == word)
            self.require(TOKEN_GATES[word], result, word, line)
        joined = " ".join(words)
        if "CURRENT LOCK TIMEOUT" in joined:
            self.require("lock-timeout", result, "CURRENT LOCK TIMEOUT")
        verb = result.verb
        if verb == "INSERT":
            tokens = result.tokens
            for k, token in enumerate(tokens):
                if token.is_word("VALUES"):
                    depth, rows = 0, 0
                    for t in tokens[k + 1:]:
                        if t.kind == "op" and t.value == "(":
                            depth += 1
                            rows += depth == 1
                        elif t.kind == "op" and t.value == ")":
                            depth -= 1
                    if rows > 1:
                        self.require("multirow-insert", result, f"INSERT with {rows} VALUES rows")
                    break
        elif verb == "ALTER" and words[1:2] == ["TABLE"]:
            if "ALTER PARTITIONING TO PARTITION BY RANGE" in joined:
                self.require("alter-partitioning-range", result, "ALTER PARTITIONING TO PARTITION BY RANGE")
            if "ALTER PARTITIONING TO PARTITION BY GROWTH" in joined:
                self.require("alter-partitioning-growth", result, "ALTER PARTITIONING TO PARTITION BY GROWTH")
            if " ADD " in f" {joined} " and "ROWID" in words and "IMPLICITLY HIDDEN" in joined:
                self.require("hidden-rowid-add-column", result, "ADD COLUMN ... ROWID ... IMPLICITLY HIDDEN")
            if "COMPRESS YES FIXEDLENGTH" in joined or "COMPRESS YES HUFFMAN" in joined:
                self.require("compress-algorithm", result, "COMPRESS YES FIXEDLENGTH/HUFFMAN")
            if "KEY LABEL" in joined:
                self.require("key-label", result, "KEY LABEL")
        elif verb == "ALTER" and words[1:2] == ["TABLESPACE"]:
            if "FOR SORT" in joined or "FOR DGTT" in joined:
                self.require("workfile-usage", result, "ALTER TABLESPACE FOR SORT/FOR DGTT (also needs PH71332)")
            if "MOVE TABLE" in joined:
                self.require("alter-tablespace-move-table", result, "MOVE TABLE")
            if "COMPRESS YES FIXEDLENGTH" in joined or "COMPRESS YES HUFFMAN" in joined:
                self.require("compress-algorithm", result, "COMPRESS YES FIXEDLENGTH/HUFFMAN")
        elif verb == "ALTER" and words[1:2] == ["STOGROUP"] and "KEY LABEL" in joined:
            self.require("key-label", result, "KEY LABEL")
        elif verb == "TRANSFER" and words[:2] == ["TRANSFER", "OWNERSHIP"]:
            target = words[3] if len(words) > 3 and words[2] == "OF" else ""
            if target in ("PROCEDURE", "FUNCTION", "SEQUENCE", "SPECIFIC"):
                self.require("transfer-ownership-routines", result, f"TRANSFER OWNERSHIP OF {target}")
            self.r.not_checked["TRANSFER OWNERSHIP"] += 1

    def reference(self, kind, key, result, what, line=None):
        """Resolve a reference; report forward or external references. Returns True when created earlier."""
        registry = {"database": self.r.databases, "stogroup": self.r.stogroups, "tablespace": self.r.tablespaces,
                    "relation": self.r.relations, "type": self.r.types}[kind]
        if key in registry:
            return True
        assumed = self.assumed.get(kind, set()) | (self.assumed.get("table", set()) if kind == "relation" else set())
        if key.upper() in assumed or key in assumed:
            return False
        later = self.created_at.get((kind, key))
        if later and later > result.statement.index:
            self.find("dependency.order", f"{what} {key} is referenced before it is created (statement {later}).", result, line)
        else:
            self.find("dependency.external", f"{what} {key} is not created in this script; it must already exist "
                      f"(declare it with --assume {kind if kind != 'relation' else 'table'}:{key}).", result, line)
        return False

    def check_name(self, result, name, limit, what, line=None, short=False):
        if "{{" in name.name:
            return
        size = sq.utf8_len(name.name)
        if size > limit:
            self.find("name.length", f"{what} name {name.name} is {size} bytes; the limit is {limit}.", result, line or name.line)
        if name.schema and sq.utf8_len(name.schema) > 128:
            self.find("name.length", f"Schema {name.schema} exceeds 128 bytes.", result, line or name.line)
        if short and not name.delimited:
            if not SHORT_NAME.fullmatch(name.name):
                if SHORT_NAME_EXTENDED.fullmatch(name.name) and name.name[0].isalpha():
                    self.find("name.short-identifier-extender", f"{what} name {name.name} contains _, $, # or @.", result, line or name.line)
                else:
                    self.find("name.short-identifier-form", f"{what} name {name.name} must start with a letter and contain only letters and digits.", result, line or name.line)
        elif short and name.delimited:
            self.find("name.short-identifier-form", f"{what} name {name.name} is a delimited identifier; database and table-space names must be ordinary identifiers.", result, line or name.line)

    def removed_feature(self, result, what):
        applcompat = level_key(self.r.options.applcompat)
        if applcompat is not None and applcompat < UTS_BASELINE:
            self.find("fl.deprecated-feature", f"{what} is deprecated; it cannot be created at APPLCOMPAT V12R1M504 or higher and IBM announces removal at V13R1M511.", result)
        else:
            level = self.r.options.applcompat or "unrecorded (assuming the V12R1M504+ UTS baseline)"
            self.find("fl.removed-feature", f"{what} cannot be created at APPLCOMPAT V12R1M504 or higher (profile: {level}).", result)

    def check_column_name(self, result, column):
        size = sq.utf8_len(column.name)
        expansion = self.r.options.column_name_expansion
        if size > 128:
            self.find("name.length", f"Column {column.name} is {size} bytes; the limit is 128.", result, column.line)
        elif size > 30:
            if expansion:
                self.find("name.column-expansion", f"Column {column.name} is {size} bytes and relies on TABLE_COLUMN_NAME_EXPANSION.", result, column.line)
            else:
                state = "off" if expansion is False else "not recorded in the profile"
                self.find("name.length", f"Column {column.name} is {size} bytes; without TABLE_COLUMN_NAME_EXPANSION ({state}) the limit is 30.", result, column.line)

    def check_bufferpool(self, result, value, what, line=None):
        if value and not BUFFERPOOL.fullmatch(value):
            self.find("name.bufferpool", f"{what} {value} is not a documented buffer-pool name.", result, line)

    def duplicates(self, result, obj):
        for clause, line in obj.attrs.get("duplicate_clauses", []):
            self.find("syntax.duplicate-clause", f"{clause.upper()} is specified more than once.", result, line)

    # ---- dispatch
    def apply(self, result):
        self.scan_tokens(result)
        if result.verb == "CREATE" and result.obj is not None:
            self.r.objects.append(result)
            handler = {"stogroup": self.stogroup, "database": self.database, "tablespace": self.tablespace,
                       "lob-tablespace": self.tablespace, "table": self.table, "auxiliary-table": self.aux_table,
                       "index": self.index}.get(result.obj.kind)
            if handler:
                handler(result)
            else:
                self.other(result)
        elif result.verb == "ALTER":
            self.alter(result)
        elif result.verb == "DROP":
            self.drop(result)
        elif result.verb in ("COMMENT", "LABEL", "GRANT", "REVOKE"):
            self.r.not_checked[result.verb] += 1

    def stogroup(self, result):
        obj = result.obj
        self.check_name(result, obj.name, 128, "Storage group")
        if "key_label" in obj.attrs:
            self.require("key-label", result, "CREATE STOGROUP ... KEY LABEL")
        self.duplicates(result, obj)
        self.register(self.r.stogroups, obj.name.name, result, obj)

    def database(self, result):
        obj = result.obj
        name = obj.name.name
        self.check_name(result, obj.name, 8, "Database", short=True)
        if name.startswith("DSNDB") or re.fullmatch(r"DSN\d{5}", name):
            self.find("name.reserved-database", f"Database name {name} is reserved.", result)
        self.check_bufferpool(result, obj.attrs.get("bufferpool"), "BUFFERPOOL")
        self.check_bufferpool(result, obj.attrs.get("indexbp"), "INDEXBP")
        if obj.attrs.get("stogroup"):
            self.reference("stogroup", obj.attrs["stogroup"], result, "Storage group")
        self.duplicates(result, obj)
        self.register(self.r.databases, name, result, obj)

    def register(self, registry, key, result, value):
        if key in registry:
            self.find("name.duplicate-object", f"{key} is already created in statement {self._statement_of(registry[key])}.", result)
        registry[key] = value

    @staticmethod
    def _statement_of(value):
        obj = getattr(value, "obj", value)
        return getattr(obj, "statement", "?")

    def tablespace(self, result):
        obj, a = result.obj, result.obj.attrs
        lob = obj.kind == "lob-tablespace"
        self.check_name(result, obj.name, 8, "Table space", short=True)
        database = a.get("database") or "DSNDB04"
        if not a.get("database"):
            self.find("dependency.default-database", f"Table space {obj.name.name} has no IN clause and is created in DSNDB04.", result)
        else:
            self.reference("database", database, result, "Database")
        self.check_bufferpool(result, a.get("bufferpool"), "BUFFERPOOL")
        if a.get("stogroup"):
            self.reference("stogroup", a["stogroup"], result, "Storage group")
        self.duplicates(result, obj)
        segsize = a.get("segsize")
        if segsize is not None and (segsize < 4 or segsize > 64 or segsize % 4):
            self.find("tablespace.segsize-range", f"SEGSIZE {segsize} is not a multiple of 4 in 4-64.", result)
        kind = a.get("type")
        pages = page_size(a.get("bufferpool"))
        dssize = a.get("dssize")
        if "maxpartitions" in a:
            mp = a["maxpartitions"]
            if not 1 <= mp <= 4096:
                self.find("tablespace.maxpartitions-range", f"MAXPARTITIONS {mp} is outside 1-4096.", result)
            elif dssize in MAXPART_CEILING and pages and mp > MAXPART_CEILING[dssize][pages]:
                self.find("tablespace.maxpartitions-range", f"MAXPARTITIONS {mp} exceeds {MAXPART_CEILING[dssize][pages]} for DSSIZE {dssize} G with {pages} KB pages.", result)
        if "numparts" in a:
            n = a["numparts"]
            if not 1 <= n <= 4096:
                self.find("tablespace.numparts-range", f"NUMPARTS {n} is outside 1-4096.", result)
            if "maxpartitions" in a and n > a["maxpartitions"]:
                self.find("tablespace.numparts-range", f"NUMPARTS {n} exceeds MAXPARTITIONS {a['maxpartitions']}.", result)
        relative = a.get("pagenum") == "RELATIVE"
        for part in a.get("partitions", []):
            if part.get("dssize") is not None:
                if not relative:
                    self.find("tablespace.dssize-value", f"Partition {part['number']} DSSIZE requires PAGENUM RELATIVE.", result, part.get("line"))
                elif not 1 <= part["dssize"] <= 1024:
                    self.find("tablespace.dssize-value", f"Partition {part['number']} DSSIZE {part['dssize']} G is outside 1-1024 G.", result, part.get("line"))
        if dssize is not None:
            if kind == "PBR" and relative:
                if not 1 <= dssize <= 1024:
                    self.find("tablespace.dssize-value", f"DSSIZE {dssize} G is outside 1-1024 G for relative page numbering.", result)
            elif dssize not in POWERS_OF_TWO and not lob:
                self.find("tablespace.dssize-value", f"DSSIZE {dssize} G must be a power of two from 1 to 256.", result)
            if dssize > 4:
                self.find("tablespace.dssize-dfsms", f"DSSIZE {dssize} G needs an extended-format, extended-addressability DFSMS data class.", result)
        self.free_space(result, a, "Table space")
        for part in a.get("partitions", []):
            self.free_space(result, part, f"Partition {part['number']}", part.get("line"))
        if "maxrows" in a and not 1 <= a["maxrows"] <= 255:
            self.find("tablespace.maxrows-range", f"MAXROWS {a['maxrows']} is outside 1-255.", result)
        locksize = a.get("locksize")
        allowed = {"ANY", "LOB"} if lob else {"ANY", "TABLESPACE", "PAGE", "ROW"}
        if locksize and locksize not in allowed:
            self.find("tablespace.locksize-value", f"LOCKSIZE {locksize} is not valid for a {'LOB' if lob else 'base'} table space.", result)
        if locksize == "TABLESPACE" and a.get("lockmax") not in (None, 0):
            self.find("tablespace.lockmax-locksize", "LOCKSIZE TABLESPACE requires LOCKMAX to be omitted or 0.", result)
        if kind != "PBR":
            if "pagenum" in a:
                self.find("tablespace.pbr-only-clause", "PAGENUM is only part of the partition-by-range specification.", result)
            if a.get("partitions"):
                self.find("tablespace.pbr-only-clause", "PARTITION clauses are only part of the partition-by-range specification.", result)
        else:
            numbers = [p["number"] for p in a.get("partitions", [])]
            for number in numbers:
                if not 1 <= number <= a.get("numparts", 0) or numbers.count(number) > 1:
                    self.find("tablespace.partition-number", f"PARTITION {number} is duplicated or outside 1-{a.get('numparts')}.", result)
        if kind == "PBG" and a.get("vcat"):
            self.find("tablespace.pbg-vcat", "A PBG table space cannot specify USING VCAT.", result)
        for target in [a] + a.get("partitions", []):
            if target.get("compress") in ("YES FIXEDLENGTH", "YES HUFFMAN"):
                self.require("compress-algorithm", result, f"COMPRESS {target['compress']}", target.get("line"))
            for attr, low in (("priqty", 1), ("secqty", 0)):
                value = target.get(attr)
                if value is None:
                    continue
                if value != -1 and value < low:
                    self.find("tablespace.space-quantity", f"{attr.upper()} {value} is invalid; use {'a positive integer' if low else 'a positive integer, 0'} or -1.", result, target.get("line"))
                elif value > 67108864:
                    self.require("large-space-quantities", result, f"{attr.upper()} {value} KB (above 64 GB)", target.get("line"), severity="warning")
        for attr, detail in (("pagenum", "CREATE TABLESPACE PAGENUM"), ("insert_algorithm", "CREATE TABLESPACE INSERT ALGORITHM")):
            if attr in a:
                self.require("v12-function-level-500-ddl", result, detail)
        if a.get("pagenum") == "ABSOLUTE":
            self.find("fl.deprecated-feature", "PAGENUM ABSOLUTE (absolute page numbering for PBR) is deprecated in Db2 13; use PAGENUM RELATIVE.", result)
        if a.get("usage"):
            self.require("workfile-usage", result, f"FOR {a['usage']}")
            database_obj = self.r.databases.get(database)
            if kind != "PBG" or (database_obj is not None and not database_obj.attrs.get("workfile")):
                self.find("tablespace.workfile-usage", f"FOR {a['usage']} needs a PBG table space in a work file database.", result)
        if kind == "PBG" and "maxpartitions" not in a:
            self.default_maxpartitions += 1
        key = f"{database}.{obj.name.name}"
        self.register(self.r.tablespaces, key, result, TablespaceState(obj, key, database))

    def free_space(self, result, a, what, line=None):
        if "freepage" in a and not 0 <= a["freepage"] <= 255:
            self.find("tablespace.free-space-range", f"{what} FREEPAGE {a['freepage']} is outside 0-255.", result, line)
        if "pctfree" in a and not 0 <= a["pctfree"] <= 99:
            self.find("tablespace.free-space-range", f"{what} PCTFREE {a['pctfree']} is outside 0-99.", result, line)
        update = a.get("pctfree_for_update")
        if update is not None:
            if not -1 <= update <= 99:
                self.find("tablespace.free-space-range", f"{what} FOR UPDATE {update} is outside -1 to 99.", result, line)
            elif a.get("pctfree", 5) + max(update, 0) > 99:
                self.find("tablespace.free-space-range", f"{what} PCTFREE plus FOR UPDATE exceeds 99.", result, line)

    # ---- tables
    def table(self, result):
        obj, a = result.obj, result.obj.attrs
        default = result.detail.get("schema_default")
        key = qualified(obj.name, default)
        state = TableState(obj, key, default, rules=result.detail.get("rules", "DB2"))
        self.check_name(result, obj.name, 128, "Table")
        self.duplicates(result, obj)
        if a.get("partial"):
            state.external = True
        if a.get("definition") != "explicit":
            self.find("table.copy-definition-unchecked", f"Table {key} uses a {a.get('definition')} definition; derived columns are not checked.", result)
            state.external = True
            if a.get("source"):
                self.reference("relation", qualified(a["source"], default), result, "Source table")
        self.placement(result, state)
        if a.get("data_capture") == "CHANGES" and not_logged(state):
            self.find("table.data-capture-not-logged", f"{key} is in a NOT LOGGED table space; DATA CAPTURE CHANGES is not allowed.", result)
        if a.get("compress") in ("YES FIXEDLENGTH", "YES HUFFMAN"):
            self.require("compress-algorithm", result, f"CREATE TABLE ... COMPRESS {a['compress']}")
        if "key_label" in a:
            self.require("key-label", result, "CREATE TABLE ... KEY LABEL")
        if "pagenum" in a:
            self.require("v12-function-level-500-ddl", result, "CREATE TABLE ... PAGENUM")
        if a.get("hash"):
            self.removed_feature(result, "ORGANIZE BY HASH (hash-organized table)")
        for period in a.get("periods", []):
            if period.get("mode"):
                self.require("v12-function-level-500-ddl", result, f"PERIOD {period['name']} {period['mode']}", period.get("line"))
        for constraint in a.get("constraints", []):
            if constraint.period:
                self.require("v12-function-level-500-ddl", result, f"{constraint.period} in a constraint", constraint.line)
        for column in a.get("columns", []):
            if column.type is not None and column.type.ccsid and column.type.family in ("CHAR", "VARCHAR", "GRAPHIC", "VARGRAPHIC", "CLOB", "DBCLOB"):
                self.require("v12-function-level-500-ddl", result, f"column {column.name} CCSID {column.type.ccsid}", column.line)
        for column in a.get("columns", []):
            self.column(result, state, column)
        self.constraints(result, state)
        defined = [(c, qualified(c.parent, default), delete_rule(c, state)) for c in state.fks
                   if qualified(c.parent, default) != key]
        for number, (constraint, _, rule) in enumerate(defined):
            self.delete_paths(result, state, constraint, rule, defined[:number])
        self.periods(result, state)
        self.partitioning(result, state)
        self.row_length(result, state)
        if key in self.r.relations:
            self.find("name.duplicate-object", f"{key} is already created.", result)
        self.r.relations[key] = state
        self.r.tables[key] = state

    def placement(self, result, state):
        a = state.obj.attrs
        placement = a.get("placement")
        if placement == "tablespace":
            database = a.get("database") or "DSNDB04"
            if not a.get("database"):
                self.find("dependency.default-database", f"IN {a['tablespace']} without a database resolves to DSNDB04.", result)
            key = f"{database}.{a['tablespace']}"
            state.database = database
            if self.reference("tablespace", key, result, "Table space"):
                ts = self.r.tablespaces[key]
                if ts.obj.kind == "lob-tablespace":
                    self.find("table.tablespace-eligibility", f"{key} is a LOB table space; base tables cannot be created in it.", result)
                elif ts.table:
                    self.find("table.tablespace-eligibility", f"{key} already contains table {ts.table}; a UTS holds one table.", result)
                else:
                    ts.table = state.key
                    state.tablespace = ts
            for clause in ("logged", "compress", "dssize", "bufferpool", "member_cluster", "trackmod", "pagenum"):
                if clause in a:
                    self.find("table.explicit-space-physical-conflict", f"{clause.replace('_', ' ').upper()} on CREATE TABLE is only valid for an implicitly created table space, not IN {key}.", result)
        elif placement == "database":
            state.database = a["database"]
            state.implicit_space = True
            self.reference("database", a["database"], result, "Database")
        elif placement == "omitted":
            state.implicit_space = True
        self.check_bufferpool(result, a.get("bufferpool"), "BUFFERPOOL")

    def column(self, result, state, column):
        self.check_column_name(result, column)
        if column.name in state.columns:
            self.find("table.duplicate-column", f"Column {column.name} is defined more than once.", result, column.line)
        state.columns[column.name] = column
        dt = column.type
        if dt is not None:
            if dt.foreign:
                if dt.name not in self.r.types and dt.name.upper() not in self.assumed.get("type", set()):
                    self.find("dialect.data-type", f"Column {column.name}: {dt.name} — {dt.foreign}.", result, column.line)
            elif dt.family is None and dt.distinct is not None:
                key = qualified(dt.distinct, state.schema_default) if dt.distinct.schema else dt.distinct.name
                known = key in self.r.types or dt.distinct.name in self.r.types or \
                    key.upper() in self.assumed.get("type", set()) or dt.distinct.name in self.assumed.get("type", set())
                if not known:
                    later = any(k[0] == "type" and k[1].split(".")[-1] == dt.distinct.name for k in self.created_at)
                    if later:
                        self.find("dependency.order", f"Column {column.name}: distinct type {dt.name} is created later in the script.", result, column.line)
                    else:
                        self.find("dialect.data-type", f"Column {column.name}: {dt.name} is not a Db2 13 for z/OS built-in type and no CREATE TYPE was seen (use --assume type:{dt.name} if it exists).", result, column.line)
            elif dt.family in TYPE_LIMITS:
                low, high = TYPE_LIMITS[dt.family]
                value = dt.length
                if value is not None and not low <= value <= high:
                    self.find("table.data-type-range", f"Column {column.name}: {dt.raw} length/precision {value} is outside {low}-{high}.", result, column.line)
                if dt.family == "DECIMAL" and dt.scale is not None and not 0 <= dt.scale <= (dt.length or 5):
                    self.find("table.data-type-range", f"Column {column.name}: DECIMAL scale {dt.scale} must be between 0 and the precision.", result, column.line)
                if dt.family in ("VARCHAR", "VARGRAPHIC", "VARBINARY") and not dt.explicit_length:
                    self.find("table.data-type-range", f"Column {column.name}: {dt.name} requires a length.", result, column.line)
            if dt.family == "DECFLOAT" and dt.length not in (16, 34):
                self.find("table.data-type-range", f"Column {column.name}: DECFLOAT precision must be 16 or 34.", result, column.line)
        generated = column.generated
        if column.default is not None and (generated in ("identity", "row-change-timestamp", "rowid", "row-begin", "row-end", "transaction-start-id") or (dt and dt.family == "XML")):
            self.find("table.default-on-generated", f"Column {column.name}: DEFAULT cannot be combined with {generated or 'XML'}.", result, column.line)
        if column.default == "cast-function" and dt is not None and dt.family is not None:
            self.find("table.cast-default-distinct", f"Column {column.name}: the cast-function DEFAULT form applies only to distinct types.", result, column.line)
        if generated == "identity" and dt is not None and dt.family is not None:
            if dt.family not in ("SMALLINT", "INTEGER", "BIGINT", "DECIMAL") or (dt.family == "DECIMAL" and dt.scale):
                self.find("table.identity-cardinality", f"Column {column.name}: an identity column must be SMALLINT, INTEGER, BIGINT or DECIMAL with scale 0.", result, column.line)
        if generated in ("rowid", "row-change-timestamp", "row-begin", "row-end") and not column.not_null:
            self.find("table.generated-not-null", f"Column {column.name}: a {generated} column must be defined NOT NULL.", result, column.line)
        if dt is not None and dt.family == "ROWID" and not column.not_null:
            self.find("table.generated-not-null", f"Column {column.name}: a ROWID column must be NOT NULL.", result, column.line)

    def constraints(self, result, state):
        a = state.obj.attrs
        columns = state.columns
        counts = Counter(c.generated for c in columns.values() if c.generated)
        if counts["identity"] > 1:
            self.find("table.identity-cardinality", "A table can have only one identity column.", result)
        for kind in ("row-change-timestamp", "row-begin", "row-end", "transaction-start-id"):
            if counts[kind] > 1:
                self.find("table.generated-cardinality", f"A table can have only one {kind} column.", result)
        names = Counter(c.name for c in a.get("constraints", []) if c.name)
        for name, count in names.items():
            if count > 1:
                self.find("name.duplicate-constraint", f"Constraint name {name} is used {count} times.", result)
        for constraint in a.get("constraints", []):
            if constraint.name:
                self.check_name(result, sq.Name(None, constraint.name), 128, "Constraint", constraint.line)
            if constraint.kind in ("primary", "unique"):
                self.unique_key(result, state, constraint)
            elif constraint.kind == "check":
                state.checks.append(constraint)
                size = sq.utf8_len(constraint.condition or "")
                if size > 3800:
                    self.find("table.check-length", f"CHECK constraint {constraint.name or ''} is about {size} bytes; the limit is 3800.".replace("  ", " "), result, constraint.line)
        for constraint in a.get("constraints", []):
            if constraint.kind == "foreign":
                self.foreign_key(result, state, constraint, creating=True)
        if len(a.get("columns", [])) > (749 if state.fks else 750):
            self.find("table.column-count", f"Table has {len(a['columns'])} columns; the limit is {749 if state.fks else 750}.", result)

    def key_columns(self, result, state, names, what, line):
        found, seen = [], set()
        for name in names:
            if name in seen:
                self.find("table.key-count", f"{what}: column {name} is repeated.", result, line)
            seen.add(name)
            column = state.columns.get(name)
            if column is None:
                if not state.external:
                    self.find("table.key-column-missing", f"{what}: {name} is not a column of the table.", result, line)
                continue
            found.append(column)
        if len(names) > 64:
            self.find("table.key-count", f"{what} has {len(names)} columns; the limit is 64.", result, line)
        return found

    def unique_key(self, result, state, constraint):
        what = f"{'PRIMARY KEY' if constraint.kind == 'primary' else 'UNIQUE'} {constraint.name or ''}".strip()
        if constraint.kind == "primary":
            if state.pk is not None:
                self.find("table.primary-key-cardinality", "A table can have only one primary key.", result, constraint.line)
            state.pk = constraint
        else:
            state.uniques.append(constraint)
        columns = self.key_columns(result, state, constraint.columns, what, constraint.line)
        for column in columns:
            if not column.not_null:
                self.find("table.key-not-null", f"{what}: column {column.name} must be NOT NULL.", result, constraint.line)
            family = column.type.family if column.type else None
            if family in sq.LOB_FAMILIES or family in ("ROWID", "XML") or column.generated == "row-change-timestamp":
                self.find("table.key-column-type", f"{what}: {column.name} ({family or column.generated}) cannot be a key column.", result, constraint.line)
            if family == "DECFLOAT":
                self.require("decfloat-keys", result, f"DECFLOAT column {column.name} in {what}", constraint.line)
        measured = key_length(columns)
        if measured and len(columns) == len(constraint.columns):
            total, nullable, varying, decfloat = measured
            limit = 2000 - nullable - 2 * varying - 3 * decfloat
            if total > limit:
                self.find("table.key-length", f"{what} length is {total} bytes; the limit is {limit}.", result, constraint.line)

    def parent_state(self, result, state, constraint, creating):
        default = state.schema_default
        parent_key = qualified(constraint.parent, default)
        if creating and parent_key == state.key:
            self.find("table.fk-self-reference", f"Foreign key {constraint.name or ''} references the table being created; add it later with ALTER TABLE ... ADD FOREIGN KEY.".replace("  ", " "), result, constraint.line)
            return None, parent_key
        if parent_key == state.key:
            return state, parent_key
        if not self.reference("relation", parent_key, result, "Parent table", constraint.line):
            return None, parent_key
        parent = self.r.relations[parent_key]
        if not isinstance(parent, TableState):
            return None, parent_key
        return parent, parent_key

    def delete_graph(self):
        """Parent table -> [(dependent, delete rule)] for the relationships defined so far. Self-referencing
        relationships have their own rule (CASCADE or NO ACTION) and stay out of path analysis."""
        graph = defaultdict(list)
        for table in self.r.tables.values():
            for fk in table.fks:
                parent = qualified(fk.parent, table.schema_default)
                if parent != table.key:
                    graph[parent].append((table.key, delete_rule(fk, table)))
        return graph

    @staticmethod
    def cascades(graph, start):
        """Tables that a delete from `start` reaches through CASCADE relationships only."""
        found, pending = set(), [start]
        while pending:
            for child, rule in graph.get(pending.pop(), []):
                if rule == "CASCADE" and child not in found and child != start:
                    found.add(child)
                    pending.append(child)
        return found

    def shared_delete_path(self, graph, t2, t3):
        """The CREATE TABLE and ALTER TABLE conditions under which the relationships to parents T2 and T3 must
        have one delete rule that is not SET NULL: T2 and T3 are the same table, the deletion of rows from one
        cascades to the other, or the deletion of rows from a third table cascades to both."""
        if t2 == t3 or t2 in self.cascades(graph, t3) or t3 in self.cascades(graph, t2):
            return True
        return any({t2, t3} <= self.cascades(graph, table) for table in list(graph))

    def delete_paths(self, result, state, constraint, rule, others):
        """`others` are (constraint, parent, delete rule) of the dependent's other relationships."""
        graph = self.delete_graph()
        parent = qualified(constraint.parent, state.schema_default)
        for other, other_parent, other_rule in others:
            if self.shared_delete_path(graph, parent, other_parent) and (rule != other_rule or "SET NULL" in (rule, other_rule)):
                names = " and ".join(f"{c.name or 'unnamed'} ({r})" for c, r in ((other, other_rule), (constraint, rule)))
                how = f"references {parent} twice" if parent == other_parent else \
                    f"is delete-connected through {parent} and {other_parent}, which cascading deletes link"
                self.find("table.fk-delete-paths", f"{state.key} {how}; {names} must have the same delete rule, "
                          "and it must not be SET NULL.", result, constraint.line)

    def foreign_key(self, result, state, constraint, creating):
        what = f"FOREIGN KEY {constraint.name or ''}".strip()
        state.fks.append(constraint)
        columns = self.key_columns(result, state, constraint.columns, what, constraint.line)
        for column in columns:
            family = column.type.family if column.type else None
            if family in sq.LOB_FAMILIES or family in ("ROWID", "XML", "DECFLOAT") or column.generated == "row-change-timestamp" or column.security_label:
                self.find("table.key-column-type", f"{what}: {column.name} ({family or column.generated}) cannot be a foreign-key column.", result, constraint.line)
        if constraint.delete_rule == "SET NULL" and columns and not any(c.nullable for c in columns):
            self.find("table.fk-set-null", f"{what}: ON DELETE SET NULL needs a nullable foreign-key column.", result, constraint.line)
        measured = key_length(columns)
        if measured and len(columns) == len(constraint.columns):
            total, nullable, _, _ = measured
            if total > 255 - nullable:
                self.find("table.fk-key-length", f"{what} length is {total} bytes; the limit is 255 - {nullable} nullable = {255 - nullable}.", result, constraint.line)
        fk_period = constraint.period == "PERIOD BUSINESS_TIME"
        if fk_period != constraint.parent_period:
            self.find("table.fk-business-time", f"{what}: PERIOD BUSINESS_TIME must be in both the FOREIGN KEY and REFERENCES lists, or in neither.", result, constraint.line)
        if fk_period or constraint.parent_period:
            effective = constraint.delete_rule or ("RESTRICT" if result.detail.get("rules", state.rules) == "DB2" else "NO ACTION")
            if effective != "RESTRICT":
                self.find("table.fk-business-time", f"{what}: PERIOD BUSINESS_TIME requires ON DELETE RESTRICT (effective rule: {effective}).", result, constraint.line)
        parent, parent_key = self.parent_state(result, state, constraint, creating)
        if parent is state:
            # "If T1 and T2 are the same table, CASCADE or NO ACTION must be specified" (ibm-alter-table). The
            # omitted rule follows CURRENT RULES when this statement runs, not when the table was created.
            effective = constraint.delete_rule or ("RESTRICT" if result.detail.get("rules", state.rules) == "DB2" else "NO ACTION")
            if effective not in ("CASCADE", "NO ACTION"):
                self.find("table.fk-self-reference-delete-rule", f"{what} references its own table, so its delete rule must be CASCADE or NO ACTION (effective rule: {effective}).", result, constraint.line)
        if parent is None or parent.external:
            return
        if constraint.parent_columns is None:
            if parent.pk is None:
                self.find("table.fk-parent-key", f"{what}: no parent column list was given and {parent_key} has no primary key.", result, constraint.line)
                return
            parent_columns = list(parent.pk.columns)
        else:
            parent_columns = list(constraint.parent_columns)
        keys = ([tuple(parent.pk.columns)] if parent.pk else []) + [tuple(u.columns) for u in parent.uniques]
        if tuple(parent_columns) not in keys:
            hint = " (same columns in a different order)" if any(sorted(k) == sorted(parent_columns) for k in keys) else ""
            self.find("table.fk-parent-key", f"{what}: ({', '.join(parent_columns)}) is not the primary key or a unique key of {parent_key}{hint}.", result, constraint.line)
        if len(parent_columns) != len(constraint.columns):
            self.find("table.fk-arity", f"{what} has {len(constraint.columns)} columns but the parent key has {len(parent_columns)}.", result, constraint.line)
            return
        for child_name, parent_name in zip(constraint.columns, parent_columns):
            child, parent_column = state.columns.get(child_name), parent.columns.get(parent_name)
            if child is None or parent_column is None or child.type is None or parent_column.type is None:
                continue
            if self.signature(child.type) != self.signature(parent_column.type):
                self.find("table.fk-type-identity", f"{what}: {child_name} {child.type.raw} differs from {parent_key}.{parent_name} {parent_column.type.raw}.", result, constraint.line)
        parent_key = next((c for c in ([parent.pk] if parent.pk else []) + parent.uniques if tuple(c.columns) == tuple(parent_columns)), None)
        if not parent.implicit_space and parent_key is not None and enforcement_key(parent_key) not in parent.enforced_keys and not parent.external:
            self.find("table.fk-parent-unique-index", f"{what}: {parent_key} has no unique index on ({', '.join(parent_columns)}) yet; create the parent's enforcing index before this child.", result, constraint.line)

    @staticmethod
    def signature(dt):
        sig = dt.signature()
        if dt.family == "FLOAT":
            return ("FLOAT", "REAL" if (dt.length or 53) <= 21 else "DOUBLE")
        return sig

    def periods(self, result, state):
        for period in state.obj.attrs.get("periods", []):
            columns = [state.columns.get(c) for c in period["columns"]]
            for name, column in zip(period["columns"], columns):
                if column is None:
                    self.find("table.key-column-missing", f"PERIOD {period['name']}: {name} is not a column.", result, period["line"])
            if len(period["columns"]) != 2 or None in columns:
                continue
            if period["name"] == "BUSINESS_TIME":
                for column in columns:
                    dt = column.type
                    ok = dt is not None and (dt.family == "DATE" or (dt.family == "TIMESTAMP" and dt.length == 6 and not dt.time_zone))
                    if not ok or not column.not_null or column.generated:
                        self.find("table.period-columns", f"BUSINESS_TIME column {column.name} must be DATE or TIMESTAMP(6) NOT NULL and not generated.", result, period["line"])
            elif period["name"] == "SYSTEM_TIME":
                if columns[0].generated != "row-begin" or columns[1].generated != "row-end":
                    self.find("table.period-columns", "SYSTEM_TIME must name the AS ROW BEGIN column, then the AS ROW END column.", result, period["line"])

    def partitioning(self, result, state):
        a = state.obj.attrs
        ts = state.tablespace
        has_range = "range_partitions" in a
        if has_range:
            names = [k for k, _ in a["partition_keys"]]
            columns = self.key_columns(result, state, names, "PARTITION BY", state.obj.line)
            measured = key_length(columns)
            if measured and len(columns) == len(names) and measured[0] > 255 - measured[1]:
                self.find("table.partition-key-length", f"Partitioning key is {measured[0]} bytes; the limit is {255 - measured[1]}.", result)
            if len(names) > 64:
                self.find("table.partition-key-length", "Partitioning key exceeds 64 columns.", result)
        if ts is None:
            return
        kind = ts.obj.attrs.get("type")
        if kind == "PBR":
            parts = ts.obj.attrs.get("numparts")
            if not has_range:
                self.find("table.partitioning-mismatch", f"{ts.key} is partition-by-range; the table needs PARTITION BY RANGE with {parts} partitions.", result)
            elif len(a["range_partitions"]) != parts:
                self.find("table.partitioning-mismatch", f"PARTITION BY RANGE defines {len(a['range_partitions'])} partitions but {ts.key} has NUMPARTS {parts}.", result)
        elif kind == "PBG" and (has_range or "partition_by_size" in a):
            if has_range:
                self.find("table.partitioning-mismatch", f"{ts.key} is partition-by-growth and cannot hold a range-partitioned table.", result)

    def row_length(self, result, state):
        if state.external:
            return
        if state.tablespace is None:
            return  # Implicit spaces: Db2 can select a larger page size near the limit.
        pool = state.tablespace.obj.attrs.get("bufferpool")
        if pool is None:
            database = self.r.databases.get(state.tablespace.database)
            pool = database.attrs.get("bufferpool") if database is not None else None
        pages = page_size(pool)
        if pages is None:
            return  # The database or installation default pool is unknown.
        for column in state.columns.values():
            dt = column.type
            if dt is not None and dt.family in VARYING_LIMIT and dt.length and dt.length > VARYING_LIMIT[dt.family][pages]:
                self.find("table.data-type-range", f"Column {column.name}: {dt.raw} exceeds {VARYING_LIMIT[dt.family][pages]} for a table space with {pages} KB pages ({pool}).", result, column.line)
        total = 6
        for column in state.columns.values():
            dt = column.type
            if dt is None or dt.family is None:
                return
            total += dt.storage_bytes() + (1 if column.nullable else 0)
            if dt.family in sq.VARYING_FAMILIES or dt.family == "ROWID":
                total += 2
            if dt.family in sq.LOB_FAMILIES or dt.family == "XML":
                total += 6 + (column.inline_length or 0)
        limit = RECORD_LIMIT[pages] - (10 if state.obj.attrs.get("editproc") else 0)
        if total > limit:
            self.find("table.row-length", f"Estimated maximum record length {total} bytes exceeds {limit} for {pages} KB pages ({pool}).", result)

    # ---- auxiliary tables
    def aux_table(self, result):
        obj, a = result.obj, result.obj.attrs
        default = result.detail.get("schema_default")
        key = qualified(obj.name, default)
        self.check_name(result, obj.name, 128, "Auxiliary table")
        database = a.get("database") or "DSNDB04"
        ts_key = f"{database}.{a['tablespace']}"
        state = TableState(obj, key, default, aux=True)
        if self.reference("tablespace", ts_key, result, "LOB table space"):
            ts = self.r.tablespaces[ts_key]
            if ts.obj.kind != "lob-tablespace":
                self.find("auxtable.placement", f"{ts_key} is not a LOB table space.", result)
            elif ts.table:
                self.find("auxtable.placement", f"{ts_key} already holds {ts.table}; it must be empty.", result)
            else:
                ts.table = key
                state.tablespace = ts
        base_key = qualified(a["base"], default)
        if self.reference("relation", base_key, result, "Base table"):
            base = self.r.relations[base_key]
            if isinstance(base, TableState) and not base.external:
                column = base.columns.get(a["column"])
                if column is None or column.type is None or column.type.family not in sq.LOB_FAMILIES:
                    self.find("auxtable.placement", f"{base_key}.{a['column']} is not a LOB column.", result)
                kind = base.tablespace.obj.attrs.get("type") if base.tablespace is not None else None
                if kind in ("PBG", "PBR") and a.get("part") is None:
                    self.find("auxtable.part-required", f"{base_key} is in a {kind} table space; specify PART n (one auxiliary table per partition).", result)
                elif kind in ("PBG", "PBR") and not 1 <= a["part"] <= base.tablespace.obj.attrs.get("numparts", 1) and kind == "PBR":
                    self.find("auxtable.part-required", f"PART {a['part']} is outside 1-{base.tablespace.obj.attrs.get('numparts')} for {base_key}.", result)
                elif kind is None and a.get("part") is not None and base.tablespace is not None:
                    self.find("auxtable.part-required", "PART is allowed only when the base table is in a partitioned table space.", result)
                slot = (a["column"], a.get("part"))
                if slot in base.aux_tables:
                    self.find("auxtable.placement", f"{base_key}.{a['column']} already has auxiliary table {base.aux_tables[slot]} for this partition.", result)
                base.aux_tables[slot] = key
                if base.database and database != base.database:
                    self.find("auxtable.placement", f"The LOB table space must be in the base table's database {base.database}.", result)
        if key in self.r.relations:
            self.find("name.duplicate-object", f"{key} is already created.", result)
        self.r.relations[key] = state
        self.r.tables[key] = state

    # ---- indexes
    def index(self, result):
        obj, a = result.obj, result.obj.attrs
        default = result.detail.get("schema_default")
        key = qualified(obj.name, default)
        self.check_name(result, obj.name, 128, "Index")
        self.duplicates(result, obj)
        self.check_bufferpool(result, a.get("bufferpool"), "BUFFERPOOL")
        if a.get("stogroup"):
            self.reference("stogroup", a["stogroup"], result, "Storage group")
        for what in ("freepage", "pctfree"):
            limit = 255 if what == "freepage" else 99
            for target in [a] + a.get("partitions", []):
                if what in target and not 0 <= target[what] <= limit:
                    self.find("index.free-space-range", f"Index {what.upper()} {target[what]} is outside 0-{limit}.", result)
        if key in self.r.indexes:
            self.find("name.duplicate-object", f"Index {key} is already created.", result)
        self.r.indexes[key] = result
        table_key = qualified(a["table"], default)
        if not self.reference("relation", table_key, result, "Index table"):
            return
        table = self.r.relations[table_key]
        if not isinstance(table, TableState) or a.get("partial"):
            return
        a["_table_key"] = table_key
        table.indexes.append(key)
        if table.aux:
            if a["keys"]:
                self.find("index.auxiliary", "An index on an auxiliary table must not list key columns.", result)
            if getattr(table, "aux_index", None):
                self.find("index.auxiliary", f"Auxiliary table {table_key} already has index {table.aux_index}.", result)
            table.aux_index = key
            return
        if a.get("auxiliary"):
            self.find("index.auxiliary", f"{table_key} is not an auxiliary table, so the index needs a key list.", result)
            return
        keys = [k for k, _ in a["keys"]]
        include = a.get("include", [])
        if len(keys) + len(include) > 64:
            self.find("index.key-count", f"Index has {len(keys) + len(include)} columns including INCLUDE; the limit is 64.", result)
        if a["unique"] is False and include:
            self.find("index.include-requires-unique", "INCLUDE requires a UNIQUE index.", result)
        if include and (a["expression"] or a["xmlpattern"]):
            self.find("index.include-requires-unique", "INCLUDE is not allowed for expression or XML indexes.", result)
        if a.get("cluster"):
            if a["expression"] or a["xmlpattern"]:
                self.find("index.cluster", "CLUSTER cannot be specified with a key expression or XMLPATTERN.", result)
            if table.clustering_index:
                self.find("index.cluster", f"{table_key} already has clustering index {table.clustering_index}.", result)
            table.clustering_index = key
        if a["expression"]:
            for _, order in a["keys"]:
                if order == "DESC":
                    self.find("index.order-restrictions", "DESC cannot be used when the index has key expressions.", result)
            self.register_enforcing(result, table, a, None)
            return
        if table.external:
            return
        columns = []
        for name in keys + include:
            column = table.columns.get(name)
            if column is None:
                self.find("index.column-missing", f"{name} is not a column of {table_key}.", result)
            else:
                columns.append(column)
        repeated = [n for n, c in Counter(keys + include).items() if c > 1]
        for name in repeated:
            self.find("index.include-columns" if name in include else "index.key-count", f"Column {name} appears more than once in the index.", result)
        by_name = {c.name: c for c in columns}
        for name in keys:
            column = by_name.get(name)
            if column is None or column.type is None:
                continue
            family = column.type.family
            if family in sq.LOB_FAMILIES:
                self.find("index.key-column-type", f"LOB column {name} cannot be an index key.", result)
            if family == "XML" and not a["xmlpattern"]:
                self.find("index.key-column-type", f"XML column {name} needs GENERATE KEY USING XMLPATTERN.", result)
            if family == "VARBINARY" and a.get("padded") is True:
                self.find("index.key-column-type", f"VARBINARY column {name} cannot be in a PADDED index.", result)
        for name in keys:
            column = by_name.get(name)
            if column is not None and column.type is not None and column.type.family == "DECFLOAT":
                self.require("decfloat-keys", result, f"DECFLOAT index key {name}")
        if "dssize" in a or any("dssize" in p for p in a.get("partitions", [])):
            self.require("v12-function-level-500-ddl", result, "CREATE INDEX ... DSSIZE")
        for name in include:
            column = by_name.get(name)
            if column is not None and column.type is not None and (column.type.family in sq.LOB_FAMILIES or column.type.family == "DECFLOAT"):
                self.find("index.include-columns", f"INCLUDE column {name} cannot be LOB or DECFLOAT.", result)
        for name, order in a["keys"]:
            column = by_name.get(name)
            if order == "RANDOM" and column is not None and column.type is not None:
                if column.type.family == "DECFLOAT" or (column.type.family == "TIMESTAMP" and column.type.time_zone):
                    self.find("index.order-restrictions", f"RANDOM cannot be used with {column.type.raw} key {name}.", result)
                if column.type.family in sq.VARYING_FAMILIES and a.get("padded") is False:
                    self.find("index.order-restrictions", f"RANDOM cannot be used with varying-length key {name} in a NOT PADDED index.", result)
        partitioned = a.get("partitioned") or bool(a.get("partitions"))
        if partitioned and not table.partitioned:
            self.find("index.partitioned-pbg", f"{table_key} is not in a partition-by-range table space.", result)
        partition_keys = [k for k, _ in table.obj.attrs.get("partition_keys", [])]
        is_partitioning = partitioning_index(table, a)
        if a.get("partitioned") and a["unique"] and partition_keys and not set(partition_keys) <= set(keys) and not is_partitioning:
            self.find("index.unique-partitioned-superset", "A UNIQUE partitioned secondary index must contain every partitioning column in its key.", result)
        index_columns = [by_name[n] for n in keys + include if n in by_name]
        if len(index_columns) == len(keys) + len(include):
            self.index_key_length(result, a, index_columns, partitioned and is_partitioning)
        self.register_enforcing(result, table, a, keys)

    def index_key_length(self, result, a, columns, partitioning):
        measured = key_length(columns)
        if not measured:
            return
        total, n, m, d = measured
        base = 255 if partitioning else 2000
        padded_limit, unpadded_limit = base - n, base - n - 2 * m - 3 * d
        padded = a.get("padded")
        if m and padded is None:
            padix = str(self.r.options.subsystem_parameters.get("PADIX", "")).upper()
            padded = True if padix in ("YES", "Y") else False if padix in ("NO", "N") else None
        if not m or padded is True:
            limit = padded_limit
        elif padded is False:
            limit = unpadded_limit
        else:
            self.padix_dependent += 1
            if total > padded_limit:
                self.find("index.key-length", f"Index key is {total} bytes; the limit is {padded_limit} even when padded.", result)
            elif total > unpadded_limit:
                self.find("index.key-length", f"Index key is {total} bytes; it exceeds {unpadded_limit} if PADIX makes the index NOT PADDED. Specify PADDED explicitly or shorten the key.", result, severity="warning")
            return
        if total > limit:
            self.find("index.key-length", f"Index key is {total} bytes; the limit is {limit}.", result)

    def register_enforcing(self, result, table, a, keys):
        if not a["unique"] or a.get("where_not_null") or keys is None:
            return
        table.enforced_keys.add(index_key(a))

    # ---- other statements
    def alter(self, result):
        detail = result.detail
        if result.kind != "table" or detail.get("unmodeled") or detail.get("partial"):
            self.r.not_checked[f"ALTER {(result.kind or '').upper()}".strip()] += 1
            return
        table_key = qualified(detail["table"], detail.get("schema_default"))
        options, constraints = detail.get("options", {}), detail.get("constraints", [])
        for clause, line in detail.get("duplicate_clauses", []):
            self.find("syntax.duplicate-clause", f"{clause.upper()} is specified more than once in one ALTER TABLE.", result, line)
        clauses = set(options) | ({"constraint"} if constraints else set())
        if table_key.startswith("SYSIBM."):
            if clauses != {"data_capture"} or options["data_capture"] != "CHANGES":
                self.find("table.alter-clause-for-table-kind", f"{table_key} is a catalog table; DATA CAPTURE CHANGES is the only clause it accepts.", result)
            return
        if not self.reference("relation", table_key, result, "Table"):
            return
        state = self.r.relations[table_key]
        if not isinstance(state, TableState):
            return
        # Db2 rejects the whole statement on these errors, so none of its clauses is applied.
        kind, allowed = next(((k, a) for k, a in ALTER_LIMITS if k(state)), (None, None))
        failed = False
        if kind is not None and clauses - allowed:
            names = ", ".join(sorted(c.replace("_", " ").upper() for c in clauses - allowed))
            self.find("table.alter-clause-for-table-kind", f"{table_key} is {kind.__doc__}; it does not accept {names}.", result)
            failed = True
        if options.get("data_capture") == "CHANGES" and not_logged(state):
            self.find("table.data-capture-not-logged", f"{table_key} is in a NOT LOGGED table space; DATA CAPTURE CHANGES is not allowed.", result)
            failed = True
        for constraint in constraints:
            if constraint.kind in ("primary", "unique") and not state.implicit_space and state.tablespace is not None \
                    and enforcement_key(constraint) not in state.enforced_keys:
                self.find("table.alter-key-needs-index", f"{table_key} has no unique index on ({', '.join(constraint.columns)}) yet; "
                          "create it before ALTER TABLE adds the key.", result, constraint.line)
                failed = True
        if failed:
            return
        # An option set later by ALTER TABLE gives the catalog state of the same CREATE TABLE clause
        # (ibm-alter-table), so it becomes part of the definition that bundles and the diff read.
        for attribute, value in options.items():
            if value is None:
                state.obj.attrs.pop(attribute, None)  # VALIDPROC NULL
            else:
                state.obj.attrs[attribute] = value
        names = {c.name for c in state.obj.attrs.get("constraints", []) if c.name}
        for constraint in constraints:
            if constraint.name in names:
                self.find("name.duplicate-constraint", f"Constraint name {constraint.name} is already used by {table_key}.", result, constraint.line)
            names.add(constraint.name)
            # The omitted delete rule follows CURRENT RULES when the ALTER TABLE statement is processed (ibm-alter-table).
            constraint.rules = detail.get("rules", "DB2")
            if constraint.kind in ("primary", "unique"):
                self.unique_key(result, state, constraint)
            elif constraint.kind == "foreign":
                self.added_foreign_key(result, state, constraint)
                self.foreign_key(result, state, constraint, creating=False)
            elif constraint.kind == "check":
                state.checks.append(constraint)
            state.obj.attrs.setdefault("constraints", []).append(constraint)

    def added_foreign_key(self, result, state, constraint):
        """Delete-rule restrictions of ALTER TABLE ... ADD FOREIGN KEY (ibm-alter-table, ON DELETE)."""
        parent, rule = qualified(constraint.parent, state.schema_default), delete_rule(constraint, state)
        if parent == state.key:
            return  # a self-reference has its own rule: CASCADE or NO ACTION
        graph = self.delete_graph()
        descendants, pending = set(), [state.key]
        while pending:
            for child, _ in graph.get(pending.pop(), []):
                if child not in descendants:
                    descendants.add(child)
                    pending.append(child)
        if parent in descendants:  # the new relationship closes a cycle
            cascaded = self.cascades(graph, state.key)
            if parent in cascaded:
                self.find("table.fk-delete-cycle", f"Every relationship from {state.key} down to {parent} is CASCADE, so the cycle "
                          "this foreign key closes would delete-connect a table to itself.", result, constraint.line)
            elif rule == "CASCADE" and parent in {child for table in cascaded | {state.key} for child, _ in graph.get(table, [])}:
                self.find("table.fk-delete-cycle", f"{parent} is delete-connected to {state.key}, so this foreign key cannot be CASCADE.",
                          result, constraint.line)
        others = [(c, qualified(c.parent, state.schema_default), delete_rule(c, state)) for c in state.fks
                  if qualified(c.parent, state.schema_default) != state.key]
        self.delete_paths(result, state, constraint, rule, others)
        if constraint.delete_rule == "SET NULL":
            for index_key_ in state.indexes:
                index = self.r.indexes.get(index_key_)
                if index is None or not partitioning_index(state, index.obj.attrs):
                    continue
                keys = {name for name, _ in index.obj.attrs.get("keys", [])}
                nullable = [c for c in constraint.columns if c in keys and state.columns.get(c) is not None and state.columns[c].nullable]
                if nullable:
                    self.find("table.fk-set-null-partitioning-key", f"SET NULL is not allowed: nullable foreign-key column(s) "
                              f"{', '.join(nullable)} are in the key of partitioning index {index_key_}.", result, constraint.line)

    def drop(self, result):
        name = result.detail.get("name")
        if name is None:
            return
        default = result.detail.get("schema_default")
        kind = result.kind
        self.r.drops.append((kind, name, result.statement.index))
        if kind == "index":
            key = qualified(name, default)
            index = self.r.indexes.pop(key, None)
            if index is not None:
                table = self.r.relations.get(index.obj.attrs.get("_table_key"))
                if isinstance(table, TableState) and index_key(index.obj.attrs) in self.constraint_keys(table) and index.obj.attrs.get("unique"):
                    self.find("cleanup.drop-enforcing-index", f"Index {key} enforces a primary/unique key of {table.key}; drop the constraint or the table/table space instead.", result)
        elif kind in ("table", "view", "alias", "synonym"):
            key = qualified(name, default)
            state = self.r.relations.get(key)
            if kind == "table" and isinstance(state, TableState) and state.tablespace is not None:
                self.require("drop-table-explicit-uts", result, f"DROP TABLE {key} in explicit UTS {state.tablespace.key}")
            state = self.r.relations.pop(key, None)
            self.r.tables.pop(key, None)
            if isinstance(state, TableState) and state.tablespace is not None:
                state.tablespace.table = None
        elif kind == "tablespace":
            database = name.schema or "DSNDB04"
            key = f"{database}.{name.name}"
            ts = self.r.tablespaces.pop(key, None)
            if ts and ts.table:
                self.r.relations.pop(ts.table, None)
                self.r.tables.pop(ts.table, None)
        elif kind == "database":
            self.r.databases.pop(name.name, None)
            for key in [k for k in self.r.tablespaces if k.split(".")[0] == name.name]:
                ts = self.r.tablespaces.pop(key)
                if ts.table:
                    self.r.relations.pop(ts.table, None)
                    self.r.tables.pop(ts.table, None)
        elif kind == "stogroup":
            self.r.stogroups.pop(name.name, None)

    def evaluate_levels(self):
        options = self.r.options
        applcompat, function_level = level_key(options.applcompat), level_key(options.function_level)
        for label, value, key in (("APPLCOMPAT", options.applcompat, applcompat), ("function level", options.function_level, function_level)):
            if value and key is None:
                self.r.add("fl.profile-inconsistent", f"Profile {label} {value!r} is not a valid V10R1/V11R1/V12R1Mnnn/V13R1Mnnn level.")
        if function_level is not None and function_level[0] != 13:
            self.r.add("fl.profile-inconsistent", f"Function level {options.function_level} is not a Db2 13 function level (V13R1Mnnn).")
            function_level = None
        if applcompat and function_level and applcompat > function_level:
            self.r.add("fl.profile-inconsistent", f"APPLCOMPAT {options.applcompat} exceeds the activated function level {options.function_level}.")
        grouped = defaultdict(list)
        for gate, line, statement, detail, severity in self.requirements:
            grouped[gate].append((line, statement, detail, severity))
        gates = []
        for gate, uses in sorted(grouped.items(), key=lambda kv: (level_key(self.gates[kv[0]]["applcompat"]), kv[0])):
            need = level_key(self.gates[gate]["applcompat"])
            line, statement, detail, severity = uses[0]
            more = f" (+{len(uses) - 1} more)" if len(uses) > 1 else ""
            gates.append({"gate": gate, "applcompat": level_name(need), "function_level": level_name(need) if need[0] == 13 else "any Db2 13 level",
                          "uses": len(uses), "first_line": line, "example": detail, "source_ref": self.gates[gate]["source_ref"]})
            if applcompat is not None and applcompat < need:
                self.r.add("fl.applcompat-gate", f"{detail}{more} needs APPLCOMPAT {level_name(need)}; the profile records {options.applcompat}.",
                           line, statement, None, severity)
            if need[0] == 13 and function_level is not None and function_level < need:
                self.r.add("fl.function-level-gate", f"{detail}{more} needs function level {level_name(need)}; the profile records {options.function_level}.",
                           line, statement, None, severity)
        minimum = max([level_key(g["applcompat"]) for g in gates], default=None)
        minimum_fl = max([level_key(g["applcompat"]) for g in gates if g["applcompat"].startswith("V13")], default=(13, 100))
        self.r.compatibility = {"minimum_applcompat": level_name(minimum) if minimum else None,
                                "minimum_function_level": level_name(minimum_fl), "profile_applcompat": options.applcompat,
                                "profile_function_level": options.function_level, "gates": gates,
                                "source": "kb/data/db2z13-function-levels.json"}
        if gates:
            state = "checked against the profile" if applcompat is not None else "not checked: record function_level and applcompat in a profile"
            self.r.add("fl.requirements", f"Gated syntax needs at least APPLCOMPAT {level_name(minimum)} and function level {level_name(minimum_fl)} "
                       f"({', '.join(g['gate'] for g in gates)}); {state}.")
        if self.default_maxpartitions:
            if applcompat is None:
                effect = "254 at APPLCOMPAT V13R1M500 or higher, 256 at V12R1M504-V13R1M100"
            elif applcompat >= (13, 500):
                effect = "254 at the profile's APPLCOMPAT"
            elif applcompat >= UTS_BASELINE:
                effect = "256 (default DSSIZE 4 G) at the profile's APPLCOMPAT"
            else:
                effect = "a non-UTS or level-dependent result below V12R1M504"
            self.r.add("fl.behavior-change", f"{self.default_maxpartitions} PBG table space(s) omit MAXPARTITIONS; the default is {effect}.")

    @staticmethod
    def constraint_keys(table):
        return {enforcement_key(c) for c in ([table.pk] if table.pk else []) + table.uniques}

    def other(self, result):
        obj = result.obj
        kind = obj.kind
        default = result.detail.get("schema_default")
        self.r.not_checked[f"CREATE {kind.upper()}"] += 1
        words = [t.value for t in result.tokens if t.kind == "word"]
        joined = " ".join(words)
        if kind == "synonym":
            self.removed_feature(result, "CREATE SYNONYM")
        if kind in ("procedure", "function"):
            if words[1:3] == ["OR", "REPLACE"] and kind == "procedure":
                self.require("procedure-or-replace-specific", result, "CREATE OR REPLACE PROCEDURE")
            if kind == "procedure" and "SPECIFIC" in words:
                self.require("procedure-or-replace-specific", result, "CREATE PROCEDURE ... SPECIFIC")
            if re.search(r"PACKAGE OWNER \S+ AS (ROLE|USER)", joined):
                self.require("package-owner-type", result, "PACKAGE OWNER ... AS ROLE/USER")
            if kind == "procedure" and "LANGUAGE SQL" in joined and ("FENCED" in words or "EXTERNAL" in words):
                self.find("fl.deprecated-feature", f"{obj.name} looks like an external SQL procedure (LANGUAGE SQL with FENCED/EXTERNAL), which is deprecated; use a native SQL procedure.", result)
        if kind in ("procedure", "function", "trigger"):
            if "WRAPPED" in words:
                self.require("v12-function-level-500-ddl", result, "WRAPPED")
            if "CONCENTRATE STATEMENTS" in joined:
                self.require("v12-function-level-500-ddl", result, "CONCENTRATE STATEMENTS")
        if kind == "trigger" and "MODE DB2SQL" not in joined:
            self.require("v12-function-level-500-ddl", result, "advanced trigger (no MODE DB2SQL)")
        if kind in ("trigger", "procedure") and obj.attrs.get("unbalanced_begin"):
            self.find("script.sqlpl-terminator", f"{kind.upper()} {obj.name} has BEGIN without END in this statement; the body was split by the outer terminator '{result.statement.terminator}'.", result)
        if kind == "type":
            self.r.types[qualified(obj.name, default)] = obj
            self.r.types[obj.name.name] = obj
        elif kind in ("view", "alias", "synonym", "global-temporary-table"):
            key = qualified(obj.name, default)
            if key in self.r.relations:
                self.find("name.duplicate-object", f"{key} is already created.", result)
            self.r.relations[key] = obj
        elif kind == "trigger" and obj.attrs.get("subject"):
            self.reference("relation", qualified(obj.attrs["subject"], default), result, "Trigger subject")

    # ---- end of script
    def finish(self):
        for key, state in self.r.tables.items():
            if state.external or state.aux:
                continue
            result = next((p for p in self.r.parsed if p.obj is state.obj), None)
            if result is None:
                continue
            if not state.implicit_space and state.tablespace is not None:
                missing = []
                for constraint in ([state.pk] if state.pk else []) + state.uniques:
                    if enforcement_key(constraint) not in state.enforced_keys:
                        missing.append(f"{'primary' if constraint.kind == 'primary' else 'unique'} key ({', '.join(constraint.columns)})")
                for column in state.columns.values():
                    if column.generated == "rowid" and column.generated_mode == "BY DEFAULT" and (column.name,) not in state.enforced_keys:
                        missing.append(f"ROWID GENERATED BY DEFAULT column {column.name}")
                if missing:
                    self.find("table.incomplete-definition", f"{key} still needs a unique index with the same columns in the same order for: {'; '.join(missing)}.", result, obj=f"table {key}")
            lobs = [c for c in state.columns.values() if c.type is not None and c.type.family in sq.LOB_FAMILIES]
            if lobs and not state.implicit_space and state.rules == "DB2" and state.tablespace is not None:
                partitioned = state.tablespace.obj.attrs.get("type") in ("PBG", "PBR")
                parts = state.tablespace.obj.attrs.get("numparts", 1) if partitioned else 1
                for column in lobs:
                    slots = [(column.name, p) for p in (range(1, parts + 1) if partitioned else [None])]
                    missing_slots = [s for s in slots if s not in state.aux_tables]
                    unindexed = [s for s in slots if s in state.aux_tables and not getattr(self.r.relations.get(state.aux_tables[s]), "aux_index", None)]
                    if missing_slots or unindexed:
                        self.find("table.lob-auxiliary-missing", f"{key}.{column.name} needs a LOB table space, auxiliary table and auxiliary index"
                                  f"{' for each of ' + str(parts) + ' partition(s), with PART n' if partitioned else ''} (missing {len(missing_slots)} auxiliary table(s), {len(unindexed)} index(es)).", result, obj=f"table {key}")
        for key, ts in self.r.tablespaces.items():
            if ts.table is None and ts.obj.kind == "tablespace" and not ts.external:
                result = next((p for p in self.r.parsed if p.obj is ts.obj), None)
                if result is not None:
                    self.find("tablespace.unused", f"Table space {key} holds no table in this script.", result)
        self.evaluate_levels()
        if self.padix_dependent:
            self.r.add("index.padding-environment", f"{self.padix_dependent} index(es) with varying-length keys omit PADDED/NOT PADDED; PADIX supplies the default.")
        for kind, count in sorted(self.r.not_checked.items()):
            self.r.add("scope.not-checked", f"{count} {kind} statement(s) were recognized but not checked.")


# =========================================================================== coverage

KB_OBJECT = {"tablespace": "tablespace", "lob-tablespace": "tablespace", "table": "table", "auxiliary-table": "table",
             "index": "index", "database": "database", "stogroup": "stogroup"}
OMITTABLE = {
    "tablespace": ["bufferpool", "dssize", "segsize", "ccsid", "close", "compress", "define", "freepage", "pctfree",
                   "pctfree-for-update", "gbpcache", "insert-algorithm", "lockmax", "locksize", "logging", "maxrows",
                   "member-cluster", "trackmod", "using-stogroup"],
    "lob-tablespace": ["bufferpool", "close", "compress", "define", "dssize", "gbpcache", "lockmax", "locksize", "logging"],
    "table": ["audit", "data-capture", "append", "volatile", "ccsid", "restrict-on-drop"],
    "index": ["unique", "cluster", "padding", "freepage", "pctfree", "gbpcache", "define", "compress", "null-keys", "bufferpool",
              "close", "defer", "copy", "using-stogroup"],
    "database": ["bufferpool", "indexbp", "stogroup", "ccsid"],
}
OMITTED = "<omitted>"
SPECIFIED = "<specified>"


def _value(value):
    if value is True:
        return SPECIFIED
    return str(value)


def coverage(report, baseline=None):
    """Measure syntax variety of a script against KB clause IDs and derived facets."""
    features = defaultdict(Counter)
    facets = defaultdict(Counter)
    shapes = defaultdict(set)
    counts = Counter()
    for result in report.objects:
        obj = result.obj
        kind = obj.kind
        kb_object = KB_OBJECT.get(kind)
        counts[kind] += 1
        if kb_object is None:
            continue
        present = set()
        for clause in obj.clauses:
            features[f"{kb_object}.{clause.clause}"][_value(clause.value)] += 1
            present.add(clause.clause)
        for clause in OMITTABLE.get(kind, []):
            if clause not in present:
                features[f"{kb_object}.{clause}"][OMITTED] += 1
        signature = tuple(sorted((c.clause, _value(c.value)) for c in obj.clauses
                                 if c.clause not in ("in-database", "priqty", "secqty", "explicit-elements", "key-list",
                                                     "partition-block", "partition-attributes")))
        a = obj.attrs
        if kind in ("tablespace", "lob-tablespace"):
            facets["tablespace.type"][a.get("type")] += 1
            facets["tablespace.page-size"][f"{page_size(a['bufferpool'])}K" if a.get("bufferpool") else OMITTED] += 1
        elif kind == "table":
            _table_features(report, result, features, facets)
            signature += tuple(sorted({("type", c.type.family or "DISTINCT") for c in a.get("columns", []) if c.type}))
        elif kind == "index":
            uniqueness = "unique-where-not-null" if a.get("where_not_null") else "unique" if a.get("unique") else "nonunique"
            facets["index.uniqueness"][uniqueness] += 1
            index_kind = "auxiliary" if a.get("auxiliary") else "xml" if a.get("xmlpattern") else \
                "expression" if a.get("expression") else "partitioned" if a.get("partitioned") else "ordinary"
            facets["index.kind"][index_kind] += 1
            if a.get("include"):
                facets["index.kind"]["include"] += 1
        shapes[kind].add(signature)
    data = read_json(KB)
    clause_coverage = {}
    for kb_object, obj in data["objects"].items():
        if kb_object not in {KB_OBJECT[k] for k in counts if k in KB_OBJECT}:
            continue
        exercised = sorted(c["id"] for c in obj["clauses"]
                           if any(v != OMITTED for v in features.get(f"{kb_object}.{c['id']}", {})))
        if kb_object in ("table", "tablespace", "index", "database", "stogroup"):
            exercised = sorted(set(exercised) | {"name"})
        unexercised = [c["id"] for c in obj["clauses"] if c["id"] not in exercised]
        clause_coverage[kb_object] = {"exercised": exercised, "unexercised": unexercised,
                                      "ratio": f"{len(exercised)}/{len(obj['clauses'])}"}
    result = {
        "objects": dict(counts),
        "kb_clause_coverage": clause_coverage,
        "features": {k: dict(v) for k, v in sorted(features.items())},
        "facets": {k: dict(v) for k, v in sorted(facets.items())},
        "shapes": {k: {"objects": counts[k], "distinct_option_signatures": len(v)} for k, v in sorted(shapes.items())},
        "scope": "Counts syntax used in the script against normalized KB clause IDs. It does not measure Db2 acceptance, "
                 "product extraction or semantic verification. <omitted> counts clauses left to their defaults.",
    }
    if baseline is not None:
        result["baseline"] = check_baseline(result, baseline)
    return result


def _table_features(report, result, features, facets):
    a = result.obj.attrs
    add = lambda clause, value=SPECIFIED: features[f"table.{clause}"].__setitem__(value, features[f"table.{clause}"][value] + 1)
    placement = {"tablespace": "explicit", "database": "implicit-in-database", "omitted": "fully-implicit",
                 "accelerator": "accelerator"}.get(a.get("placement"), a.get("placement"))
    facets["table.placement"][placement] += 1
    lob = any(c.type is not None and c.type.family in sq.LOB_FAMILIES for c in a.get("columns", []))
    if lob:
        state = report.tables.get(qualified(result.obj.name, result.detail.get("schema_default")))
        explicit = state is not None and bool(state.aux_tables)
        facets["table.lob-support"]["explicit" if explicit else "implicit"] += 1
    periods = {p["name"] for p in a.get("periods", [])}
    facets["table.temporal"]["bitemporal" if len(periods) == 2 else (next(iter(periods)).lower() if periods else "none")] += 1
    for column in a.get("columns", []):
        add("column-definition")
        if column.type is not None:
            add("data-type", column.type.family or "DISTINCT")
            if column.type.subtype or column.type.ccsid:
                add("data-type", f"{column.type.family} FOR {column.type.subtype} DATA" if column.type.subtype else f"{column.type.family} CCSID {column.type.ccsid}")
            if column.type.time_zone:
                add("data-type", "TIMESTAMP WITH TIME ZONE")
        add("not-null", "NOT NULL" if column.not_null else OMITTED)
        add("default", column.default or OMITTED)
        generated = {"identity": "identity", "row-change-timestamp": "row-change-timestamp", "rowid": "rowid",
                     "row-begin": "row-begin", "row-end": "row-end", "transaction-start-id": "transaction-start-id",
                     "expression": "generated-provenance"}.get(column.generated)
        if generated:
            add(generated, column.generated_mode or "ALWAYS")
            if column.identity_options:
                add("identity", "with options")
        if column.hidden:
            add("implicitly-hidden")
        if column.inline_length is not None:
            add("inline-length")
        if column.fieldproc:
            add("fieldproc")
        if column.security_label:
            add("security-label")
    for constraint in a.get("constraints", []):
        if constraint.column_level:
            add("column-constraint", constraint.kind)
        if constraint.kind == "primary":
            add("primary-key", "BUSINESS_TIME WITHOUT OVERLAPS" if constraint.period else SPECIFIED)
        elif constraint.kind == "unique":
            add("unique", "BUSINESS_TIME WITHOUT OVERLAPS" if constraint.period else SPECIFIED)
        elif constraint.kind == "foreign":
            add("foreign-key", constraint.delete_rule or OMITTED)
            facets["foreign-key.enforced"]["ENFORCED" if constraint.enforced else "NOT ENFORCED"] += 1
            facets["foreign-key.columns"]["composite" if len(constraint.columns) > 1 else "single"] += 1
        elif constraint.kind == "check":
            add("check")


BASELINES = paths.VARIETY_BASELINE


def load_baseline(name):
    """Return a baseline by id (resolving `extends`) or from a JSON file path."""
    if Path(name).is_file():
        return read_json(name)
    catalog = {b["id"]: b for b in read_json(BASELINES)["baselines"]}
    if name not in catalog:
        raise ValueError(f"Unknown baseline {name!r}; choose one of {sorted(catalog)} or a file path")
    chain, current = [], catalog[name]
    while current:
        chain.insert(0, current)
        current = catalog.get(current.get("extends")) if current.get("extends") else None
    merged = {}
    for baseline in chain:
        for requirement in baseline["requirements"]:
            merged[requirement["feature"]] = requirement
    return {"id": name, "description": catalog[name]["description"], "requirements": list(merged.values())}


def check_baseline(cov, baseline):
    outcomes = []
    for requirement in baseline["requirements"]:
        feature = requirement["feature"]
        if feature.startswith("facet:"):
            observed = cov["facets"].get(feature[6:], {})
        else:
            observed = cov["features"].get(feature, {})
        values = set(observed)
        met, detail = True, []
        if "min_distinct" in requirement:
            pool = values if requirement.get("count_omitted", True) else values - {OMITTED}
            if len(pool) < requirement["min_distinct"]:
                met = False
                detail.append(f"needs {requirement['min_distinct']} distinct values, found {len(pool)}")
        if requirement.get("specified") and not (values - {OMITTED}):
            met = False
            detail.append("needs at least one explicit use")
        if "values" in requirement:
            missing = sorted(set(requirement["values"]) - values)
            if missing:
                met = False
                detail.append(f"missing values {missing}")
        if "any_of" in requirement and not values & set(requirement["any_of"]):
            met = False
            detail.append(f"needs one of {requirement['any_of']}")
        outcomes.append({"feature": feature, "met": met, "observed": sorted(values), "detail": "; ".join(detail),
                         "note": requirement.get("note", "")})
    unmet = [o for o in outcomes if not o["met"]]
    return {"id": baseline["id"], "met": len(outcomes) - len(unmet), "total": len(outcomes), "complete": not unmet,
            "unmet": unmet}


# =========================================================================== semantic diff

FIXED_DEFAULTS = {  # value used by Db2 when the clause is omitted; independent of subsystem parameters
    "tablespace": {"close": "YES", "define": "YES", "freepage": 0, "pctfree": 5, "locksize": "ANY", "logged": "LOGGED",
                   "maxrows": 255, "member_cluster": False, "gbpcache": "CHANGED", "insert_algorithm": 0,
                   "compress": "NO", "erase": "NO", "priqty": -1, "secqty": -1},
    "lob-tablespace": {"close": "YES", "define": "YES", "locksize": "ANY", "logged": "LOGGED", "gbpcache": "CHANGED",
                       "compress": "NO", "erase": "NO", "dssize": 4, "priqty": -1, "secqty": -1},
    "table": {"audit": "NONE", "data_capture": "NONE", "append": "NO", "volatile": "NOT VOLATILE",
              "restrict_on_drop": False},
    "index": {"cluster": False, "freepage": 0, "pctfree": 10, "gbpcache": "CHANGED", "compress": "NO",
              "null_keys": "INCLUDE", "close": "YES", "defer": "NO", "copy": "NO", "partitioned": False, "erase": "NO",
              "priqty": -1, "secqty": -1},
    "database": {"stogroup": "SYSDEFLT"},
}
DEFAULT_SOURCES = {"tablespace": "kb:tablespace (clause defaults); ibm-create-tablespace",
                   "lob-tablespace": "kb:tablespace (clause defaults); ibm-create-lob-tablespace",
                   "table": "kb:table (clause defaults); ibm-create-table",
                   "index": "kb:index (clause defaults); ibm-create-index",
                   "database": "kb:database (clause defaults); ibm-create-database"}
# A partition without its own value takes the value given outside any PARTITION clause
# (ibm-create-tablespace and ibm-create-index precedence lists). USING is inherited as one
# block: a partition with its own USING clause takes none of the outer USING values.
# Partition DSSIZE and PCTFREE ... FOR UPDATE have no documented inheritance and stay per partition.
USING_BLOCK = ("stogroup", "vcat", "priqty", "secqty", "erase")
PARTITION_INHERITED = {"tablespace": ("freepage", "pctfree", "gbpcache", "compress", "trackmod"),
                       "index": ("freepage", "pctfree", "gbpcache")}
EXPRESSION_SYNONYMS = {"USER": "SESSION_USER"}  # generated-expression inventory, kb/objects/table.md
GENERATED_NAME = ("The source leaves this constraint unnamed, so Db2 generates its name (ibm-create-table); "
                  "the target names it explicitly.")
ENVIRONMENT_DEFAULTS = {  # attribute: subsystem parameter or container that supplies an omitted value
    "tablespace": {"segsize": "DPSEGSZ", "trackmod": "IMPTKMOD", "pctfree_for_update": "PCTFREE_UPD",
                   "maxpartitions": "APPLCOMPAT (254 at V13R1M500 or higher; 256 at V12R1M504-V13R1M100)",
                   "pagenum": "PAGESET_PAGENUM (Db2 13 FL 100 default RELATIVE)",
                   "dssize": "page size and MAXPARTITIONS/NUMPARTS", "bufferpool": "database BUFFERPOOL",
                   "ccsid": "database CCSID", "stogroup": "database STOGROUP"},
    "lob-tablespace": {"bufferpool": "database/TBSBPLOB", "stogroup": "database STOGROUP"},
    "table": {"compress": "IMPTSCMP", "dssize": "IMPDSSIZE", "trackmod": "IMPTKMOD", "bufferpool": "TBSBPOOL family",
              "logged": "implicit table space default", "ccsid": "database CCSID"},
    "index": {"padded": "PADIX", "bufferpool": "database INDEXBP", "define": "base table space allocation state",
              "stogroup": "database STOGROUP", "piecesize": "Db2 calculation", "dssize": "base table space"},
    "database": {"bufferpool": "TBSBPOOL", "indexbp": "IDXBPOOL", "ccsid": "DEF ENCODING SCHEME"},
}
TYPE_MAX = {"SMALLINT": 32767, "INTEGER": 2147483647, "BIGINT": 9223372036854775807}
INTERNAL = {"duplicate_clauses", "partial", "_table_key", "line", "columns", "constraints", "periods", "partitions",
            "keys", "include", "range_partitions", "partition_keys", "partition_nulls_last", "words", "type", "database", "tablespace",
            "table", "base", "unique", "where_not_null", "expression", "xmlpattern", "auxiliary", "placement",
            "definition", "source", "copy_options", "column_list", "references", "subject", "target", "sqlpl",
            "unbalanced_begin", "source_type", "business_time", "column", "part", "volumes", "hash"}


class NameMap:
    def __init__(self, schemas=None, databases=None, objects=None):
        self.schemas, self.databases, self.objects = schemas or {}, databases or {}, objects or {}

    @classmethod
    def load(cls, data):
        return cls(data.get("schemas", {}), data.get("databases", {}), data.get("objects", {}))

    def relation(self, key):
        if key in self.objects:
            return self.objects[key]
        schema, _, name = key.rpartition(".")
        return f"{self.schemas.get(schema, schema)}.{name}" if schema else key

    def database(self, name):
        return self.databases.get(name, name) if name else name

    def tablespace(self, key):
        db, _, name = key.partition(".")
        return f"{self.database(db)}.{name}"

    def as_dict(self):
        return {"schemas": self.schemas, "databases": self.databases, "objects": self.objects}


def semantic_objects(report, names=None):
    names = names or NameMap()
    out = {}
    databases = {}  # databases this script creates, with the defaults they give child spaces and indexes
    for result in report.objects:
        obj = result.obj
        if obj.kind == "database":
            databases[obj.name.name] = {**obj.attrs, "stogroup": obj.attrs.get("stogroup") or FIXED_DEFAULTS["database"]["stogroup"]}
    for result in report.objects:
        obj, a = result.obj, result.obj.attrs
        default = result.detail.get("schema_default")
        rules = result.detail.get("rules", "DB2")
        options = {k: v for k, v in a.items() if k not in INTERNAL}
        if obj.kind in ("tablespace", "lob-tablespace"):
            key = ("tablespace", names.tablespace(f"{a.get('database') or 'DSNDB04'}.{obj.name.name}"))
        elif obj.kind in ("database", "stogroup"):
            key = (obj.kind, names.database(obj.name.name) if obj.kind == "database" else obj.name.name)
        else:
            key = ("table" if obj.kind == "auxiliary-table" else obj.kind, names.relation(qualified(obj.name, default)))
        if a.get("partial"):
            issue = next((i for i in result.issues if report.rules.get(i[0], {}).get("severity") == "unsupported"), None)
            out[key] = {"kind": obj.kind, "not_compared": f"Statement {result.statement.index} was only partly parsed"
                        + (f" (line {issue[2]}: {issue[1]})" if issue else "") + "; its definition is not compared."}
            continue
        if obj.kind == "database":
            out[key] = {"kind": "database", "options": options}
        elif obj.kind == "stogroup":
            out[key] = {"kind": "stogroup", "options": options, "volumes": sorted(a.get("volumes", []))}
        elif obj.kind in ("tablespace", "lob-tablespace"):
            database = a.get("database") or "DSNDB04"
            if a.get("type") == "PBG":
                options.setdefault("numparts", 1)
            if "lockmax" not in options:
                options["lockmax"] = "SYSTEM" if options.get("locksize", "ANY") in ("ANY", "LOB") else 0
            for attribute in ("bufferpool", "ccsid", "stogroup"):
                if attribute not in options and database in databases and databases[database].get(attribute) \
                        and not (attribute == "stogroup" and "vcat" in options):
                    options[attribute] = databases[database][attribute]
            parts = {}
            if a.get("type") == "PBR":
                parts = _effective_partitions(options, a.get("partitions", []), a.get("numparts"), "tablespace")
            out[key] = {"kind": obj.kind, "type": a.get("type"), "options": options, "partitions": parts}
        elif obj.kind == "table":
            out[key] = _semantic_table(a, default, rules, names, _table_encoding(report, result, databases))
        elif obj.kind == "auxiliary-table":
            out[key] = {
                "kind": "auxiliary-table", "tablespace": names.tablespace(f"{a.get('database') or 'DSNDB04'}.{a['tablespace']}"),
                "stores": names.relation(qualified(a["base"], default)), "column": a["column"], "part": a.get("part"),
                "options": options}
        elif obj.kind == "index":
            table = report.tables.get(qualified(a["table"], default))
            database = databases.get(table.database) if table is not None and table.database else None
            if database is not None:
                # The database supplies an omitted index buffer pool (INDEXBP) and storage group (kb/objects/database.md).
                for attribute, source in (("bufferpool", "indexbp"), ("stogroup", "stogroup")):
                    if attribute not in options and database.get(source) and not (attribute == "stogroup" and "vcat" in options):
                        options[attribute] = database[source]
            parts = {}
            if a.get("partitioned") or a.get("partitions"):
                count = table.tablespace.obj.attrs.get("numparts") if table is not None and table.partitioned else None
                parts = _effective_partitions(options, a.get("partitions", []), count, "index")
            keys = [{"key": k, "order": o or "ASC"} for k, o in a.get("keys", [])]
            out[key] = {
                "kind": "index", "table": names.relation(qualified(a["table"], default)),
                "uniqueness": "UNIQUE WHERE NOT NULL" if a.get("where_not_null") else "UNIQUE" if a.get("unique") else "NONUNIQUE",
                "keys": keys, "include": list(a.get("include", [])), "business_time": a.get("business_time"),
                "options": options, "partitions": parts}
        else:
            out[key] = {"kind": obj.kind, "not_compared": f"CREATE {obj.kind.upper()} is recognized, but its definition is not compared."}
    return out


def _effective_partitions(options, partitions, count, kind):
    """Per-partition attributes after IBM's precedence. Inherited attributes move from `options` into
    every partition, so a product that repeats them per partition, or omits them, compares equal."""
    own = {str(p["number"]): {k: v for k, v in p.items() if k not in ("number", "line")} for p in partitions}
    numbers = [str(n) for n in range(1, count + 1)] if count else sorted(own, key=int)
    if not numbers:
        return {}  # partition count unknown and no PARTITION clauses: compare the outer values as they are
    inherited = PARTITION_INHERITED[kind]
    outer = {k: options.pop(k) for k in USING_BLOCK + inherited if k in options}
    result = {}
    for number in numbers:
        mine = own.get(number, {})
        using = mine if any(k in mine for k in ("stogroup", "vcat")) else outer
        effective = {k: using[k] for k in USING_BLOCK if k in using}
        effective.update({k: mine.get(k, outer.get(k)) for k in inherited if k in mine or k in outer})
        effective.update({k: v for k, v in mine.items() if k not in USING_BLOCK and k not in inherited})
        result[number] = effective
    for number in sorted(set(own) - set(numbers), key=int):
        result[number] = own[number]  # a PARTITION clause outside NUMPARTS stays visible
    return result


def _table_encoding(report, result, databases):
    """Encoding scheme of a table: its CCSID clause, else its table space's, else its database's, when the script shows it."""
    a = result.obj.attrs
    if a.get("ccsid"):
        return a["ccsid"]
    state = report.tables.get(qualified(result.obj.name, result.detail.get("schema_default")))
    if state is None:
        return None
    if state.tablespace is not None and state.tablespace.obj.attrs.get("ccsid"):
        return state.tablespace.obj.attrs["ccsid"]
    return databases.get(state.database, {}).get("ccsid") if state.database else None


def _semantic_table(a, default, rules, names, encoding=None):
    columns = []
    for column in a.get("columns", []):
        dt = column.type
        identity = None
        if column.generated == "identity":
            identity = _identity(column)
        default_value = column.default
        if default_value is None and column.nullable and column.generated is None:
            default_value = "null"
        columns.append({"name": column.name, "type": list(Checker.signature(dt)) if dt else None,
                        "type_text": dt.raw if dt else None, "not_null": column.not_null or not column.nullable,
                        "default": default_value, "default_text": column.default_raw if column.default not in (None, "null", "type-default") else None,
                        "generated": column.generated, "generated_mode": column.generated_mode, "identity": identity,
                        "generated_expression": _token_signature(column.generated_expression, EXPRESSION_SYNONYMS) if column.generated_expression else None,
                        "hidden": column.hidden, "inline_length": column.inline_length, "fieldproc": column.fieldproc,
                        "fieldproc_parameters": _token_signature(column.fieldproc_parameters) if column.fieldproc_parameters else None,
                        "security_label": column.security_label})
    constraints = {"primary": None, "unique": [], "foreign": [], "check": []}
    for c in a.get("constraints", []):
        if c.kind == "primary":
            constraints["primary"] = {"name": c.name, "columns": c.columns, "period": c.period}
        elif c.kind == "unique":
            constraints["unique"].append({"name": c.name, "columns": c.columns, "period": c.period})
        elif c.kind == "foreign":
            delete = c.delete_rule or ("RESTRICT" if (c.rules or rules) == "DB2" else "NO ACTION")
            constraints["foreign"].append({
                "name": c.name, "columns": c.columns, "parent": names.relation(qualified(c.parent, default)),
                "parent_columns": c.parent_columns, "delete_rule": delete, "delete_rule_explicit": c.delete_rule is not None,
                "enforced": c.enforced, "query_optimization": True if not c.enforced and not c.query_optimization else c.query_optimization,
                "period": c.period})
        elif c.kind == "check":
            constraints["check"].append({"name": c.name, "condition": _token_signature(c.condition_tokens)})
    constraints["unique"].sort(key=lambda u: u["columns"])
    constraints["foreign"].sort(key=lambda f: (f["columns"], f["parent"]))
    constraints["check"].sort(key=lambda c: (c["name"] or "", c["condition"]))
    placement = a.get("placement")
    space = None
    if placement == "tablespace":
        space = names.tablespace(f"{a.get('database') or 'DSNDB04'}.{a['tablespace']}")
    elif placement == "database":
        space = f"IN DATABASE {names.database(a['database'])}"
    options = {k: v for k, v in a.items() if k not in INTERNAL and k not in ("partition_by_size",)}
    if encoding and "ccsid" not in options:
        options["ccsid"] = encoding  # an omitted table CCSID takes the encoding of its table space or database
    partitioning = None
    if a.get("range_partitions"):
        # ENDING AT defines the limit key, the highest key value of the partition (ibm-create-table,
        # ibm-partition-boundary), so INCLUSIVE does not change the boundary and is not compared.
        nulls_last = set(a.get("partition_nulls_last", []))
        partitioning = {"keys": [[k, o] + (["NULLS LAST"] if k in nulls_last else []) for k, o in a["partition_keys"]],
                        "partitions": [{"number": p["number"], "values": p["values"]} for p in a["range_partitions"]]}
    elif "partition_by_size" in a:
        partitioning = {"size": a.get("partition_by_size")}
    return {"kind": "table", "definition": a.get("definition"), "placement": space or placement,
            "columns": columns, "constraints": constraints,
            "periods": sorted([{"name": p["name"], "columns": p["columns"], "mode": p["mode"] or ("EXCLUSIVE" if p["name"] == "BUSINESS_TIME" else None)} for p in a.get("periods", [])], key=lambda p: p["name"]),
            "partitioning": partitioning, "options": options, "_encoding": encoding}


def _identity(column):
    o = column.identity_options
    increment = Decimal(o.get("INCREMENT BY", "1"))
    ascending = increment >= 0
    family = column.type.family if column.type else None
    type_max = TYPE_MAX.get(family)
    if family == "DECIMAL":
        type_max = 10 ** (column.type.length or 5) - 1
    effective = {"INCREMENT BY": str(increment), "CYCLE": o.get("CYCLE", False), "CACHE": o.get("CACHE", "20"),
                 "ORDER": o.get("ORDER", False)}
    if ascending:
        start = o.get("START WITH")
        minimum = o.get("MINVALUE") if o.get("MINVALUE") is not None else (start or "1")
        effective["MINVALUE"] = str(Decimal(minimum))
        effective["START WITH"] = str(Decimal(start if start is not None else minimum))
        maximum = o.get("MAXVALUE")
        effective["MAXVALUE"] = str(Decimal(maximum)) if maximum is not None else (str(type_max) if type_max else "type maximum")
    else:
        for key in ("START WITH", "MINVALUE", "MAXVALUE"):
            effective[key] = str(Decimal(o[key])) if o.get(key) is not None else "type-dependent (descending)"
    if effective["CACHE"] is not None:
        effective["CACHE"] = str(effective["CACHE"])
    return effective


def _token_signature(tokens, synonyms=None):
    """Order-preserving token identity: keywords compared case-insensitively, literals exactly. A delimited
    identifier that spells an ordinary identifier ("STATUS") is that identifier (ibm-sql-identifiers)."""
    parts = []
    for t in tokens:
        if t.kind == "word":
            parts.append((synonyms or {}).get(t.value, t.value))
        elif t.kind == "ident" and sq.ORDINARY_IDENTIFIER.fullmatch(t.value):
            parts.append(t.value)
        elif t.kind in ("string", "ident"):
            parts.append(f"{t.kind}:{t.prefix}{t.value}")
        else:
            parts.append(t.value)
    return " ".join(parts)


def diff(source, target, names=None, profile=None):
    """Compare two parsed scripts. source/target are Reports. Returns a JSON-able dict."""
    params = {}
    if profile:
        context = profile.get("product_context", profile)
        params = dict(context.get("subsystem_parameters") or {})
        if context.get("applcompat"):
            params["_APPLCOMPAT"] = context["applcompat"]
    left, right = semantic_objects(source, names), semantic_objects(target)
    differences = []
    for key in sorted(set(left) | set(right)):
        label = f"{key[0]} {key[1]}"
        if key not in right:
            differences.append({"object": label, "status": "missing", "detail": "Created by the source script but not by the target script."})
            continue
        if key not in left:
            differences.append({"object": label, "status": "extra", "detail": "Created only by the target script (for example an explicit form of an implicitly created object). Review it."})
            continue
        _compare_object(label, left[key], right[key], differences, params)
    differences.extend(_uncompared_statements(source, "source") + _uncompared_statements(target, "target"))
    statuses = Counter(d["status"] for d in differences)
    definite = statuses["missing"] + statuses["different"]
    unresolved = statuses["extra"] + statuses["environment-dependent"] + statuses["not-compared"]
    return {"status": "mismatch" if definite else "unresolved" if unresolved else "match",
            "counts": dict(statuses), "differences": differences,
            "scope": "Parsed DDL semantics only. Equivalent-default entries are not defects. Environment-dependent entries "
                     "need the recorded subsystem parameters or catalog evidence. Not-compared entries are statements or "
                     "objects the diff could not read or does not model; review them separately. A match does not replace "
                     "execution and catalog comparison."}


def _uncompared_statements(report, side):
    """Statements outside CREATE whose effect on the compared objects the diff cannot model."""
    out = []
    for result in report.parsed:
        if result.obj is not None:
            continue  # a partly parsed CREATE is reported with its object
        issue = next((i for i in result.issues if report.rules.get(i[0], {}).get("severity") == "unsupported"), None)
        if issue:
            detail = f"Not parsed: {issue[1]}"
        elif result.verb == "ALTER" and (result.kind != "table" or result.detail.get("unmodeled")):
            detail = f"ALTER {(result.kind or '').upper()} is not modeled; its effect on compared objects is unknown."
        elif result.verb == "RENAME":
            detail = "RENAME is not modeled; names after it are unknown."
        else:
            continue
        out.append({"object": f"statement {result.statement.index}", "status": "not-compared", "side": side,
                    "line": result.statement.line, "detail": detail})
    return out


def _compare_object(label, left, right, out, params):
    kind = left.get("kind")
    if kind != right.get("kind"):
        out.append({"object": label, "status": "different", "attribute": "kind", "source": kind, "target": right.get("kind")})
        return
    if left.get("not_compared") or right.get("not_compared"):
        sides = [side for side, value in (("source", left), ("target", right)) if value.get("not_compared")]
        out.append({"object": label, "status": "not-compared", "side": sides[0] if len(sides) == 1 else "both",
                    "detail": (left.get("not_compared") or right.get("not_compared"))})
        return
    for attribute in sorted((set(left) | set(right)) - {"options", "kind", "partitions"}):
        lv, rv = left.get(attribute), right.get(attribute)
        if attribute.startswith("_"):
            continue  # context for other comparisons, such as the table's resolved encoding
        if attribute == "columns":
            _compare_columns(label, lv or [], rv or [], out, params, left.get("_encoding") or right.get("_encoding"))
        elif attribute == "constraints":
            _compare_constraints(label, lv, rv, out)
        elif lv != rv:
            out.append({"object": label, "status": "different", "attribute": attribute, "source": lv, "target": rv})
    _compare_options(label, kind, left.get("options", {}), right.get("options", {}), out, params)
    lp, rp = left.get("partitions") or {}, right.get("partitions") or {}
    for number in sorted(set(lp) | set(rp), key=int):
        if number in lp and number in rp:
            _compare_options(label, kind, lp[number], rp[number], out, params, f"partition {number} ")
        else:
            out.append({"object": label, "status": "different", "attribute": f"partition {number}",
                        "source": lp.get(number), "target": rp.get(number), "detail": "The partition is defined on one side only."})


def _compare_options(label, kind, lo, ro, out, params, prefix=""):
    """Compare option maps; an option given on one side only is judged against its documented default."""
    fixed = FIXED_DEFAULTS.get(kind, {})
    env = ENVIRONMENT_DEFAULTS.get(kind, {})
    for attribute in sorted(set(lo) | set(ro)):
        lv, rv = lo.get(attribute), ro.get(attribute)
        if attribute in lo and attribute in ro:
            if not _same(lv, rv):
                out.append({"object": label, "status": "different", "attribute": prefix + attribute, "source": lv, "target": rv})
            continue
        explicit = lv if attribute in lo else rv
        side = "source" if attribute in lo else "target"
        resolved = _resolve_env(kind, attribute, params)
        default = fixed.get(attribute, resolved)
        entry = {"object": label, "attribute": prefix + attribute, "source": lv if attribute in lo else None,
                 "target": rv if attribute in ro else None, "explicit_on": side}
        if default is not None:
            entry.update(status="equivalent-default" if _same(default, explicit) else "different",
                         default=default, default_source=DEFAULT_SOURCES.get(kind, "") if attribute in fixed else "profile subsystem parameter")
        elif attribute in env:
            entry.update(status="environment-dependent", default_from=env[attribute])
        else:
            entry.update(status="different", detail="Specified on one side only; no documented fixed default is encoded.")
        out.append(entry)


def _resolve_env(kind, attribute, params):
    def flag(name):
        value = str(params.get(name, "")).upper()
        return "YES" if value in ("YES", "Y", "1") else "NO" if value in ("NO", "N", "0") else None
    if kind == "tablespace" and attribute == "segsize" and params.get("DPSEGSZ") is not None:
        value = int(params["DPSEGSZ"])
        return 32 if value == 0 else value
    if kind in ("tablespace", "table") and attribute == "trackmod":
        return flag("IMPTKMOD")
    if kind == "tablespace" and attribute == "pctfree_for_update" and params.get("PCTFREE_UPD") is not None:
        return params["PCTFREE_UPD"]
    if kind == "index" and attribute == "padded" and flag("PADIX"):
        return flag("PADIX") == "YES"
    if kind == "table" and attribute == "compress":
        return flag("IMPTSCMP")
    if kind == "tablespace" and attribute == "maxpartitions":
        applcompat = level_key(params.get("_APPLCOMPAT"))
        if applcompat is not None and applcompat >= (13, 500):
            return 254
        if applcompat is not None and applcompat >= UTS_BASELINE:
            return 256
    if kind == "tablespace" and attribute == "pagenum" and params.get("PAGESET_PAGENUM"):
        return str(params["PAGESET_PAGENUM"]).upper()
    return None


def _same(a, b):
    if a == b:
        return True
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return str(a).upper() == str(b).upper() if isinstance(a, str) and isinstance(b, str) and a.isalpha() else False


def _subtype_default(label, name, lv, rv, texts, params, encoding):
    """Judge a character column whose FOR subtype DATA clause is given on one side only. The omitted
    subtype is MIXED for Unicode data and, for ASCII or EBCDIC data, SBCS or MIXED as the MIXED DATA
    field on installation panel DSNTIPF says (ibm-create-table). Returns None for other type changes."""
    if not (lv and rv and len(lv) == len(rv) == 6 and lv[0] in ("CHAR", "VARCHAR", "CLOB") and lv[:4] == rv[:4]
            and lv[5] == rv[5] and "" in (lv[4], rv[4]) and "BIT" not in (lv[4], rv[4])):
        return None
    explicit = lv[4] or rv[4]
    entry = {"object": label, "attribute": f"column {name}.subtype", "source": texts[0], "target": texts[1],
             "explicit_on": "source" if lv[4] else "target"}
    default, origin = None, None
    mixed = str(params.get("MIXED", params.get("MIXED_DATA", ""))).upper()
    if encoding == "UNICODE":
        default, origin = "MIXED", "ibm-create-table (Unicode data)"
    elif encoding in ("EBCDIC", "ASCII") and mixed in ("YES", "Y", "NO", "N"):
        default, origin = ("MIXED" if mixed in ("YES", "Y") else "SBCS"), "profile subsystem parameter MIXED"
    if default:
        entry.update(status="equivalent-default" if explicit == default else "different", default=default, default_source=origin)
    else:
        entry.update(status="environment-dependent", default_from="MIXED DATA (DSNTIPF)" if encoding in ("EBCDIC", "ASCII")
                     else "the table's encoding scheme and MIXED DATA (DSNTIPF)")
    return entry


def _compare_columns(label, left, right, out, params=None, encoding=None):
    lnames, rnames = [c["name"] for c in left], [c["name"] for c in right]
    if lnames != rnames:
        if sorted(lnames) == sorted(rnames):
            out.append({"object": label, "status": "different", "attribute": "column order", "source": lnames, "target": rnames})
        else:
            out.append({"object": label, "status": "different", "attribute": "columns",
                        "source_only": sorted(set(lnames) - set(rnames)), "target_only": sorted(set(rnames) - set(lnames))})
    by_name = {c["name"]: c for c in right}
    for column in left:
        other = by_name.get(column["name"])
        if other is None:
            continue
        for attribute in column:
            if attribute in ("type_text",):
                continue
            lv, rv = column[attribute], other[attribute]
            if attribute == "default_text" and lv is not None and rv is not None and _same(lv, rv):
                continue
            if lv != rv and not (attribute == "default" and {lv, rv} <= {"type-default"}):
                if attribute == "type":
                    entry = _subtype_default(label, column["name"], lv, rv, (column["type_text"], other["type_text"]),
                                             params or {}, encoding)
                    if entry is not None:
                        out.append(entry)
                        continue
                out.append({"object": label, "status": "different", "attribute": f"column {column['name']}.{attribute}",
                            "source": lv if attribute != "type" else column["type_text"],
                            "target": rv if attribute != "type" else other["type_text"]})


def _compare_constraints(label, left, right, out):
    left, right = left or {}, right or {}
    for kind in ("primary", "unique", "foreign", "check"):
        lv, rv = left.get(kind), right.get(kind)
        if kind == "foreign":
            lv = [{k: v for k, v in f.items() if k != "delete_rule_explicit"} for f in (lv or [])]
            rv = [{k: v for k, v in f.items() if k != "delete_rule_explicit"} for f in (rv or [])]
        if lv != rv:
            litems, ritems = _items(lv), _items(rv)
            names_only = _contents(litems) == _contents(ritems)
            generated = names_only and _generated_names(litems, ritems)
            out.append({"object": label, "status": "equivalent-default" if generated else "different",
                        "attribute": f"{kind} constraints", "source": lv, "target": rv,
                        "detail": GENERATED_NAME if generated else "Only constraint names differ." if names_only else None})


def _items(value):
    return [] if value is None else [value] if isinstance(value, dict) else value


def _contents(items):
    return sorted(json.dumps(_strip_names(item), sort_keys=True) for item in items)


def _generated_names(left, right):
    """True when every name difference is a source constraint left unnamed, whose name Db2 generates."""
    names = defaultdict(list)
    for item in left:
        names[json.dumps(_strip_names(item), sort_keys=True)].append(item.get("name"))
    for item in right:
        pending = names[json.dumps(_strip_names(item), sort_keys=True)]
        if item.get("name") in pending:
            pending.remove(item.get("name"))
        elif None in pending:
            pending.remove(None)
        else:
            return False
    return True


def _strip_names(value):
    if isinstance(value, dict):
        return {k: _strip_names(v) for k, v in value.items() if k != "name"}
    if isinstance(value, list):
        return [_strip_names(v) for v in value]
    return value


# =========================================================================== QA bundle

CATALOG_COLUMNS = paths.CATALOG_COLUMNS
COLTYPE = {"INTEGER": "INTEGER", "SMALLINT": "SMALLINT", "BIGINT": "BIGINT", "DECIMAL": "DECIMAL", "FLOAT": "FLOAT",
           "DECFLOAT": "DECFLOAT", "CHAR": "CHAR", "VARCHAR": "VARCHAR", "GRAPHIC": "GRAPHIC", "VARGRAPHIC": "VARG",
           "CLOB": "CLOB", "BLOB": "BLOB", "DBCLOB": "DBCLOB", "BINARY": "BINARY", "VARBINARY": "VARBIN",
           "DATE": "DATE", "TIME": "TIME", "ROWID": "ROWID", "XML": "XML"}
LOCKRULE = {"ANY": "A", "PAGE": "P", "ROW": "R", "TABLESPACE": "S", "LOB": "L"}
GBPCACHE = {"CHANGED": "", "ALL": "A", "NONE": "N", "SYSTEM": "S"}
ENCODING = {"EBCDIC": "E", "ASCII": "A", "UNICODE": "U"}
DELETERULE = {"NO ACTION": "A", "CASCADE": "C", "SET NULL": "N", "RESTRICT": "R"}
DEFAULT_CODE = {("identity", "ALWAYS"): "I", ("identity", "BY DEFAULT"): "J", ("row-change-timestamp", "ALWAYS"): "E",
                ("row-change-timestamp", "BY DEFAULT"): "F", ("rowid", "ALWAYS"): "A", ("rowid", "BY DEFAULT"): "D",
                ("row-begin", "ALWAYS"): "Q", ("row-end", "ALWAYS"): "R", ("transaction-start-id", "ALWAYS"): "X"}
IDENT = re.compile(r"[A-Z][A-Z0-9_]*")


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def _in_list(values):
    return ", ".join(_literal(v) for v in sorted(values))


class CatalogQueries:
    def __init__(self):
        self.columns = {t: set(v["columns"]) for t, v in read_json(CATALOG_COLUMNS)["tables"].items()}
        self.types = {t: v["columns"] for t, v in read_json(CATALOG_COLUMNS)["tables"].items()}
        self.queries = []

    def add(self, qid, table, fields, key, where, rows, expressions=None, expression_types=None):
        expressions, expression_types = expressions or {}, expression_types or {}
        missing = [f for f in fields if f not in expressions and f not in self.columns[table]]
        if missing:
            raise ValueError(f"Catalog query {qid} selects unverified columns {missing} from {table}")
        if set(expressions) != set(expression_types):
            raise ValueError(f"Catalog query {qid}: every computed field needs a declared type")
        rtrim = [f for f in fields if f not in expressions and self.types[table][f].startswith("CHAR(")]
        def render(side):
            select = ", ".join(expressions[f][side] + f" AS {f}" if f in expressions else f for f in fields)
            return f"SELECT {select} FROM {table} WHERE {where[side]}"
        low, high = rows if isinstance(rows, tuple) else (rows, rows)
        self.queries.append({"id": qid, "table": table, "fields": fields, "key": key, "rtrim_fields": rtrim,
                             "types": {f: expression_types[f] if f in expressions else self.types[table][f] for f in fields},
                             "min_rows": low, "max_rows": high, "source_sql": render("source"),
                             "replay_sql": render("replay")})


def bundle(report, text, names, run, profile, out=None):
    """Return {path: content} for a QA bundle derived from a lint-clean script."""
    if report.failed():
        raise ValueError("The script has error/unsupported findings; fix them before deriving a bundle (run lint).")
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,7}", run):
        raise ValueError("--run must be 2-8 uppercase letters/digits starting with a letter")
    tables = {k: s for k, s in report.tables.items()}
    created_dbs = [r.obj.name.name for r in report.objects if r.obj.kind == "database" and r.obj.name.name in report.databases]
    schemas = sorted({k.rpartition(".")[0] for k in list(tables) + list(report.indexes)})
    if DEFAULT_SCHEMA in schemas:
        raise ValueError("Some objects are unqualified and no SET CURRENT SCHEMA/SQLID was seen; qualify them so catalog queries can target them.")
    needed = [f"--replay-schema {s}=<TARGET>" for s in schemas if s not in names.schemas] + \
             [f"--replay-database {d}=<TARGET>" for d in created_dbs if d not in names.databases]
    if needed:
        raise ValueError("Name the clean replay target for every source schema and created database: " + " ".join(needed))
    for source, target in list(names.schemas.items()) + list(names.databases.items()):
        if not IDENT.fullmatch(target) or source == target:
            raise ValueError(f"Replay name {target!r} for {source} must be a different ordinary identifier")
    for target in names.databases.values():
        if len(target) > 8:
            raise ValueError(f"Replay database {target} exceeds 8 bytes")
    q = CatalogQueries()
    assertions = []

    def both(build):
        return {"source": build(lambda s: s, lambda d: d), "replay": build(names.schemas.get, names.database)}

    for index, db in enumerate(created_dbs, 1):
        obj = report.databases[db]
        q.add(f"database_{index}", "SYSIBM.SYSDATABASE", ["TYPE", "STGROUP", "BPOOL", "INDEXBP", "ENCODING_SCHEME", "IMPLICIT"],
              ["TYPE"], both(lambda s, d, db=db: f"NAME = {_literal(d(db))}"), 1)
        expect = {"IMPLICIT": "N"}
        if obj.attrs.get("bufferpool"):
            expect["BPOOL"] = obj.attrs["bufferpool"]
        if obj.attrs.get("indexbp"):
            expect["INDEXBP"] = obj.attrs["indexbp"]
        if obj.attrs.get("ccsid"):
            expect["ENCODING_SCHEME"] = ENCODING[obj.attrs["ccsid"]]
        assertions.append({"catalog": f"database_{index}", "where": {}, "equals": expect})
    spaces = defaultdict(list)
    for key, ts in report.tablespaces.items():
        spaces[ts.database].append(ts)
    for n, (database, group) in enumerate(sorted(spaces.items()), 1):
        names_list = [ts.obj.name.name for ts in group]
        qid = f"tablespaces_{n}"
        q.add(qid, "SYSIBM.SYSTABLESPACE",
              ["NAME", "TYPE", "PARTITIONS", "SEGSIZE", "MAXPARTITIONS", "DSSIZE", "BPOOL", "PGSIZE", "LOCKRULE", "LOCKMAX",
               "CLOSERULE", "ERASERULE", "ENCODING_SCHEME", "MAXROWS", "LOG", "MEMBER_CLUSTER", "PAGENUM", "INSERTALG",
               "FREEPAGE", "PCTFREE", "PCTFREE_UPD", "COMPRESS", "GBPCACHE", "TRACKMOD", "STORTYPE", "IMPLICIT"],
              ["NAME"], both(lambda s, d, database=database, names_list=names_list: f"DBNAME = {_literal(d(database))} AND NAME IN ({_in_list(names_list)})"), len(group))
        part_rows = 0
        for ts in group:
            a = ts.obj.attrs
            expect = {"TYPE": {"PBG": "G", "PBR": "R", "LOB": "O"}[a["type"]], "IMPLICIT": "N"}
            for attr, field_, conv in (("segsize", "SEGSIZE", int), ("maxpartitions", "MAXPARTITIONS", int),
                                       ("maxrows", "MAXROWS", int), ("freepage", "FREEPAGE", int), ("pctfree", "PCTFREE", int),
                                       ("pctfree_for_update", "PCTFREE_UPD", int), ("insert_algorithm", "INSERTALG", int),
                                       ("bufferpool", "BPOOL", str)):
                if attr in a:
                    expect[field_] = conv(a[attr])
            if "dssize" in a:
                expect["DSSIZE"] = a["dssize"] * 1048576
            if "locksize" in a:
                expect["LOCKRULE"] = LOCKRULE[a["locksize"]]
            if "lockmax" in a:
                expect["LOCKMAX"] = -1 if a["lockmax"] == "SYSTEM" else a["lockmax"]
            if "close" in a:
                expect["CLOSERULE"] = "Y" if a["close"] == "YES" else "N"
            if "logged" in a:
                expect["LOG"] = "Y" if a["logged"] == "LOGGED" else "N"
            if a.get("member_cluster"):
                expect["MEMBER_CLUSTER"] = "Y"
            if "gbpcache" in a:
                expect["GBPCACHE"] = GBPCACHE.get(a["gbpcache"], a["gbpcache"])
            if "trackmod" in a:
                expect["TRACKMOD"] = "" if a["trackmod"] == "YES" else "N"
            if "ccsid" in a:
                expect["ENCODING_SCHEME"] = ENCODING[a["ccsid"]]
            if "compress" in a:
                expect["COMPRESS"] = {"YES": "Y", "YES FIXEDLENGTH": "F", "YES HUFFMAN": "H", "NO": ""}[a["compress"]]
            if "pagenum" in a:
                expect["PAGENUM"] = a["pagenum"][0]
            if a["type"] == "PBR":
                expect["PARTITIONS"] = a["numparts"]
            if a.get("bufferpool"):
                expect["PGSIZE"] = page_size(a["bufferpool"])
            assertions.append({"catalog": qid, "where": {"NAME": ts.obj.name.name}, "equals": expect})
            part_rows += a.get("numparts", 1) if a["type"] != "LOB" else 1
        q.add(f"tablespace_parts_{n}", "SYSIBM.SYSTABLEPART",
              ["TSNAME", "PARTITION", "FREEPAGE", "PCTFREE", "PCTFREE_UPD", "COMPRESS", "TRACKMOD", "GBPCACHE", "STORTYPE", "LIMITKEY"],
              ["TSNAME", "PARTITION"], both(lambda s, d, database=database, names_list=names_list: f"DBNAME = {_literal(d(database))} AND TSNAME IN ({_in_list(names_list)})"), part_rows)
    by_schema = defaultdict(list)
    for key, state in tables.items():
        by_schema[key.rpartition(".")[0]].append(state)
    for n, (schema, group) in enumerate(sorted(by_schema.items()), 1):
        tnames = [s.obj.name.name for s in group]
        explicit_ts = sorted({s.tablespace.obj.name.name for s in group if s.tablespace is not None})
        tsname_expr = (lambda s, d: f"CASE WHEN TSNAME IN ({_in_list(explicit_ts)}) THEN TSNAME ELSE '*IMPLICIT*' END") if explicit_ts else (lambda s, d: "'*IMPLICIT*'")
        qid = f"tables_{n}"
        q.add(qid, "SYSIBM.SYSTABLES",
              ["NAME", "TYPE", "STATUS", "TABLESTATUS", "AUDITING", "DATACAPTURE", "APPEND", "SPLIT_ROWS", "CLUSTERTYPE",
               "ENCODING_SCHEME", "EDPROC", "VALPROC", "KEYCOLUMNS", "PARTKEYCOLNUM", "PARENTS", "CHILDREN", "CHECKS", "TSNAME_EXPLICIT"],
              ["NAME"], both(lambda s, d, schema=schema, tnames=tnames: f"CREATOR = {_literal(s(schema))} AND NAME IN ({_in_list(tnames)})"),
              len(group), expressions={"TSNAME_EXPLICIT": both(tsname_expr)}, expression_types={"TSNAME_EXPLICIT": "VARCHAR(24) NOT NULL"})
        columns_low = columns_high = 0
        column_assertions = []
        for state in group:
            a = state.obj.attrs
            expect = {"TYPE": "X" if state.aux else "T"}
            if not state.aux and not state.external:
                expect["STATUS"] = "X" if state.pk or state.uniques else ""
                expect["AUDITING"] = {"NONE": "", "CHANGES": "C", "ALL": "A"}[a.get("audit", "NONE")]
                expect["DATACAPTURE"] = "Y" if a.get("data_capture") == "CHANGES" else ""
                expect["APPEND"] = "Y" if a.get("append") == "YES" else "N"
                expect["SPLIT_ROWS"] = "Y" if a.get("volatile") == "VOLATILE" else ""
                expect["CLUSTERTYPE"] = "Y" if a.get("restrict_on_drop") else ""
                expect["TSNAME_EXPLICIT"] = state.tablespace.obj.name.name if state.tablespace is not None else "*IMPLICIT*"
            assertions.append({"catalog": qid, "where": {"NAME": state.obj.name.name}, "equals": expect})
            if state.aux or state.external:
                continue
            declared = list(state.columns.values())
            implicit = 0
            if any(c.type and c.type.family in sq.LOB_FAMILIES for c in declared) and not any(c.type and c.type.family == "ROWID" for c in declared):
                implicit += 1
            if any(c.type and c.type.family == "XML" for c in declared):
                implicit += 1
            columns_low += len(declared)
            columns_high += len(declared) + implicit
            for number, column in enumerate(declared, 1):
                dt = column.type
                expect = {"NAME": column.name, "NULLS": "Y" if column.nullable else "N",
                          "HIDDEN": "P" if column.hidden and not (dt and dt.family == "ROWID") else "R" if column.hidden else "N"}
                if dt is not None and dt.family:
                    expect["COLTYPE"] = "TIMESTZ" if dt.family == "TIMESTAMP" and dt.time_zone else "TIMESTMP" if dt.family == "TIMESTAMP" else COLTYPE[dt.family]
                    if dt.family in ("CHAR", "VARCHAR", "BINARY", "VARBINARY", "GRAPHIC", "VARGRAPHIC", "DECIMAL"):
                        expect["LENGTH"] = dt.length
                    if dt.family in ("SMALLINT", "INTEGER", "BIGINT"):
                        expect["LENGTH"] = {"SMALLINT": 2, "INTEGER": 4, "BIGINT": 8}[dt.family]
                    if dt.family == "DECIMAL":
                        expect["SCALE"] = dt.scale or 0
                elif dt is not None:
                    expect["COLTYPE"] = "DISTINCT"
                code = DEFAULT_CODE.get((column.generated, column.generated_mode or "ALWAYS"))
                if code:
                    expect["DEFAULT"] = code
                elif column.default == "user":
                    expect["DEFAULT"] = "U"
                elif column.default == "current-sqlid":
                    expect["DEFAULT"] = "S"
                elif column.default is None and column.not_null and not column.generated:
                    expect["DEFAULT"] = "N"
                elif column.default in (None, "null") and column.nullable and not column.generated:
                    expect["DEFAULT"] = "Y"
                if column.security_label:
                    expect["DEFAULT"] = "L"
                column_assertions.append({"catalog": f"columns_{n}", "where": {"TBNAME": state.obj.name.name, "COLNO": number}, "equals": expect})
        if columns_high:
            q.add(f"columns_{n}", "SYSIBM.SYSCOLUMNS",
                  ["TBNAME", "COLNO", "NAME", "COLTYPE", "LENGTH", "SCALE", "NULLS", "DEFAULT", "DEFAULTVALUE", "HIDDEN",
                   "FOREIGNKEY", "PERIOD", "PARTKEY_COLSEQ", "PARTKEY_ORDERING", "KEYSEQ", "LENGTH2", "TYPENAME"],
                  ["TBNAME", "COLNO"], both(lambda s, d, schema=schema, tnames=[t.obj.name.name for t in group if not t.aux and not t.external]: f"TBCREATOR = {_literal(s(schema))} AND TBNAME IN ({_in_list(tnames)})"),
                  (columns_low, columns_high))
            assertions.extend(column_assertions)
        fks = [(state, c) for state in group for c in state.fks]
        if fks:
            unnamed = [f"{s.obj.name.name}({', '.join(c.columns)})" for s, c in fks if not c.name]
            q.add(f"relations_{n}", "SYSIBM.SYSRELS",
                  ["TBNAME", "RELNAME", "REFTBNAME", "COLCOUNT", "DELETERULE", "ENFORCED", "CHECKEXISTINGDATA", "PARENT_SCHEMA_MATCH"],
                  ["TBNAME", "RELNAME"], both(lambda s, d, schema=schema, tnames=sorted({st.obj.name.name for st, _ in fks}): f"CREATOR = {_literal(s(schema))} AND TBNAME IN ({_in_list(tnames)})"),
                  len(fks), expressions={"PARENT_SCHEMA_MATCH": {"source": "CASE WHEN REFTBCREATOR IN (" + _in_list({qualified(c.parent, s.schema_default).rpartition('.')[0] for s, c in fks}) + ") THEN 1 ELSE 0 END",
                                                                  "replay": "CASE WHEN REFTBCREATOR IN (" + _in_list({names.schemas.get(p, p) for p in {qualified(c.parent, s.schema_default).rpartition('.')[0] for s, c in fks}}) + ") THEN 1 ELSE 0 END"}},
                  expression_types={"PARENT_SCHEMA_MATCH": "INTEGER NOT NULL"})
            q.add(f"foreign_keys_{n}", "SYSIBM.SYSFOREIGNKEYS", ["TBNAME", "RELNAME", "COLSEQ", "COLNAME", "COLNO"],
                  ["TBNAME", "RELNAME", "COLSEQ"], both(lambda s, d, schema=schema, tnames=sorted({st.obj.name.name for st, _ in fks}): f"CREATOR = {_literal(s(schema))} AND TBNAME IN ({_in_list(tnames)})"),
                  sum(len(c.columns) for _, c in fks))
            for state, c in fks:
                if not c.name:
                    continue
                rule = c.delete_rule or ("RESTRICT" if (c.rules or state.rules) == "DB2" else "NO ACTION")
                assertions.append({"catalog": f"relations_{n}", "where": {"TBNAME": state.obj.name.name, "RELNAME": c.name},
                                   "equals": {"REFTBNAME": c.parent.name, "COLCOUNT": len(c.columns), "DELETERULE": DELETERULE[rule],
                                              "ENFORCED": "Y" if c.enforced else "N", "PARENT_SCHEMA_MATCH": 1}})
                for seq, column in enumerate(c.columns, 1):
                    assertions.append({"catalog": f"foreign_keys_{n}", "where": {"TBNAME": state.obj.name.name, "RELNAME": c.name, "COLSEQ": seq},
                                       "equals": {"COLNAME": column}})
            if unnamed:
                report.add("scope.not-checked", f"Unnamed foreign keys get Db2-generated names, so source/replay RELNAME keys may differ: {', '.join(unnamed[:5])}.", severity="notice")
        checks = [(state, c) for state in group for c in state.checks]
        periods = sum(1 for state in group for p in state.obj.attrs.get("periods", []) if p["name"] == "BUSINESS_TIME")
        if checks:
            q.add(f"checks_{n}", "SYSIBM.SYSCHECKS", ["TBNAME", "CHECKNAME", "CHECKCONDITION", "PERIOD"], ["TBNAME", "CHECKNAME"],
                  both(lambda s, d, schema=schema, tnames=sorted({st.obj.name.name for st, _ in checks}): f"TBOWNER = {_literal(s(schema))} AND TBNAME IN ({_in_list(tnames)})"),
                  (len(checks), len(checks) + periods))
        aux = [s for s in group if s.aux]
        if aux:
            q.add(f"auxrels_{n}", "SYSIBM.SYSAUXRELS", ["TBNAME", "COLNAME", "PARTITION", "AUXTBNAME"], ["AUXTBNAME"],
                  both(lambda s, d, schema=schema, anames=[x.obj.name.name for x in aux]: f"TBOWNER = {_literal(s(schema))} AND AUXTBNAME IN ({_in_list(anames)})"), len(aux))
            for state in aux:
                assertions.append({"catalog": f"auxrels_{n}", "where": {"AUXTBNAME": state.obj.name.name},
                                   "equals": {"TBNAME": state.obj.attrs["base"].name, "COLNAME": state.obj.attrs["column"]}})
    index_groups = defaultdict(list)
    for key, result in report.indexes.items():
        index_groups[key.rpartition(".")[0]].append((key, result))
    for n, (schema, group) in enumerate(sorted(index_groups.items()), 1):
        inames = [r.obj.name.name for _, r in group]
        q.add(f"indexes_{n}", "SYSIBM.SYSINDEXES",
              ["NAME", "TBNAME", "UNIQUERULE", "COLCOUNT", "CLUSTERING", "PADDED", "COMPRESS", "FREEPAGE", "PCTFREE", "GBPCACHE",
               "PGSIZE", "BPOOL", "CLOSERULE", "COPY", "PIECESIZE", "INDEXTYPE", "ERASERULE", "STORTYPE", "PAGENUM"],
              ["NAME"], both(lambda s, d, schema=schema, inames=inames: f"CREATOR = {_literal(s(schema))} AND NAME IN ({_in_list(inames)})"), len(group))
        key_rows, key_names, partitioned_rows, partitioned = 0, [], 0, []
        for key, result in group:
            a = result.obj.attrs
            table = report.tables.get(a.get("_table_key"))
            expect = {"TBNAME": a["table"].name}
            if table is not None and not table.aux and not table.external:
                keys = tuple(k for k, _ in a["keys"])
                parent_keys = {tuple(fk.parent_columns or []) for other in report.tables.values() for fk in other.fks
                               if qualified(fk.parent, other.schema_default) == table.key}
                if a.get("where_not_null"):
                    expect["UNIQUERULE"] = "N"
                elif not a.get("unique"):
                    expect["UNIQUERULE"] = "D"
                elif table.pk and keys == tuple(table.pk.columns):
                    expect["UNIQUERULE"] = "P"
                elif keys in {tuple(u.columns) for u in table.uniques}:
                    expect["UNIQUERULE"] = "R" if keys in parent_keys else "C"
                elif len(keys) == 1 and table.columns.get(keys[0]) is not None and table.columns[keys[0]].generated == "rowid" and table.columns[keys[0]].generated_mode == "BY DEFAULT":
                    expect["UNIQUERULE"] = "G"
                else:
                    expect["UNIQUERULE"] = "U"
                if not a["expression"] and not a["xmlpattern"]:
                    expect["COLCOUNT"] = len(a["keys"]) + len(a["include"])
                    key_rows += len(a["keys"]) + len(a["include"])
                    key_names.append(result.obj.name.name)
                    varying = any(table.columns.get(k) is not None and table.columns[k].type is not None and table.columns[k].type.family in ("VARCHAR", "VARGRAPHIC") for k in keys)
                    if not varying:
                        expect["PADDED"] = ""
                    elif "padded" in a:
                        expect["PADDED"] = "Y" if a["padded"] else "N"
                    for seq, (name, order) in enumerate(a["keys"], 1):
                        assertions.append({"catalog": f"index_keys_{n}", "where": {"IXNAME": result.obj.name.name, "COLSEQ": seq},
                                           "equals": {"COLNAME": name, "ORDERING": {"ASC": "A", "DESC": "D", "RANDOM": "R"}[order or "ASC"]}})
                    for seq, name in enumerate(a["include"], len(a["keys"]) + 1):
                        assertions.append({"catalog": f"index_keys_{n}", "where": {"IXNAME": result.obj.name.name, "COLSEQ": seq},
                                           "equals": {"COLNAME": name, "ORDERING": ""}})
                if a.get("partitioned") and table.partitioned:
                    partitioned.append(result.obj.name.name)
                    partitioned_rows += table.tablespace.obj.attrs.get("numparts", 1)
            expect["CLUSTERING"] = "Y" if a.get("cluster") else "N"
            for attr, field_ in (("freepage", "FREEPAGE"), ("pctfree", "PCTFREE")):
                if attr in a:
                    expect[field_] = a[attr]
            if "compress" in a:
                expect["COMPRESS"] = "Y" if a["compress"] == "YES" else "N"
            if "close" in a:
                expect["CLOSERULE"] = "Y" if a["close"] == "YES" else "N"
            if "copy" in a:
                expect["COPY"] = "Y" if a["copy"] == "YES" else "N"
            if "gbpcache" in a:
                expect["GBPCACHE"] = GBPCACHE.get(a["gbpcache"], a["gbpcache"])
            if a.get("bufferpool"):
                expect["BPOOL"] = a["bufferpool"]
            assertions.append({"catalog": f"indexes_{n}", "where": {"NAME": result.obj.name.name}, "equals": expect})
        if key_rows:
            q.add(f"index_keys_{n}", "SYSIBM.SYSKEYS", ["IXNAME", "COLSEQ", "COLNAME", "COLNO", "ORDERING", "PERIOD"], ["IXNAME", "COLSEQ"],
                  both(lambda s, d, schema=schema, key_names=key_names: f"IXCREATOR = {_literal(s(schema))} AND IXNAME IN ({_in_list(key_names)})"), key_rows)
        if partitioned:
            q.add(f"index_parts_{n}", "SYSIBM.SYSINDEXPART", ["IXNAME", "PARTITION", "FREEPAGE", "PCTFREE", "GBPCACHE", "STORTYPE", "LIMITKEY"],
                  ["IXNAME", "PARTITION"], both(lambda s, d, schema=schema, partitioned=partitioned: f"IXCREATOR = {_literal(s(schema))} AND IXNAME IN ({_in_list(partitioned)})"), partitioned_rows)
    case_object = "database" if created_dbs else "table"
    case_id = f"DB2Z13-{case_object.upper()}-{run}-001"
    contract = {"case_id": case_id, "model": "ddl-bundle", "catalog": q.queries, "assertions": assertions,
                "violated_constraint": None, "statement_terminator": report.options.terminator,
                "scope": "Selected definition fields of objects created by the source script. Implicit objects with generated names, statistics, OBIDs and timestamps are excluded."}
    cleanup = _cleanup(report, names)
    objects = _inventory(report, names)
    name_map = {"schemas": names.schemas, "databases": names.databases, "objects": {o["source"]: o["replay"] for o in objects if o["source"] != o["replay"]}}
    context = (profile or {}).get("product_context")
    if not context:
        raise ValueError("A profile with product_context is required (use qa/profiles/example.json for unverified offline work)")
    statements = [p.statement.sql for p in report.parsed]
    record = {
        "schema_version": "1.0.0", "id": case_id, "title": f"DDL bundle {run}: product extraction round trip",
        "description": "Execute the source script, extract its objects with the administration product, replay the product output under the clean names, and compare catalog definitions.",
        "object": case_object, "category": "round_trip", "status": "design", "product_context": context,
        "source_refs": ["ibm-create-table", "ibm-create-tablespace", "ibm-create-index", "ibm-create-database",
                        "ibm-catalog-systables", "ibm-catalog-syscolumns", "ibm-catalog-sysindexes", "ibm-catalog-systablespace"],
        "variation": {"primary_clause": "table.explicit-elements", "dimensions": [f"objects:{k}={v}" for k, v in sorted(Counter(o["kind"] for o in objects).items())] or ["objects:none"],
                      "explicitness": "not_applicable"},
        "parameters": {"RUN": run, **{f"SCHEMA_{s}": t for s, t in names.schemas.items()}, **{f"DATABASE_{s}": t for s, t in names.databases.items()}},
        "prerequisites": ["Run lint.json's checks again after any edit; the bundle was derived from a lint-clean script.",
                          "Verify function level, APPLCOMPAT, CURRENT RULES, subsystem parameters, buffer pools, storage groups and authority on the target subsystem.",
                          "Every replay schema/database name must be unused; the source names must be unused before setup."],
        "setup_sql": [], "action_sql": statements,
        "expected": {"outcome": "success", "failure_phase": "none", "sqlcode": 0, "sqlstate": "00000",
                     "catalog_assertions": [f"{q_['id']}: rows {q_['min_rows']}..{q_['max_rows']}" for q_ in q.queries],
                     "notes": "Expected success is a design assertion. Catalog equality covers only catalog-contract.json fields."},
        "ofs_validation": {"generation_target": ", ".join(sorted({o['source'] for o in objects if o['kind'] in ('database', 'table')})) or "script objects",
                           "name_map": {**{s: t for s, t in names.schemas.items()}, **{s: t for s, t in names.databases.items()}},
                           "generated_ddl_must_include": [], "generated_ddl_must_exclude": [],
                           "comparison_policy": {"semantic_fields": [f"{q_['id']}.{f}" for q_ in q.queries for f in q_["fields"]],
                                                 "ignored_fields": ["All unselected fields, implicit objects with generated names, OBIDs, timestamps and statistics"],
                                                 "notes": "Apply the name map with the product or an SQL-aware adapter, never blanket text replacement."}},
        "cleanup_sql": cleanup["source"],
        "artifacts": {"catalog_contract": "catalog-contract.json", "source_ddl": "source.sql", "ofs_generated_ddl": "product-generated.sql"},
    }
    files = {
        "source.sql": text,
        "lint.json": json.dumps(report.as_dict(), indent=2) + "\n",
        "coverage.json": json.dumps(coverage(report), indent=2) + "\n",
        "inventory.json": json.dumps({"objects": objects, "implicit_objects_expected": _implicit(report)}, indent=2) + "\n",
        "name-map.json": json.dumps(name_map, indent=2) + "\n",
        "catalog-contract.json": json.dumps(contract, indent=2) + "\n",
        "catalog-source.sql": _sql_file([f"-- result set: {x['id']}\n{x['source_sql']}" for x in q.queries], "Source catalog queries; export each result set as JSON by id."),
        "catalog-replay.sql": _sql_file([f"-- result set: {x['id']}\n{x['replay_sql']}" for x in q.queries], "Replay catalog queries for the clean target names."),
        "cleanup-source.sql": _sql_file(cleanup["source"] + ["COMMIT"], "Destructive. Run only after verifying that this run created every listed object."),
        "cleanup-replay.sql": _sql_file(cleanup["replay"] + ["COMMIT"], "Destructive. Drops the replay copies created from product output."),
        "case.json": json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        "RUN.md": _run_md(run, report, names, cleanup),
    }
    return files


def _wrap(sql, width=72):
    """Break generated SQL after commas or before keywords outside literals so records stay <= width."""
    lines = []
    for line in sql.split("\n"):
        while len(line) > width:
            cut, quote = -1, False
            for i, ch in enumerate(line[:width]):
                if ch == "'":
                    quote = not quote
                elif not quote and ((ch == "," and i + 1 < len(line) and line[i + 1] == " ") or (ch == " " and i > 0)):
                    cut = i + 1
            if cut <= 0:
                break
            lines.append(line[:cut].rstrip())
            line = "  " + line[cut:].lstrip()
        lines.append(line)
    return "\n".join(lines)


def _sql_file(statements, note):
    return "-- " + note + "\n" + "".join(f"\n{_wrap(s)}\n;\n" for s in statements)


def _inventory(report, names):
    objects = []
    for result in report.objects:
        obj = result.obj
        default = result.detail.get("schema_default")
        if obj.kind in ("tablespace", "lob-tablespace"):
            key = f"{obj.attrs.get('database') or 'DSNDB04'}.{obj.name.name}"
            if key not in report.tablespaces:
                continue
            replay = names.tablespace(key)
        elif obj.kind == "database":
            key = obj.name.name
            if key not in report.databases:
                continue
            replay = names.database(key)
        elif obj.kind == "stogroup":
            key = replay = obj.name.name
        else:
            key = qualified(obj.name, default)
            if obj.kind == "index" and key not in report.indexes:
                continue
            if obj.kind in ("table", "auxiliary-table") and key not in report.tables:
                continue
            replay = names.relation(key)
        objects.append({"kind": obj.kind, "source": key, "replay": replay, "statement": result.statement.index,
                        "line": result.statement.line, "checked": obj.kind in KB_OBJECT})
    return objects


def _implicit(report):
    implicit = []
    for key, state in report.tables.items():
        if state.aux or state.external:
            continue
        if state.implicit_space:
            implicit.append({"table": key, "object": "table space", "reason": "IN DATABASE or no IN clause"})
            if state.pk or state.uniques:
                implicit.append({"table": key, "object": "enforcing unique index(es)", "reason": "implicit table space"})
        if any(c.type and c.type.family in sq.LOB_FAMILIES for c in state.columns.values()):
            if not any(c.type and c.type.family == "ROWID" for c in state.columns.values()):
                implicit.append({"table": key, "object": "hidden ROWID column", "reason": "LOB column without an explicit ROWID"})
            if state.implicit_space or state.rules == "STD":
                implicit.append({"table": key, "object": "LOB table space, auxiliary table and auxiliary index", "reason": "eligible implicit LOB creation"})
        if any(c.type and c.type.family == "XML" for c in state.columns.values()):
            implicit.append({"table": key, "object": "XML table space, XML table, DOCID column and indexes", "reason": "XML column"})
    return implicit


def _cleanup(report, names):
    """Ownership-aware drops in reverse dependency order for objects that exist at the end of the script."""
    # RESTRICT ON DROP blocks dropping the table, its table space and its database until it is removed (ibm-alter-table).
    restricted = [key for key, state in report.tables.items() if state.obj.attrs.get("restrict_on_drop")]
    source = [f"ALTER TABLE {key} DROP RESTRICT ON DROP" for key in restricted]
    replay = [f"ALTER TABLE {names.relation(key)} DROP RESTRICT ON DROP" for key in restricted]
    created_dbs = {r.obj.name.name for r in report.objects if r.obj.kind == "database" and r.obj.name.name in report.databases}
    covered_tables = set()
    for key, ts in report.tablespaces.items():
        if ts.database in created_dbs:
            if ts.table:
                covered_tables.add(ts.table)
    handled_spaces = set()
    for result in reversed(report.objects):
        obj = result.obj
        default = result.detail.get("schema_default")
        if obj.kind in NOT_CHECKED_KINDS and obj.kind not in ("trigger",):
            key = qualified(obj.name, default)
            source.append(f"-- review: DROP {obj.kind.upper()} {key} (not derived automatically)")
            replay.append(f"-- review: DROP {obj.kind.upper()} {names.relation(key)} (not derived automatically)")
            continue
        if obj.kind in ("table", "auxiliary-table"):
            key = qualified(obj.name, default)
            state = report.tables.get(key)
            if state is None or key in covered_tables or state.aux:
                continue
            if state.database in created_dbs:
                continue
            if state.tablespace is not None:
                ts_key = state.tablespace.key
                if ts_key not in handled_spaces:
                    handled_spaces.add(ts_key)
                    source.append(f"DROP TABLESPACE {ts_key}")
                    replay.append(f"DROP TABLESPACE {names.tablespace(ts_key)}")
            else:
                source.append(f"DROP TABLE {key}")
                replay.append(f"DROP TABLE {names.relation(key)}")
        elif obj.kind in ("tablespace", "lob-tablespace"):
            key = f"{obj.attrs.get('database') or 'DSNDB04'}.{obj.name.name}"
            ts = report.tablespaces.get(key)
            if ts is None or ts.database in created_dbs or key in handled_spaces:
                continue
            handled_spaces.add(key)
            source.append(f"DROP TABLESPACE {key}")
            replay.append(f"DROP TABLESPACE {names.tablespace(key)}")
    for result in reversed(report.objects):
        obj = result.obj
        if obj.kind == "database" and obj.name.name in created_dbs:
            source.append(f"DROP DATABASE {obj.name.name}")
            replay.append(f"DROP DATABASE {names.database(obj.name.name)}")
    for result in reversed(report.objects):
        obj = result.obj
        if obj.kind == "stogroup" and obj.name.name in report.stogroups:
            source.append(f"DROP STOGROUP {obj.name.name}")
    return {"source": source, "replay": replay}


def _run_md(run, report, names, cleanup):
    return (f"# DDL bundle {run}\n\nStatus: design. Nothing has been executed on Db2 or by the administration product.\n\n"
            f"Outer terminator: `{report.options.terminator}`. `lint.json` passed with {report.counts().get('warning', 0)} warning(s); "
            "review every warning and notice before execution.\n\n"
            "1. Verify the profile (function level, APPLCOMPAT, CURRENT RULES, subsystem parameters, pools, storage groups, authority). "
            "Confirm every source and replay name is unused.\n"
            "2. Run `source.sql` statement by statement. Keep SQLCODE/SQLSTATE per statement. Stop at the first error; a failed setup blocks the case. "
            "Record it: `python3 tools/qa.py record case.json --phase source --result pass --sqlcode 0 --evidence <log>` "
            "(or `--result blocked --note ...`).\n"
            "3. Run `catalog-source.sql`. Export each result set as CSV with its header row, named `<result set id>.csv` "
            "after its `-- result set:` comment, into one directory, then "
            "`python3 tools/qa.py snapshot --contract catalog-contract.json --side source --csv-dir <dir> --out source.json`.\n"
            "4. Extract the objects in `inventory.json` with the administration product, including table spaces, enforcing indexes, "
            "auxiliary objects and dependent objects. Save the raw output as `product-generated.sql`, then record it with "
            "`--phase extraction --product <name> --product-version <version> [--option KEY=VALUE] --evidence product-generated.sql`.\n"
            "5. Offline first check: `python3 tools/ddl.py diff source.sql product-generated.sql --map name-map.json --text` "
            "(map only if the product already applied the replay names). Investigate every `different` entry.\n"
            f"6. Apply the replay names ({', '.join(f'{k}->{v}' for k, v in {**names.schemas, **names.databases}.items())}) through the product or an SQL-aware adapter. "
            "Never use blanket text replacement. Run the product output in the clean target and record `--phase replay`.\n"
            "7. Run `catalog-replay.sql`, export it the same way and convert it with `--side replay`. Then "
            "`python3 tools/qa.py record case.json --phase comparison --source source.json --replay replay.json` runs the comparison "
            "and records its result; `python3 tools/qa.py status .` shows the case status.\n"
            "8. Keep all evidence, then run `cleanup-replay.sql` and `cleanup-source.sql` only for objects this run created. "
            "Lines starting with `-- review:` need a manual decision.\n")


def coverage_text(result):
    lines = ["Objects: " + ", ".join(f"{k}={v}" for k, v in sorted(result["objects"].items()))]
    for kind, shape in result["shapes"].items():
        lines.append(f"  {kind}: {shape['objects']} object(s), {shape['distinct_option_signatures']} distinct option signature(s)")
    lines.append("KB clause coverage (explicitly exercised / normalized):")
    for kind, data in result["kb_clause_coverage"].items():
        lines.append(f"  {kind}: {data['ratio']}; never exercised: {', '.join(data['unexercised']) or 'none'}")
    lines.append("Clause values (<omitted> = default left to Db2):")
    for feature, values in result["features"].items():
        lines.append(f"  {feature}: " + ", ".join(f"{k}×{v}" for k, v in sorted(values.items(), key=lambda kv: -kv[1])))
    lines.append("Facets:")
    for facet, values in result["facets"].items():
        lines.append(f"  {facet}: " + ", ".join(f"{k}×{v}" for k, v in sorted(values.items(), key=lambda kv: -kv[1])))
    if "baseline" in result:
        b = result["baseline"]
        lines.append(f"Baseline {b['id']}: {b['met']}/{b['total']} requirements met.")
        for item in b["unmet"]:
            lines.append(f"  UNMET {item['feature']}: {item['detail']} (observed: {', '.join(item['observed']) or 'none'})")
    lines.append(result["scope"])
    return "\n".join(lines)
