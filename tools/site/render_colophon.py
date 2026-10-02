#!/usr/bin/env python3
"""Render site/pages/cgm-remote-monitor-15.0.9-colophon.html from
releases/cgm-remote-monitor-15.0.9/colophon.md and colophon-data.json.

A LIVING rich page (site/pages/pages.yaml). Its text is the markdown,
converted as-is, in the programme page's layout. Each `<!-- chart: NAME -->`
comment in the markdown becomes a figure: a chart drawn in the browser by
tools/site/colophon-charts.js from the JSON, plus a table of the same values
that needs no script.

    python3 tools/programme/colophon-data.py          # re-measure the series
    tools/site/.venv/bin/python tools/site/render_colophon.py

Then set `source_commit` for the page in site/pages/pages.yaml to the commit
that last changed either source (the script prints it).
"""
from __future__ import annotations

import html
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

import markdown

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_programme import CSS as BASE_CSS  # noqa: E402  (one look for the rich pages)

REPO = Path(__file__).resolve().parents[2]
SRC = "releases/cgm-remote-monitor-15.0.9/colophon.md"
DATA = "releases/cgm-remote-monitor-15.0.9/colophon-data.json"
JS = REPO / "tools/site/colophon-charts.js"
OUT = REPO / "site/pages/cgm-remote-monitor-15.0.9-colophon.html"
PAGE_DIR = "site/pages"

ORIGINS = [("latent", "found by audit, lab or survey", "--s1"), ("github", "from GitHub issues", "--s2"),
           ("connector", "in the CGM connector", "--s3"), ("review", "in review before merge", "--s4"),
           ("escaped", "introduced by a fix (regression)", "--s5")]

