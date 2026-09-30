#!/usr/bin/env python3
"""Stage the repository's git-tracked documentation into build/site-src/ and
build the static site with MkDocs Material.

Reads ONLY `git ls-files`; it never walks the working tree, so untracked
material (externals/, virtualenvs, vendored build output) cannot leak in.

    python tools/site/build.py              # stage + mkdocs build + report
    python tools/site/build.py --stage-only # stage only (for mkdocs serve)

Outputs:
    build/site-src/        staged markdown and images, repo path layout kept
    build/site-nav.yaml    generated nav (read by tools/site/hooks.py)
    build/site/            the built site
    build/site-report.json counts, rewritten/unresolved links, timings
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pseudonym import Pseudonymizer  # noqa: E402
from labels import Labeller, label_generated  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "build"
SRC = BUILD / "site-src"
OUT = BUILD / "site"
NAV_FILE = BUILD / "site-nav.yaml"
REPORT_FILE = BUILD / "site-report.json"
SITE_TOOLS = REPO / "tools" / "site"

GITHUB_REPO = "https://github.com/bewest/rag-nightscout-ecosystem-alignment"
PAGE_EXT = {".md"}
IMAGE_EXT = {".png", ".svg", ".jpg", ".jpeg", ".gif"}
GALLERY_ROOTS = ("visualizations", "docs/visualizations")
PASSTHROUGH_DIR = "site/pages"
GALLERY_NAME = "gallery.md"
GENERATED_INDEX = "index.md"
MARKER = "(not published)"
IMAGE_MARKER = "(image not published)"
NOINDEX = '<meta name="robots" content="noindex, nofollow">'
AXES = {"disclosure", "health-data", "consent", "correspondence", "noise"}
# Tabs: top-level folders with at least this many staged pages+images get a
# tab of their own; smaller ones are grouped under "More".
TAB_MIN = 20


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------
def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True,
                          capture_output=True, text=True).stdout


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], check=True,
                         capture_output=True).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p]


# --------------------------------------------------------------------------
# exclusions
# --------------------------------------------------------------------------
def glob_to_regex(pattern: str) -> re.Pattern:
    i, out = 0, []
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif pattern.startswith("/**", i) and i + 3 == len(pattern):
            out.append("(?:/.*)?"); i += 3
        elif pattern.startswith("**", i):
            out.append(".*"); i += 2
        elif pattern[i] == "*":
            out.append("[^/]*"); i += 1
        elif pattern[i] == "?":
            out.append("[^/]"); i += 1
        else:
            out.append(re.escape(pattern[i])); i += 1
    return re.compile("".join(out) + r"\Z")


def load_exclusions(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text()) or {}
    entries = data.get("exclusions") or []
    need = {"pattern", "axis", "reason", "decided_by"}
    for n, e in enumerate(entries):
        if set(e) != need:
            sys.exit(f"exclusions.yaml entry {n}: fields must be exactly {sorted(need)}, got {sorted(e)}")
        if e["axis"] not in AXES:
            sys.exit(f"exclusions.yaml entry {n}: unknown axis {e['axis']!r}; one of {sorted(AXES)}")
        e["_re"] = glob_to_regex(e["pattern"])
    return entries


# --------------------------------------------------------------------------
# workspace.lock.json -> externals
# --------------------------------------------------------------------------
def load_externals() -> tuple[str, dict]:
    lock = json.loads((REPO / "workspace.lock.json").read_text())
    ext_dir = lock.get("externals_dir", "externals").strip("/")
    by_name = {}
    for r in lock.get("repos", []):
        url = r["url"]
        if url.endswith(".git"):
            url = url[:-4]
        by_name[r["name"]] = {"url": url, "ref": r["ref"],
                              "submodules": bool(r.get("submodules"))}
    return ext_dir, by_name


# --------------------------------------------------------------------------
# markdown scanning
# --------------------------------------------------------------------------
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)((?:(?!\n[ \t]*\n).)+?)(?<!`)\1(?!`)", re.S)  # no span across a blank line
REFDEF_RE = re.compile(r"^( {0,3}\[[^\]]+\]:[ \t]*)(<[^>]*>|\S+)(.*)$")
HTML_ATTR_RE = re.compile(r"(<(img|a|source|video)\b[^>]*?\s(?:src|href)\s*=\s*)([\"'])(.*?)\3([^>]*>)",
                          re.I | re.S)
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def code_mask(text: str) -> list[bool]:
    """Per-character mask: True where the character is inside a fenced code
    block or an inline code span (links there are not links)."""
    mask = [False] * len(text)
    pos, fence = 0, None
    for line in text.splitlines(keepends=True):
        m = FENCE_RE.match(line)
        if fence is None and m:
            fence = m.group(1)
            for k in range(pos, pos + len(line)):
                mask[k] = True
        elif fence is not None:
            for k in range(pos, pos + len(line)):
                mask[k] = True
            s = line.strip()
            if s.startswith(fence[0] * len(fence)) and set(s) <= {fence[0]}:
                fence = None
        pos += len(line)
    for m in INLINE_CODE_RE.finditer(text):
        if not mask[m.start()]:
            for k in range(m.start(), m.end()):
                mask[k] = True
    return mask


def parse_inline_target(text: str, i: int):
    """text[i] is just after '](' . Return (target_start, target_end,
    close_paren_index) or None."""
    n = len(text)
    j = i
    while j < n and text[j] in " \t":
        j += 1
    if j < n and text[j] == "<":
        k = text.find(">", j)
        if k < 0 or "\n" in text[j:k]:
            return None
        ts, te = j + 1, k
        j = k + 1
    else:
        ts, depth = j, 0
        while j < n:
            c = text[j]
            if c == "\\" and j + 1 < n:
                j += 2; continue
            if c == "(":
                depth += 1
            elif c == ")":
                if depth == 0:
                    break
                depth -= 1
            elif c in " \t\n":
                break
            j += 1
        te = j
    # title / whitespace up to the closing paren
    depth = 0
    while j < n:
        c = text[j]
        if c == "\n" and text[j:j + 2] == "\n\n":
            return None
        if c == "(":
            depth += 1
        elif c == ")":
            if depth == 0:
                return ts, te, j
            depth -= 1
        j += 1
    return None


def find_link_open(text: str, close_bracket: int, mask) -> int | None:
    """Walk back from the ']' at close_bracket to its matching '['."""
    depth, j = 0, close_bracket
    lo = max(0, close_bracket - 2000)
    while j >= lo:
        c = text[j]
        if not mask[j] and (j == 0 or text[j - 1] != "\\"):
            if c == "]":
                depth += 1
            elif c == "[":
                depth -= 1
                if depth == 0:
                    return j
        j -= 1
    return None


# --------------------------------------------------------------------------
# the site model
# --------------------------------------------------------------------------
class Site:
    def __init__(self, exclusions_path: Path):
        self.t0 = time.time()
        self.head = git("rev-parse", "HEAD").strip()
        self.tracked = tracked_files()
        self.tracked_set = set(self.tracked)
        self.tracked_dirs = set()
        for p in self.tracked:
            d = posixpath.dirname(p)
            while d:
                self.tracked_dirs.add(d)
                d = posixpath.dirname(d)
        self.exclusions = load_exclusions(exclusions_path)
        self.ext_dir, self.externals = load_externals()
        self.landing = yaml.safe_load((SITE_TOOLS / "landing.yaml").read_text())["sections"]
        self.nav_groups = (yaml.safe_load((SITE_TOOLS / "nav-groups.yaml").read_text()) or {}).get("groups") or {}
        self.group_counts: dict[str, dict[str, int]] = {}
        self.labeller = Labeller(REPO, SITE_TOOLS / "page-kinds.yaml")

        self.excluded: dict[str, dict] = {}
        self.match_counts = collections.Counter()
        for p in self.tracked:
            for e in self.exclusions:
                if e["_re"].match(p):
                    self.excluded[p] = e
                    self.match_counts[e["pattern"]] += 1
                    break

        # hand-written landing pages are published at <dir>/index.md, not
        # at their own path under tools/site/landing/
        landing_sources = {s["index"] for s in self.landing if s.get("index")}
        self.pages, self.images, self.passthrough = [], [], []
        for p in self.tracked:
            if p in self.excluded or p in landing_sources:
                continue
            ext = posixpath.splitext(p)[1].lower()
            if ext in PAGE_EXT:
                self.pages.append(p)
            elif ext in IMAGE_EXT:
                self.images.append(p)
            elif p.startswith(PASSTHROUGH_DIR + "/") and ext in {".html", ".htm"}:
                self.passthrough.append(p)
        self.staged = set(self.pages) | set(self.images) | set(self.passthrough)

        # directories fully excluded (every tracked file below is excluded)
        below = collections.defaultdict(lambda: [0, 0])  # dir -> [tracked, excluded]
        for p in self.tracked:
            d = posixpath.dirname(p)
            while d:
                below[d][0] += 1
                if p in self.excluded:
                    below[d][1] += 1
                d = posixpath.dirname(d)
        self.excluded_dirs = {d for d, (t, x) in below.items() if t and t == x}

        # directories that become nav sections: anything with a staged page
        # below it, plus gallery folders
        self.gallery_dirs = sorted({posixpath.dirname(p) for p in self.images
                                    if any(p.startswith(r + "/") for r in GALLERY_ROOTS)})
        self.section_dirs = {""}
        for p in self.pages + [posixpath.join(d, GALLERY_NAME) for d in self.gallery_dirs]:
            d = posixpath.dirname(p)
            while d:
                self.section_dirs.add(d)
                d = posixpath.dirname(d)
        self.landing_index = {}
        for s in self.landing:
            if s.get("index"):
                self.landing_index[s["dir"]] = s["index"]

        # index page per section directory
        self.index_of: dict[str, str] = {}
        self.generated_index: set[str] = set()
        staged_pages = set(self.pages)
        for d in self.section_dirs:
            for name in ("index.md", "README.md"):
                cand = posixpath.join(d, name) if d else name
                if cand in staged_pages:
                    self.index_of[d] = cand
                    break
            else:
                cand = posixpath.join(d, GENERATED_INDEX) if d else GENERATED_INDEX
                if cand in self.tracked_set:
                    sys.exit(f"STOP: generated index {cand} would shadow a tracked file")
                self.index_of[d] = cand
                self.generated_index.add(cand)
        for d in self.gallery_dirs:
            g = posixpath.join(d, GALLERY_NAME)
            if g in self.tracked_set:
                sys.exit(f"STOP: gallery page {g} would shadow a tracked file")

        self.link_kinds = collections.Counter()
        self.unresolved: list[dict] = []
        self.marker_links: list[dict] = []
        self.titles: dict[str, str] = {}

    # ---------------- link resolution ----------------
    def resolve(self, src: str, target: str, is_image: bool):
        """Return (kind, new_target_or_None). new_target None = unchanged;
        kind 'excluded' means replace the link with the marker."""
        raw = target.strip()
        if not raw or raw.startswith("#"):
            return "anchor", None
        if SCHEME_RE.match(raw) or raw.startswith("//"):
            return "external-url", None
        path_part, frag = (raw.split("#", 1) + [None])[:2]
        path_part, query = (path_part.split("?", 1) + [None])[:2]
        suffix = ("?" + query if query is not None else "") + ("#" + frag if frag is not None else "")
        decoded = urllib.parse.unquote(path_part)
        trailing = decoded.endswith("/")
        if decoded.startswith("/"):
            joined = decoded.lstrip("/")
            rooted = True
        else:
            joined = posixpath.join(posixpath.dirname(src), decoded)
            rooted = False
        norm = posixpath.normpath(joined) if joined else "."
        if norm == ".":
            norm = ""
        if norm.startswith("../") or norm == "..":
            return "unresolved", None

        def rel(to: str) -> str:
            r = posixpath.relpath(to, posixpath.dirname(src) or ".")
            return urllib.parse.quote(r) + suffix

        # excluded file or wholly excluded directory
        if norm in self.excluded or norm in self.excluded_dirs:
            return "excluded", None
        # staged file
        if norm in self.staged:
            if rooted:
                return "root-relative", rel(norm)
            return "staged", None
        # directory with a nav section -> its index page
        if norm in self.section_dirs and (norm in self.tracked_dirs or norm == ""):
            return "dir-index", rel(self.index_of[norm])
        # tracked but not staged -> GitHub at HEAD
        if norm in self.tracked_set:
            return "github-blob", f"{GITHUB_REPO}/blob/{self.head}/{urllib.parse.quote(norm)}{suffix}"
        if norm in self.tracked_dirs or norm == "":
            return "github-tree", f"{GITHUB_REPO}/tree/{self.head}/{urllib.parse.quote(norm)}{suffix}"
        # externals/<name>/... -> upstream at pinned ref
        prefix = self.ext_dir + "/"
        if norm.startswith(prefix):
            rest = norm[len(prefix):]
            name, _, sub = rest.partition("/")
            repo = self.externals.get(name)
            if repo:
                kind = "tree" if (not sub or trailing) else "blob"
                url = f"{repo['url']}/{kind}/{repo['ref']}"
                if sub:
                    url += "/" + urllib.parse.quote(sub)
                label = "externals-submodule-repo" if repo["submodules"] else "externals"
                return label, url + suffix
        return "unresolved", None

    def record(self, src, target, kind, line):
        self.link_kinds[kind] += 1
        if kind == "unresolved":
            self.unresolved.append({"file": src, "line": line, "target": target})
        elif kind == "excluded":
            self.marker_links.append({"file": src, "line": line, "target": target})

    # ---------------- markdown rewriting ----------------
    def rewrite_markdown(self, src: str, text: str) -> str:
        mask = code_mask(text)
        line_starts = [0] + [m.end() for m in re.finditer("\n", text)]

        import bisect

        def lineno(pos):
            return bisect.bisect_right(line_starts, pos)

        edits = []  # (start, end, replacement)
        # inline links / images
        for m in re.finditer(r"\]\(", text):
            b = m.start()
            if mask[b] or (b > 0 and text[b - 1] == "\\"):
                continue
            parsed = parse_inline_target(text, m.end())
            if not parsed:
                continue
            ts, te, close = parsed
            target = text[ts:te]
            opener = find_link_open(text, b, mask)
            if opener is None:
                continue
            is_image = opener > 0 and text[opener - 1] == "!"
            kind, new = self.resolve(src, target, is_image)
            self.record(src, target, kind, lineno(ts))
            if kind == "excluded":
                if is_image:
                    edits.append((opener - 1, close + 1, IMAGE_MARKER))
                else:
                    label = text[opener + 1:b]
                    edits.append((opener, close + 1, f"{label} {MARKER}"))
            elif new is not None:
                edits.append((ts, te, new))
        # reference definitions
        pos = 0
        for line in text.splitlines(keepends=True):
            if pos < len(mask) and not mask[pos]:
                m = REFDEF_RE.match(line.rstrip("\n"))
                if m:
                    tgt = m.group(2)
                    inner = tgt[1:-1] if tgt.startswith("<") else tgt
                    kind, new = self.resolve(src, inner, False)
                    self.record(src, inner, kind, lineno(pos))
                    s = pos + m.start(2)
                    if kind == "excluded":
                        edits.append((s, s + len(tgt), "#not-published"))
                    elif new is not None:
                        edits.append((s, s + len(tgt), new))
            pos += len(line)
        # raw HTML src/href
        for m in HTML_ATTR_RE.finditer(text):
            if mask[m.start()]:
                continue
            tgt = m.group(4)
            kind, new = self.resolve(src, tgt, m.group(2).lower() == "img")
            self.record(src, tgt, kind, lineno(m.start(4)))
            if kind == "excluded":
                if m.group(2).lower() == "a":
                    edits.append((m.start(), m.end(), f'<a title="not published">{MARKER} '))
                else:
                    edits.append((m.start(), m.end(), IMAGE_MARKER))
            elif new is not None:
                edits.append((m.start(4), m.end(4), new))
        if not edits:
            return text
        edits.sort()
        out, last = [], 0
        for s, e, r in edits:
            if s < last:  # overlapping (e.g. image inside an excluded link) - keep the outer one
                continue
            out.append(text[last:s]); out.append(r); last = e
        out.append(text[last:])
        return "".join(out)

    # ---------------- titles ----------------
    def title_of(self, page: str) -> str:
        if page in self.titles:
            return self.titles[page]
        t = None
        try:
            with open(REPO / page, encoding="utf-8", errors="replace") as fh:
                in_fence = False
                for n, line in enumerate(fh):
                    if n > 200:
                        break
                    if FENCE_RE.match(line):
                        in_fence = not in_fence
                    if not in_fence and line.startswith("# "):
                        t = line[2:].strip().strip("#").strip()
                        break
        except FileNotFoundError:
            pass
        self.titles[page] = t or posixpath.basename(page)
        return self.titles[page]

    # ---------------- staging ----------------
    def stage(self):
        if SRC.exists():
            shutil.rmtree(SRC)
        SRC.mkdir(parents=True)
        # participant-ID pseudonyms: collect the raw staged text first, so the
        # full-ID set (and the fail-closed key check) sees everything
        raw = {p: (REPO / p).read_text(encoding="utf-8", errors="replace")
               for p in self.pages + self.passthrough + [i for i in self.images if i.lower().endswith(".svg")]}
        for src in set(self.landing_index.values()):
            raw[src] = (REPO / src).read_text(encoding="utf-8", errors="replace")
        try:
            self.pseudo = Pseudonymizer(raw, sorted(self.staged) + sorted(self.generated_index))
        except SystemExit:
            shutil.rmtree(SRC)
            if OUT.exists():
                shutil.rmtree(OUT)  # never leave a stale site behind a failed build
            raise
        P = self.pseudo

        def write(rel: str, text: str):
            dst = SRC / P.path(rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(P.text(text, where=rel), encoding="utf-8")

        for p in self.images:
            if p.lower().endswith(".svg"):
                write(p, raw[p])
            else:
                dst = SRC / P.path(p)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / p, dst)
        L = self.labeller
        head_date, head_sha = git("log", "-1", "--format=%cs %h").split()
        for p in self.pages:
            write(p, L.label(p, self.rewrite_markdown(p, raw[p])))
        for p in self.passthrough:
            html = raw[p]
            if 'name="robots"' not in html:
                html, n = re.subn(r"(<head[^>]*>)", r"\1\n" + NOINDEX, html, count=1, flags=re.I)
                if n == 0:
                    html = NOINDEX + "\n" + html
            write(p, html)
        for d in sorted(self.generated_index):
            dirpath = posixpath.dirname(d)
            if dirpath in self.landing_index:
                src = self.landing_index[dirpath]
                body = L.label(d, self.rewrite_markdown(d, raw[src]), date_source=src)
            else:
                body = label_generated(L, self.render_index(dirpath), head_date, head_sha)
            write(d, body)
        for d in self.gallery_dirs:
            write(posixpath.join(d, GALLERY_NAME),
                  label_generated(L, self.render_gallery(d), head_date, head_sha))
        (SRC / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
        NAV_FILE.write_text(P.text(yaml.safe_dump(self.nav(), sort_keys=False, allow_unicode=True),
                                   where="build/site-nav.yaml"))
        if P.errors:
            for e in P.errors:
                print(f"site: participant-id: {e}", file=sys.stderr)
            shutil.rmtree(SRC)
            if OUT.exists():
                shutil.rmtree(OUT)
            raise SystemExit(f"site: FAIL: {len(P.errors)} participant-ID short form(s) could not be resolved; "
                             f"fix them at the source")

    def children(self, d: str):
        pages = sorted(p for p in self.pages if posixpath.dirname(p) == d)
        subdirs = sorted(s for s in self.section_dirs
                         if s and posixpath.dirname(s) == d)
        return pages, subdirs

    def render_index(self, d: str) -> str:
        pages, subdirs = self.children(d)
        name = d or "Repository"
        lines = [f"# {name}", "",
                 f"*Generated index: `{d or '/'}` has no README.md or index.md.*", ""]
        if d in self.gallery_dirs:
            lines += [f"- [Image gallery]({GALLERY_NAME})", ""]
        if subdirs:
            lines += ["## Folders", ""]
            for s in subdirs:
                r = posixpath.relpath(self.index_of[s], d or ".")
                lines.append(f"- [{posixpath.basename(s)}/]({urllib.parse.quote(r)})")
            lines.append("")
        others = [p for p in pages if p != self.index_of.get(d)]
        if others:
            lines += ["## Pages", ""]
            for p in others:
                r = posixpath.relpath(p, d or ".")
                t = self.title_of(p).replace("[", "\\[").replace("]", "\\]")
                lines.append(f"- [{t}]({urllib.parse.quote(r)})")
            lines.append("")
        return "\n".join(lines)

    def render_gallery(self, d: str) -> str:
        imgs = sorted(p for p in self.images if posixpath.dirname(p) == d)
        lines = [f"# Gallery: {d}", "",
                 f"*Generated. {len(imgs)} image(s) tracked in `{d}/`; images load as you scroll.*", ""]
        for p in imgs:
            b = posixpath.basename(p)
            q = urllib.parse.quote(b)
            lines += [f"### {b}", "",
                      f'<a href="{q}"><img src="{q}" alt="{b}" loading="lazy" decoding="async" '
                      f'style="max-width:100%;height:auto"></a>', ""]
        return "\n".join(lines)

    # ---------------- nav ----------------
    def section_nav(self, d: str, order: list[str] | None = None, skip=frozenset()):
        pages, subdirs = self.children(d)
        idx = self.index_of[d]
        items = [idx]
        ordered = []
        for name in order or []:
            p = posixpath.join(d, name)
            if p in pages and p != idx:
                ordered.append(p)
        rest = [p for p in pages if p != idx and p not in ordered]
        if d in self.nav_groups:
            items += ordered + self.grouped(d, rest)
        else:
            items += ordered + rest
        if d in self.gallery_dirs:
            items.append({"Gallery": posixpath.join(d, GALLERY_NAME)})
        for s in subdirs:
            if s in skip:
                continue
            items.append({posixpath.basename(s) + "/": self.section_nav(s, skip=skip)})
        return items

    def grouped(self, d: str, pages: list[str]) -> list:
        """Bucket a large flat folder's pages into titled sub-sections."""
        cfg = self.nav_groups[d]
        rules = cfg.get("rules") or []
        buckets = {r["title"]: [] for r in rules}
        other = []
        for p in pages:
            name = posixpath.basename(p)
            m = re.match(r"exp[-_]?(\d+)", name)
            for r in rules:
                if "exp_range" in r:
                    lo, hi = r["exp_range"]
                    if m and lo <= int(m.group(1)) < hi:
                        buckets[r["title"]].append(p); break
                elif re.search(r["match"], name):
                    buckets[r["title"]].append(p); break
            else:
                other.append(p)
        if other:
            buckets[cfg.get("other", "Other")] = other
        self.group_counts[d] = {t: len(v) for t, v in buckets.items() if v}
        return [{t: v} for t, v in buckets.items() if v]

    def nav(self):
        landing_dirs = {s["dir"] for s in self.landing}
        nav = [{"Home": self.index_of[""]}]
        for s in self.landing:
            if s["dir"] in self.section_dirs:
                nav.append({s["title"]: self.section_nav(s["dir"], s.get("pages"), landing_dirs)})
        top_pages, top_dirs = self.children("")
        weight = collections.Counter(p.split("/", 1)[0] for p in self.pages + self.images if "/" in p)
        more = []
        for t in top_dirs:
            if t in landing_dirs:
                continue
            sub = self.section_nav(t, skip=landing_dirs)
            if weight[t] >= TAB_MIN:
                nav.append({t + "/": sub})
            else:
                more.append({t + "/": sub})
        roots = [p for p in top_pages if p != self.index_of[""]]
        if roots:
            more.append({"Root files": roots})
        if self.passthrough:
            pages = []
            for p in sorted(self.passthrough):
                html = (REPO / p).read_text(encoding="utf-8", errors="replace")
                m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
                pages.append({(m.group(1).strip() if m else posixpath.basename(p)): p})
            nav.append({"Pages": pages})
        if more:
            nav.append({"More": more})
        return nav


