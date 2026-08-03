# Syntax-summary notation

The object chapters restate IBM syntax diagrams in compact EBNF-like text. This notation is for test design; it is not an executable grammar.

| Notation | Meaning |
|---|---|
| uppercase words | SQL keywords |
| `<name>` | a value supplied by the author |
| `[ item ]` | optional item |
| `{ a \| b }` | choose one alternative |
| `( item )...` | repeat one or more times |
| `DEFAULT => value` | effective default documented by IBM |
| `SUBSYSTEM => name` | omission is resolved by a subsystem parameter |
| `FL nnn` | function-level gate |
| `APPLCOMPAT >= level` | application-compatibility rule |

Comma placement and grouping are significant. The summaries show IBM's preferred syntax. Accepted compatibility synonyms are listed separately so they can be tested without making deprecated spellings the normal template.

The normalized JSON assigns every clause a stable lowercase ID such as `maxpartitions` or `where-not-null`. Rules refer to those IDs, use source IDs from [sources.md](sources.md), and carry tags such as `boundary`, `implicit`, `compatibility`, `storage`, or `negative`.

## Source-of-truth order

Use the following resolution order when authoring or triaging a case:

1. IBM's statement syntax diagram and its diagram notes
2. IBM's clause descriptions and statement notes
3. IBM's concept/administration topic for object behavior
4. the prose chapter in this repository
5. the normalized JSON

This order matters because a visual grammar can allow a token whose prose restricts it to one object subtype, such as `GBPCACHE SYSTEM`, which is meaningful for LOB table spaces and not an ordinary base table-space choice.
