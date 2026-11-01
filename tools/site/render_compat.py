#!/usr/bin/env python3
"""Render site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html from the
committed data in releases/cgm-remote-monitor-16.0.0/compat/.

A LIVING rich page (site/pages/pages.yaml). The words come from page.yaml, the
group metadata from groups.yaml (already folded into groups.json), the
"Decisions that could restore compatibility" cards from reconsider.json, and
every figure from the page datasets that tools/qc/compat/build_page.py writes.
The datasets are embedded as JSON blocks and drawn in the browser by
tools/site/compat-dash.js with d3 (pinned, from the CDN, with SRI).

    tools/site/.venv/bin/python tools/site/render_compat.py

Then set `source_commit` for the page in site/pages/pages.yaml to the commit
that last changed any source (the script prints it). The refresh steps that
come before this one are in tools/qc/compat/README.md.
"""
from __future__ import annotations

import html
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_programme import CSS as BASE_CSS  # noqa: E402  (one look for the rich pages)

REPO = Path(__file__).resolve().parents[2]
DIR = "releases/cgm-remote-monitor-16.0.0/compat"
DATASETS = ["headline", "groups", "heat", "families", "triage", "clients", "cells"]
SOURCES = [f"{DIR}/{n}.json" for n in DATASETS] + [f"{DIR}/groups.yaml", f"{DIR}/page.yaml", f"{DIR}/reconsider.json"]
JS = REPO / "tools/site/compat-dash.js"
OUT = REPO / "site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html"
PAGE_DIR = "site/pages"
D3_URL = "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"
D3_SRI = "sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i"
COST_ORDER = {"near zero": 0, "low": 1, "high": 2}

# Tokens. The page keeps the dashboard's token names (--color-*, --cds-*) and maps
# them onto the rich pages' palette (render_programme.CSS: --ink, --muted, --rule,
# --surface, --bg, --accent, --warn). Chart slots 1-3 are the dataviz reference
# palette's categorical slots used by render_colophon.VIZ_CSS; status colours are
# chosen for at least 4.5:1 as text on the panel colour in each scheme.
TOKENS_LIGHT = ("--color-ok:#1b7a4a;--color-warn:#8a5a00;--color-bad:#b42318;"
                "--cds-chart-1:#2a78d6;--cds-chart-2:#eb6834;--cds-chart-3:#1baf7a;"
                "--cds-chart-grid:#e1e0d9;--cds-chart-axis:#6b6a65;--cds-chart-status-critical:#d92d20;"
                "--cds-shadow-popover:0 4px 14px rgba(0,0,0,.12)")
TOKENS_DARK = ("--color-ok:#4cc38a;--color-warn:#f0c26a;--color-bad:#ff8a80;"
               "--cds-chart-1:#3987e5;--cds-chart-2:#d95926;--cds-chart-3:#199e70;"
               "--cds-chart-grid:#24353a;--cds-chart-axis:#9bb0b3;--cds-chart-status-critical:#f97066;"
               "--cds-shadow-popover:0 4px 14px rgba(0,0,0,.45)")
TOKENS_CSS = (
    ":root{--color-fg:var(--ink);--color-fg-muted:var(--muted);--color-bg:var(--bg);--color-panel:var(--surface);"
    "--color-border-line:var(--rule);--cds-border:var(--rule);--cds-surface-popover:var(--surface);--cds-text-secondary:var(--muted);"
    "--cds-font-size-title:clamp(26px,3.6vw,34px);--cds-font-size-heading:20px;--cds-font-size-body:16px;--cds-font-size-caption:13.5px;"
    "--cds-font-weight-medium:600;--cds-gap-xs:4px;--cds-gap-sm:8px;--cds-gap-md:14px;--cds-gap-lg:20px;--cds-gap-xl:32px;"
    "--cds-pad-xs:4px;--cds-pad-sm:8px;--cds-pad-md:12px;--cds-pad-lg:18px;--cds-radius:8px;--cds-dur-slow:.3s;"
    '--font-sans:"Public Sans",system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;'
    '--font-serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,"Times New Roman",serif;'
    '--font-mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;'
    + TOKENS_LIGHT + "}\n"
    "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){" + TOKENS_DARK + "}}\n"
    ":root[data-theme=\"dark\"]{" + TOKENS_DARK + "}\n"
)

