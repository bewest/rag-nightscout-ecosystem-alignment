#!/usr/bin/env python3
"""Render site/pages/nightscout-ecosystem-programme.html from
docs/00-overview/ECOSYSTEM-PROGRAMME.md.

The page is a LIVING rich page (site/pages/pages.yaml): its content is the
markdown, converted as-is. The layout and CSS follow the earlier artifact
design. The only additions are page chrome: the table of contents (built from
the headings), the layer figure drawn from the markdown's own text diagram in
§2, and one provenance line naming the source and commit.

    tools/site/.venv/bin/python tools/site/render_programme.py

Then set `source_commit` for the page in site/pages/pages.yaml to the commit
that last changed the source (the script prints it).
"""
from __future__ import annotations

import html
import posixpath
import re
import subprocess
import sys
from pathlib import Path

import markdown

REPO = Path(__file__).resolve().parents[2]
SRC = "docs/00-overview/ECOSYSTEM-PROGRAMME.md"
OUT = REPO / "site/pages/nightscout-ecosystem-programme.html"
PAGE_DIR = "site/pages"


def git(*a):
    return subprocess.run(["git", "-C", str(REPO), *a], check=True, capture_output=True, text=True).stdout.strip()


def site_href(target: str) -> str:
    """A link in the markdown -> its page on the site, relative to site/pages/."""
    if re.match(r"^[a-z]+:", target) or target.startswith("#"):
        return target
    path, _, frag = target.partition("#")
    repo_path = posixpath.normpath(posixpath.join(posixpath.dirname(SRC), path))
    tracked = set(git("ls-files", "--", repo_path).splitlines())
    if repo_path not in tracked:
        sys.exit(f"render: link target {repo_path} is not a tracked file; fix the source")
    if not repo_path.endswith(".md"):
        sys.exit(f"render: link target {repo_path} is not a page")
    base = posixpath.basename(repo_path)
    html_path = (posixpath.dirname(repo_path) + "/index.html") if base in ("README.md", "index.md") \
        else repo_path[:-3] + ".html"
    rel = posixpath.relpath(html_path, PAGE_DIR)
    return rel + ("#" + frag if frag else "")


FIGURE = """<figure class="layers" aria-label="The five layers">
<div class="shared"><div class="cap">shared, stewarded by the foundation</div>
<div class="L"><span class="n">5</span>Forward platform <small>MCP, agent-readable APIs</small></div>
<div class="L"><span class="n">4</span>Research and quality commons</div>
<div class="L"><span class="n">3</span>Identity and trust</div>
<div class="L"><span class="n">2</span>Interoperability commons</div></div>
<div class="L ref"><span class="n">1</span>Reference implementation: cgm-remote-monitor</div>
<div class="side"><div class="cap"><span class="arrow" aria-hidden="true">&larr;&rarr;</span> built and run by each project</div>
<ul><li>Nightscout (cgm-remote-monitor)</li><li>Nocturne</li><li>hosted operators</li><li>other compatible servers</li></ul>
<ul><li>Loop, Trio, AndroidAPS, xDrip+,</li><li>followers, reports, researchers</li></ul></div>
</figure>"""

CSS = r"""
:root{--bg:#f6f8f8;--surface:#ffffff;--ink:#17262a;--muted:#55686d;--rule:#d5dfe0;--accent:#1d6b73;--accent-soft:#e2eff0;--warn:#8a5a00;--warn-soft:#fbf1dc;--code:#eef3f3}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#0f1719;--surface:#152125;--ink:#e3ecec;--muted:#9bb0b3;--rule:#2a3b3f;--accent:#6cc3cb;--accent-soft:#1a3236;--warn:#f0c26a;--warn-soft:#352a14;--code:#1b2a2e}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#0f1719;--surface:#152125;--ink:#e3ecec;--muted:#9bb0b3;--rule:#2a3b3f;--accent:#6cc3cb;--accent-soft:#1a3236;--warn:#f0c26a;--warn-soft:#352a14;--code:#1b2a2e}
*{box-sizing:border-box}
html{scroll-padding-top:16px}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.62 "Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
img{max-width:100%}
.wrap{max-width:1120px;margin:0 auto;padding:40px 16px 80px}
.cap{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
h1{font-size:clamp(28px,4.2vw,40px);line-height:1.15;margin:8px 0 16px;text-wrap:balance;font-weight:700;max-width:24ch}
h2{font-size:22px;margin:44px 0 12px;text-wrap:balance;padding-top:12px;border-top:1px solid var(--rule)}
h2:first-child{margin-top:0;border-top:0;padding-top:0}
p,li{max-width:68ch}
a{color:var(--accent);text-underline-offset:2px;overflow-wrap:anywhere}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
code{font:13.5px/1.4 "JetBrains Mono",ui-monospace,Menlo,monospace;background:var(--code);padding:1px 5px;border-radius:3px;overflow-wrap:anywhere}
.meta{background:var(--warn-soft);border-left:3px solid var(--warn);padding:12px 16px;max-width:78ch;border-radius:0 4px 4px 0}
.meta p{margin:0;font-size:15px}.meta strong{color:var(--warn)}
.src{font-size:13px;color:var(--muted);margin-top:12px}
.grid{display:grid;grid-template-columns:200px minmax(0,1fr);gap:48px;margin-top:40px}
.toc{position:sticky;top:20px;align-self:start;font-size:14px}
.toc ol{list-style:none;padding-left:0;margin:8px 0 0;display:grid;gap:6px}.toc a{color:var(--ink);text-decoration:none}.toc a:hover{color:var(--accent)}
.doc{min-width:0}
.tw{overflow-x:auto;margin:16px 0;border:1px solid var(--rule);border-radius:6px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:14.5px;font-variant-numeric:tabular-nums}
th,td{text-align:left;vertical-align:top;padding:9px 12px;border-bottom:1px solid var(--rule)}
th{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);background:var(--accent-soft)}
tr:last-child td{border-bottom:0}
.layers{margin:20px 0 28px;display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:12px 20px;align-items:start}
.shared{border:1.5px solid var(--accent);border-radius:8px;padding:12px;display:grid;gap:8px;background:var(--accent-soft)}
.L{background:var(--surface);border:1px solid var(--rule);border-radius:5px;padding:9px 12px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;font-weight:600}
.L small{font-weight:400;color:var(--muted)}
.n{font:500 13px "JetBrains Mono",monospace;color:var(--accent);min-width:1ch}
.ref{grid-column:1;border-style:dashed}
.side{grid-column:2;grid-row:1 / span 2;border:1px solid var(--rule);border-radius:8px;padding:12px;background:var(--surface)}
.side ul{margin:6px 0 14px;padding-left:18px}.side li{margin:2px 0}
.arrow{color:var(--accent);font-weight:700;margin-right:4px}
@media (max-width:820px){.grid{grid-template-columns:1fr;gap:24px}.toc{position:static}.layers{grid-template-columns:1fr}.side{grid-column:1;grid-row:auto}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
"""


