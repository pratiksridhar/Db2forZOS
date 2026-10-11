# Test map

Install the development environment first (see the [command reference](../docs/commands.md#repository-checks)).
Run everything with `.venv/bin/python -m unittest discover -s tests -v`, or one file from
the repository root with `.venv/bin/python -m unittest tests.<module> -v`.

| Module | Guards |
|---|---|
| [test_db2check](test_db2check.py) | Every checker rule has a triggering fixture; parser, coverage, diff and bundle behavior |
| [test_ddl](test_ddl.py) | `ddl.py` request plans and command behavior |
| [test_kb](test_kb.py) | KB IDs and sources, Markdown links, templates, `kb.py` and `agent.py` smoke checks |
| [test_layout](test_layout.py) | Every document is reachable from the README; clean root; shared locations in `tools/paths.py` |
| [test_qa](test_qa.py) | Modeled-case selection, validation, campaign build and catalog comparison |
| [test_relational](test_relational.py) | Parent/child model, dependency order and foreign-key catalog checks |
| [test_routine_models](test_routine_models.py) | Trigger and native-procedure models |
| [test_sqltext](test_sqltext.py) | SQL text framing, terminators and selection boundaries |
| [test_supply_chain_logistics_schema](test_supply_chain_logistics_schema.py) | The supply-chain example generator's topology and static checks |

A new checker rule needs a fixture in `test_db2check`; see the [tool code map](../tools/README.md#add-a-checker-rule).

`fixtures/` holds test inputs. `varied-schema-regenerated.sql` imitates extraction-tool
formatting of the exemplar; it is not product evidence. `test_db2check` requires the
diff to accept it unchanged and to report every defect seeded into it.
