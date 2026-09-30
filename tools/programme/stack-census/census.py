#!/usr/bin/env python3
"""Measure activity and test surface for every repository in repos.tsv.

Reads the clones that fetch.sh makes under externals/stack/ and writes one JSON line per
repository plus a Markdown table. Every figure is taken from the default branch at the commit
recorded in the output, so a later run can be compared row by row.

    tools/programme/stack-census/fetch.sh
    python3 tools/programme/stack-census/census.py --asof 2026-09-30

What the columns mean (and do not mean):
  commits_6m / commits_12m  non-merge commits on the default branch in the trailing window
  bot_commits_12m           of those, commits by automation accounts (github-actions, dependabot,
                            translation and build bots)
  agent_commits_12m         of those, commits whose author is a coding agent (Claude, Copilot);
                            people direct these, so they are neither bots nor extra authors
  authors_12m               distinct human author names (after .mailmap) in the trailing 12 months
  top_author_share_12m      share of human-authored commits by the most frequent author
  tags_12m                  tags whose date falls in the trailing 12 months (a release proxy;
                            projects that release without tags read as 0)
  workflows / ci_runs_tests GitHub Actions files, and whether any of them mentions a test step
  test_files / test_cases   files in test locations, and test declarations counted by pattern;
                            a count of declarations, not of passing tests
  sim_paths                 paths whose names suggest a simulator, fake, mock or fixture
  branch                    the branch measured: the default branch, unless origin/dev or
                            origin/develop has more non-merge commits in the trailing 12 months
                            (several projects develop on dev and merge to the default at release);
                            a non-default branch is measured in a worktree under externals/stack/.dev/
"""
import argparse
import datetime as dt
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STACK = ROOT / "externals" / "stack"

CODE_EXT = {".swift", ".m", ".h", ".c", ".cpp", ".kt", ".java", ".js", ".ts", ".py", ".go",
            ".cs", ".rs", ".dart", ".sh"}
TEST_DIR = re.compile(r"(^|/)(tests?|Tests|[A-Za-z]+Tests|spec|__tests__|androidTest|testing|test-data)(/|$)")
TEST_FILE = re.compile(r"(Tests?\.(swift|kt|java|cs)$|_test\.(go|py)$|(^|/)test_[^/]*\.py$|\.(test|spec)\.(js|ts)$)")
TEST_DECL = re.compile(
    r"(\bfunc\s+test\w*\s*\(|@Test\b|\bit\s*\(\s*['\"`]|\bdef\s+test_\w*\s*\(|\bfunc\s+Test\w+\s*\(t\s|"
    r"\btest\s*\(\s*['\"`]|\[(Fact|Theory|Test|TestMethod)\b)")
BOT = re.compile(r"(\[bot\]$|[-\s]bot$|^github-actions|^dependabot|^renovate)", re.I)
AGENT = {"claude", "copilot"}
SIM_PATH = re.compile(r"(simulat|emulat|fake|mock|fixture|vectors?\b|replay)", re.I)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout


def pick_branch(repo, since12, until):
    """Return (branch label, path to a checkout of it)."""
    best, best_n = "HEAD", -1
    for ref in ("HEAD", "origin/dev", "origin/develop"):
        if subprocess.run(["git", "-C", str(repo), "rev-parse", "-q", "--verify", ref],
                          capture_output=True).returncode:
            continue
        n = int(git(repo, "rev-list", "--count", "--no-merges", f"--since={since12}",
                    f"--until={until}", ref).strip() or 0)
        if n > best_n:
            best, best_n = ref, n
    if best == "HEAD":
        return git(repo, "rev-parse", "--abbrev-ref", "origin/HEAD").strip().removeprefix("origin/"), repo
    wt = STACK / ".dev" / repo.name
    if (wt / ".git").exists():
        git(wt, "checkout", "--quiet", "--detach", best)
    else:
        wt.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "worktree", "add", "--quiet", "--detach", str(wt), best)
    return best.removeprefix("origin/"), wt


