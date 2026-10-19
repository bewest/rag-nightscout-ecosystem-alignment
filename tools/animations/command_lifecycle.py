"""Command lifecycle (proposed, commands specification): five conformance cases, call by call.

Each case under specs/sync/conformance/commands/ is replayed call by call: an arrow per call between
the role that makes it and the hub, the reply the case expects under it, and the hub's record of the
proposal and the command below. The replies are the case's `expected` block; the record states
between calls are what the reference decision function tools/nsschema/commands.py reports at each
call's time (and at an expiry that falls between two calls), and the replay refuses to render if the
reference's replies or final states differ from the case's. Hashes are payload_hash() (sha256 over
RFC 8785 canonical JSON), shown to 8 hex digits. Rule ids and names come from the cases' `rules` and
docs/30-design/platform/spec/commands.md §4-§7. Ends on a frame listing every case's path and outcome.

    manim -qm --format webm --media_dir <scratch> tools/animations/command_lifecycle.py CommandLifecycle
"""
import sys
from pathlib import Path

import yaml
from manim import Arrow, FadeIn, GrowArrow, Scene, VGroup, linear

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BAD, BAD_T, BLUE, BLUE_T, CARD, FAINT, GOOD, GOOD_T, INK, MUTED, ORANGE, ORANGE_T, P, PX,  # noqa: E402
                    REPO, RULE, TimeAxis, at, box, cell, dot, fit, hline, text_block, vdash, T, width_px)
from nsschema import commands  # noqa: E402
from sources import CM_CASES, COMMAND_CASES, rule_names  # noqa: E402

COLS = {"proposer": 150, "sender": 440, "hub": 780, "controller": 1120}
HEADS = {"proposer": ("proposer", "{agent} instance"), "sender": ("approver / sender", "holds api:commands:create"),
         "hub": ("hub", "records, routes, never judges"), "controller": ("controller", "{ctl}, command sink")}
ROW0, STEP = 196, 46


def short(h):
    return h[:15] + "…"          # "sha256:" + 8 hex digits


def payload_text(p):
    return "{" + ", ".join(f"{k}: {v}" for k, v in p.items()) + "}"


def replay(case):
    """[(call or None for an expiry, expected reply or the expiry time, {id: state} after it)]."""
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


def snapshot(hub, at_):
    s = {}
    for pid, p in hub.proposals.items():
        hub._proposal({"proposal": pid, "tenant": p["tenant"], "at": at_})
        s[pid] = (p["state"], p["payloadHash"], p["expiresAt"])
    for cid, c in hub.commands.items():
        s[cid] = (hub._public(cid, at_), c["payloadHash"], c["expiresAt"])
    return s


def reply_text(call, r):
    kind = call["kind"]
    if kind == "enact":
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


def call_text(case, call, hub_hashes):
    k, t = call["kind"], f"t={call['at']}"
    if k == "propose":
        h = commands.payload_hash(call["payload"])
        return f"{t} propose {payload_text(call['payload'])}, {short(h)}, expiresAt {call['expiresAt']}"
    if k == "approve":
        return f"{t} approve {call['proposal']}, names {short(commands.payload_hash(call['approves']))}"
    if k == "command":
        h = commands.payload_hash(call["payload"])
        return f"{t} command {payload_text(call['payload'])}, {short(h)}, expiresAt {call['expiresAt']}"
    if k == "fetch":
        return f"{t} fetch"
    if k == "report":
        r = f", reason {call['reason']}" if call.get("reason") else ""
        h = commands.payload_hash(call["checked"]) if call.get("checked") else hub_hashes[call["command"]]
        return f"{t} report {call['command']} {call['state']}{r}, hash {short(h)}"
    if k == "read":
        return f"{t} read {call['command']}"
    if k == "cancel":
        return f"{t} cancel {call['command']}"
    return f"{t} {k}"


