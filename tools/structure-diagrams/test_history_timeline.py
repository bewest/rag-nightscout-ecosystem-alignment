"""history-timeline.svg is what history_timeline.py draws, and every row it draws is a row of HISTORY.md.

  python3 -m pytest tools/structure-diagrams/test_history_timeline.py -q

The tamper tests are the controls: a changed date in a copy of HISTORY.md must fail exactly the row
drawn from it, the untampered copy must fail none, and a changed row in a copy of the data must make
the committed figure stale.
"""
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import history_timeline as ht  # noqa: E402

HISTORY = ht.REPO / "docs" / "00-overview" / "observations" / "HISTORY.md"


def history_rows(text):
    """(section number, date cell, row text) for every dated table row of HISTORY.md."""
    out, sec = [], None
    for ln in text.splitlines():
        m = re.match(r"## (\d+)\.", ln)
        if m:
            sec = int(m.group(1))
        m = re.match(r"\| (\d{4}(?:-\d{2}){0,2}[^|]*?) \| (.*?) \|", ln)
        if m and sec:
            out.append((sec, m.group(1).strip(), m.group(2)))
    return out


def mismatches(history_text, data):
    hist = history_rows(history_text)
    return [r["key"] for r in data["rows"]
            if not any(s == r["section"] and d == str(r["date"]) and r["match"] in t for s, d, t in hist)]


def data():
    return yaml.safe_load(ht.DATA.read_text())


def test_committed_svg_is_generated():
    for n, t in ht.build().items():
        assert (ht.OUT / n).read_text() == t, f"stale: {n} (run make history-timeline)"


def test_every_row_matches_history():
    assert mismatches(HISTORY.read_text(), data()) == []


def test_control_tampered_history_date_fails_exactly_that_row(tmp_path):
    text = HISTORY.read_text()
    assert "| 2016-06-04 |" in text
    assert mismatches(text, data()) == []                                     # positive control, same text
    assert mismatches(text.replace("| 2016-06-04 |", "| 2016-06-05 |"), data()) == ["aaps"]


def test_control_tampered_data_makes_figure_stale(tmp_path):
    d = data()
    next(r for r in d["rows"] if r["key"] == "trio")["date"] = "2024-09-02"
    p = tmp_path / "timeline.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True))
    assert ht.build(p)[ht.NAME] != (ht.OUT / ht.NAME).read_text()
    p.write_text(ht.DATA.read_text())
    assert ht.build(p)[ht.NAME] == (ht.OUT / ht.NAME).read_text()               # positive control


def test_title_desc_and_determinism():
    a, b = ht.build(), ht.build()
    assert a == b
    t = a[ht.NAME]
    assert re.search(r"<title>[^<]+</title>", t) and re.search(r"<desc>[^<]+</desc>", t)
    assert all(float(s) >= 12 for s in re.findall(r'font-size="([\d.]+)"', t))