# --------------------------------------------------------------------------
# mkdocs
# --------------------------------------------------------------------------
WARN_KINDS = [
    (re.compile(r"contains a link .* but the target .* is not found"), "link target not found"),
    (re.compile(r"contains a link .* but there is no such anchor"), "missing anchor"),
    (re.compile(r"contains an absolute link"), "absolute link"),
    (re.compile(r"unrecognized relative link"), "unrecognized relative link"),
    (re.compile(r"nav.*not found|not found in the documentation files"), "nav reference not found"),
    (re.compile(r"Excluding 'README.md'"), "README.md shadowed by index.md"),
]


def classify(msg: str) -> str:
    for rx, k in WARN_KINDS:
        if rx.search(msg):
            return k
    return re.sub(r"'[^']*'", "'…'", msg)[:90]


def check_pages_manifest(site: "Site") -> dict:
    """site/pages/pages.yaml rules; returns counts, exits naming every problem."""
    mf = REPO / PASSTHROUGH_DIR / "pages.yaml"
    entries = ((yaml.safe_load(mf.read_text()) or {}).get("pages") or {}) if mf.exists() else {}
    files = {posixpath.basename(p): p for p in site.passthrough}
    errors, kinds = [], collections.Counter()
    for name in sorted(set(files) - set(entries)):
        errors.append(f"{name}: no entry in site/pages/pages.yaml")
    for name, e in sorted(entries.items()):
        if name not in files:
            errors.append(f"{name}: listed in pages.yaml but not a tracked, unexcluded file in site/pages/")
            continue
        kind = (e or {}).get("kind")
        kinds[kind] += 1
        html = (REPO / files[name]).read_text(encoding="utf-8", errors="replace")
        if kind == "snapshot":
            as_of = e.get("as_of")
            if not as_of:
                errors.append(f"{name}: snapshot without as_of")
                continue
            m = re.search(r'<[^>]*data-site-banner="snapshot"[^>]*>(.*?)</', html, re.S)
            if not m or str(as_of) not in re.sub(r"<[^>]+>", "", html[m.start():m.start() + 2000]):
                errors.append(f"{name}: snapshot without a visible banner naming {as_of} "
                              f'(an element with data-site-banner="snapshot")')
        elif kind == "living":
            sources, commit = e.get("sources"), e.get("source_commit")
            if not sources or not commit:
                errors.append(f"{name}: living page needs sources and source_commit")
                continue
            for src in sources:
                if src not in site.tracked_set:
                    errors.append(f"{name}: source {src} is not a tracked file")
                    continue
                r = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", str(commit), "HEAD", "--", src])
                if r.returncode == 1:
                    errors.append(f"{name}: source {src} changed after source_commit {commit}; "
                                  f"re-render the page and move source_commit forward")
                elif r.returncode != 0:
                    errors.append(f"{name}: source_commit {commit} is not a commit here")
        else:
            errors.append(f"{name}: kind must be snapshot or living")
    if errors:
        for er in errors:
            print(f"site: pages.yaml: {er}", file=sys.stderr)
        if OUT.exists():
            shutil.rmtree(OUT)
        raise SystemExit(f"site: FAIL: {len(errors)} site/pages manifest problem(s)")
    return dict(kinds)


