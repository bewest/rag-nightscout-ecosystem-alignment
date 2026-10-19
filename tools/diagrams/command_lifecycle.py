"""The command lifecycle as the commands specification proposes it: five conformance cases, call by call.

Input: specs/sync/conformance/commands/<case>.yaml (synthetic, expectations authored by hand) and the
rule names of docs/30-design/platform/spec/commands.md. Each case is one panel:
  title, rules   the case's title; its rules with their bold names from the specification
  one row a call t (hub time, seconds), the role that makes the call, the call, and the reply the
                 case expects (green when accepted or succeeded, red otherwise; the reply's status,
                 code or state is always written)
  expiry row     an expiry that falls between two calls, in red: no call is made, the clock passes it
  enact row      the controller's check: the hash of the payload it received against the command's
  final          the record states the case expects after its last call
Payloads are shown as written; a hash is payload_hash() (sha256 over RFC 8785 canonical JSON) to 8
hex digits. The reference decision function tools/nsschema/commands.py replays every case: build()
refuses a case whose replies or final states differ from the reference's, and the hashes of the
command a report or an enact names come from the reference's record at that call.
"""
import re
import sys

import yaml

from svgkit import (BAD, BAD_T, FAINT, GOOD, GOOD_T, INK, MUTED, ORANGE, ORANGE_T, REPO, RULE, W, line, rect,
                    svg, text, tw, wrap)

sys.path.insert(0, str(REPO / "tools"))
from nsschema import commands  # noqa: E402

CASES = REPO / "specs" / "sync" / "conformance" / "commands"
SPEC = REPO / "docs" / "30-design" / "platform" / "spec" / "commands.md"
DRAWN = ["approve-creates-command-with-proposal-payload", "approve-after-proposal-expiry",
         "enact-hash-mismatch-refused", "report-on-unconfirmed-after-expiry-accepted",
         "cancel-after-fetch-is-a-request"]
INPUTS = [CASES / f"{c}.yaml" for c in DRAWN] + [SPEC]

# shown 688 px wide on a 1440 px desktop window (0.956 of the 720 px card): 13 px text shows at 12.4 px
FS, FS_HEAD, FS_TITLE, LH = 13, 14, 16, 17
PAD = 12
T_X, ROLE_X, CALL_X, REPLY_X = PAD + 6, PAD + 50, PAD + 136, 468
CALL_W, REPLY_W = REPLY_X - CALL_X - 12, W - PAD - 6 - REPLY_X


def short(h):
    return h[:15] + "…"          # "sha256:" + 8 hex digits


def payload_text(p):
    return "{" + ", ".join(f"{k}: {v}" for k, v in p.items()) + "}"


def load(cid):
    return yaml.safe_load((CASES / f"{cid}.yaml").read_text())


def rule_names(ids):
    spec = SPEC.read_text()
    out = []
    for rid in ids:
        m = re.search(r"^\| " + re.escape(rid) + r" \| \*\*(.+?)\*\*", spec, re.M)
        if not m:
            raise SystemExit(f"rule {rid} not found in {SPEC.relative_to(REPO)}")
        out.append(f"{rid} {m.group(1).rstrip('.')}")
    return out


def snapshot(hub, at_):
    s = {}
    for pid, p in hub.proposals.items():
        hub._proposal({"proposal": pid, "tenant": p["tenant"], "at": at_})
        s[pid] = (p["state"], p["payloadHash"], p["expiresAt"])
    for cid, c in hub.commands.items():
        s[cid] = (hub._public(cid, at_), c["payloadHash"], c["expiresAt"])
    return s


def replay(case):
    """[(call, or None for an expiry; the expected reply, or the expiry time; {id: state} after it)]."""
    hub = commands.Hub(case)
    calls, want = case["calls"], case["expected"]["calls"]
    expiries = sorted({c["expiresAt"] for c in calls if c.get("expiresAt")})
    out, prev = [], -1
    for call, exp in zip(calls, want):
        for e in expiries:
            if prev < e <= call["at"] and e != call["at"]:
                out.append((None, e, snapshot(hub, e)))
        got = getattr(hub, call["kind"])(call)
        if got != exp:
            raise SystemExit(f"{case['id']}: reference reply {got} differs from expected {exp}")
        out.append((call, exp, snapshot(hub, call["at"])))
        prev = call["at"]
    final = commands.run(case)
    if final["commands"] != case["expected"].get("commands", {}) or \
            final["proposals"] != case["expected"].get("proposals", {}):
        raise SystemExit(f"{case['id']}: reference final states differ from expected")
    return out


def reply_text(call, r):
    if call["kind"] == "enact":
        return r["state"] + (f", reason {r['reason']}" if r.get("reason") else "")
    bits = [str(r["status"])] if "status" in r else []
    if r.get("code"):
        bits.append(r["code"])
    for k in ("proposalId", "commandId"):
        if r.get(k):
            bits.append(r[k])
    if r.get("state"):
        bits.append(r["state"])
    if r.get("cancelRequested"):
        bits.append("cancelRequested")
    if "commands" in r:
        bits.append("commands [" + ", ".join(r["commands"]) + "]")
    if r.get("cancels"):
        bits.append("cancels [" + ", ".join(r["cancels"]) + "]")
    return " · ".join(bits)


def ok(call, r):
    if call["kind"] == "enact":
        return r["state"] == "succeeded"
    return r.get("status", 200) < 300


def who(call):
    return {"propose": "proposer", "fetch": "controller", "report": "controller", "enact": "controller"}.get(
        call["kind"], "sender")


