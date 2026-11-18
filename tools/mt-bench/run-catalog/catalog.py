#!/usr/bin/env python3
"""Index and compare private experiment results without editing their originals."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from retained import get, key_digest, project

ARTIFACTS = Path("/mnt/data/nightscout-workspace/artifacts")
ID_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")
UNSAFE_PROVENANCE = {"PROVENANCE_INVALID", "PROVENANCE_MISMATCH", "CONFIG_MISMATCH"}
TERMINAL = {"OBSERVED", "PARTIAL", "FAILED", "FAILED_PARTIAL", "PASS", "FAIL", "REFUSED",
            "ABORTED", "STARTUP_ONLY", "MEASURED", "NOT_STARTED", "VERIFIED",
            "COMPLETED", "COMPLETED_PARTIAL", "OBSERVED_PARTIAL"}
NONTERMINAL = {"PREPARING", "PREPARED", "RUNNING", "SESSION_OPEN", "PENDING", "READY"}


class CatalogError(ValueError):
    pass


def identifier(value):
    if len(value) > 768 or not all(ID_PART.fullmatch(part) for part in value.split("/")):
        raise CatalogError("invalid run ID")
    return value


def record_path(index, run_id):
    return index / (key_digest(identifier(run_id)) + ".json")


def read_record(path):
    with path.open() as handle:
        record = json.load(handle)
    if not isinstance(record, dict) or record.get("version") != 1 or not isinstance(record.get("id"), str):
        raise CatalogError(f"invalid record at {path}")
    if record_path(path.parent, record["id"]) != path:
        raise CatalogError(f"run ID does not match record at {path}")
    return record


def add(artifacts, index, path, *, allow_partial=False):
    root = path.resolve(strict=True)
    try:
        run_id = identifier(root.relative_to(artifacts).as_posix())
    except ValueError as exc:
        raise CatalogError("run directory must be under the artifacts root") from exc
    if not root.is_dir():
        raise CatalogError("expected a run directory")
    record = project(root, run_id)
    if not record["evidence"]:
        raise CatalogError("no recognized run evidence")
    if record["runStatus"] in NONTERMINAL:
        raise CatalogError("run is still open; select its completed observation")
    if record["runStatus"] not in TERMINAL and not allow_partial:
        raise CatalogError("terminal status unavailable; use --partial after the run has stopped")
    target = record_path(index, run_id)
    index.mkdir(mode=0o700, parents=True, exist_ok=True)
    # A successful link publishes the fully written candidate without replacing
    # any earlier capture. Readers never see a partially written record.
    with tempfile.NamedTemporaryFile(mode="w", dir=index, prefix=".incoming-") as staged:
        json.dump(record, staged, indent=2, sort_keys=True, allow_nan=False)
        staged.write("\n")
        staged.flush()
        os.fsync(staged.fileno())
        try:
            os.link(staged.name, target)
        except FileExistsError:
            if record != read_record(target):
                raise CatalogError(f"run ID already has a different record: {run_id}") from None
    fd = os.open(index, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return record


def list_records(index):
    return sorted((read_record(path) for path in index.glob("*.json")), key=lambda row: row["id"])


def compare(current, baseline, *, source_change=False):
    changes = {}
    reasons = []

    def check(name, after, before, *, required=False, allow=False):
        if after != before:
            changes[name] = {"baseline": before, "current": after}
            if not allow:
                reasons.append(name + " differs")
        if required and (after is None or before is None):
            reasons.append(name + " is unmeasured")

    for name in ("producer", "tier", "population", "replicas", "cadence"):
        check(name, current[name], baseline[name], required=True)
    for name in ("source", "image", "tool", "workload", "allocation", "config"):
        after = current["provenance"][name]
        before = baseline["provenance"][name]
        if name == "source" and (not all(after.values()) or not all(before.values())):
            reasons.append("source tuple is unmeasured")
        check(name, after, before, required=True,
              allow=name == "config" or source_change and name in ("source", "image"))
    if source_change:
        same_pair = current["provenance"]["source"] == baseline["provenance"]["source"]
        same_image = current["provenance"]["image"] == baseline["provenance"]["image"]
        if not same_pair and same_image:
            reasons.append("changed source has the same image identity")
    for name in ("host", "contention", "driverHostSha256", "observerHostSha256", "cores", "loadAverage1m"):
        check("environment." + name, current["environment"].get(name), baseline["environment"].get(name),
              required=name in ("host", "contention"), allow=name == "loadAverage1m")
    for name in ("runtime", "priorObservations", "priorPlan", "elapsedSeconds", "declaredSha256"):
        check("history." + name, current["history"].get(name), baseline["history"].get(name),
              required=name in ("runtime", "priorPlan"), allow=name in ("elapsedSeconds", "declaredSha256"))
    check("work.scope", current["work"]["scope"], baseline["work"]["scope"])
    for record in (current, baseline):
        if any(issue["code"] in UNSAFE_PROVENANCE for issue in record["issues"]):
            reasons.append(record["id"] + " has inconsistent provenance")
        if record["work"]["issued"] in (None, 0):
            reasons.append(record["id"] + " has no measured issued scenario work")
        if not record["limits"]["nativeReadback"]:
            reasons.append(record["id"] + " has no native resource readback")

    results = {}
    for name in sorted(current["signals"].keys() | baseline["signals"].keys()):
        after = current["signals"].get(name)
        before = baseline["signals"].get(name)
        entry = {"current": after, "baseline": before, "delta": None}
        if get(after, "status") != "MEASURED" or get(before, "status") != "MEASURED":
            entry["status"] = "UNMEASURED"
        elif any(after[key] != before[key] for key in ("unit", "denominator", "scope")):
            entry["status"] = "DENOMINATOR_OR_SCOPE_MISMATCH"
        elif reasons:
            entry["status"] = "RUNS_INCOMPATIBLE"
        else:
            entry.update(status="COMPARED", delta=after["value"] - before["value"])
        results[name] = entry
    return {
        "current": current["id"], "baseline": baseline["id"], "changedAxes": changes,
        "status": "INCOMPATIBLE" if reasons else "COMPARABLE",
        "reasons": reasons, "signals": results,
        "work": {"current": current["work"], "baseline": baseline["work"]},
        "oracles": {"current": current["oracles"], "baseline": baseline["oracles"]},
        "capacityAcceptance": "NOT_GRANTED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    sub = parser.add_subparsers(dest="action", required=True)
    index = sub.add_parser("add", help="index one completed run or observation directory")
    index.add_argument("run", type=Path)
    index.add_argument("--partial", action="store_true", help="index interrupted evidence after all writers stop")
    session = sub.add_parser("session", help="index closed observations under a session directory")
    session.add_argument("run", type=Path)
    sub.add_parser("list", help="derive the index from complete immutable records")
    show = sub.add_parser("show")
    show.add_argument("run")
    diff = sub.add_parser("compare")
    diff.add_argument("run")
    diff.add_argument("baseline")
    diff.add_argument("--change", choices=["source"], help="allow a deliberate core/deployment/image comparison")
    args = parser.parse_args(argv)
    artifacts = args.artifacts.resolve()
    index = artifacts / "capacity-index"
    try:
        if args.action == "add":
            result = add(artifacts, index, args.run, allow_partial=args.partial)
        elif args.action == "session":
            if not args.run.resolve().is_relative_to(artifacts):
                raise CatalogError("session directory must be under the artifacts root")
            indexed = []
            skipped = []
            for path in sorted(args.run.glob("observations/*/result.json")):
                try:
                    indexed.append(add(artifacts, index, path.parent)["id"])
                except (CatalogError, OSError) as exc:
                    skipped.append({"observation": path.parent.name, "error": str(exc)})
            result = {"indexed": indexed, "skipped": skipped}
        elif args.action == "list":
            result = list_records(index)
        elif args.action == "show":
            result = read_record(record_path(index, args.run))
        else:
            result = compare(read_record(record_path(index, args.run)),
                             read_record(record_path(index, args.baseline)), source_change=args.change == "source")
    except (CatalogError, OSError, json.JSONDecodeError) as exc:
        print(f"catalog: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 2 if args.action == "compare" and result["status"] == "INCOMPATIBLE" else 0


if __name__ == "__main__":
    sys.exit(main())
