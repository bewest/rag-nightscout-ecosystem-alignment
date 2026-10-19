"""The platform specifications' control-loop analysis (queue item SPEC-STPA-PLATFORM).

specs/sync/stpa/platform-control-loops.yaml lists each loop's control actions and feedback, and
each unsafe control action with the hazards it leads to and what prevents it. These tests hold the
analysis to the specifications: every rule or section it cites exists, every case it cites exists
and, where the case names its rules, is about one of the cited rules; every control action is
considered under each STPA type; a gap points at an open item the specification carries; and the
analysis page lists exactly the entries in the file.
"""
import re

import pytest
import yaml

from nsschema import corpus, stpa_tables

ROOT = corpus.repo_root()
SPEC_DIR = ROOT / "docs" / "30-design" / "platform" / "spec"
CASES_DIR = ROOT / "specs" / "sync" / "conformance"
STPA = yaml.safe_load((ROOT / "specs" / "sync" / "stpa" / "platform-control-loops.yaml").read_text())
PAGE = (SPEC_DIR / "control-loops.md").read_text()

ACTION_TYPES = ("provided", "not-provided", "timing", "duration")
FEEDBACK_TYPES = ("incorrect", "absent", "delayed")
STATUSES = ("covered", "uncased", "controller", "gap")
SEVERITIES = ("S1", "S2", "S3", "S4")

# The specifications the analysis cites; never the analysis page itself.
SPECS = {p.stem: p.read_text() for p in SPEC_DIR.glob("*.md") if p.stem != "control-loops"}
RULES = {m.group(1)
         for text in SPECS.values()
         for m in re.finditer(r"^\| \*?\*?([A-Z]{1,3}[0-9]+[a-z]?)\*?\*? \|", text, re.M)}
DECISIONS = {"D18", "D19", "D20"}

ACTIONS = {}
for loop in STPA["loops"].values():
    for aid in loop.get("actions", {}):
        ACTIONS[aid] = ACTION_TYPES
    for fid in loop.get("feedback", {}):
        ACTIONS[fid] = FEEDBACK_TYPES

ENTRIES = {u["id"]: u for u in STPA["ucas"]}
FAMILIES = r"UCA-(?:CMD|PROP|ROUTE|SYNC-STORE|SYNC-SERVE|SYNC-DL|DEF|AUTH|PLAN)|FB-(?:CMD|STATE|PLAN)"


def _heading(ref):
    """`commands §9` -> the heading `## 9. ...` of spec/commands.md, or None."""
    m = re.fullmatch(r"([a-z-]+) §(\d+)", ref)
    if not m or m.group(1) not in SPECS:
        return None
    h = re.search(r"^## %s\. (.*)$" % m.group(2), SPECS[m.group(1)], re.M)
    return h.group(1) if h else None


def _section(ref):
    return _heading(ref) is not None


def _section_text(ref):
    """The text of `<spec> §N`, from its heading to the next `## `."""
    spec, n = ref.split(" §")
    text = SPECS[spec]
    start = re.search(r"^## %s\. " % n, text, re.M).start()
    end = re.search(r"^## ", text[start + 3:], re.M)
    return text[start:start + 3 + end.start()] if end else text[start:]


def _constraint_exists(ref):
    return ref in RULES or ref in DECISIONS or _section(ref)


def _case(ref):
    p = CASES_DIR / ("%s.yaml" % ref)
    return yaml.safe_load(p.read_text()) if p.exists() else None


def _check_exists(ref):
    path, _, name = ref.partition("::")
    p = ROOT / path
    return p.exists() and re.search(r"^def %s\(" % re.escape(name), p.read_text(), re.M) is not None


def test_ids_are_unique():
    assert len(ENTRIES) == len(STPA["ucas"])


def test_hazards_name_losses_and_are_used():
    used = {h for u in STPA["ucas"] for h in u["hazards"]}
    for hid, hazard in STPA["hazards"].items():
        assert set(hazard["losses"]) <= set(STPA["losses"]), hid
        assert hid in used, hid


def test_every_loop_cites_sections_that_exist():
    for name, loop in STPA["loops"].items():
        for ref in loop["specs"]:
            assert _section(ref), (name, ref)


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_every_type_is_considered(action):
    found = {u["type"] for u in STPA["ucas"] if u["action"] == action}
    considered = set(STPA["considered"].get(action, {}))
    assert found, action
    assert found | considered == set(ACTIONS[action]), (action, found, considered)
    assert not found & considered, (action, found & considered)