class CommandLifecycle(Scene):
    def construct(self):
        cases = {cid: yaml.safe_load((REPO / CM_CASES / f"{cid}.yaml").read_text()) for cid in COMMAND_CASES}
        spec = (REPO / "docs/30-design/platform/spec/commands.md").read_text()
        played = {cid: replay(c) for cid, c in cases.items()}
        tag = VGroup(box(880, 14, 1252, 48, ORANGE_T, ORANGE, r=4),
                     at(T("proposed · commands specification", 16, ORANGE, bold=True), 1076, 31, "center"))
        title = at(T("Command lifecycle", 24, bold=True), 40, 31)
        self.add(tag, title)
        seen = []
        for cid in COMMAND_CASES:
            case = cases[cid]
            inst = case["instances"]
            agent = next((v["product"] for v in inst.values() if v.get("proposes")), "AgentTool")
            ctl = next(v["product"] for v in inst.values() if v.get("sinks"))
            names = rule_names(spec, case["rules"])
            head = VGroup(at(fit(f"{cid}: {case['title']}", 16, 1200), 40, 66),
                          at(fit(" · ".join(names), 14, 1200, color=MUTED), 40, 90))
            lanes = VGroup()
            for role, x in COLS.items():
                a, b = HEADS[role]
                lanes.add(box(x - 130, 108, x + 130, 156, BLUE_T if role == "hub" else FAINT,
                              BLUE if role == "hub" else RULE, r=4))
                lanes.add(at(T(a, 16, bold=True), x, 122, "center"))
                lanes.add(at(T(b.format(agent=agent, ctl=ctl), 14, MUTED), x, 143, "center"))
                lanes.add(vdash(x, 158, 470, color=RULE))
            steps = played[cid]
            times = [c["at"] for c, _, _ in steps if c] + [e for c, e, _ in steps if c is None]
            times += [c["expiresAt"] for c, _, _ in steps if c and c.get("expiresAt")]
            ax = TimeAxis(0, 20 * -(-(max(times) + 15) // 20), 140, 1240)
            tl = VGroup(hline(140, 1240, 640, MUTED), at(T("hub time, s", 14, MUTED), 40, 640))
            for t in range(0, int(ax.hi) + 1, 20 if ax.hi <= 200 else 50):
                tl.add(at(T(str(t), 14, MUTED), ax.x(t), 658, "center"))
            for e in sorted({c["expiresAt"] for c, _, _ in steps if c and c.get("expiresAt")}):
                tl.add(vdash(ax.x(e), 622, 646, color=BAD, sw=2))
                tl.add(at(T(f"expiresAt {e}", 14, BAD), ax.x(e) + 6, 618))
            footer, _ = text_block(f"Synthetic conformance case {CM_CASES}/{cid}.yaml; replies from its expected "
                                   "block; record states from the reference tools/nsschema/commands.py.", 40, 688,
                                   14, 1200, color=MUTED, italic=True)
            now = dot(ax.x(0), 640, BLUE, r=6)
            self.add(head, lanes, tl, footer, now)
            self.wait(0.8)

            records = VGroup()
            arrows = VGroup()
            for i, (call, reply, snap) in enumerate(steps):
                y = ROW0 + i * STEP
                fast = call is not None and (call, reply) in seen
                if call is None:
                    row = VGroup(hline(40, 1240, y, BAD, sw=1.5),
                                 at(T(f"t={reply}: expiresAt passes; no call", 14, BAD), 40, y - 12))
                    anims = [FadeIn(row)]
                else:
                    seen.append((call, reply))
                    src, dst = COLS[who(call)], COLS["hub"]
                    hashes = {k: v[1] for k, v in snap.items()}
                    label = call_text(case, call, hashes)
                    good = ok(call, reply)
                    ink = GOOD if good else BAD
                    if call["kind"] == "enact":
                        cmd = cases[cid]["calls"]
                        c = snap[call["command"]]
                        rec = call.get("received")
                        rh = commands.payload_hash(rec) if rec else c[1]
                        chk = (f"t={call['at']} enact: received payload {short(rh)} "
                               f"{'=' if rh == c[1] else '≠'} command's {short(c[1])}; expiresAt {c[2]}")
                        row = VGroup(at(fit(chk, 14, 700), COLS["controller"] - 12, y - 10, "right"),
                                     cell(("→ " if good else "≠ → ") + reply_text(call, reply), COLS["controller"] - 30 - 120,
                                          y + 12, ink=INK, edge=ink, fill=GOOD_T if good else BAD_T, max_right=COLS["controller"] - 20))
                        anims = [FadeIn(row)]
                        del cmd
                    else:
                        arr = Arrow(P(src, y), P(dst, y), buff=0, color=INK, stroke_width=2,
                                    max_tip_length_to_length_ratio=0.04, tip_length=10 * PX)
                        if src < dst:
                            lbl = at(fit(label, 14, dst - 48), dst - 8, y - 12, "right")
                        else:
                            lbl = at(fit(label, 14, 1240 - dst), dst + 8, y - 12)
                        rep = cell(reply_text(call, reply), dst + (110 if src < dst else -110), y + 12,
                                   edge=ink, fill=GOOD_T if good else BAD_T)
                        if src < dst:
                            rep = cell(reply_text(call, reply), 0, y + 12, edge=ink, fill=GOOD_T if good else BAD_T)
                            rep.move_to(P(dst + 10, y + 12), aligned_edge=[-1, 0, 0])
                        else:
                            rep = cell(reply_text(call, reply), 0, y + 12, edge=ink, fill=GOOD_T if good else BAD_T)
                            rep.move_to(P(dst - 10, y + 12), aligned_edge=[1, 0, 0])
                        row = VGroup(lbl, arr, rep)
                        anims = [GrowArrow(arr), FadeIn(lbl), FadeIn(rep)]
                arrows.add(row)
                t_now = call["at"] if call else reply
                new_records = self.records(snap)
                move = now.animate.move_to(P(ax.x(t_now), 640))
                if fast:
                    self.add(row)
                    self.remove(records)
                    self.add(new_records)
                    now.move_to(P(ax.x(t_now), 640))
                    self.wait(0.15)
                else:
                    self.play(*anims, move, run_time=0.45, rate_func=linear)
                    self.remove(records)
                    self.add(new_records)
                    self.wait(0.7)
                records = new_records
            self.wait(0.3)
            self.remove(*[m for m in self.mobjects if m is not tag and m is not title])
        self.remove(title)
        self.summary(cases, played, spec)

    def records(self, snap):
        """The hub's record of each proposal and command at this moment."""
        g = VGroup(at(T("hub records", 14, MUTED), 40, 494))
        y = 520
        for k, (state, h, exp) in snap.items():
            kind = "proposal" if k.startswith("p") else "command"
            final = state in commands.FINAL or state in ("approved", "rejected", "withdrawn")
            bad = state in ("expired", "refused", "failed", "cancelled", "unconfirmed", "undeliverable")
            s = f"{kind} {k}: {state} · payloadHash {short(h)} · expiresAt {exp}"
            t = T(s, 16, bold=False)
            w = width_px(t) + 24
            g.add(box(40, y - 17, 40 + w, y + 17, BAD_T if bad else (GOOD_T if final else CARD), BAD if bad else RULE, r=4))
            g.add(at(t, 52, y))
            y += 40
        if len(snap) == 0:
            g.add(at(T("none yet", 16, MUTED), 40, 520))
        return g

    def summary(self, cases, played, spec):
        """The poster: every case's calls and replies, its final record states, and its rules."""
        g = VGroup(at(T("Command lifecycle: five conformance cases", 24, bold=True), 40, 31))
        y = 74
        for cid in COMMAND_CASES:
            case = cases[cid]
            g.add(box(28, y - 14, 1252, y + 92, FAINT))
            g.add(at(fit(case["title"], 16, 1180, bold=True), 40, y + 4))
            path = []
            for call, reply, _ in played[cid]:
                if call is None:
                    path.append(f"t={reply} expiry passes")
                else:
                    path.append(f"{call['kind']} → {reply_text(call, reply)}")
            lines, yy = text_block(" ⟶ ".join(path), 40, y + 28, 14, 1190)
            g.add(lines)
            fin = case["expected"]
            states = [f"proposal {k} {v['state']}" for k, v in fin.get("proposals", {}).items()]
            states += [f"command {k} {v['state']}" + (", report hash mismatch" if v.get("hashMismatch") else "")
                       for k, v in fin.get("commands", {}).items()]
            g.add(at(fit("final: " + ("; ".join(states) or "no command") + " · rules " + ", ".join(case["rules"]),
                         14, 1190, color=MUTED), 40, yy + 2))
            y += 118
        g.add(at(fit("proposed (commands specification, docs/30-design/platform/spec/commands.md §4-§7); synthetic "
                     f"cases under {CM_CASES}/.", 14, 1200, color=MUTED, italic=True), 40, 704))
        self.add(g)
        self.wait(3)