# The dashboard's own styles, with its host font tokens renamed to --font-sans /
# --font-serif / --font-mono, and resets for the base styles it sits on.
DASH_CSS = r"""
.wrap{max-width:1240px}
.cw { display: grid; gap: var(--cds-gap-xl); font-family: var(--font-sans); }
.cw h1 { font-family: var(--font-serif); font-weight: 400; font-size: var(--cds-font-size-title); margin: 0; text-wrap: balance; max-width: none; }
.cw h2 { font-size: var(--cds-font-size-heading); font-weight: var(--cds-font-weight-medium); margin: 0; text-wrap: balance; border-top: 0; padding-top: 0; }
.cw h3 { font-size: 16px; margin: 0; line-height: 1.35; }
.cw p { margin: 0; max-width: 72ch; line-height: 1.5; }
.cw .muted { color: var(--color-fg-muted); font-size: var(--cds-font-size-caption); }
.cw .lede { font-size: var(--cds-font-size-body); }
.cw .lede b { font-weight: 600; }
.cw-head { display: grid; gap: var(--cds-gap-sm); }
.cw-banner { background: var(--warn-soft); border-left: 3px solid var(--warn); padding: var(--cds-pad-md) var(--cds-pad-lg); border-radius: 0 4px 4px 0; font-size: 14.5px; line-height: 1.5; max-width: 90ch; }
.cw-banner p { max-width: none; }
.cw-banner p + p { margin-top: var(--cds-gap-xs); }
.cw-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 9.5rem), 1fr)); gap: var(--cds-gap-md); }
.cw-tile { background: var(--color-panel); border: 1px solid var(--color-border-line); border-radius: var(--cds-radius); padding: var(--cds-pad-md); display: grid; gap: var(--cds-gap-xs); align-content: start; }
.cw-tile .v { font-family: var(--font-serif); font-size: var(--cds-font-size-title); font-variant-numeric: tabular-nums; line-height: 1.1; }
.cw-tile .l { font-size: var(--cds-font-size-caption); color: var(--color-fg-muted); }
.cw-tile.bad .v { color: var(--color-bad); }
.cw-card { background: var(--color-panel); border: 1px solid var(--color-border-line); border-radius: var(--cds-radius); padding: var(--cds-pad-lg); display: grid; gap: var(--cds-gap-md); min-width: 0; }
.cw-grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 30rem), 1fr)); gap: var(--cds-gap-md); }
.cw-section { display: grid; gap: var(--cds-gap-md); }
.cw-chart { position: relative; min-width: 0; }
.cw-scroll { overflow-x: auto; }
.cw-tablebox { max-height: 34rem; overflow: auto; border: 1px solid var(--color-border-line); border-radius: var(--cds-radius); }
.cw table { border-collapse: collapse; width: 100%; font-size: var(--cds-font-size-caption); font-variant-numeric: tabular-nums; }
.cw th { position: sticky; top: 0; background: var(--color-panel); text-align: left; font-weight: var(--cds-font-weight-medium); color: var(--color-fg-muted); padding: var(--cds-pad-xs) var(--cds-pad-sm); border-bottom: 1px solid var(--color-border-line); white-space: nowrap; z-index: 1; font-size: var(--cds-font-size-caption); letter-spacing: normal; text-transform: none; }
.cw th button { all: unset; cursor: pointer; }
.cw th button:focus-visible { outline: 2px solid var(--cds-chart-axis); outline-offset: 2px; }
.cw td { padding: var(--cds-pad-xs) var(--cds-pad-sm); border-bottom: 1px solid var(--color-border-line); vertical-align: top; }
.cw td.num { text-align: right; }
.cw td.wrap { min-width: 16rem; line-height: 1.4; }
.cw code, .cw .mono { font-family: var(--font-mono); font-size: 0.92em; background: none; padding: 0; }
.chip { display: inline-block; padding: 0.05rem 0.45rem; border-radius: 999px; border: 1px solid var(--color-border-line); white-space: nowrap; font-size: var(--cds-font-size-caption); }
.chip.defect { color: var(--color-bad); border-color: currentColor; font-weight: 600; }
.chip.fix { color: var(--color-ok); border-color: currentColor; }
.chip.none { color: var(--color-fg-muted); }
.chip.measured { color: var(--color-ok); border-color: currentColor; }
.chip.read { color: var(--color-warn); border-color: currentColor; }
.chip.noclient { color: var(--color-fg-muted); }
.chip.cand { color: var(--color-ok); border-color: currentColor; font-weight: 600; }
a.chip { text-decoration: none; white-space: normal; line-height: 1.35; }
a.chip:hover { text-decoration: underline; }
.restore-links { display: flex; flex-wrap: wrap; gap: var(--cds-gap-xs); min-width: 12rem; }
.bar { display: flex; height: 0.6rem; border-radius: 3px; overflow: hidden; min-width: 4rem; background: var(--cds-chart-grid); }
.bar > span { display: block; height: 100%; }
.legend { display: flex; flex-wrap: wrap; gap: var(--cds-gap-md); font-size: var(--cds-font-size-caption); color: var(--color-fg-muted); align-items: center; }
.legend i { display: inline-block; width: 0.7rem; height: 0.7rem; border-radius: 2px; margin-right: 0.35rem; vertical-align: -0.05rem; }
.controls { display: flex; flex-wrap: wrap; gap: var(--cds-gap-sm); align-items: center; }
.controls input, .controls select { font: inherit; font-size: var(--cds-font-size-caption); padding: var(--cds-pad-xs) var(--cds-pad-sm); border: 1px solid var(--color-border-line); border-radius: var(--cds-radius); background: var(--color-bg); color: var(--color-fg); min-width: 0; }
.controls button { font: inherit; font-size: var(--cds-font-size-caption); padding: var(--cds-pad-xs) var(--cds-pad-sm); border: 1px solid var(--color-border-line); border-radius: var(--cds-radius); background: var(--color-bg); color: var(--color-fg); cursor: pointer; }
.tip { position: absolute; pointer-events: none; background: var(--cds-surface-popover); border: 1px solid var(--cds-border); border-radius: var(--cds-radius); box-shadow: var(--cds-shadow-popover); padding: var(--cds-pad-xs) var(--cds-pad-sm); font-size: var(--cds-font-size-caption); max-width: 18rem; z-index: 5; line-height: 1.4; }
.tip .k { color: var(--cds-text-secondary); }
.cw ul { margin: 0; padding-left: 1.2rem; display: grid; gap: var(--cds-gap-xs); max-width: 80ch; line-height: 1.45; }
.cw .finding { border-left: 3px solid var(--color-bad); padding-left: var(--cds-pad-md); display: grid; gap: var(--cds-gap-xs); }
.cw svg text { fill: var(--color-fg-muted); font-family: var(--font-sans); }
.rc-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 22rem), 1fr)); gap: var(--cds-gap-md); }
.rc-card { background: var(--color-panel); border: 1px solid var(--color-border-line); border-left: 4px solid var(--color-ok); border-radius: var(--cds-radius); padding: var(--cds-pad-lg); display: grid; gap: var(--cds-gap-sm); align-content: start; min-width: 0; scroll-margin-top: 16px; }
.rc-card.keep { border-left-color: var(--color-border-line); }
.rc-card:target { box-shadow: 0 0 0 2px var(--accent); }
.rc-top { display: flex; flex-wrap: wrap; gap: var(--cds-gap-sm); align-items: center; }
.rc-letter { font-family: var(--font-mono); font-weight: 600; font-size: 13px; color: var(--color-fg-muted); }
.rc-tag { font-size: 11px; letter-spacing: .06em; text-transform: uppercase; font-weight: 700; padding: 0.05rem 0.45rem; border-radius: 999px; border: 1px solid currentColor; }
.rc-tag.cand { color: var(--color-ok); }
.rc-tag.keep { color: var(--color-fg-muted); }
.rc-card dl { display: grid; grid-template-columns: 1fr; gap: 2px; margin: 0; font-size: 14px; line-height: 1.45; }
.rc-card dt { color: var(--color-fg-muted); font-size: 12.5px; margin-top: var(--cds-gap-sm); }
.rc-card dd { margin: 0; }
.rc-bar { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--cds-gap-sm); align-items: center; }
.rc-bar .bar { height: 0.7rem; }
.rc-bar .bar > span { background: var(--cds-chart-1); }
.rc-bar .rc-n { font-variant-numeric: tabular-nums; font-size: 14px; font-weight: 600; }
.cw-src { font-size: 13px; color: var(--muted); }
@media (max-width: 560px) { .cw-banner { padding: var(--cds-pad-sm) var(--cds-pad-md); } }
"""


