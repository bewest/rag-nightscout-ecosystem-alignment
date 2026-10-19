"""The app compatibility table (queue item SPEC-COMPAT-APPS).

specs/sync/compat/*.yaml says, per app and per layer, what the app does today and what it sees
from a hub that implements the platform specifications without the app changing. These tests hold
the data to its sources and to the specifications: every app the consumer-impact survey read has an
entry, every source file exists, every layer has a verdict and both cells, every rule cited exists,
an `affected` cell names the rule that changes the answer, and the page's tables are generated.
"""
import re

import pytest

from nsschema import compat_tables, corpus

ROOT = corpus.repo_root()
SPEC_DIR = ROOT / "docs" / "30-design" / "platform" / "spec"
CLIENTS = ROOT / "reports" / "consumer-impact-15.0.9" / "clients"
ENTRIES = compat_tables.load()
BY_APP = {e["app"]: e for e in ENTRIES}
KINDS = ("controller", "uploader", "follower", "reader", "hub", "tool")
VERDICTS = ("unchanged", "gains", "opt-in", "affected", "none")
SPECS = {p.stem: p.read_text() for p in SPEC_DIR.glob("*.md") if p.stem != "compatibility"}
RULES = {m.group(1)
         for text in SPECS.values()
         for m in re.finditer(r"^\| \*?\*?([A-Z]{1,3}[0-9]+[a-z]?)\*?\*? \|", text, re.M)}
DECISIONS = {"D7", "D13", "D14", "D15", "D16", "D17", "D18", "D19", "D20"}


def _section(ref):
    m = re.fullmatch(r"([a-z-]+) §(\d+)", ref)
    return bool(m and m.group(1) in SPECS
                and re.search(r"^## %s\. " % m.group(2), SPECS[m.group(1)], re.M))


def test_apps_are_unique():
    assert len(BY_APP) == len(ENTRIES)


def test_every_surveyed_client_has_an_entry():
    # Each per-client file of the consumer-impact survey is the source of some entry.
    cited = {e.get("source") for e in ENTRIES}
    for path in sorted(CLIENTS.glob("*/*.md")):
        if path.name == "summary.md":
            continue
        rel = str(path.relative_to(ROOT))
        assert rel in cited, rel


def test_what_is_not_read_is_listed():
    assert any(e["kind"] == "tool" and e["app"] == "Not read" for e in ENTRIES)


@pytest.mark.parametrize("app", sorted(BY_APP))
def test_entry(app):
    e = BY_APP[app]
    assert e["kind"] in KINDS, app
    assert e.get("ref"), app
    if e["app"] != "Not read":
        assert (ROOT / e["source"]).exists(), (app, e.get("source"))
    assert set(e["layers"]) == set(compat_tables.LAYERS), app
    for layer, c in e["layers"].items():
        assert c["verdict"] in VERDICTS, (app, layer)
        assert str(c.get("today", "")).strip() and str(c.get("newer", "")).strip(), (app, layer)
        for ref in c.get("rules") or []:
            assert ref in RULES or ref in DECISIONS or _section(ref), (app, layer, ref)
        if c["verdict"] in ("gains", "affected", "opt-in"):
            assert c.get("rules"), (app, layer, "a gains, opt-in or affected cell names its rule")


def test_page_tables_are_generated():
    page = compat_tables.PAGE.read_text()
    assert compat_tables.render(page, ENTRIES) == page


def test_page_lists_every_affected_cell():
    # §5 of the page names every app and layer whose answer changes.
    page = compat_tables.PAGE.read_text()
    found = page[page.index("## 5. "):page.index("## 6. ")]
    for e in ENTRIES:
        for layer, c in e["layers"].items():
            if c["verdict"] == "affected":
                assert e["app"] in found and layer in found, (e["app"], layer)