def run_mkdocs() -> tuple[float, list[str], int]:
    exe = SITE_TOOLS / ".venv" / "bin" / "mkdocs"
    cmd = [str(exe) if exe.exists() else "mkdocs", "build", "-f", str(REPO / "mkdocs.yml"), "--clean"]
    t = time.time()
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    dt = time.time() - t
    log = (p.stdout + p.stderr).splitlines()
    (BUILD / "site-mkdocs.log").write_text("\n".join(log) + "\n")
    warnings = [l.split("-", 1)[1].strip() if "-" in l else l for l in log if l.startswith("WARNING")]
    return dt, warnings, p.returncode


def dir_size(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):  # our own build output, not the source tree
        for f in files:
            total += os.lstat(os.path.join(root, f)).st_size
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage-only", action="store_true")
    ap.add_argument("--exclusions", default=str(SITE_TOOLS / "exclusions.yaml"))
    args = ap.parse_args()

    BUILD.mkdir(exist_ok=True)
    site = Site(Path(args.exclusions))
    pages_manifest = check_pages_manifest(site)
    site.stage()
    stage_s = time.time() - site.t0

    report = {
        "head": site.head,
        "tracked_files": len(site.tracked),
        "pages_staged": len(site.pages),
        "generated_index_pages": len(site.generated_index),
        "gallery_pages": len(site.gallery_dirs),
        "images_staged": len(site.images),
        "passthrough_html": len(site.passthrough),
        "excluded_files": len(site.excluded),
        "excluded_per_axis": dict(collections.Counter(e["axis"] for e in site.excluded.values())),
        "exclusion_matches": {e["pattern"]: site.match_counts.get(e["pattern"], 0) for e in site.exclusions},
        "links_per_kind": dict(site.link_kinds.most_common()),
        "links_rewritten": sum(v for k, v in site.link_kinds.items()
                               if k not in ("staged", "anchor", "external-url", "unresolved")),
        "unresolved_count": len(site.unresolved),
        "unresolved": site.unresolved,
        "not_published_markers": site.marker_links,
        "stage_seconds": round(stage_s, 2),
        "nav_groups": site.group_counts,
        "participant_ids": site.pseudo.stats(),
        "page_labels": dict(site.labeller.counts),
        "rich_pages": pages_manifest,
        "record_candidates_for_living": sorted(site.labeller.candidates),
    }
    # fail closed: the content scan over the staged tree must pass before MkDocs runs
    sys.path.insert(0, str(SITE_TOOLS))
    import scan as content_scan
    scan_res = content_scan.scan(SRC)
    report["content_scan"] = scan_res
    rc = 0
    if scan_res["blocked"]:
        rc = 2
        if OUT.exists():
            shutil.rmtree(OUT)  # never leave a stale, unscanned site behind
    elif not args.stage_only:
        mk_s, warnings, rc = run_mkdocs()
        kinds = collections.Counter(classify(w) for w in warnings)
        report.update({
            "mkdocs_seconds": round(mk_s, 2),
            "mkdocs_exit": rc,
            "warnings": len(warnings),
            "warning_kinds": dict(kinds.most_common()),
            "output_bytes": dir_size(OUT) if OUT.exists() else 0,
        })
    report["build_seconds"] = round(time.time() - site.t0, 2)
    # the report names files and link targets: never let a raw participant ID into it
    REPORT_FILE.write_text(site.pseudo.text(json.dumps(report, indent=1)) + "\n")

    print(f"site: HEAD {site.head[:8]}, {report['tracked_files']} tracked files")
    print(f"  staged: {report['pages_staged']} pages (+{report['generated_index_pages']} generated index, "
          f"{report['gallery_pages']} galleries), {report['images_staged']} images, "
          f"{report['passthrough_html']} site/pages HTML")
    print(f"  excluded: {report['excluded_files']} files {report['excluded_per_axis']}")
    print(f"  links: {report['links_per_kind']}")
    print(f"  participant IDs: {report['participant_ids']}")
    print(f"  page labels: {report['page_labels']}; {len(site.labeller.candidates)} dated page(s) "
          f"look living (candidates for tools/site/page-kinds.yaml, listed in the report)")
    print(f"  unresolved links: {report['unresolved_count']} (see {REPORT_FILE.relative_to(REPO)})")
    content_scan.report(scan_res, prefix="  scan")
    if "mkdocs_exit" in report:
        print(f"  mkdocs: exit {rc}, {report['warnings']} warnings, {report['mkdocs_seconds']} s")
        for k, v in list(report["warning_kinds"].items())[:5]:
            print(f"    {v:6d}  {k}")
        print(f"  output: {report['output_bytes'] / 1e6:.1f} MB in {OUT.relative_to(REPO)}/")
    print(f"  total: {report['build_seconds']} s")
    return rc


if __name__ == "__main__":
    sys.exit(main())
