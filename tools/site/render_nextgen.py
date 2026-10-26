#!/usr/bin/env python3
"""Render site/pages/nightscout-next-gen-platform.html from
docs/30-design/platform/next-gen-platform-plan.md and next-gen-platform-plan.json.

A LIVING rich page (site/pages/pages.yaml). Its text is the markdown, converted
as-is, in the programme page's layout. Three markers in the markdown become
figures drawn from the JSON:

    <!-- chart: map -->        the dependency map (tools/site/nextgen-map.js),
                               with a table of every item that needs no script
    <!-- chart: decisions -->  one card per open decision, each naming the
                               items it holds up
    <!-- chart: options -->    the seam options side by side

    tools/site/.venv/bin/python tools/site/render_nextgen.py

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
from render_colophon import VIZ_CSS  # noqa: E402  (the validated chart tokens)

REPO = Path(__file__).resolve().parents[2]
SRC = "docs/30-design/platform/next-gen-platform-plan.md"
DATA = "docs/30-design/platform/next-gen-platform-plan.json"
JS = REPO / "tools/site/nextgen-map.js"
OUT = REPO / "site/pages/nightscout-next-gen-platform.html"
PAGE_DIR = "site/pages"

MAP_CSS = r"""
.map-filter{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 12px}
.chip{display:inline-flex;align-items:center;gap:6px;font:13.5px system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--surface);border:1px solid var(--rule);border-radius:999px;padding:4px 12px;cursor:pointer}
.chip:not(.on){color:var(--muted);opacity:.6}.chip:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.map-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:6px}
.viz .band{fill:transparent}.viz .band.b1{fill:var(--accent-soft);fill-opacity:.35}
.viz .edge{fill:none;stroke:var(--vbase);stroke-width:1.5}.viz .arrowhead{fill:var(--vbase)}
.viz .node{cursor:pointer}.viz .node:focus{outline:none}
.viz .node .box{fill:var(--surface);stroke:var(--vbase);stroke-width:1}
.viz .node.st-done .box{fill:var(--accent-soft);stroke:var(--c)}
.viz .node.st-review .box{stroke:var(--c);stroke-width:2}
.viz .node.st-decision .box{stroke:var(--warn);stroke-dasharray:4 3;stroke-width:1.5}
.viz .node.st-planned .box{stroke-dasharray:2 3}
.viz .node:focus .box,.viz .node:hover .box{stroke-width:2.5}
.viz .nid{fill:var(--ink);font:600 12px "JetBrains Mono",monospace}
.viz .ntl{fill:var(--ink);font:12.5px system-ui,-apple-system,"Segoe UI",sans-serif}
.viz .nst{fill:var(--muted);font:11px system-ui,-apple-system,"Segoe UI",sans-serif}
.viz svg.focus .node{opacity:.28}.viz svg.focus .edge{opacity:.15}
.viz svg.focus .node.on,.viz svg.focus .node.up,.viz svg.focus .node.down,.viz svg.focus .node.held{opacity:1}
.viz svg.focus .node.on .box{stroke-width:3}.viz svg.focus .node.held .box{stroke:var(--warn);stroke-width:3}
.viz svg.focus .node.down .box{stroke-dasharray:5 3}
.viz svg.focus .edge.on{opacity:1;stroke:var(--accent);stroke-width:2}
.viz .node.dim,.viz .edge.dim{display:none}
.map-detail{margin:12px 0 0;padding:12px 14px;border:1px solid var(--rule);border-radius:8px;background:var(--bg);font-size:14.5px}
.map-detail .dh{font-size:13px;color:var(--muted)}.map-detail p{margin:4px 0 8px}.map-detail .mut{color:var(--muted)}
.dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:0}.dl dt{color:var(--muted);font-size:13px}.dl dd{margin:0}
.map-key{display:flex;flex-wrap:wrap;gap:6px 18px;margin:6px 0 4px;padding:0;list-style:none;font-size:13px;color:var(--muted)}
.map-key li{max-width:none}
.dcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin:18px 0 26px}
.dcard{border:1px solid var(--rule);border-left:4px solid var(--warn);border-radius:8px;background:var(--surface);padding:12px 14px;font-size:14.5px}
.dcard.on{box-shadow:0 0 0 2px var(--warn)}
.dcard h3{font-size:15.5px;margin:0 0 4px}.dcard .who{font-size:12.5px;color:var(--muted);margin:0 0 8px}
.dcard ol{margin:6px 0;padding-left:20px}.dcard li{margin:4px 0;max-width:none}
.dcard .rec{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);font-weight:700;margin-left:6px}
.dcard .gr{display:block;color:var(--muted);font-size:13.5px}
.dcard button{margin-top:6px;font:13px system-ui,sans-serif;color:var(--accent);background:none;border:1px solid var(--rule);border-radius:6px;padding:4px 10px;cursor:pointer}
.opts{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin:18px 0 26px}
.opt{border:1px solid var(--rule);border-radius:8px;background:var(--surface);padding:12px 14px;font-size:14.5px}
.opt.pick{border:2px solid var(--accent)}
.opt h3{font-size:15.5px;margin:0 0 6px}.opt .tag{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);font-weight:700}
.opt dl{display:grid;grid-template-columns:1fr;gap:2px;margin:8px 0 0}.opt dt{color:var(--muted);font-size:12.5px;margin-top:6px}.opt dd{margin:0}
"""


def git(*a):
    return subprocess.run(["git", "-C", str(REPO), *a], check=True, capture_output=True, text=True).stdout.strip()


def site_href(target: str, base: str = SRC) -> str:
    """A link in the markdown or the data -> its page on the site, relative to site/pages/."""
    if re.match(r"^[a-z]+:", target) or target.startswith("#"):
        return target
    path, _, frag = target.partition("#")
    repo_path = posixpath.normpath(posixpath.join(posixpath.dirname(base), path))
    if not (REPO / repo_path).exists():
        sys.exit(f"render: link target {repo_path} does not exist; fix the source")
    if repo_path.endswith(".md"):
        b = posixpath.basename(repo_path)
        html_path = (posixpath.dirname(repo_path) + "/index.html") if b in ("README.md", "index.md") \
            else repo_path[:-3] + ".html"
    else:
        html_path = repo_path
    rel = posixpath.relpath(html_path, PAGE_DIR)
    return rel + ("#" + frag if frag else "")


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def check(data):
    """Refuse a data file whose references do not resolve."""
    tracks = {t["id"] for t in data["tracks"]}
    phases = {p["id"] for p in data["phases"]}
    states = {s["id"] for s in data["states"]}
    ids = [i["id"] for i in data["items"]]
    errs = []
    if len(ids) != len(set(ids)):
        errs.append("duplicate item ids")
    for it in data["items"]:
        for k, allowed in (("track", tracks), ("phase", phases), ("state", states)):
            if it.get(k) not in allowed:
                errs.append(f"{it['id']}: unknown {k} {it.get(k)!r}")
        for d in it.get("depends", []):
            if d not in ids:
                errs.append(f"{it['id']}: depends on unknown {d}")
    for d in data["decisions"]:
        for h in d.get("holds", []):
            if h not in ids:
                errs.append(f"decision {d['id']}: holds unknown {h}")
    if errs:
        sys.exit("render: " + "; ".join(errs))


def figures(data):
    st = {s["id"]: s for s in data["states"]}
    trk = {t["id"]: t for t in data["tracks"]}
    ph = {p["id"]: p for p in data["phases"]}
    for it in data["items"]:
        if it.get("ref_href"):
            it["ref_href"] = site_href(it["ref_href"], DATA)
        for s in it.get("spec", []):
            s["href"] = site_href(s["href"], DATA)
    key = "".join(f'<li>{esc(s["mark"])} {esc(s["label"])}: {esc(s["means"])}</li>' for s in data["states"])
    rows = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in (
            f"<code>{esc(i['id'])}</code>", esc(trk[i["track"]]["label"]), esc(ph[i["phase"]]["label"]),
            esc(st[i["state"]]["label"]), esc(i["title"]),
            ", ".join(esc(x) for x in i.get("depends", [])) or "none",
            (f'<a href="{esc(i["ref_href"])}">{esc(i["ref"])}</a>' if i.get("ref_href") else esc(i.get("ref", ""))),
        )) + "</tr>" for i in data["items"])
    out = {}
    out["map"] = (
        '<figure class="viz"><figcaption><strong>Work items, by track and phase</strong>'
        '<span>Select an item to see what it needs and what waits on it; select a track to hide or show it. '
        'Arrows run from a prerequisite to the item that needs it.</span></figcaption>'
        '<div id="map-filter" class="map-filter" role="group" aria-label="Tracks"></div>'
        f'<div data-chart="map"></div><ul class="map-key">{key}</ul>'
        '<div id="map-detail" class="map-detail" hidden aria-live="polite"></div>'
        '<details><summary>Table of every item</summary><div class="tw"><table><thead><tr>'
        '<th>item</th><th>track</th><th>phase</th><th>state</th><th>what</th><th>needs</th><th>branch or PR</th>'
        f'</tr></thead><tbody>{rows}</tbody></table></div></details></figure>')
    cards = []
    for d in data["decisions"]:
        opts = "".join(
            f'<li><strong>{esc(o["label"])}</strong>{"<span class=rec>recommended</span>" if o.get("recommended") else ""}'
            f'<span class="gr">Gains: {esc(o["gains"])}</span><span class="gr">Risks: {esc(o["risks"])}</span></li>'
            for o in d["options"])
        cards.append(
            f'<article class="dcard" id="d-{esc(d["id"])}"><h3>{esc(d["id"])}: {esc(d["short"])}</h3>'
            f'<p class="who">{esc(d["owner"])} · holds up {", ".join(esc(h) for h in d.get("holds", [])) or "nothing yet"}</p>'
            f'<p>{esc(d["question"])}</p><ol>{opts}</ol>'
            f'<button type="button" data-decision="{esc(d["id"])}">Show on the map</button></article>')
    out["decisions"] = f'<div class="dcards">{"".join(cards)}</div>'
    opts = []
    for o in data["seam_options"]:
        dl = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in o["facts"])
        opts.append(f'<article class="opt{" pick" if o.get("pick") else ""}">'
                    f'{"<div class=tag>" + esc(o["pick"]) + "</div>" if o.get("pick") else ""}'
                    f'<h3>{esc(o["label"])}</h3><p>{esc(o["summary"])}</p><dl>{dl}</dl></article>')
    out["options"] = f'<div class="opts">{"".join(opts)}</div>'
    return out


def main():
    md_text = (REPO / SRC).read_text(encoding="utf-8")
    data = json.loads((REPO / DATA).read_text(encoding="utf-8"))
    check(data)
    commit = git("log", "-1", "--format=%h", "--", SRC, DATA) or "uncommitted"
    date = git("log", "-1", "--format=%cs", "--", SRC, DATA) or "not yet committed"
    lines = md_text.splitlines()
    assert lines[0].startswith("# "), "source must start with its H1"
    title = lines[0][2:].strip()
    body = "\n".join(lines[1:])
    figs = figures(data)
    used = set(re.findall(r"<!-- chart: (\w+) -->", body))
    if used - set(figs):
        sys.exit(f"render: unknown chart marker(s) {sorted(used - set(figs))}")
    body = re.sub(r"<!-- chart: (\w+) -->", lambda mm: f"\n\nCHART_{mm.group(1)}\n\n", body)
    md = markdown.Markdown(extensions=["tables", "toc"], extension_configs={"toc": {"toc_depth": "2"}})
    content = md.convert(body)
    content = re.sub(r"<p>[^<]*<a href=\"[^\"]*nightscout-next-gen-platform\.html\">.*?</p>\n?", "", content, flags=re.S)
    content = re.sub(r'href="([^"]+)"', lambda mm: 'href="%s"' % esc(site_href(html.unescape(mm.group(1)))), content)
    content = content.replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")
    content = content.replace("\\|", "|")
    for k, frag in figs.items():
        content = content.replace(f"<p>CHART_{k}</p>", frag)
    first = re.match(r"\s*(<p><em>.*?</em></p>)", content, re.S)
    if not first:
        sys.exit("render: the status paragraph was not found")
    meta = first.group(1)
    content = content[first.end():]
    toks = md.toc_tokens[0]["children"] if md.toc_tokens and md.toc_tokens[0].get("children") else md.toc_tokens
    toc = "".join(f'<li><a href="#{t["id"]}">{esc(t["name"])}</a></li>' for t in toks)
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = f"""<!doctype html>
<!-- Generated by tools/site/render_nextgen.py from {SRC} and {DATA} at {commit}. Do not edit by hand; re-run the script. Living page: see site/pages/pages.yaml. -->
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{BASE_CSS}{VIZ_CSS}{MAP_CSS}</style></head><body>
<div class="wrap">
<header class="top">
<h1>{esc(title)}</h1><div class="meta">{meta}</div>
<p class="src">Living document, rendered from <a href="{site_href(posixpath.basename(SRC))}"><code>{SRC}</code></a> and its data file, last changed {date} at <code>{commit}</code>. Item states measured {esc(data["measured"])}.</p></header>
<div class="grid"><nav class="toc" aria-label="Sections"><div class="cap">On this page</div><ol>{toc}</ol></nav>
<main class="doc">{content}</main></div></div>
<script type="application/json" id="nextgen-data">{payload}</script>
<script>{JS.read_text(encoding="utf-8")}</script>
</body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} from {SRC} + {DATA} at {commit} ({date})")


if __name__ == "__main__":
    main()