# Chart tokens: the dataviz reference palette's categorical slots 1-5, validated
# (tools: dataviz validate_palette.js) against this page's surfaces, #ffffff
# light and #152125 dark. Light slots 3-5 sit below 3:1 on white, so every
# chart carries a legend with labels and a table of its values.
VIZ_CSS = r"""
:root{--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--vgrid:#e1e0d9;--vbase:#c3c2b7;--vax:#6b6a65;--vmute:#b9c3c5}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--vgrid:#24353a;--vbase:#3a4d52;--vax:#9bb0b3;--vmute:#4a5d62}}
:root[data-theme="dark"]{--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--vgrid:#24353a;--vbase:#3a4d52;--vax:#9bb0b3;--vmute:#4a5d62}
.viz{margin:20px 0 28px;padding:16px 16px 12px;border:1px solid var(--rule);border-radius:8px;background:var(--surface)}
.viz figcaption{margin:0 0 8px}.viz figcaption strong{display:block;font-size:16px}
.viz figcaption span{display:block;color:var(--muted);font-size:14px;max-width:72ch}
.viz [data-chart]{width:100%;min-height:120px}
.viz svg{display:block;max-width:100%;overflow:visible}
.viz .grid{stroke:var(--vgrid);stroke-width:1}.viz .base{stroke:var(--vbase);stroke-width:1}
.viz .ax{fill:var(--vax);font:12px system-ui,-apple-system,"Segoe UI",sans-serif;font-variant-numeric:tabular-nums}
.viz .lab{fill:var(--ink);font:12.5px system-ui,-apple-system,"Segoe UI",sans-serif}
.viz .line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.viz .dot{stroke:var(--surface);stroke-width:2}.viz .dot.hollow{fill:var(--surface);stroke-width:2}
.viz .ref{stroke:var(--vax);stroke-width:1}
.viz .span{stroke:var(--vbase);stroke-width:2}
.viz .cross{stroke:var(--vax);stroke-width:1;opacity:0;pointer-events:none}
.viz .hit{fill:transparent;cursor:default}.viz .hit:focus{outline:none;fill:var(--accent-soft);fill-opacity:.35}
.viz .pin{fill:var(--surface);stroke:var(--vax);stroke-width:1}.viz .pin-n{fill:var(--ink);font:600 10px system-ui,sans-serif;text-anchor:middle}
.viz-legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin:4px 0 10px;padding:0;list-style:none;font-size:13.5px;color:var(--ink)}
.viz-legend li{display:flex;align-items:center;gap:6px;max-width:none}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px}.sw.ln{height:2px;width:16px;border-radius:1px}
.sw.dt{width:10px;height:10px;border-radius:50%}.sw.ho{width:10px;height:10px;border-radius:50%;background:transparent!important;border:2px solid var(--s1)}
.sw.rf{height:1px;width:16px;background:var(--vax)}
.viz-checks{margin:8px 0 4px;padding-left:22px;font-size:13.5px;color:var(--muted);columns:2 260px}
.viz-checks li{margin:2px 0}
.viz details{margin-top:8px;font-size:14px}.viz summary{cursor:pointer;color:var(--accent)}
.viz details .tw{max-height:360px;overflow:auto}
.viz-tip{position:absolute;display:none;z-index:10;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--rule);border-radius:6px;padding:8px 10px;font:13px system-ui,-apple-system,"Segoe UI",sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.12);max-width:300px}
.viz-tip-h{color:var(--muted);margin-bottom:4px}.viz-tip-r{display:flex;align-items:center;gap:6px;margin:2px 0}
.viz-tip-r strong{font-variant-numeric:tabular-nums}.viz-key{display:inline-block;width:12px;height:2px;border-radius:1px}
.kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:20px 0 28px}
.kpi{border:1px solid var(--rule);border-radius:8px;padding:12px 14px;background:var(--surface)}
.kpi .k{font-size:13px;color:var(--muted)}.kpi .v{font-size:28px;font-weight:600;line-height:1.2;margin:2px 0}
.kpi .d{font-size:13px;color:var(--muted)}
@media (max-width:560px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""


def git(*a):
    return subprocess.run(["git", "-C", str(REPO), *a], check=True, capture_output=True, text=True).stdout.strip()


def site_href(target: str) -> str:
    """A link in the markdown -> its page on the site, relative to site/pages/."""
    if re.match(r"^[a-z]+:", target) or target.startswith("#"):
        return target
    path, _, frag = target.partition("#")
    repo_path = posixpath.normpath(posixpath.join(posixpath.dirname(SRC), path))
    tracked = set(git("ls-files", "--", repo_path).splitlines())
    if repo_path not in tracked and not (REPO / repo_path).exists():
        sys.exit(f"render: link target {repo_path} does not exist; fix the source")
    if repo_path.endswith(".html"):
        html_path = repo_path
    elif repo_path.endswith(".md"):
        base = posixpath.basename(repo_path)
        html_path = (posixpath.dirname(repo_path) + "/index.html") if base in ("README.md", "index.md") \
            else repo_path[:-3] + ".html"
    else:
        html_path = repo_path
    rel = posixpath.relpath(html_path, PAGE_DIR)
    return rel + ("#" + frag if frag else "")


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def table(head, rows) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f'<details><summary>Table of these values</summary><div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div></details>'


def legend(items) -> str:
    """items: (kind, colorVar, label); kind is sw (box), ln (line), dt (dot), ho (hollow dot), rf (reference)."""
    li = "".join(f'<li><span class="sw {k}" style="background:var({c})" aria-hidden="true"></span>{esc(lab)}</li>'
                 for k, c, lab in items)
    return f'<ul class="viz-legend">{li}</ul>'


def figure(key, title, sub, aria, body_extra="", leg="", tbl=""):
    return (f'<figure class="viz"><figcaption><strong>{esc(title)}</strong><span>{esc(sub)}</span></figcaption>{leg}'
            f'<div data-chart="{key}" aria-label="{esc(aria)}"></div>{body_extra}{tbl}</figure>')


def d(s):
    return s[5:]


def charts(data):
    k, dd, runs = data["kpis"], data["defects"], data["runs"]
    rng = data["range"]
    out = {}
    tiles = [
        ("PR merges", f'{k["pr_merges"]:,}', f'{rng["base"]}..{rng["tip"]}'),
        ("Commits", f'{k["commits"]:,}', f'{k["non_merge_commits"]:,} non-merge'),
        ("Tests passing", f'{k["passing"]["tip"]:,}', f'15.0.8: {k["passing"]["base"]:,}'),
        ("Test cases (it calls)", f'{k["it_calls"]["tip"]:,}', f'15.0.8: {k["it_calls"]["base"]:,}'),
        ("Defects filed", f'{k["defect_ids"]:,}', f'{k["defect_ids_in_scope"]:,} in 15.0.9\'s scope'),
        ("Regressions caught before release", f'{k["regressions_caught"]}', "introduced by a fix, fixed on dev"),
    ]
    out["kpis"] = '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="k">{esc(a)}</div><div class="v">{esc(b)}</div><div class="d">{esc(c)}</div></div>'
        for a, b, c in tiles) + "</div>"

    m = data["merges_per_day"]
    out["merges"] = figure(
        "merges", "Pull requests merged each day",
        f"First-parent merges into dev, {d(m[0]['date'])} to {d(m[-1]['date'])}. Hover a day for its PR numbers.",
        "Column chart of pull requests merged per day",
        tbl=table(["date", "PRs merged", "PR numbers"],
                  [(x["date"], x["count"], ", ".join(f"#{p}" for p in x["prs"])) for x in m if x["count"]]))

    checks = "".join(f'<li value="{i + 1}">{esc(d(c["date"]))}: {esc(c["label"])}</li>' for i, c in enumerate(data["checks"]))
    out["arrival"] = figure(
        "arrival", "Defects filed each day, by where they were found",
        "Register entries in 15.0.9's scope, by the day each was first written down. The numbered pins mark the "
        "day a new kind of check was first run; filings rise with each new check and fall once it stops finding new ones.",
        "Stacked column chart of register entries filed per day by origin",
        body_extra=f'<ol class="viz-checks">{checks}</ol>',
        leg=legend([("", c, lab) for _, lab, c in ORIGINS]),
        tbl=table(["date"] + [lab for _, lab, _ in ORIGINS] + ["not in 15.0.9"],
                  [(x["date"], *[x["filed"][o] for o, _, _ in ORIGINS], x["filed_out_of_scope"])
                   for x in dd if sum(x["filed"].values()) or x["filed_out_of_scope"]]))

    out["burnup"] = figure(
        "burnup", "Filed and closed, running totals",
        "The gap between the two lines is what is still open. Closed means merged to dev, closed, or decided; "
        "entries carried as known issues stay open.",
        "Line chart of cumulative register entries filed and closed",
        leg=legend([("ln", "--s1", "filed"), ("ln", "--s3", "closed")]),
        tbl=table(["date", "filed (total)", "closed (total)", "open"],
                  [(x["date"], x["filed_cum"], x["closed_cum"], x["filed_cum"] - x["closed_cum"]) for x in dd]))

    out["tests"] = figure(
        "tests", "Tests passing, by release-candidate run",
        "Full suite on each candidate tree. Filled points are runs across six (or more) Node and MongoDB "
        "combinations; hollow points are one merge checked on its own branch or in CI. A count can fall when a "
        "unit is removed from a candidate.",
        "Line chart of passing tests by run",
        leg=legend([("dt", "--s1", "six-cell run (or more)"), ("ho", "--s1", "one merge, one cell or CI"), ("rf", "--vax", "15.0.8 baseline")]),
        tbl=table(["run", "date", "cells", "passing"], [(r["label"], r["date"], r["cells"] or "not recorded", r["passing"]) for r in runs]))

    reg = data["regressions"]
    out["regressions"] = figure(
        "regressions", "Seven regressions, from cause to fix",
        "Each row is a defect a merged fix introduced on dev. None reached a release.",
        "Dot plot of regression cause, filing and fix dates",
        leg=legend([("dt", "--s1", "cause merged"), ("dt", "--s2", "found and filed"), ("dt", "--s3", "fix merged")]),
        tbl=table(["id", "cause merged", "filed", "fix merged", "family"],
                  [(r["id"], f'#{r["cause_pr"]}, {r["caused"]}', r["filed"], f'#{r["fix_pr"]}, {r["fixed"]}', r["family"]) for r in reg]))
    oe = data.get("open_entries") or []
    out["open"] = figure(
        "open", "The open entries, by what is planned for each",
        f"All {sum(o['count'] for o in oe)} register entries in 15.0.9's scope that are not closed. "
        "The highlighted rows are the ones with no decision recorded yet.",
        "Bar chart of open register entries by disposition",
        leg=legend([("", "--s1", "no decision recorded yet"), ("", "--vmute", "decided or planned")]),
        tbl=table(["disposition", "count", "entries"], [(o["disposition"], o["count"], ", ".join(o["ids"])) for o in oe]))
    return out


def main():
    md_text = (REPO / SRC).read_text(encoding="utf-8")
    data = json.loads((REPO / DATA).read_text(encoding="utf-8"))
    commit = git("log", "-1", "--format=%h", "--", SRC, DATA)
    date = git("log", "-1", "--format=%cs", "--", SRC, DATA)
    lines = md_text.splitlines()
    assert lines[0].startswith("# "), "source must start with its H1"
    title = lines[0][2:].strip()
    body = "\n".join(lines[1:])
    figs = charts(data)
    used = set(re.findall(r"<!-- chart: (\w+) -->", body))
    missing = used - set(figs)
    if missing:
        sys.exit(f"render: unknown chart marker(s) {sorted(missing)}")
    body = re.sub(r"<!-- chart: (\w+) -->", lambda mm: f"\n\nCHART_{mm.group(1)}\n\n", body)
    md = markdown.Markdown(extensions=["tables", "toc"], extension_configs={"toc": {"toc_depth": "2"}})
    content = md.convert(body)
    # the markdown's pointer to this page is dropped from the page itself
    content = re.sub(r"<p>[^<]*<a href=\"[^\"]*cgm-remote-monitor-15\.0\.9-colophon\.html\">.*?</p>\n?", "", content, flags=re.S)
    content = re.sub(r'href="([^"]+)"', lambda mm: 'href="%s"' % esc(site_href(html.unescape(mm.group(1)))), content)
    content = content.replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")
    content = content.replace("\\|", "|")  # a table cell's escaped pipe, inside code
    for key, frag in figs.items():
        content = content.replace(f"<p>CHART_{key}</p>", frag)
    first = re.match(r"\s*(<p><em>.*?</em></p>)", content, re.S)
    if not first:
        sys.exit("render: the status paragraph was not found")
    meta = first.group(1)
    content = content[first.end():]
    toks = md.toc_tokens[0]["children"] if md.toc_tokens and md.toc_tokens[0].get("children") else md.toc_tokens
    toc = "".join(f'<li><a href="#{t["id"]}">{esc(t["name"])}</a></li>' for t in toks)
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = f"""<!doctype html>
<!-- Generated by tools/site/render_colophon.py from {SRC} and {DATA} at {commit}. Do not edit by hand; re-run the script. Living page: see site/pages/pages.yaml. -->
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{BASE_CSS}{VIZ_CSS}</style></head><body>
<div class="wrap">
<header class="top">
<h1>{esc(title)}</h1><div class="meta">{meta}</div>
<p class="src">Living document, rendered from <a href="{site_href(posixpath.basename(SRC))}"><code>{SRC}</code></a> and its data file, last changed {date} at <code>{commit}</code>. Chart data measured {esc(data["measured"])} on <code>{esc(data["range"]["base"])}..{esc(data["range"]["tip"])}</code>.</p></header>
<div class="grid"><nav class="toc" aria-label="Sections"><div class="cap">On this page</div><ol>{toc}</ol></nav>
<main class="doc">{content}</main></div></div>
<script type="application/json" id="colophon-data">{payload}</script>
<script>{JS.read_text(encoding="utf-8")}</script>
</body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} from {SRC} + {DATA} at {commit} ({date})")


if __name__ == "__main__":
    main()
