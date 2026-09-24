#!/usr/bin/env python3
"""Read the adminnotifies JSON on stdin, print the distinct resolved client
addresses Nightscout recorded, comma-separated and sorted.

The observation channel is the admin-notify a failed authentication emits:
  "A device at IP address <IP> attempted authenticating with Nightscout ..."
Each distinct IP is a distinct notify (the API de-duplicates by message and
increments a count), so the set of IPs here is the set of addresses Nightscout
resolved for the failed attempts since the last reboot.
"""
import json
import re
import sys

RE = re.compile(r"IP address (.+?) attempted")


def main() -> int:
    try:
        doc = json.load(sys.stdin)
    except Exception:
        print("")
        return 0
    notifies = (doc.get("message") or {}).get("notifies") or []
    ips = set()
    for n in notifies:
        m = RE.search(n.get("message", ""))
        if m:
            ips.add(m.group(1))
    print(",".join(sorted(ips)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
