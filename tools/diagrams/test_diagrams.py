"""The committed figures under docs/30-design/platform/diagrams/ are what tools/diagrams generates.

  python3 -m pytest tools/diagrams/test_diagrams.py -q

test_committed_svgs_are_generated regenerates every figure and fails naming each one that differs.
The tamper tests are its controls: one input changed in a temporary copy must make exactly the
figure drawn from it differ, so the comparison is shown to see each source.
"""
import json
import re
import shutil
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import active_state_rules  # noqa: E402
import build  # noqa: E402
import end_encoding  # noqa: E402
import hub_active_state  # noqa: E402
from svgkit import OUT  # noqa: E402


def stale_against_committed():
    return [n for n, t in build.generate().items()
            if not (OUT / n).exists() or (OUT / n).read_text() != t]


def test_committed_svgs_are_generated():
    stale = stale_against_committed()
    assert not stale, f"stale figures (run make diagrams-svg): {stale}"


def test_no_orphan_svgs():
    made = set(build.generate())
    ours = {p.name for p in OUT.glob("*.svg")
            if p.name.startswith(("hub-active-state-", "end-encoding-", "active-state-"))}
    assert ours <= made, sorted(ours - made)


def test_every_svg_has_title_and_desc():
    for name, text in build.generate().items():
        assert re.search(r"<title>[^<]+</title>", text), name
        assert re.search(r"<desc>[^<]+</desc>", text), name


def test_generation_is_deterministic():
    assert build.generate() == build.generate()


def test_control_tampered_lab_result(tmp_path, monkeypatch):
    crm = json.loads(hub_active_state.INPUTS[1].read_text())
    case = next(c for c in crm["cases"] if c["id"] == "c4-ps-timed-after-permanent")
    case["queries"][2]["answers"]["profile"]["key"] = "Default basal=1.100"
    p = tmp_path / "crm.json"
    p.write_text(json.dumps(crm))
    inputs = list(hub_active_state.INPUTS)
    inputs[1] = p
    monkeypatch.setattr(hub_active_state, "INPUTS", inputs)
    assert stale_against_committed() == ["hub-active-state-devicestatus-profile.svg"]


def test_control_tampered_registration(tmp_path, monkeypatch):
    reg = tmp_path / "registrations"
    shutil.copytree(end_encoding.REG, reg)
    trio = yaml.safe_load((reg / "trio.yaml").read_text())
    trio["spec"]["stateSpans"][1]["wire"]["endedEncoding"] = "amend-duration"
    (reg / "trio.yaml").write_text(yaml.safe_dump(trio, sort_keys=False))
    monkeypatch.setattr(end_encoding, "REG", reg)
    assert stale_against_committed() == ["end-encoding-trio.svg"]


def test_control_tampered_conformance_case(tmp_path, monkeypatch):
    cases = tmp_path / "active-state"
    shutil.copytree(active_state_rules.CASES, cases)
    f = cases / "overlay-returns-to-open-ended.yaml"
    case = yaml.safe_load(f.read_text())
    case["expected"]["instances"][1]["end"] = "2026-10-18T10:45:00Z"
    f.write_text(yaml.safe_dump(case, sort_keys=False))
    monkeypatch.setattr(active_state_rules, "CASES", cases)
    assert stale_against_committed() == ["active-state-a8.svg"]


@pytest.mark.parametrize("rule", sorted(active_state_rules.RULES))
def test_rule_figures_draw_cases_that_cite_the_rule(rule):
    # build() refuses a drawn case that neither cites the rule nor is the control of one that does
    ids = active_state_rules.RULES[rule][1]
    cases = {c: active_state_rules.load(c) for c in ids}
    assert any(rule in c["rules"] for c in cases.values()), rule