def git(*a):
    return subprocess.run(["git", "-C", str(REPO), *a], check=True, capture_output=True, text=True).stdout.strip()


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def inline(s: str) -> str:
    """Escape, then `code` -> mono span and **x** -> <b>x</b>."""
    out = esc(s)
    out = re.sub(r"`([^`]+)`", r'<span class="mono">\1</span>', out)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)


def site_href(repo_path: str) -> str:
    """A repository path -> its page on the site, relative to site/pages/."""
    if not (REPO / repo_path).exists():
        sys.exit(f"render: link target {repo_path} does not exist")
    if repo_path.endswith(".md"):
        b = posixpath.basename(repo_path)
        repo_path = (posixpath.dirname(repo_path) + "/index.html") if b in ("README.md", "index.md") else repo_path[:-3] + ".html"
    return posixpath.relpath(repo_path, PAGE_DIR)


def load():
    data = {n: json.loads((REPO / DIR / f"{n}.json").read_text(encoding="utf-8")) for n in DATASETS}
    page = yaml.safe_load((REPO / DIR / "page.yaml").read_text(encoding="utf-8"))
    rec = json.loads((REPO / DIR / "reconsider.json").read_text(encoding="utf-8"))
    groups = yaml.safe_load((REPO / DIR / "groups.yaml").read_text(encoding="utf-8"))["groups"]
    errs = []
    ids = [r["id"] for r in rec]
    if len(ids) != len(set(ids)):
        errs.append("reconsider.json: duplicate id")
    for r in rec:
        if r.get("cost_to_objectives") not in COST_ORDER:
            errs.append(f"reconsider.json {r.get('id')}: cost_to_objectives must be one of {', '.join(COST_ORDER)}")
        for g in r.get("groups", []):
            if g not in groups:
                errs.append(f"reconsider.json {r['id']}: group {g} is not in groups.yaml")
    head = {h["metric"]: h["value"] for h in data["headline"]}
    for t in page["tiles"]:
        if t["metric"] not in head:
            errs.append(f"page.yaml: tile metric {t['metric']} is not in headline.json")
    if errs:
        sys.exit("render: " + "; ".join(errs))
    return data, page, rec, head


