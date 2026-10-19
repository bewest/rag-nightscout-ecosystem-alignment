"""Effect link prototype: how a command's outcome links to the record of its
effect (docs/30-design/platform/effect-link-prototype-2026-10-18.md).

Every scenario runs against the baseline and the four options. EXPECTED holds
the links correct/wrong/missing (and E3's flagged pairs) per scenario, written
from each scenario's description; the generated tables in the note must match
the model, so neither can drift from the other.
"""
import pytest

from nsschema.prototypes import effect_link as el

# scenario: B0, E1, E2, E3, E4 as correct/wrong/missing, " fN" when N pairs are flagged
EXPECTED = {
    "bolus-one-record":                   "1/0/0 1/0/0 1/0/0 1/0/0 1/0/0",
    "override-ended-by-amend":            "1/0/0 1/0/0 1/0/0 1/0/0 1/0/0",
    "override-ended-by-repost":           "0/0/2 1/0/1 2/0/0 2/0/0f1 2/0/0",
    "override-then-remote-cancel":        "1/0/1 2/0/0 1/0/1 2/0/0f1 2/0/0",
    "carbs-edited-by-command":            "1/0/1 2/0/0 2/0/0 2/0/0 2/0/0",
    "upload-request-lost-resent":         "1/0/0 1/0/0 1/0/0 1/0/0 1/0/0",
    "upload-reply-lost-no-identifier":    "1/0/0 0/0/1 1/0/0 1/0/0f1 1/0/0",
    "report-before-record":               "1/0/0 1/0/0 1/0/0 1/0/0 1/0/0",
    "report-after-record":                "1/0/0 1/0/0 1/0/0 1/0/0 1/0/0",
    "restart-effects-kept":               "1/0/0 1/0/0 1/0/0 1/0/0 1/0/0",
    "restart-effects-not-kept":           "1/0/0 0/0/1 1/0/0 1/0/0f1 0/0/1",
    "refused-then-local-dose":            "0/0/0 0/0/0 0/0/0 0/0/0 0/0/0",
    "local-dose-after-command":           "1/0/0 1/0/0 1/0/0 1/0/0 1/0/0",
    "local-dose-while-command-in-flight": "0/1/1 1/0/0 1/0/0 1/0/0 1/0/0",
    "meal-part-enacted":                  "0/0/1 1/0/0 1/0/0 1/0/0 1/0/0",
    "meal-two-records":                   "2/0/0 2/0/0 2/0/0 2/0/0 2/0/0",
    "effect-amended":                     "1/0/0 1/0/0 1/0/0 1/0/0 1/0/0",
    "effect-deleted":                     "0/0/1 1/0/0 1/0/0 1/0/0 1/0/0",
    "effect-replaced-by-follower":        "1/0/0 1/0/0 1/0/0 1/0/0 1/0/0",
    "controller-cannot-tag":              "1/0/0 1/0/0 0/0/1 1/0/0 1/0/0",
    "two-commands-close":                 "0/2/2 2/0/0 2/0/0 2/0/0 2/0/0",
    "enacted-twice":                      "1/0/1 1/0/1 2/0/0 2/0/0f1 1/0/1",
    "fault-report-names-local-record":    "1/0/0 0/1/1 1/0/0 1/1/0f2 0/1/1",
    "fault-tag-on-local-record":          "1/0/0 1/0/0 1/1/0 1/1/0f1 1/0/0",
}

FAULTS = {n for n, s in el.SCENARIOS.items() if s.get("faults")}
PAIRS = [(n, o) for n in sorted(el.SCENARIOS) for o in el.OPTIONS]


def cell(m):
    return "%d/%d/%d" % (m["correct"], m["wrong"], m["missing"]) + (
        "f%d" % m["flagged"] if m["flagged"] else "")


def test_every_scenario_has_an_expectation():
    assert sorted(EXPECTED) == sorted(el.SCENARIOS)
    assert len(el.SCENARIOS) >= 20
    assert all(s.get("about") for s in el.SCENARIOS.values())


@pytest.mark.parametrize("name,option", PAIRS)
def test_links(name, option):
    want = dict(zip(el.OPTIONS, EXPECTED[name].split()))[option]
    assert cell(el.measure(el.SCENARIOS[name], option)) == want


