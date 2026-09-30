#!/usr/bin/env python3
"""Render ws_chain.sh JSONL into SANITISED markdown (same rules as analyze.py).

  ws_analyze.py matrix <results-ws.jsonl> <out.md> <date> <dev_sha> <pr_sha>
  ws_analyze.py idle   <results-ws-idle.jsonl> <out.md> <date> <sha> <sha>

The matrix holds honest-client cells only (lab container addresses). Adversarial
detail never reaches these files.
"""
import json
import sys
from collections import OrderedDict

CLIENT = "172.31.66.14"  # ws client container
ORDER = ["UNSET", "false", "1", "2", "3", "4", "true"]


def load(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def matrix(rows, out, date, dev_sha, pr_sha):
    trs = list(OrderedDict.fromkeys(r["transports"] for r in rows))
    topos = list(OrderedDict.fromkeys(r["topology"] for r in rows))
    pr = [r for r in rows if r["tree"] == "pr"]
    settings = [s for s in ORDER if any(r["trust_proxy"] == s for r in pr)]
    cell = {(r["tree"], r["topology"], r["trust_proxy"], r["transports"]): r for r in rows}
    L = [f"# Proxy-trust lab, socket.io cells (SANITISED)", "",
         f"Date: {date}  |  dev tree: `{dev_sha}`  |  PR tree: `{pr_sha}`", "",
         f"Socket address = the address Nightscout recorded for a wrong-secret socket `authorize`"
         f" (correct = `{CLIENT}`). **=http** means a wrong-secret HTTP request from the same client"
         " then recorded the same address; **≠http** means it recorded a different one. W0 = the"
         " socket ended on the transport asked for: with `websocket` in the list, on websocket with"
         " a 101 logged at every HTTP hop; with `polling` alone (the web client's setting), on"
         " polling without an upgrade.", ""]
    for tr in trs:
        L += [f"## Transports `{tr}`", "", "| topology | dev UNSET | " +
              " | ".join(f"TP={s}" for s in settings) + " |",
              "|---|---|" + "---|" * len(settings)]
        for t in topos:
            def fmt(r):
                if not r:
                    return "-"
                ip = r["ws_resolved"]
                tagm = "=http" if r["http_match"] == "yes" else "≠http"
                w0 = "" if r["w0"] == "ok" else " (W0 fail)"
                return f"{ip} {tagm}{w0}"
            row = [fmt(cell.get(("dev", t, "UNSET", tr)))]
            row += [fmt(cell.get(("pr", t, s, tr))) for s in settings]
            L.append(f"| {t} | " + " | ".join(row) + " |")
        L.append("")
    bad = [r for r in rows if r["w0"] != "ok" or r["http_match"] != "yes"]
    L += ["## Cells needing attention", ""]
    if not bad:
        L.append("None: every cell ended on the transport asked for and agreed with HTTP.")
    for r in bad:
        L.append(f"- {r['topology']} {r['tree']} TP={r['trust_proxy']} `{r['transports']}`: "
                 f"W0={r['w0']} (transport={r['transport']}, hops={r['hops_101']}, error={r['error'] or '-'}), "
                 f"http_match={r['http_match']}")
    open(out, "w").write("\n".join(L) + "\n")
    print(f"wrote {out}")


def idle(rows, out, date, sha, _):
    L = [f"# Proxy-trust lab, idle sockets vs hop timeouts (W3)", "",
         f"Date: {date}  |  tree: `{sha}`  |  topology: {rows[0]['topology'] if rows else '-'}"
         f"  |  TRUST_PROXY={rows[0]['trust_proxy'] if rows else '-'}", "",
         "Every HTTP hop gets `proxy_read_timeout`/`proxy_send_timeout` = the hop timeout"
         " (`default` = nginx's 60s). The socket is left idle (no application traffic) for the"
         " window; socket.io's own ping is the only traffic. Disconnects are counted with"
         " client reconnection on.", "",
         "| hop timeout | requested transport | ended on | idle window | disconnects | reasons | connected at end |",
         "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['hop_timeout']} | `{r['requested']}` | {r.get('transport') or '-'} | "
                 f"{int(r.get('idleMs') or 0) // 1000}s | {r.get('disconnects', '-')} | "
                 f"{', '.join(r.get('reasons') or []) or '-'} | {r.get('connectedAtEnd', '-')}"
                 f"{' (error: ' + r['error'] + ')' if r.get('error') else ''} |")
    open(out, "w").write("\n".join(L) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    kind, src, out, a, b, c = sys.argv[1:7]
    {"matrix": matrix, "idle": idle}[kind](load(src), out, a, b, c)
