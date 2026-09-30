"""Search-index policy for the static site (tools/site/search.yaml).

Material for MkDocs builds its search index from every page. On this site that
index reached 24 MB, and the browser's search worker held about 780 MB building
it (phone emulation, 2026-09-30). This module rewrites staged markdown with
Material's own mechanisms so the index stays small and the right pages rank:

* front matter `search: {exclude: true}` drops a page from the index;
* a `{ data-search-exclude }` attribute on a heading drops that section;
* front matter `search: {boost: N}` raises a page's rank.

Source docs are never edited; this runs at staging time.
"""
from __future__ import annotations

import collections
import re
from pathlib import Path

import yaml

FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
ATX = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")


def glob_re(pattern: str) -> re.Pattern:
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif pattern.startswith("**", i):
            out.append(".*"); i += 2
        elif pattern[i] == "*":
            out.append("[^/]*"); i += 1
        else:
            out.append(re.escape(pattern[i])); i += 1
    return re.compile("".join(out) + r"\Z")


class SearchPolicy:
    def __init__(self, config: Path, enabled: bool = True):
        cfg = yaml.safe_load(config.read_text()) or {}
        self.enabled = enabled
        self.keep_full = [glob_re(g) for g in cfg.get("keep_full", [])]
        self.boost = [(glob_re(e["path"]), float(e["boost"])) for e in cfg.get("boost", [])]
        self.first_section = [(glob_re(e["path"]), e.get("kind", "any")) for e in cfg.get("first_section_only", [])]
        self.exclude = [glob_re(g) for g in cfg.get("exclude", [])]
        self.exclude_generated = bool(cfg.get("exclude_generated", True))
        self.counts = collections.Counter()

    def _kept(self, path: str) -> bool:
        return any(r.match(path) for r in self.keep_full)

    def apply(self, path: str, text: str, kind: str, generated: bool = False) -> str:
        """path: the repo path the page is published under (staged path)."""
        if not self.enabled:
            return text
        meta = {}
        boost = next((b for r, b in self.boost if r.match(path)), None)
        if boost:
            meta["boost"] = boost
            self.counts["boosted"] += 1
        kept = self._kept(path)
        if not kept and ((generated and self.exclude_generated) or any(r.match(path) for r in self.exclude)):
            meta["exclude"] = True
            self.counts["page-excluded"] += 1
        elif not kept and any(r.match(path) and k in ("any", kind) for r, k in self.first_section):
            text, n = first_section_only(text)
            self.counts["first-section-only"] += 1
            self.counts["sections-excluded"] += n
        return with_front_matter(text, {"search": meta}) if meta else text


def first_section_only(text: str) -> tuple[str, int]:
    """Keep the title section and the first `##` section (with its subsections);
    mark every later heading `{ data-search-exclude }`, so its section leaves the
    index. Headings before the first `##` (e.g. `###` under the title) are
    marked too."""
    lines = text.split("\n")
    fence, seen_h2, in_first, n = None, False, False, 0
    for i, line in enumerate(lines):
        m = FENCE.match(line)
        if fence is None and m:
            fence = m.group(1)[0]
            continue
        if fence is not None:
            if line.strip().startswith(fence * 3):
                fence = None
            continue
        h = ATX.match(line)
        if not h or len(h.group(1)) == 1:
            continue
        level = len(h.group(1))
        if not seen_h2:
            seen_h2 = in_first = level == 2 or seen_h2
            if level == 2:
                continue
        if in_first:
            if level > 2:
                continue  # subsections of the first `##` section stay indexed
            in_first = False
        body = h.group(2)
        a = re.search(r"\{([^{}]*)\}\s*$", body)
        if a and (a.group(1).strip().startswith(("#", ".")) or "=" in a.group(1)):
            body = body[:a.start()] + "{" + a.group(1).rstrip() + " data-search-exclude }"
        else:
            body = body + " { data-search-exclude }"
        lines[i] = f"{h.group(1)} {body}"
        n += 1
    return "\n".join(lines), n


def with_front_matter(text: str, add: dict) -> str:
    """Merge keys into YAML front matter, creating it when absent."""
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end > 0:
            fm = yaml.safe_load(text[4:end]) or {}
            for k, v in add.items():
                if isinstance(v, dict) and isinstance(fm.get(k), dict):
                    fm[k].update(v)
                else:
                    fm[k] = v
            rest = text[end + 4:]
            return "---\n" + yaml.safe_dump(fm, sort_keys=False).rstrip("\n") + "\n---" + rest
    return "---\n" + yaml.safe_dump(add, sort_keys=False) + "---\n\n" + text
