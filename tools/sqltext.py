"""Lossless SQL framing checks, deliberately not a Db2 grammar or SQL parser."""

from __future__ import annotations

import hashlib


def inspect_sql(sql):
    """Locate code punctuation without treating literals/comments as SQL syntax."""
    if not isinstance(sql, str) or not sql.strip() or "\x00" in sql:
        raise ValueError("SQL must be nonempty text without NUL characters")
    i, depth, quote = 0, 0, None
    code = []
    nested = False
    while i < len(sql):
        char, pair = sql[i], sql[i:i + 2]
        if depth:
            if pair == "/*":
                depth += 1
                nested = True
                i += 2
            elif pair == "*/":
                depth -= 1
                i += 2
            else:
                i += 1
        elif quote:
            if char == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    i += 2
                else:
                    quote = None
                    i += 1
            else:
                i += 1
        elif pair == "--":
            while i < len(sql) and sql[i] not in "\r\n":
                i += 1
        elif pair == "/*":
            depth = 1
            i += 2
        elif pair == "*/":
            raise ValueError("Unmatched bracketed-comment close")
        elif char in "'\"":
            code.append((i, char))
            quote = char
            i += 1
        else:
            if not char.isspace():
                code.append((i, char))
            i += 1
    if depth or quote:
        raise ValueError("Unclosed SQL comment, string literal, or delimited identifier")
    if not code:
        raise ValueError("SQL contains only comments")
    lines = sql.splitlines()
    return {
        "semicolon_positions": [i for i, c in code if c == ";"],
        "last_code_character": code[-1][1],
        "nested_comments": nested,
        "characters": len(sql),
        "utf8_bytes": len(sql.encode("utf-8")),
        "lines": len(lines),
        "maximum_line_characters": max(map(len, lines)),
        "sha256_utf8": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
    }


def validate_statement(sql, kind="sql", terminator=";"):
    if kind not in {"sql", "sql_pl"}:
        raise ValueError("Statement kind must be sql or sql_pl")
    if terminator not in {";", "@", "#", "!"}:
        raise ValueError("Supported outer terminators: ; @ # !")
    info = inspect_sql(sql)
    if info["nested_comments"]:
        raise ValueError("Nested comments are outside the portable SQL-processor subset")
    if kind == "sql" and info["semicolon_positions"]:
        raise ValueError("Ordinary SQL nodes require one unterminated statement")
    if kind == "sql_pl":
        if terminator == ";":
            raise ValueError("SQL PL requires an alternate outer terminator")
        if info["last_code_character"] == ";":
            raise ValueError("Do not terminate the outermost SQL PL statement inside a node")
    # Some processors inspect raw input, so keep alternate delimiters out of text too.
    if terminator != ";" and terminator in sql:
        raise ValueError("Outer terminator occurs inside statement text; choose another terminator")
    return info


def emit_sql(statements, note="", terminator=";"):
    header = ("-- " + note + "\n") if note else ""
    if terminator != ";":
        header += f"-- Outer terminator: {terminator}. Configure your SQL processor before submitting.\n"
    chunks = []
    for sql in statements:
        validate_statement(sql, "sql_pl" if terminator != ";" else "sql", terminator)
        # A separate line prevents a trailing -- comment from swallowing the delimiter.
        chunks.append(sql + "\n" + terminator)
    return header + "\n\n".join(chunks) + "\n"
