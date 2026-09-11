"""sync_cost.py — what does a controller's Nightscout sync cost on the wire?

"Fewer network requests" needs a baseline. This counts the distinct HTTP
calls each controller makes per sync cycle, from its own client source, and
prices them at the cadence the corpus shows.

It is a source-derived count of *endpoints the sync path can call*, not a
packet capture: a cycle with nothing to upload makes fewer calls, and a
catch-up after an outage makes more. The number is therefore an upper bound
per cycle and a fair basis for comparing sync *designs*, which is what it is
for.

The three clients do not share a design:

* **AndroidAPS** uses v3 properly — one ``lastModified`` watermark call,
  then a ``history/{from}`` delta per collection, then a write per
  collection. Cursor-based, but fanned out across collections.
* **Loop** (NightscoutKit) and **Trio** are on v1 only, with no watermark
  and no delta endpoint at all. They page by date range and re-fetch.

So the wire cost is dominated by *per-collection fan-out*, in every client,
whichever API version it is on.
"""

import argparse
import json
import re
from pathlib import Path

from . import corpus

# (label, client source file, endpoint-extraction pattern, api version)
CLIENTS = [
    ("AndroidAPS", "AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/"
     "networking/NightscoutRemoteService.kt",
     r'@(GET|POST|PUT|DELETE)\("([^"]+)"\)', "v3"),
    ("Loop/NightscoutKit", "NightscoutKit/Sources/NightscoutKit/NightscoutClient.swift",
     r'case\s+\w+\s*=\s*"(/api/v[13][^"]*)"', "v1"),
    ("Trio", "Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift",
     r'static let \w+ = "(/api/v[13][^"]*)"', "v1"),
]

# Cycle cadence, from the corpus: oref0 and Loop both run about every five
# minutes, which the census confirms as the devicestatus inter-arrival.
CYCLE_MINUTES = 5
CYCLES_PER_DAY = 24 * 60 // CYCLE_MINUTES


def extract(root: Path, rel, pattern):
    path = root / "externals" / rel
    if not path.is_file():
        return None
    found = []
    for match in re.finditer(pattern, path.read_text(errors="replace")):
        groups = [g for g in match.groups() if g]
        found.append(groups[-1] if len(groups) == 1 else f"{groups[0]} {groups[-1]}")
    return sorted(set(found))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="reports/schema-census/sync-cost.json", type=Path)
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    clients = {}
    for label, rel, pattern, version in CLIENTS:
        endpoints = extract(root, rel, pattern)
        if endpoints is None:
            print(f"  {label:22s} source not present, skipped")
            continue
        reads = [e for e in endpoints if e.startswith("GET") or "/api/v1" in e]
        writes = [e for e in endpoints if e.startswith("POST") or e.startswith("PUT")]
        clients[label] = {
            "source": rel,
            "api_version": version,
            "endpoints": endpoints,
            "endpoint_count": len(endpoints),
            "has_watermark": any("lastModified" in e for e in endpoints),
            "has_delta_endpoint": any("history" in e for e in endpoints),
            "read_endpoints": len(reads),
            "write_endpoints": len(writes),
        }
        print(f"  {label:22s} {version}  {len(endpoints):2d} endpoints  "
              f"watermark={clients[label]['has_watermark']}  "
              f"delta={clients[label]['has_delta_endpoint']}")

    # A batched design: one delta read and one batched write per cycle.
    batched = 2
    comparison = {}
    for label, info in clients.items():
        # Upper bound per cycle: every endpoint the sync path can call.
        per_cycle = info["endpoint_count"]
        comparison[label] = {
            "requests_per_cycle_upper_bound": per_cycle,
            "requests_per_day_upper_bound": per_cycle * CYCLES_PER_DAY,
            "batched_requests_per_cycle": batched,
            "batched_requests_per_day": batched * CYCLES_PER_DAY,
            "reduction_factor": round(per_cycle / batched, 1),
        }

    report = {
        "generated_by": "tools/nsschema/sync_cost.py",
        "note": ("Source-derived upper bound on distinct endpoint calls per sync "
                 "cycle, not a packet capture. Useful for comparing designs."),
        "cycle_minutes": CYCLE_MINUTES,
        "cycles_per_day": CYCLES_PER_DAY,
        "clients": clients,
        "against_a_batched_design": comparison,
    }
    print(f"\n  at {CYCLE_MINUTES}-minute cycles ({CYCLES_PER_DAY}/day), "
          f"against a 2-request batched design:")
    for label, c in sorted(comparison.items()):
        print(f"    {label:22s} up to {c['requests_per_day_upper_bound']:>6,}/day "
              f"-> {c['batched_requests_per_day']:,}  ({c['reduction_factor']}x)")

    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=1) + "\n")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
