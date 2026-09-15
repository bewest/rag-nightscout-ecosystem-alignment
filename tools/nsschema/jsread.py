"""jsread.py — read literal declarations out of cgm-remote-monitor's source.

Four of the nine collections the server opens have never been censused, and
no OpenAPI document describes them. Their only authority is the server's own
source, so this module reads that source rather than asking anyone to retype
it: a hand-copied field list is a fifth independent declaration of the
document model and the one most likely to rot.

The subset parsed here is deliberately tiny — the object, array, string,
number and boolean literals that cgm-remote-monitor uses to declare record
templates, index lists and default roles. It is not a JavaScript engine and
must never become one; anything it cannot parse raises, so a source change it
cannot follow fails loudly instead of yielding a plausible-looking field set.

Identifiers are returned as :class:`Ident` rather than resolved, because
resolving them is the caller's problem: ``position: HIDDEN`` in the food
quick-pick template is only a number once you have found ``var HIDDEN``.
"""

import re
from dataclasses import dataclass


class JsParseError(ValueError):
    """The source used a construct this reader deliberately does not handle."""


@dataclass(frozen=True)
class Ident:
    """A bare identifier used as a value, e.g. ``position: HIDDEN``."""
    name: str


_WS = " \t\r\n"
_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"-?(?:0[xX][0-9a-fA-F]+|\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def strip_comments(text: str) -> str:
    """Blank out // and /* */ comments, preserving offsets and line breaks.

    Offsets are preserved so that an error message can still point at a line
    in the original file, and so a caller may slice the original text with an
    index found in the stripped text.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'`":
            quote = ch
            i += 1
            while i < n and text[i] != quote:
                i += 2 if text[i] == "\\" else 1
            i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            out[i] = out[i + 1] = " "
            i += 2
        else:
            i += 1
    return "".join(out)


class _Reader:
    def __init__(self, text: str, pos: int = 0):
        self.text = text
        self.pos = pos

    def skip(self):
        while self.pos < len(self.text) and self.text[self.pos] in _WS:
            self.pos += 1

    def peek(self):
        self.skip()
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def expect(self, ch):
        if self.peek() != ch:
            raise JsParseError(f"expected {ch!r} at offset {self.pos}, "
                               f"found {self.text[self.pos:self.pos + 20]!r}")
        self.pos += 1

    def value(self):
        ch = self.peek()
        if ch == "":
            raise JsParseError("unexpected end of source")
        if ch == "{":
            return self.obj()
        if ch == "[":
            return self.arr()
        if ch in "\"'":
            return self.string()
        if ch == "`":
            raise JsParseError("template literals are not read; declare a plain string")
        match = _NUMBER.match(self.text, self.pos)
        if match and (ch.isdigit() or ch == "-" or ch == "."):
            self.pos = match.end()
            raw = match.group(0)
            if raw.lower().startswith("0x") or raw.lower().startswith("-0x"):
                return int(raw, 16)
            return float(raw) if any(c in raw for c in ".eE") else int(raw)
        match = _IDENT.match(self.text, self.pos)
        if match:
            self.pos = match.end()
            word = match.group(0)
            if word == "true":
                return True
            if word == "false":
                return False
            if word == "null":
                return None
            if self.peek() in "(.":
                raise JsParseError(f"{word!r} is a call or member expression, not a literal")
            return Ident(word)
        raise JsParseError(f"cannot read a value at offset {self.pos}: "
                           f"{self.text[self.pos:self.pos + 20]!r}")

    def string(self):
        quote = self.text[self.pos]
        self.pos += 1
        out = []
        while self.pos < len(self.text) and self.text[self.pos] != quote:
            ch = self.text[self.pos]
            if ch == "\\":
                self.pos += 1
                nxt = self.text[self.pos]
                out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
            else:
                out.append(ch)
            self.pos += 1
        if self.pos >= len(self.text):
            raise JsParseError("unterminated string")
        self.pos += 1
        return "".join(out)

    def arr(self):
        self.expect("[")
        items = []
        while True:
            if self.peek() == "]":
                self.pos += 1
                return items
            items.append(self.value())
            if self.peek() == ",":
                self.pos += 1
            elif self.peek() != "]":
                raise JsParseError(f"expected ',' or ']' at offset {self.pos}")

    def obj(self):
        self.expect("{")
        out = {}
        while True:
            ch = self.peek()
            if ch == "}":
                self.pos += 1
                return out
            if ch == ",":
                # cgm-remote-monitor writes leading-comma object literals, so a
                # comma may appear before the first key as well as between keys.
                self.pos += 1
                continue
            if ch in "\"'":
                key = self.string()
            else:
                match = _IDENT.match(self.text, self.pos)
                if not match:
                    raise JsParseError(f"expected a property name at offset {self.pos}")
                self.pos = match.end()
                key = match.group(0)
            self.expect(":")
            out[key] = self.value()


def read_literal(text: str, target: str):
    """Parse the literal assigned to ``target``, e.g. ``foodrec_template``.

    ``target`` may be a dotted path (``storage.defaultRoles``). The first
    assignment wins; a second assignment to the same name raises, because a
    reader that silently took one of two declarations would be guessing.
    """
    stripped = strip_comments(text)
    pattern = re.compile(
        r"(?:^|[^\w$.])" + re.escape(target) + r"\s*=\s*(?=[\[{'\"])", re.M)
    matches = list(pattern.finditer(stripped))
    if not matches:
        raise KeyError(f"no literal assignment to {target!r}")
    if len(matches) > 1:
        raise JsParseError(
            f"{target!r} is assigned {len(matches)} times; "
            "this reader will not choose between them")
    return _Reader(stripped, matches[0].end()).value()


def literal_line(text: str, target: str) -> int:
    """The 1-based line on which ``target``'s literal assignment begins.

    So that a generated artifact can cite ``lib/server/entries.js:246``
    rather than a bare filename, and a reviewer can open the line.
    """
    stripped = strip_comments(text)
    pattern = re.compile(
        r"(?:^|[^\w$.])" + re.escape(target) + r"\s*=\s*(?=[\[{'\"])", re.M)
    match = pattern.search(stripped)
    if not match:
        raise KeyError(f"no literal assignment to {target!r}")
    return text.count("\n", 0, match.end()) + 1


def call_line(text: str, call: str) -> int:
    """The 1-based line of the first call to ``call``."""
    stripped = strip_comments(text)
    match = re.search(r"(?:^|[^\w$.])" + re.escape(call) + r"\s*\(", stripped, re.M)
    if not match:
        raise KeyError(f"no call to {call!r}")
    return text.count("\n", 0, match.end()) + 1


def read_constant(text: str, target: str):
    """Parse a scalar constant, e.g. ``var HIDDEN = 99999``.

    Separate from :func:`read_literal` so that resolving an identifier used as
    a value is an explicit act. ``quickpickrec_template.position`` is
    ``Ident('HIDDEN')`` until someone asks for ``HIDDEN`` by name.
    """
    stripped = strip_comments(text)
    pattern = re.compile(
        r"(?:^|[^\w$.])" + re.escape(target) + r"\s*=\s*(?![=>])", re.M)
    matches = list(pattern.finditer(stripped))
    if not matches:
        raise KeyError(f"no assignment to {target!r}")
    if len(matches) > 1:
        raise JsParseError(
            f"{target!r} is assigned {len(matches)} times; "
            "this reader will not choose between them")
    return _Reader(stripped, matches[0].end()).value()


def assigned_properties(text: str, receiver: str):
    """Property names assigned on ``receiver``, e.g. every ``subject.x = ...``.

    Returns them in source order, de-duplicated. This is how the fields a
    module *writes onto* a document are found when there is no template
    literal to read — ``authorization/storage.js`` decorates each subject in
    ``reload()`` rather than declaring a shape.
    """
    stripped = strip_comments(text)
    pattern = re.compile(
        r"(?:^|[^\w$.])" + re.escape(receiver) + r"\.([A-Za-z_$][\w$]*)\s*=(?!=)", re.M)
    seen = []
    for match in pattern.finditer(stripped):
        if match.group(1) not in seen:
            seen.append(match.group(1))
    return seen


def deleted_properties(text: str, receiver: str):
    """Property names ``delete``d from ``receiver``.

    A name a module goes out of its way to remove is a name someone expected
    to be there. ``delete role.autoGenerated`` is the only mention of that
    field anywhere in cgm-remote-monitor, and a model that listed only
    assigned names would not record that the guard exists.
    """
    stripped = strip_comments(text)
    pattern = re.compile(
        r"\bdelete\s+" + re.escape(receiver) + r"\.([A-Za-z_$][\w$]*)")
    seen = []
    for match in pattern.finditer(stripped):
        if match.group(1) not in seen:
            seen.append(match.group(1))
    return seen


def call_argument(text: str, call: str, index: int):
    """The literal at position ``index`` of the first call to ``call``.

    Used for ``pick(subject, ['_id', 'name', ...])`` and
    ``ensureIndexes(rolesCollection, ['name'])``, where the field list is an
    argument rather than an assignment.
    """
    stripped = strip_comments(text)
    match = re.search(r"(?:^|[^\w$.])" + re.escape(call) + r"\s*\(", stripped, re.M)
    if not match:
        raise KeyError(f"no call to {call!r}")
    reader = _Reader(stripped, match.end())
    args = []
    while True:
        if reader.peek() == ")":
            break
        args.append(reader.value())
        if reader.peek() == ",":
            reader.pos += 1
        else:
            break
    if index >= len(args):
        raise JsParseError(f"{call}() has {len(args)} arguments, wanted #{index}")
    return args[index]


def keyed_call_argument(text: str, call: str, key: str, index: int = 1):
    """The literal at ``index`` of the call ``call('<key>', ...)``.

    ``app.set`` is invoked a dozen times in lib/api3/index.js and only one of
    those calls declares the enabled collections, so the first-call rule of
    :func:`call_argument` is not enough. Matching on the key makes the anchor
    survive a reordering of the surrounding calls.
    """
    stripped = strip_comments(text)
    pattern = re.compile(
        r"(?:^|[^\w$.])" + re.escape(call) + r"\s*\(\s*['\"]" + re.escape(key)
        + r"['\"]\s*,", re.M)
    matches = list(pattern.finditer(stripped))
    if not matches:
        raise KeyError(f"no call to {call}({key!r}, ...)")
    if len(matches) > 1:
        raise JsParseError(f"{call}({key!r}, ...) appears {len(matches)} times")
    reader = _Reader(stripped, matches[0].end())
    args = [None]
    while True:
        if reader.peek() == ")":
            break
        args.append(reader.value())
        if reader.peek() == ",":
            reader.pos += 1
        else:
            break
    if index >= len(args):
        raise JsParseError(f"{call}({key!r}, ...) has {len(args)} arguments")
    return args[index]


def js_type(value):
    """The JSON type name for a parsed literal, or None if undeterminable."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return None