# A maintainer decision on a card replaces its Candidate/Keep tag (reconsider.json `status`).
TAG = {"adopted": ("cand", "Adopted"), "kept": ("keep", "Kept"), "as-decided": ("keep", "Not taken up")}


def letters(n):
    return [chr(ord("A") + i) for i in range(n)]


def reconsider_cards(rec):
    rec = sorted(rec, key=lambda r: (COST_ORDER[r["cost_to_objectives"]], -r["cells_restored"]))
    top = max([r["cells_restored"] for r in rec] + [1])
    out = []
    for letter, r in zip(letters(len(rec)), rec):
        keep = r["cost_to_objectives"] == "high"
        head = r["decision"].split(":")[0].strip()
        if len(head) > 48:
            head = head[:46].rstrip(" ,(") + "…"
        pct = 100 * r["cells_restored"] / top
        out.append(
            f'<article class="rc-card{" keep" if keep else ""}" id="reconsider-{esc(r["id"])}" '
            f'data-groups="{esc(" ".join(r["groups"]))}" data-letter="{letter}" data-head="{esc(head)}">'
            f'<div class="rc-top"><span class="rc-letter">{letter}</span>'
            f'<span class="rc-tag {TAG.get(r.get("status"), ("keep" if keep else "cand", ""))[0]}">'
            f'{TAG.get(r.get("status"), (None, "Keep" if keep else "Candidate"))[1]}</span>'
            f'<span class="muted">cost to the objectives: {esc(r["cost_to_objectives"])}</span></div>'
            f'<h3>{esc(r["decision"])}</h3>'
            f'<div class="rc-bar" aria-label="{r["cells_restored"]:,} cells restored">'
            f'<div class="bar"><span style="width:{pct:.2f}%"></span></div>'
            f'<span class="rc-n">{r["cells_restored"]:,} cells</span></div>'
            f'<dl><dt>Alternative</dt><dd>{esc(r["alternative"])}</dd>'
            f'<dt>What it restores</dt><dd>{esc(r["restores"])}</dd>'
            f'<dt>Cost</dt><dd>{esc(r["cost"])}</dd>'
            f'<dt>Recommendation</dt><dd>{esc(r["recommendation"])}</dd>'
            + (f'<dt>Maintainer decision</dt><dd>{esc(r["status_note"])} ({esc(r.get("decided", ""))})</dd>' if r.get("status_note") else "")
            + f'<dt>Kinds of change</dt><dd>{esc(", ".join(r["groups"]))}</dd></dl></article>')
    return f'<div class="rc-cards">{"".join(out)}</div>', top


