from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
DOC_TREES = ("kb", "docs", "qa", "examples", "tools", "tests")
ROOT_FILES = {"README.md", "AGENTS.md", "requirements-dev.txt"}


def markdown_files() -> set[Path]:
    found = {ROOT / "README.md", ROOT / "AGENTS.md"}
    for top in DOC_TREES:
        found.update((ROOT / top).rglob("*.md"))
    return found


def linked(path: Path) -> set[Path]:
    targets = set()
    for target in LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        resolved = (path.parent / target.split("#", 1)[0]).resolve()
        if resolved.is_dir():
            if (resolved / "README.md").is_file():
                targets.add(resolved / "README.md")
        elif resolved.suffix == ".md":
            targets.add(resolved)
    return targets


class RepositoryLayoutTests(unittest.TestCase):
    def test_every_markdown_document_is_reachable_from_readme(self) -> None:
        seen, queue = set(), [ROOT / "README.md", ROOT / "AGENTS.md"]
        while queue:
            path = queue.pop().resolve()
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            queue.extend(linked(path))
        orphans = sorted(p.relative_to(ROOT).as_posix() for p in markdown_files() if p.resolve() not in seen)
        self.assertEqual([], orphans, "link these documents from README.md or a document it reaches")

    def test_repository_root_holds_no_artifacts(self) -> None:
        stray = sorted(p.name for p in ROOT.iterdir() if p.is_file() and not p.name.startswith(".") and p.name not in ROOT_FILES)
        self.assertEqual([], stray, "put SQL under generated/<id>/ or examples/, prose under docs/")

    def test_shared_locations_exist(self) -> None:
        for name, value in vars(paths).items():
            if isinstance(value, Path):
                with self.subTest(name=name):
                    self.assertTrue(value.exists(), f"paths.{name} -> {value}")

    def test_code_uses_shared_locations(self) -> None:
        # Tools and tests resolve repository data through tools/paths.py, so a move is a one-line change.
        pattern = re.compile(r"""ROOT\s*/\s*["'](kb|qa|examples|docs)\b""")
        for path in [*(ROOT / "tools").glob("*.py"), *(ROOT / "tests").glob("*.py")]:
            if path.name == "paths.py":
                continue
            with self.subTest(path=path.name):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), path.name)


if __name__ == "__main__":
    unittest.main()