def census(layer, name, role, asof):
    repo = STACK / name.replace("/", "__")
    if not (repo / ".git").exists():
        return {"repo": name, "layer": layer, "role": role, "missing": True}
    since12 = (asof - dt.timedelta(days=365)).isoformat()
    since6 = (asof - dt.timedelta(days=182)).isoformat()
    until = (asof + dt.timedelta(days=1)).isoformat()
    branch, repo = pick_branch(repo, since12, until)
    head = git(repo, "log", "-1", "--format=%H %cs").split()
    first = git(repo, "log", "--reverse", "--format=%cs", "--max-parents=0").split()
    a12 = git(repo, "log", "--no-merges", "--use-mailmap", f"--since={since12}", f"--until={until}",
              "--format=%aN").splitlines()
    c6 = git(repo, "rev-list", "--count", "--no-merges", f"--since={since6}", f"--until={until}", "HEAD").strip()
    names = [a.strip().lower() for a in a12 if a.strip()]
    bots = sum(1 for a in names if BOT.search(a))
    agents = sum(1 for a in names if a in AGENT)
    authors = Counter(a for a in names if not BOT.search(a) and a not in AGENT)
    tags = [d for d in git(repo, "for-each-ref", "--format=%(creatordate:short)", "refs/tags").split()
            if since12 <= d <= asof.isoformat()]
    files = git(repo, "ls-files").splitlines()
    wf = [f for f in files if f.startswith(".github/workflows/") and f.endswith((".yml", ".yaml"))]
    ci_tests = False
    for f in wf:
        try:
            if re.search(r"\b(test|xcodebuild test|gradlew .*test|npm (run )?test|pytest|go test|dotnet test)\b",
                         (repo / f).read_text(errors="ignore"), re.I):
                ci_tests = True
                break
        except OSError:
            pass
    code = [f for f in files if Path(f).suffix in CODE_EXT]
    tests = [f for f in code if TEST_DIR.search(f) or TEST_FILE.search(f)]
    decl = 0
    for f in tests:
        try:
            decl += len(TEST_DECL.findall((repo / f).read_text(errors="ignore")))
        except OSError:
            pass
    sims = sorted({f.split("/")[0] if SIM_PATH.search(f.split("/")[0]) else f
                   for f in files if SIM_PATH.search(f)})
    total12 = sum(authors.values())
    all12 = len(names)
    return {
        "repo": name, "layer": layer, "role": role, "branch": branch,
        "head": head[0][:8] if head else "", "head_date": head[1] if len(head) > 1 else "",
        "first_commit": first[0] if first else "",
        "commits_6m": int(c6 or 0), "commits_12m": all12,
        "bot_commits_12m": bots, "agent_commits_12m": agents,
        "authors_12m": len(authors),
        "top_author_share_12m": round(max(authors.values()) / total12, 2) if total12 else None,
        "tags_12m": len(tags),
        "workflows": len(wf), "ci_runs_tests": ci_tests,
        "code_files": len(code), "test_files": len(tests), "test_cases": decl,
        "sim_paths": len(sims),
        "_authors": sorted(authors),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=dt.date.today().isoformat())
    ap.add_argument("--out", default=str(HERE / "results"))
    args = ap.parse_args()
    asof = dt.date.fromisoformat(args.asof)
    rows = []
    for line in (HERE / "repos.tsv").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        layer, name, role = line.split("\t")
        rows.append(census(layer, name, role, asof))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"census-{asof}.jsonl").write_text(
        "".join(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}) + "\n" for r in rows))
    cols = ["repo", "layer", "branch", "head", "head_date", "first_commit", "commits_6m", "commits_12m",
            "bot_commits_12m", "agent_commits_12m", "authors_12m", "top_author_share_12m", "tags_12m", "workflows", "ci_runs_tests",
            "code_files", "test_files", "test_cases", "sim_paths"]
    md = [f"# Stack census, {asof}", "",
          "Generated by `tools/programme/stack-census/census.py`; column meanings are in its docstring.", "",
          "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        md.append("| " + " | ".join("missing" if r.get("missing") and c not in ("repo", "layer")
                                   else str(r.get(c, "")) for c in cols) + " |")
    md += ["", "## By layer", "",
           "A repository listed twice at the same head (a fork kept level with upstream) is counted once. "
           "Authors are distinct names across the layer's repositories, so one person active in several "
           "repositories counts once.", "",
           "| layer | repositories | active in 12 months | commits, 12 months | distinct authors, 12 months "
           "| of which bot | of which agent | CI runs tests | with simulator/fixture paths | test declarations |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    seen, layers = set(), {}
    for r in rows:
        if r.get("missing") or r["head"] in seen:
            continue
        seen.add(r["head"])
        for key in (r["layer"], "all"):
            t = layers.setdefault(key, {"n": 0, "active": 0, "commits": 0, "authors": set(), "bot": 0, "agent": 0, "ci": 0,
                                         "sim": 0, "tests": 0})
            t["n"] += 1
            t["active"] += r["commits_12m"] > 0
            t["commits"] += r["commits_12m"]
            t["authors"] |= set(r["_authors"])
            t["bot"] += r["bot_commits_12m"]
            t["agent"] += r["agent_commits_12m"]
            t["ci"] += r["ci_runs_tests"]
            t["sim"] += r["sim_paths"] > 0
            t["tests"] += r["test_cases"]
    for key, t in layers.items():
        md.append(f"| {key} | {t['n']} | {t['active']} | {t['commits']} | {len(t['authors'])} | {t['bot']} | {t['agent']} | {t['ci']} "
                  f"| {t['sim']} | {t['tests']} |")
    (out / f"census-{asof}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