def main():
    data, page, rec, head = load()
    commit = git("log", "-1", "--format=%h", "--", *SOURCES)
    date = git("log", "-1", "--format=%cs", "--", *SOURCES)
    if not commit:
        sys.exit("render: the sources are not committed yet; commit them, then render")
    fmt = lambda v: f"{v:,}"
    lede = inline(page["lede"].format(**{k: fmt(v) for k, v in head.items() if isinstance(v, (int, float))}))
    trees = ", ".join(f'<span class="mono">{esc(t["name"])} {esc(t["commit"])}</span> ({esc(t["note"])})' for t in page["trees"])
    origin_labels = page.get("origin_labels", {"8879": "#8879 only", "dev": "already on dev", "both": "dev, then #8879"})
    base_name = page["trees"][0]["name"]
    tip_name = page["trees"][-1]["name"]
    tiles = "".join(
        f'<div class="cw-tile{" bad" if t.get("bad") else ""}"><span class="v">{fmt(head[t["metric"]])}</span>'
        f'<span class="l">{esc(t["label"])}</span></div>' for t in page["tiles"])
    cards, top = reconsider_cards(rec)
    limits = "".join(f"<li>{inline(x)}</li>" for x in page["limits"])
    vclass = {"Defect": "defect", "Bug fix": "fix", "No value change": "none", "Decided": ""}
    verdicts = "".join(f'<li><span class="chip {vclass.get(v["verdict"], "")}">{esc(v["verdict"])}</span> {inline(v["text"])}</li>'
                       for v in page["verdicts"]) + f'<li>{inline(page["verdicts_note"])}</li>'
    blocks = "\n".join(
        f'<script type="application/json" id="compat-data-{n}">{json.dumps(data[n], separators=(",", ":"), ensure_ascii=False).replace("</", "<" + chr(92) + "/")}</script>'
        for n in DATASETS)
    readme = site_href("tools/qc/compat/README.md")
    contents = site_href("releases/cgm-remote-monitor-16.0.0/contents.md")
    title = page["title"]
    body = f"""
<div class="cw">
  <header class="cw-head" id="top">
    <h1>{esc(title)}</h1>
    <p class="lede">{lede}</p>
    <div class="cw-banner" data-site-banner="living">
      <p><strong>Living page.</strong> Measured {esc(page["measured"])} with the write-contract matrix (<span class="mono">{esc(page["harness"])}</span>) on {trees}.</p>
      <p>{inline(page["settings"])} {esc(page["environment"])}.</p>
      <p>Rendered from the committed data in <span class="mono">{DIR}/</span>, last changed {date} at <span class="mono">{commit}</span>; a new measurement refreshes it by the steps in <a href="{readme}">the comparison's README</a>. Part of the <a href="{contents}">16.0.0 release record</a>. All records in the matrix are synthetic test data.</p>
    </div>
  </header>

  <section class="cw-tiles" aria-label="Headline figures">{tiles}</section>

  <section class="cw-card finding" id="defect">
    <h2>{esc(page["defect"]["heading"])}</h2>
    <p>{inline(page["defect"]["text"])}</p>
  </section>

  <section class="cw-section" id="why">
    <h2>Why the count is large</h2>
    <p class="muted">{inline(page["why"])}</p>
    <div class="cw-card">
      <div class="legend"><span><i data-draw="sw0"></i>{esc(origin_labels["8879"])}</span><span><i data-draw="sw1"></i>{esc(origin_labels["dev"])}</span><span><i data-draw="sw2"></i>{esc(origin_labels["both"])}</span></div>
      <div class="cw-chart" data-draw="families" data-source="families" style="min-height: 13rem"></div>
    </div>
  </section>

  <section class="cw-section" id="kinds">
    <h2>Each kind of change</h2>
    <p class="muted">The differing cells grouped by what happens to the data. "Paths" counts distinct collection and re-send path pairs, a better measure of how many separate behaviours changed than the cell count. "Undo" is what an operator could use to get 15.0.9's behaviour back today. "Could restore" names the decision cards below whose alternative would bring this kind of change back toward 15.0.9.</p>
    <div class="cw-card">
      <div class="cw-tablebox">
        <table data-source="groups" data-row-key="group">
          <thead><tr>
            <th data-field="verdict">Verdict</th><th data-field="name">Change</th><th data-field="meaning">What happens</th><th data-field="consequence">What a person could see</th>
            <th data-field="cells">Cells</th><th>Where from</th><th data-field="combos">Paths</th><th data-field="worst_effect">Worst effect</th><th data-field="guard">Undo</th><th>Could restore</th><th data-field="clients">Clients</th><th data-field="basis">Decided by</th>
          </tr></thead>
          <tbody data-draw="groups-body"></tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="cw-section" id="reconsider">
    <h2>Decisions that could restore compatibility</h2>
    <p class="muted">{inline(page["reconsider_intro"])} Sorted by cost (near zero, low, high), then by cells restored; the bars share one scale, up to {top:,} cells.</p>
    {cards}
  </section>

  <section class="cw-section" id="map">
    <h2>Where the changes land</h2>
    <p class="muted">Each square is one kind of change on one collection and re-send path. Darker means more cells. Empty means no change there. Select a square to list its cells below.</p>
    <div class="cw-card">
      <div class="cw-scroll"><div class="cw-chart" data-draw="heat" data-source="heat groups" style="min-height: 30rem; min-width: 52rem"></div></div>
    </div>
  </section>

  <section class="cw-section" id="triage">
    <h2>Triage: what to look at first</h2>
    <p class="muted">One row per kind of change, collection and re-send path. Score = severity of the worst effect (1 to 10; bug fixes and avoided duplicates capped at 3, the defect at 10) times the number of clients read or measured as sending that shape, or half the severity where no client was found. Evidence: "measured" is a run against a server, "read" is from the client's code with file and line. Nothing is assumed.</p>
    <div class="cw-card">
      <div class="controls">
        <label class="muted" for="tri-q">Search</label><input id="tri-q" type="search" placeholder="client, collection, change">
        <label class="muted" for="tri-v">Verdict</label>
        <select id="tri-v"><option value="">All</option><option>Defect</option><option>Decided</option><option>Bug fix</option><option>No value change</option></select>
      </div>
      <div class="cw-tablebox">
        <table data-source="triage" data-row-key="key">
          <thead><tr>
            <th data-field="score"><button data-sort="score">Score</button></th><th data-field="verdict"><button data-sort="verdict">Verdict</button></th><th data-field="name"><button data-sort="name">Change</button></th>
            <th data-field="collection"><button data-sort="collection">Collection</button></th><th data-field="path"><button data-sort="path">Re-send path</button></th><th data-field="cells"><button data-sort="cells">Cells</button></th>
            <th data-field="effect"><button data-sort="effect">Worst effect</button></th><th data-field="evidence"><button data-sort="evidence">Evidence</button></th><th data-field="clients">Clients that send this shape</th>
          </tr></thead>
          <tbody data-draw="triage-body"></tbody>
        </table>
      </div>
      <p class="muted" data-draw="triage-count" data-source="triage">—</p>
    </div>
  </section>

  <section class="cw-section" id="clients">
    <h2>Which clients meet which change</h2>
    <p class="muted">Rows are clients, columns are kinds of change. A dot means the client was found sending a shape that change touches; bigger dots match more cells. Colour shows the strongest evidence.</p>
    <div class="cw-card">
      <div class="legend"><span><i data-draw="sw-measured"></i>measured</span><span><i data-draw="sw-read"></i>read from code</span></div>
      <div class="cw-scroll"><div class="cw-chart" data-draw="clientmap" data-source="clients groups" style="min-height: 26rem; min-width: 44rem"></div></div>
    </div>
  </section>

  <section class="cw-section" id="cells">
    <h2>Cell explorer</h2>
    <p class="muted">Every differing cell, with the stored records and the reply before and after. Store notation: <span class="mono">n=2 OID,str*</span> is two records, one under an ObjectId and one under a string <span class="mono">_id</span>; <span class="mono">:v2</span> marks the re-send's values; <span class="mono">:inv</span> a deleted record.</p>
    <div class="cw-card">
      <div class="controls">
        <label class="muted" for="cell-g">Change</label><select id="cell-g" data-draw="cell-groups" data-source="groups"></select>
        <label class="muted" for="cell-q">Search</label><input id="cell-q" type="search" placeholder="cell, collection, path">
        <button type="button" id="cell-clear">Clear</button>
      </div>
      <p class="muted" data-draw="cell-count" data-source="cells">—</p>
      <div class="cw-tablebox">
        <table data-source="cells" data-row-key="cell">
          <thead><tr>
            <th data-field="cell">Cell</th><th data-field="origin">Where from</th><th data-field="effect">Effect</th><th data-field="store_before">Stored on {esc(base_name)}</th><th data-field="store_after">Stored on {esc(tip_name)}</th>
            <th data-field="reply_before">Reply on {esc(base_name)}</th><th data-field="reply_after">Reply on {esc(tip_name)}</th><th data-field="cause">Cause</th>
          </tr></thead>
          <tbody data-draw="cells-body"></tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="cw-grid2" id="limits">
    <div class="cw-card">
      <h2>What this cannot see</h2>
      <ul>{limits}</ul>
    </div>
    <div class="cw-card">
      <h2>How to read the verdicts</h2>
      <ul>{verdicts}</ul>
    </div>
  </section>
  <noscript><p class="muted">The charts and tables need JavaScript; the figures above and the decision cards do not.</p></noscript>
</div>"""
    out = f"""<!doctype html>
<!-- Generated by tools/site/render_compat.py from {DIR}/ at {commit}. Do not edit by hand; re-run the script. Living page: see site/pages/pages.yaml. -->
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{BASE_CSS}{TOKENS_CSS}{DASH_CSS}</style></head><body>
<div class="wrap">{body}
</div>
{blocks}
<script src="{D3_URL}" integrity="{D3_SRI}" crossorigin="anonymous"></script>
<script>{JS.read_text(encoding="utf-8")}</script>
</body></html>
"""
    OUT.write_text(out, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} ({len(out.encode()):,} bytes) from {DIR}/ at {commit} ({date}); "
          f"set source_commit: {commit} in site/pages/pages.yaml")


if __name__ == "__main__":
    main()
