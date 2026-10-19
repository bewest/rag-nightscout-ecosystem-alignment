"""The developer guides (queue item SPEC-DEV-GUIDES).

docs/30-design/platform/guides/*.md walk a controller developer through the platform specifications
step by step. Each step table has `rule` and `case` columns. These tests fail when a step names no
rule or no case, a rule cited does not exist in a specification, a case cited does not exist, or an
example differs from the case it was copied from. Until a hub implements the specifications the
guides are checked against the cases, not run against a hub.
"""
import re

import pytest

from nsschema import corpus, guide_examples

ROOT = corpus.repo_root()
SPEC_DIR = ROOT / "docs" / "30-design" / "platform" / "spec"
GUIDES = guide_examples.pages()
SPECS = {p.stem: p.read_text() for p in SPEC_DIR.glob("*.md")}
RULES = {m.group(1)
         for text in SPECS.values()
         for m in re.finditer(r"^\| \*?\*?([A-Z]{1,3}[0-9]+[a-z]?)\*?\*? \|", text, re.M)}
DECISIONS = {"D7", "D13", "D14", "D15", "D16", "D17", "D18", "D19", "D20"}
SECTION = re.compile(r"([a-z-]+) §(\d+)(?:\.(\d+))?")


def _section_exists(ref):
    m = SECTION.fullmatch(ref)
    if not m or m.group(1) not in SPECS:
        return False
    heading = m.group(2) + ("." + m.group(3) if m.group(3) else ".")
    return bool(re.search(r"^#{2,3} %s " % re.escape(heading), SPECS[m.group(1)], re.M))


def _rule_ok(ref):
    return ref in RULES or ref in DECISIONS or _section_exists(ref)


def steps(text):
    """(rule cell, case cell, line) for each row of every table with rule and case columns."""
    out = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        head = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if lines[i].startswith("|") and "rule" in head and "case" in head:
            r, c = head.index("rule"), head.index("case")
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [x.strip() for x in lines[i].strip().strip("|").split("|")]
                out.append((cells[r], cells[c], i + 1))
                i += 1
        i += 1
    return out


def test_guides_exist():
    assert {p.stem for p in GUIDES} >= {"add-a-setting", "new-controller"}


@pytest.mark.parametrize("path", GUIDES, ids=lambda p: p.stem)
def test_steps_name_rules_and_cases(path):
    rows = steps(path.read_text())
    assert len(rows) >= 5, path
    for rule, case, line in rows:
        refs = [x.strip() for x in rule.split(",") if x.strip()]
        cases = re.findall(r"`([^`]+\.yaml)`", case)
        assert refs and cases, (path.name, line, "a step names a rule and a case")
        for ref in refs:
            assert _rule_ok(ref), (path.name, line, ref)
        for c in cases:
            assert guide_examples.case_path(c).exists(), (path.name, line, c)


@pytest.mark.parametrize("path", GUIDES, ids=lambda p: p.stem)
def test_every_case_named_exists(path):
    # Outside the step tables too: every backticked case path resolves.
    text = path.read_text()
    for c in re.findall(r"`((?:specs/)?[a-z0-9-]+(?:/[a-z0-9.-]+)*\.yaml)`", text):
        assert guide_examples.case_path(c).exists(), (path.name, c)


@pytest.mark.parametrize("path", GUIDES, ids=lambda p: p.stem)
def test_examples_are_generated(path):
    page = path.read_text()
    assert guide_examples.render(page) == page, path.name


@pytest.mark.parametrize("path", GUIDES, ids=lambda p: p.stem)
def test_older_apps_are_answered_from_the_table(path):
    # Each guide says what an older app sees, from the compatibility page.
    assert "../spec/compatibility.md" in path.read_text(), path.name


# The amendment-narration patterns of tools/queue/gates/platform-spec.js, for the guides.
NARRATION = [
    r"(?i)decided otherwise",
    r"(?i)\(withdrawn\b|\b(?:was|were|been|is now) withdrawn\b",
    r"(?i)\((?:changed|corrected|amended|added|removed) 20\d\d-\d\d-\d\d",
    r"(?i)\buntil 20\d\d-\d\d-\d\d",
    r"(?i)\bno longer (?:applies|apply|open)\b",
    r"(?i)\ban earlier (?:draft|version)\b",
]


@pytest.mark.parametrize("path", GUIDES, ids=lambda p: p.stem)
def test_header_and_no_narration(path):
    text = path.read_text()
    assert re.search(r"^\*Contributor-facing\. Living guide", text, re.M), path.name
    for pattern in NARRATION:
        assert not re.search(pattern, text), (path.name, pattern)


def test_index_links_every_guide():
    index = (ROOT / "docs" / "30-design" / "platform" / "README.md").read_text()
    for path in GUIDES:
        assert "guides/%s.md" % path.stem in index, path.name
