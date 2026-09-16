#!/usr/bin/env python3
"""fidelity.py — does every character written into a queue YAML reach the data?

    python3 tools/queue/fidelity.py                 # both queue YAMLs
    python3 tools/queue/fidelity.py path.yaml ...   # named files
    python3 tools/queue/fidelity.py --quiet         # exit code only

Also run as part of ``validate.py``, so ``make queue-validate``, ``make queue``
and ``make queue-check`` all carry it.

WHY THIS EXISTS

On 2026-09-16 three values in ``queue/work-queue.yaml`` were found to have been
silently truncated at parse time, one of them for as long as the file had
existed. In a YAML *plain* (unquoted) scalar a space followed by ``#`` begins a
comment, so::

    title: T0.1 - PR #8733, the two quadratic treatment scans

has always parsed as ``T0.1 - PR``. The worst of the three was RT-0's review
line, which read "...at least one human reviewer who is not the author —
release PR #8598 and integration PR #8605 each carry ZERO human reviews" and
arrived as everything up to "release PR". The governance finding that is the
entire reason that item demands a non-author reviewer was being deleted from
the generated queue, every time it was generated.

``queue-validate`` passed throughout, before and after, and could not have done
otherwise: **a truncated string is a perfectly valid string.** The schema check
asks whether the data is well-formed. Nothing asked whether the data is what
was written. That is the gap this file closes, and it is a different question
from every other check in this directory — those measure the manifest, this one
measures the *transport*.

THE THREE SILENT LOSSES, AND WHY ONLY SILENT ONES ARE HERE

A YAML mistake that raises is not this file's business; the parser already
reports it and nobody ships past it. What is dangerous is the mistake that
parses cleanly into something other than what the author typed:

  ``inline-comment``  a plain scalar followed by ``#`` — the observed defect.
  ``duplicate-key``   PyYAML keeps the LAST of two identical keys in a mapping
                      and says nothing. The earlier value, and whatever was
                      written into it, is gone.
  ``implicit-retype`` the source spelling does not survive the type YAML chose
                      for it: the Norway problem (``no`` -> ``False``), and
                      numbers that are rewritten (``1.20`` -> ``1.2``,
                      ``007`` -> ``7``, ``12:30`` -> ``750``).

THE INLINE-COMMENT RULE IS ABSOLUTE, DELIBERATELY

An inline comment after a plain scalar is FORBIDDEN, and no attempt is made to
guess whether a given one was intended. The tempting heuristics — ``# `` with a
space is a real comment, ``#8733`` glued to a digit is dropped prose — all have
a false-negative window, and a check with a false-negative window on exactly
the defect it was built for is the kind of instrument this programme keeps
having to throw away.

The escape hatch is free and unambiguous: **quote the scalar.** A quoted or
block scalar ends at its delimiter, not at whitespace-then-hash, so a comment
after one cannot truncate anything and is allowed without comment. When this
rule was written the two queue YAMLs between them held 2,700 lines, 83 full-line
comments and exactly ONE inline comment, on `meta.base`; quoting that scalar was
the whole cost of making the rule absolute.

Full-line comments are untouched by any of this and always have been.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import manifest  # noqa: E402  (imports yaml, and reports usefully if it is absent)

yaml = manifest.yaml

STR_TAG = "tag:yaml.org,2002:str"
BOOL_TAG = "tag:yaml.org,2002:bool"
NULL_TAG = "tag:yaml.org,2002:null"
NUMBER_TAGS = ("tag:yaml.org,2002:int", "tag:yaml.org,2002:float")

# The spellings that mean what they look like. Everything else that YAML types
# as a bool or a null is a word the author probably meant as text.
CANONICAL_BOOL = {"true", "false"}
CANONICAL_NULL = {"", "~", "null"}


def _is_plain(node):
    """A plain (unquoted, non-block) scalar — the only kind that can truncate."""
    return isinstance(node, yaml.nodes.ScalarNode) and node.style in (None, "")


def _walk(node, lines, label, problems):
    if isinstance(node, yaml.nodes.ScalarNode):
        _check_scalar(node, lines, label, problems)
        return

    if isinstance(node, yaml.nodes.MappingNode):
        # An `id:` in this mapping names the problem better than any index can.
        here = label
        for key, value in node.value:
            if getattr(key, "value", None) == "id" and isinstance(value, yaml.nodes.ScalarNode):
                here = value.value
                break

        seen = {}
        for key, value in node.value:
            name = getattr(key, "value", None)
            if name in seen:
                problems.append(
                    "%s:%d: %s: duplicate key %r (first written at line %d). "
                    "PyYAML keeps the last one and discards the other without "
                    "a word." % (label_file(lines), key.start_mark.line + 1, here,
                                 name, seen[name] + 1))
            seen[name] = key.start_mark.line
            _walk(key, lines, here, problems)
            _walk(value, lines, "%s.%s" % (here, name) if name else here, problems)
        return

    if isinstance(node, yaml.nodes.SequenceNode):
        for index, value in enumerate(node.value):
            _walk(value, lines, "%s[%d]" % (label, index), problems)


def _check_scalar(node, lines, label, problems):
    if not _is_plain(node):
        return

    raw = node.value

    # ---- 1. did a comment eat the rest of the line?
    end = node.end_mark
    if 0 <= end.line < len(lines):
        trailing = lines[end.line][end.column:]
        if trailing.lstrip().startswith("#"):
            dropped = trailing.lstrip()
            problems.append(
                "%s:%d: %s: a plain scalar is followed by %r, which YAML reads "
                "as a comment. The value arrives as %r and the rest of the line "
                "is gone. Quote the scalar (or move the comment to its own line)."
                % (label_file(lines), end.line + 1, label,
                   _clip(dropped), _clip(raw)))

    # ---- 2. did YAML retype it into something the source does not spell?
    if node.tag == STR_TAG:
        return

    if node.tag == BOOL_TAG:
        if raw.strip().lower() not in CANONICAL_BOOL:
            problems.append(
                "%s:%d: %s: %r is typed by YAML as the boolean %r. If it was "
                "meant as text, quote it; if it was meant as a boolean, write "
                "true or false."
                % (label_file(lines), node.start_mark.line + 1, label,
                   _clip(raw), yaml.safe_load(raw)))
        return

    if node.tag == NULL_TAG:
        if raw.strip().lower() not in CANONICAL_NULL:
            problems.append(
                "%s:%d: %s: %r is typed by YAML as null. If it was meant as "
                "text, quote it."
                % (label_file(lines), node.start_mark.line + 1, label, _clip(raw)))
        return

    if node.tag in NUMBER_TAGS:
        value = yaml.safe_load(raw)
        if str(value) != raw.strip():
            problems.append(
                "%s:%d: %s: %r is typed by YAML as the number %r, which is not "
                "how it is written. Quote it to keep the spelling."
                % (label_file(lines), node.start_mark.line + 1, label,
                   _clip(raw), value))


# The file being checked, carried on the `lines` list so every message can name
# it without threading another argument through the walk.
def label_file(lines):
    return getattr(lines, "path", "?")


def _display(path):
    """Repo-relative when the file is in the repo, as written when it is not."""
    relative = os.path.relpath(path, manifest.REPO_ROOT)
    return path if relative.startswith(os.pardir) else relative


class _Lines(list):
    """A list of source lines that remembers where it came from."""

    def __init__(self, text, path):
        super().__init__(text.split("\n"))
        self.path = path


def _clip(text, width=64):
    text = text.replace("\n", " ")
    return text if len(text) <= width else text[:width - 1] + "…"


def check(path):
    """Return a list of problem strings. Empty means nothing was lost."""
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    lines = _Lines(source, _display(path))
    problems = []
    for document in yaml.compose_all(source):
        if document is not None:
            _walk(document, lines, "(root)", problems)
    return problems


def default_paths():
    return [p for p in (manifest.MANIFEST_PATH, manifest.GATE_CONTROLS)
            if os.path.exists(p)]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="prove every character in a queue YAML reaches the data")
    parser.add_argument("paths", nargs="*", help="YAML files (default: both queue YAMLs)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    paths = args.paths or default_paths()
    problems = []
    for path in paths:
        try:
            problems.extend(check(path))
        except Exception as error:  # noqa: BLE001 - a parse error is a result
            problems.append("%s: %s" % (path, error))

    if not args.quiet:
        print("queue-fidelity  %s"
              % ", ".join(_display(p) for p in paths))
        for problem in problems:
            print("FAIL  %s" % problem)
        if not problems:
            print("OK    every plain scalar survives the parse intact")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
