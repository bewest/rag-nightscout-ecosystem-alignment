"""The committed animations were rendered from the sources they name, as those sources stand now.

  python3 -m pytest tools/animations/test_animations.py -q

Video bytes are not deterministic, so the test compares hashes instead: each
docs/30-design/platform/animations/<name>.sources.json holds the sha256 of the scene file and every
input at render time (sources.py), and test_rendered_from_current_sources fails naming each
animation whose scene or inputs have changed since. The tamper tests are its controls: one input
changed in a temporary copy must make exactly the animation drawn from it stale.
"""
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sources  # noqa: E402
from sources import ANIMATIONS, OUT, REPO, stale  # noqa: E402


def test_rendered_from_current_sources():
    assert not stale(), f"animations rendered from older sources (run make animations): {stale()}"


def test_every_animation_is_committed_with_poster_and_sidecar():
    for name in ANIMATIONS:
        for ext in (".webm", ".png", ".sources.json"):
            assert (OUT / f"{name}{ext}").is_file(), f"{name}{ext}"


def test_sizes_within_budget():
    sizes = {n: (OUT / f"{n}.webm").stat().st_size for n in ANIMATIONS}
    assert all(s <= 2 * 1024 * 1024 for s in sizes.values()), sizes
    assert sum(sizes.values()) <= 10 * 1024 * 1024, sizes


def test_no_orphans():
    names = {p.name.split(".")[0] for p in OUT.iterdir()}
    assert names <= set(ANIMATIONS), sorted(names - set(ANIMATIONS))


def test_sidecar_names_every_declared_input():
    for name in ANIMATIONS:
        side = json.loads(sources.sidecar(name).read_text())
        assert set(side["sha256"]) == set(sources.manifest(name)["sha256"]), name


def tampered(tmp_path, rel, edit):
    p = tmp_path / Path(rel).name
    shutil.copyfile(REPO / rel, p)
    p.write_text(edit(p.read_text()))
    return {rel: p}


def test_control_tampered_conformance_case(tmp_path):
    rel = "specs/sync/conformance/active-state/deleted-before-start.yaml"
    swap = tampered(tmp_path, rel, lambda s: s.replace("receivedAt: '2026-10-18T10:30:00Z'",
                                                       "receivedAt: '2026-10-18T11:10:00Z'"))
    assert stale(swap) == ["active-state-spans"]


def test_control_input_of_no_animation(tmp_path):
    # the hub-active-state lab results are drawn only as static figures (tools/diagrams)
    rel = "tools/lab/hub-active-state/results/nocturne.json"
    assert stale(tampered(tmp_path, rel, lambda s: s + "\n")) == []


def test_control_rule_name_but_not_other_spec_text(tmp_path):
    rel = "docs/30-design/platform/spec/state-intent.md"
    renamed = tampered(tmp_path, rel, lambda s: s.replace("**Supersession by start.**",
                                                          "**Supersession by start time.**"))
    assert stale(renamed) == ["active-state-spans"]
    prose = tampered(tmp_path, rel, lambda s: s + "\nA sentence added at the end.\n")
    assert stale(prose) == []


def test_control_tampered_scene(tmp_path):
    rel = ANIMATIONS["active-state-spans"]["scene"]
    assert stale(tampered(tmp_path, rel, lambda s: s + "\n# changed\n")) == ["active-state-spans"]


def test_control_tampered_shared_drawing_code(tmp_path):
    rel = "tools/animations/common.py"
    assert stale(tampered(tmp_path, rel, lambda s: s.replace("MIN_SIZE = 18", "MIN_SIZE = 14"))) == \
        ["active-state-spans"]