def call_text(call, snap):
    k = call["kind"]
    if k == "propose":
        return (f"propose {payload_text(call['payload'])}, {short(commands.payload_hash(call['payload']))}, "
                f"expiresAt {call['expiresAt']}")
    if k == "approve":
        return f"approve {call['proposal']}, names {short(commands.payload_hash(call['approves']))}"
    if k == "command":
        return (f"command {payload_text(call['payload'])}, {short(commands.payload_hash(call['payload']))}, "
                f"expiresAt {call['expiresAt']}")
    if k == "report":
        r = f", reason {call['reason']}" if call.get("reason") else ""
        h = commands.payload_hash(call["checked"]) if call.get("checked") else snap[call["command"]][1]
        return f"report {call['command']} {call['state']}{r}, hash {short(h)}"
    if k == "enact":
        _, h, exp = snap[call["command"]]
        rh = commands.payload_hash(call["received"]) if call.get("received") else h
        return (f"enact {call['command']}: received payload {short(rh)} {'=' if rh == h else '≠'} "
                f"command's {short(h)}; expiresAt {exp}")
    if k in ("read", "cancel"):
        return f"{k} {call['command']}"
    return k


def final_text(case):
    fin = case["expected"]
    states = [f"proposal {k} {v['state']}" for k, v in fin.get("proposals", {}).items()]
    states += [f"command {k} {v['state']}" + (", report hash mismatch" if v.get("hashMismatch") else "")
               for k, v in fin.get("commands", {}).items()]
    return "final: " + ("; ".join(states) or "no command")


def panel(case, steps, y):
    body = []
    top = y
    y += 20
    head = [(s, FS_HEAD, INK, "bold") for s in wrap(case["title"], W - 2 * PAD - 12, FS_HEAD, bold=True)]
    head += [(s, FS, MUTED, None) for s in wrap("rules " + " · ".join(rule_names(case["rules"])),
                                                W - 2 * PAD - 12, FS)]
    for s, size, fill, weight in head:
        body.append(text(T_X, y, s, size, fill, weight=weight))
        y += LH + 1
    y += 2
    for call, reply, snap in steps:
        if call is None:
            body.append(line(T_X, y - 4, W - PAD - 6, y - 4, BAD, 1.5, dash="5 3"))
            body.append(text(T_X, y + 10, f"t={reply}", FS, BAD))
            body.append(text(CALL_X, y + 10, f"expiresAt {reply} passes; no call", FS, BAD))
            y += LH + 8
            continue
        good = ok(call, reply)
        cl = wrap(call_text(call, snap), CALL_W, FS)
        rl = wrap("→ " + reply_text(call, reply), REPLY_W - 12, FS)
        n = max(len(cl), len(rl))
        body.append(rect(REPLY_X, y - 2, REPLY_W, n * LH + 6, GOOD_T if good else BAD_T, GOOD if good else BAD,
                         rx=3))
        body.append(text(T_X, y + 11, f"t={call['at']}", FS, MUTED))
        body.append(text(ROLE_X, y + 11, who(call), FS, INK))
        for i, s in enumerate(cl):
            body.append(text(CALL_X, y + 11 + i * LH, s, FS, INK))
        for i, s in enumerate(rl):
            body.append(text(REPLY_X + 6, y + 11 + i * LH, s, FS, INK))
        y += n * LH + 10
    body.append(text(T_X, y + 10, final_text(case), FS, MUTED))
    y += LH + 8
    return [rect(PAD, top, W - 2 * PAD, y - top, FAINT, rx=4)] + body, y + 8


def figure(cases, played):
    title = "Command lifecycle: five conformance cases, call by call"
    tag = "proposed · commands specification"
    tag_w = tw(tag, FS) * 1.08 + 14
    body = [text(PAD, 24, title, FS_TITLE, INK, weight="bold"),
            rect(W - PAD - tag_w, 10, tag_w, 20, ORANGE_T, ORANGE, rx=3),
            text(W - PAD - tag_w / 2, 24, tag, FS, ORANGE, anchor="middle", weight="bold")]
    sub = wrap("Each panel is one case: t is hub time in seconds; the role making each call; the call; the "
               "reply the case expects (green: accepted or succeeded; red: refused, rejected or failed). A "
               "red dashed line is an expiry passing between two calls.", W - 2 * PAD, FS)
    y = 48
    for s in sub:
        body.append(text(PAD, y, s, FS, MUTED))
        y += LH
    y += 4
    body.append(text(T_X, y + 4, "t", FS, MUTED, weight="bold"))
    body.append(text(ROLE_X, y + 4, "role", FS, MUTED, weight="bold"))
    body.append(text(CALL_X, y + 4, "call", FS, MUTED, weight="bold"))
    body.append(text(REPLY_X + 6, y + 4, "reply", FS, MUTED, weight="bold"))
    body.append(line(PAD, y + 10, W - PAD, y + 10, RULE))
    y += 18
    for cid in DRAWN:
        els, y = panel(cases[cid], played[cid], y)
        body += els
    foot = ("Proposed, docs/30-design/platform/spec/commands.md §4–§7. Synthetic cases under "
            "specs/sync/conformance/commands/; replies from each case's expected block, replayed by the "
            "reference tools/nsschema/commands.py.")
    for s in wrap(foot, W - 2 * PAD, FS):
        body.append(text(PAD, y + 6, s, FS, MUTED, italic=True))
        y += LH
    desc = ("Five synthetic command conformance cases, call by call, as the commands specification proposes. "
            + " ".join(f"{cases[c]['title']}: {final_text(cases[c])}." for c in DRAWN))
    return svg(W, y + 12, title, desc, body)


def build():
    cases = {c: load(c) for c in DRAWN}
    played = {c: replay(cases[c]) for c in DRAWN}
    return {"command-lifecycle.svg": figure(cases, played)}