@pytest.mark.parametrize("option", ("E1", "E2", "E3", "E4"))
@pytest.mark.parametrize("name", sorted(set(el.SCENARIOS) - FAULTS))
def test_a_local_action_is_never_linked(name, option):
    # Without a fault in the controller, no option links a record that a
    # local action made: a dose never looks remote that was not.
    assert el.measure(el.SCENARIOS[name], option)["localShownRemote"] == 0


@pytest.mark.parametrize("name", sorted(set(el.SCENARIOS) - FAULTS))
def test_no_option_links_wrongly_without_a_fault(name):
    for option in ("E1", "E2", "E3", "E4"):
        assert el.measure(el.SCENARIOS[name], option)["wrong"] == 0, option


def test_without_a_fault():
    # The figures the note's safety and assessment sections quote.
    clean = [s for n, s in el.SCENARIOS.items() if n not in FAULTS]
    got = {o: tuple(sum(el.measure(s, o)[k] for s in clean)
                    for k in ("wrong", "missing", "remoteShownLocal")) for o in el.OPTIONS}
    assert got == {"B0": (3, 10, 7), "E1": (0, 4, 4), "E2": (0, 2, 1),
                   "E3": (0, 0, 0), "E4": (0, 2, 2)}


def test_baseline_mislinks():
    # Non-vacuity for the test above: inference by time and kind does link
    # wrongly, on the scenarios built to show it.
    wrong = {n for n in el.SCENARIOS if el.measure(el.SCENARIOS[n], "B0")["wrong"]}
    assert wrong == {"local-dose-while-command-in-flight", "two-commands-close"}


def test_e3_flags_every_fault():
    for name in FAULTS:
        m = el.measure(el.SCENARIOS[name], "E3")
        assert m["flaggedWrong"] == m["wrong"] == 1, name


def test_second_enactment_is_visible_only_with_the_tag():
    got = {o: el.measure(el.SCENARIOS["enacted-twice"], o)["duplicateVisible"] for o in el.OPTIONS}
    assert got == {"B0": 0, "E1": 0, "E2": 1, "E3": 1, "E4": 0}


def test_an_effect_in_flight_is_known_only_from_a_report_or_reconciliation():
    got = {o: el.measure(el.SCENARIOS["report-before-record"], o)["earlyKnown"] for o in el.OPTIONS}
    assert got == {"B0": 0, "E1": 1, "E2": 0, "E3": 1, "E4": 1}


def test_records_alone_show_remote_only_with_the_tag():
    s = el.SCENARIOS["bolus-one-record"]
    assert [el.from_record_alone(s, o) for o in el.OPTIONS] == [False, False, True, True, False]


def test_carriers_and_cases_are_distinct():
    assert len(el.EFFECT_CARRIERS) == len(set(el.EFFECT_CARRIERS)) == 12
    for option, cost in el.COSTS.items():
        assert len(cost["cases"]) == len(set(cost["cases"])), option


def test_note_tables_are_current():
    path = el.note_path()
    text = path.read_text()
    for name in el.BLOCKS:
        assert "<!-- BEGIN GENERATED: %s -->" % name in text, name
    assert el.render(text) == text, "run: python3 -m nsschema.prototypes.effect_link --write"


# --- weakenings the suite must catch (non-vacuity) ---------------------------

def test_weakened_tagging_links_a_local_action(monkeypatch):
    # A controller that puts the last enacted commandId on every record it
    # writes makes the later local dose look remote under E2.
    s = el.SCENARIOS["local-dose-after-command"]
    assert el.measure(s, "E2")["localShownRemote"] == 0
    monkeypatch.setitem(el.RULES, "tagOnlyEnacted", False)
    assert el.measure(s, "E2")["localShownRemote"] == 1
    assert el.measure(s, "E1")["localShownRemote"] == 0


def test_weakened_keep_tag_loses_the_link_on_replace(monkeypatch):
    monkeypatch.setitem(el.RULES, "keepTag", False)
    assert cell(el.measure(el.SCENARIOS["effect-replaced-by-follower"], "E2")) == "0/0/1"
