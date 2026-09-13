# Agent-first DDL generation layer

For executable campaigns, start with [the campaign guide](../campaigns/README.md)
and `python3 tools/qa.py context <object>`. This directory retains the broader
planning recipes and scaffolds; its `agent_ready_from_normalized_kb` labels describe
authoring readiness, not successful compilation or execution on Db2.

This directory is the machine-oriented layer above the IBM-derived Db2 for z/OS
knowledge base. The files here tell an AI agent how to plan, compose, and verify
DDL test cases without scraping long prose chapters.

Use this layer as a planner, not as a replacement for IBM-derived truth:

1. Load `object-registry.json` to identify whether an object is normalized or an
   `extension_candidate` scaffold.
2. Load `dependency-graph.json` to resolve required capabilities and create/drop
   ordering.
3. Load `specs/<object>.json` for the generation flow and required rule sets.
4. Load `dimensions/<object>.json` to choose systematic variations.
5. Load `rules/<object>.json` to validate positive and negative combinations.
6. Choose a recipe from `recipes/<object>/` and its fixtures.
7. Fill the referenced SQL template and emit a durable JSON test case conforming
   to `kb/data/test-case.schema.json`.
8. Keep generated cases in `status: design` until executed on a recorded Db2
   subsystem and validated with catalog/behavior assertions.

`view` is included as an `extension_candidate_agent_scaffold` because future test
generation should cover views. Do not treat view syntax as normalized KB truth
until `kb/objects/view.md`, source IDs, and normalized JSON rules are added.
