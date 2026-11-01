#!/usr/bin/env python3
"""Render the 16.0.0 release colophon and its accessible evidence charts."""
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
from render_programme import CSS as BASE_CSS
from render_colophon import VIZ_CSS

REPO = Path(__file__).resolve().parents[2]
SRC = "releases/cgm-remote-monitor-16.0.0/colophon.md"
DATA = "releases/cgm-remote-monitor-16.0.0/colophon-data.json"
OUT = REPO / "site/pages/cgm-remote-monitor-16.0.0-colophon.html"
PAGE_DIR = "site/pages"
COLORS = {
    "Defect": "var(--s5)",
    "Bug fix": "var(--s3)",
    "Decided": "var(--s1)",
    "No value change": "var(--s4)",
    "pending": "var(--s4)",
    "blocked": "var(--s5)",
    "complete": "var(--s3)",
}


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def git(*args) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def site_href(target: str) -> str:
    if re.match(r"^[a-z]+:", target) or target.startswith("#"):
        return target
    path, _, fragment = target.partition("#")
    repo_path = posixpath.normpath(posixpath.join(posixpath.dirname(SRC), path))
    if not (REPO / repo_path).exists():
        sys.exit(f"render: link target {repo_path} does not exist; fix the source")
    if repo_path.endswith(".md"):
        name = posixpath.basename(repo_path)
        html_path = (
            posixpath.dirname(repo_path) + "/index.html"
            if name in ("README.md", "index.md")
            else repo_path[:-3] + ".html"
        )
    else:
        html_path = repo_path
    return posixpath.relpath(html_path, PAGE_DIR) + (
        "#" + fragment if fragment else ""
    )


def table(headers, rows) -> str:
    head = "".join(f"<th>{esc(value)}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return (
        '<details><summary>Table of these values</summary><div class="tw"><table><thead><tr>'
        + head
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div></details>"
    )


def bar_chart(key: str, title: str, description: str, rows, value_key: str) -> str:
    width, left, right, row_height = 860, 290, 70, 34
    height = max(100, 54 + row_height * len(rows))
    max_value = max((row[value_key] for row in rows), default=0) or 1
    plot_width = width - left - right
    bars = []
    for index, row in enumerate(rows):
        y = 22 + index * row_height
        value = row[value_key]
        color = COLORS.get(row.get("status", row.get("verdict", "")), "var(--s2)")
        bars.append(
            f'<text class="lab" x="{left - 10}" y="{y + 15}" text-anchor="end">'
            f"{esc(row['label'])}</text>"
            f'<rect x="{left}" y="{y}" width="{max(1, plot_width * value / max_value):.1f}" '
            f'height="21" rx="3" fill="{color}"></rect>'
            f'<text class="ax" x="{left + plot_width * value / max_value + 7:.1f}" '
            f'y="{y + 15}">{value:,}</text>'
        )
    svg = (
        f'<svg role="img" aria-labelledby="{key}-title {key}-desc" viewBox="0 0 {width} {height}" '
        f'width="100%" height="{height}"><title id="{key}-title">{esc(title)}</title>'
        f'<desc id="{key}-desc">{esc(description)}</desc>'
        + "".join(bars)
        + "</svg>"
    )
    return (
        f'<figure class="viz"><figcaption><strong>{esc(title)}</strong>'
        f"<span>{esc(description)}</span></figcaption>{svg}"
        + table(["Category", value_key.replace("_", " ")], [(row["label"], row[value_key]) for row in rows])
        + "</figure>"
    )