def main():
    md_text = (REPO / SRC).read_text(encoding="utf-8")
    commit = git("log", "-1", "--format=%h", "--", SRC)
    date = git("log", "-1", "--format=%cs", "--", SRC)
    lines = md_text.splitlines()
    assert lines[0].startswith("# "), "source must start with its H1"
    title = lines[0][2:].strip()
    body = "\n".join(lines[1:])
    # the §2 text diagram becomes the figure (same entries, same wording)
    fence = re.search(r"\n```\n(.*?)\n```\n", body, re.S)
    if not fence:
        sys.exit("render: the §2 text diagram was not found; update the figure by hand")
    diagram = fence.group(1)
    for must in ["Forward platform", "MCP, agent-readable APIs", "Research and quality commons",
                 "Identity and trust", "Interoperability commons", "Reference implementation: cgm-remote-monitor",
                 "Nightscout (cgm-remote-monitor)", "Nocturne", "hosted operators", "other compatible servers",
                 "Loop, Trio, AndroidAPS, xDrip+,", "followers, reports, researchers",
                 "shared, stewarded by the foundation", "built and run by each project"]:
        if must not in diagram:
            sys.exit(f"render: the §2 diagram no longer says {must!r}; redraw the figure")
    body = body[:fence.start()] + "\n\nFIGURE_PLACEHOLDER\n\n" + body[fence.end():]
    md = markdown.Markdown(extensions=["tables", "toc"], extension_configs={"toc": {"toc_depth": "2"}})
    content = md.convert(body)
    content = content.replace("<p>FIGURE_PLACEHOLDER</p>", FIGURE)
    content = re.sub(r'href="([^"]+)"', lambda m: 'href="%s"' % html.escape(site_href(html.unescape(m.group(1))), quote=True), content)
    content = re.sub(r"<table>", '<div class="tw"><table>', content)
    content = content.replace("</table>", "</table></div>")
    # the opening italic paragraph is the document's status note
    first = re.match(r"\s*(<p><em>.*?</em></p>)", content, re.S)
    if not first:
        sys.exit("render: the status paragraph was not found")
    meta = first.group(1)
    content = content[first.end():]
    toc = "".join(f'<li><a href="#{t["id"]}">{html.escape(t["name"])}</a></li>' for t in md.toc_tokens[0]["children"]) \
        if md.toc_tokens and md.toc_tokens[0].get("children") else \
        "".join(f'<li><a href="#{t["id"]}">{html.escape(t["name"])}</a></li>' for t in md.toc_tokens)
    page = f"""<!doctype html>
<!-- Generated by tools/site/render_programme.py from {SRC} at {commit}. Do not edit by hand; re-run the script. Living page: see site/pages/pages.yaml. -->
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{CSS}</style></head><body>
<div class="wrap">
<header class="top">
<h1>{html.escape(title)}</h1><div class="meta">{meta}</div>
<p class="src">Living document, rendered from <a href="{site_href(posixpath.basename(SRC))}"><code>{SRC}</code></a>, last changed {date} at <code>{commit}</code>.</p></header>
<div class="grid"><nav class="toc" aria-label="Sections"><div class="cap">On this page</div><ol>{toc}</ol></nav>
<main class="doc">{content}</main></div></div>
</body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} from {SRC} at {commit} ({date})")


if __name__ == "__main__":
    main()