def test_considered_names_known_actions():
    assert set(STPA["considered"]) <= set(ACTIONS)


@pytest.mark.parametrize("uid", sorted(ENTRIES))
def test_entry(uid):
    u = ENTRIES[uid]
    assert u["action"] in ACTIONS, uid
    assert u["type"] in ACTIONS[u["action"]], uid
    assert u["hazards"] and set(u["hazards"]) <= set(STPA["hazards"]), uid
    assert u["severity"] in SEVERITIES, uid
    assert u["status"] in STATUSES, uid
    assert u["constraints"], uid
    for ref in u["constraints"]:
        assert _constraint_exists(ref), (uid, ref)
    if u["status"] == "covered":
        assert u.get("verification"), uid
    else:
        assert not u.get("verification"), uid
    if u["status"] in ("gap", "uncased"):
        assert (_heading(u["open"]) or "").startswith("Open"), (uid, u.get("open"))
    if u["status"] == "controller":
        assert u.get("evidence"), uid


@pytest.mark.parametrize("uid", sorted(u for u in ENTRIES if ENTRIES[u].get("verification")))
def test_verification_exists_and_is_about_the_rule(uid):
    u = ENTRIES[uid]
    rules = {c for c in u["constraints"] if c in RULES}
    for ref in u["verification"]:
        if "::" in ref:
            assert _check_exists(ref), (uid, ref)
            continue
        case = _case(ref)
        assert case is not None, (uid, ref)
        if case.get("rules") and rules:
            assert rules & set(case["rules"]), (uid, ref, case["rules"])


def test_gaps_are_listed_in_the_open_items():
    # A gap names an open item, and that Open section names the entry, so a reader of the
    # specification finds it without the analysis.
    for uid, u in ENTRIES.items():
        if u["status"] in ("gap", "uncased"):
            assert re.search(r"\b%s\b" % re.escape(uid), _section_text(u["open"])), (uid, u["open"])


def test_page_lists_exactly_the_entries():
    # The ecosystem's earlier UCA-BOLUS, UCA-CARB, UCA-REMOTE and UCA-SYNC ids may be cited too.
    on_page = set(re.findall(r"\b((?:%s)-\d{3})\b" % FAMILIES, PAGE))
    assert on_page == set(ENTRIES), (sorted(on_page - set(ENTRIES)), sorted(set(ENTRIES) - on_page))


def test_page_tables_are_generated():
    # Every column of every row in §4 is the file's (python3 -m tools.nsschema.stpa_tables).
    assert stpa_tables.render(PAGE, STPA) == PAGE


def test_references_in_reasons_and_notes_exist():
    texts = [r for reasons in STPA["considered"].values() for r in reasons.values()]
    texts += [u.get("note", "") + u.get("evidence", "") for u in STPA["ucas"]]
    for text in texts:
        for ref in re.findall(r"\b((?:%s)-\d{3})\b" % FAMILIES, text):
            assert ref in ENTRIES, (ref, text)


def test_status_counts_match_the_page():
    counts = {s: sum(1 for u in ENTRIES.values() if u["status"] == s) for s in STATUSES}
    line = re.search(r"^Status: .*?(?=\n\n)", PAGE, re.M | re.S).group(0).replace("\n", " ")
    want = ("Of %d entries, %d are covered by a rule and a case, %d are the controller's "
            "responsibility (D18), %d have a rule and no case, and %d are gaps"
            % (len(ENTRIES), counts["covered"], counts["controller"], counts["uncased"], counts["gap"]))
    assert want in line, line


def test_findings_counts_match_the_file():
    counts = {s: sum(1 for u in ENTRIES.values() if u["status"] == s) for s in STATUSES}
    found = PAGE[PAGE.index("## 6. "):PAGE.index("## 7. ")]
    assert re.search(r"^%d gaps, " % counts["gap"], found, re.M), counts
    assert re.search(r"^%d rules have no case" % counts["uncased"], found, re.M), counts
    assert re.search(r"^%d entries are the controller's" % counts["controller"], found, re.M), counts
    for status in ("gap", "uncased", "controller"):
        for uid, u in ENTRIES.items():
            if u["status"] == status:
                assert uid in found, uid