def figures(data):
    matrix = data["matrix"]
    runs = bar_chart(
        "matrix-runs",
        "Repeated endpoint runs",
        "Cells recorded in each fresh run. Repeatability is checked separately against the per-cell output.",
        [{"label": f"{r['tree']} · run {r['run']}", "cells": r["cells"]} for r in matrix["runs"]],
        "cells",
    )
    origin = bar_chart(
        "origin-split",
        "Where changed outcomes first appear",
        "Final changed cells split across the historical pre-identity dev anchor; this does not attribute changes to individual PRs.",
        matrix["origin_split"],
        "cells",
    )
    outcomes = bar_chart(
        "changed-groups",
        "Changed cells by behavior group",
        "These are measured differences, not counts of affected real-world writes. The verdict colors distinguish defects, fixes, and decided changes.",
        matrix["groups"],
        "cells",
    )
    clients = bar_chart(
        "client-shapes",
        "Client shapes matched to changed behavior",
        "Unique client implementations with source-documented request shapes matching each group; this is a prediction, not a live-client test.",
        data["client_impact"]["groups"],
        "clients",
    )
    readiness = "".join(
        f'<tr><td><span class="gate {esc(g["status"])}">{esc(g["status"])}</span></td>'
        f"<td>{esc(g['gate'])}</td><td>{esc(g['evidence'])}</td></tr>"
        for g in data["readiness"]["gates"]
    )
    gate_table = (
        '<figure class="viz"><figcaption><strong>Release gates</strong>'
        '<span>Readiness is determined by evidence and scope, not by the number of merged changes.</span>'
        f"</figcaption><div class=\"tw\"><table><thead><tr><th>Status</th><th>Gate</th><th>Evidence</th>"
        f"</tr></thead><tbody>{readiness}</tbody></table></div></figure>"
    )
    return {
        "matrix-runs": runs,
        "origin-split": origin,
        "changed-groups": outcomes,
        "client-shapes": clients,
        "release-gates": gate_table,
    }


def main():
    source = (REPO / SRC).read_text(encoding="utf-8")
    data = json.loads((REPO / DATA).read_text(encoding="utf-8"))
    commit = git("log", "-1", "--format=%h", "--", SRC, DATA) or "uncommitted"
    date = git("log", "-1", "--format=%cs", "--", SRC, DATA) or "not yet committed"
    lines = source.splitlines()
    if not lines or not lines[0].startswith("# "):
        sys.exit("render: source must start with an H1")
    title = lines[0][2:].strip()
    body = "\n".join(lines[1:])
    rendered = figures(data)
    used = set(re.findall(r"<!-- chart: ([\w-]+) -->", body))
    if missing := used - set(rendered):
        sys.exit(f"render: unknown chart marker(s) {sorted(missing)}")
    body = re.sub(
        r"<!-- chart: ([\w-]+) -->",
        lambda match: f"\n\nCHART_{match.group(1)}\n\n",
        body,
    )
    md = markdown.Markdown(extensions=["tables", "toc"], extension_configs={"toc": {"toc_depth": "2"}})
    content = md.convert(body)
    content = re.sub(
        r'href="([^"]+)"',
        lambda match: 'href="%s"' % esc(site_href(html.unescape(match.group(1)))),
        content,
    )
    content = content.replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")
    for key, fragment in rendered.items():
        content = content.replace(f"<p>CHART_{key}</p>", fragment)
    first = re.match(r"\s*(<p><em>.*?</em></p>)", content, re.S)
    if not first:
        sys.exit("render: status paragraph not found")
    meta = first.group(1)
    content = content[first.end():]
    toc_items = md.toc_tokens[0]["children"] if md.toc_tokens and md.toc_tokens[0].get("children") else md.toc_tokens
    toc = "".join(f'<li><a href="#{esc(item["id"])}">{esc(item["name"])}</a></li>' for item in toc_items)
    page = f"""<!doctype html>
<!-- Generated by tools/site/render_cgm1600_colophon.py from {SRC} and {DATA} at {commit}. -->
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{BASE_CSS}{VIZ_CSS}
.gate{{display:inline-block;padding:2px 8px;border:1px solid var(--rule);border-radius:999px;font-size:12px;text-transform:uppercase}}
.gate.complete{{color:var(--s3)}}.gate.pending{{color:var(--s4)}}.gate.blocked{{color:var(--s5)}}
</style></head><body><div class="wrap"><header class="top"><h1>{esc(title)}</h1><div class="meta">{meta}</div>
<p class="src">Living document, rendered from <a href="{esc(site_href(posixpath.basename(SRC)))}"><code>{SRC}</code></a> and its data, last changed {esc(date)} at <code>{esc(commit)}</code>. Measurement: {esc(data["measured"])}.</p></header>
<div class="grid"><nav class="toc" aria-label="Sections"><div class="cap">On this page</div><ol>{toc}</ol></nav><main class="doc">{content}</main></div></div></body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} from {SRC} + {DATA} at {commit} ({date})")


if __name__ == "__main__":
    main()
