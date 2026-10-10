"""Repository locations shared by the command-line tools and tests.

kb/        IBM-derived reference: chapters, source manifest, normalized JSON.
qa/        Inputs the tools read: models, profiles, schemas, variety baselines.
examples/  Worked examples, request examples, domain schemas, workloads.
docs/      Workflows, command reference, roadmap and dated review history.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"

KB = ROOT / "kb"
KB_DATA = KB / "data"
CREATE_DDL = KB_DATA / "db2z13-create-ddl.json"
TRIGGER_BODY = KB_DATA / "db2z13-trigger-body-statements.json"
DDL_CHECKS = KB_DATA / "db2z13-ddl-checks.json"
FUNCTION_LEVELS = KB_DATA / "db2z13-function-levels.json"
CATALOG_COLUMNS = KB_DATA / "db2z13-catalog-columns.json"
CATALOG_VERIFICATION = KB / "catalog-verification.sql"
SOURCES = KB / "sources.md"

QA = ROOT / "qa"
MODELS = QA / "models"
EXAMPLE_PROFILE = QA / "profiles" / "example.json"
VARIETY_BASELINE = QA / "variety-baseline.json"
REQUEST_SCHEMA = QA / "schemas" / "request.schema.json"
CASE_SCHEMA = QA / "schemas" / "test-case.schema.json"
AGENT = QA / "legacy-agent"
OBJECT_REGISTRY = AGENT / "object-registry.json"
TEMPLATES = AGENT / "templates"

EXAMPLES = ROOT / "examples"
REQUEST_EXAMPLES = EXAMPLES / "requests"
VARIED_SCHEMA = EXAMPLES / "varied-schema.sql"
SAMPLE_CASE = EXAMPLES / "sample-case.json"
WORKLOAD_1000 = EXAMPLES / "workloads" / "1000-table" / "create-1000-table-qa-workload.sql"
DOMAINS = EXAMPLES / "domains"

DOCS = ROOT / "docs"


def rel(path: Path) -> str:
    """Repository-relative POSIX path, for messages and recorded artifacts."""
    return path.resolve().relative_to(ROOT).as_posix()
