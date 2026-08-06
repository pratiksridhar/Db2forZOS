# Agent task protocol

## Generate a positive case

Input example:

```json
{
  "object": "trigger",
  "recipe": "trigger_advanced_after_ddl_create_table_index_view",
  "environment": "db2z13_fl509_default",
  "case_id": "DB2Z13-TRIGGER-BODY-DDL-001"
}
```

Agent steps:

1. Read `kb/agent/object-registry.json`; refuse or mark scaffolded objects whose
   `status` is `extension_candidate` unless the user explicitly accepts design
   scaffolds.
2. Read `kb/agent/specs/<object>.json` and follow `generation_flow`.
3. Resolve `fixtures` listed by the recipe and confirm their
   `provides_capabilities` satisfy the recipe's `requires_capabilities`.
4. Read `kb/agent/rules/<object>.json`; validate the selected dimensions.
5. Read the template manifest next to the SQL template and fill every
   `required_token`.
6. Emit setup SQL, action SQL, expected catalog/behavior assertions, cleanup SQL,
   and source/rule references into a test-case JSON record.
7. If the object or recipe is an `extension_candidate`, set `status: design` and
   add a note that IBM normalization is pending.

## Generate negative companions

For each selected positive recipe, inspect `negative_companions` and structured
rules with `negative_case: true`. Generate only one primary violation per case
and set `expected.failure_phase` from the rule/recipe.

## Compose object stacks

Prefer capabilities over object names. For example, an INSTEAD OF trigger needs
`trigger_subject_instead_of`, which is provided by an eligible view fixture. That
view fixture needs `updatable_source`, which can be provided by a simple base
 table fixture.
