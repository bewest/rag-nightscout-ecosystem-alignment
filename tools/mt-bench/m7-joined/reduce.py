"""Reduce observable resource windows; absent samples are NO-MEASUREMENT."""
import csv
import math
import re
from pathlib import Path
from contract import require, metric
import json


def memory(text):
    match = re.match(r"([\d.]+)([KMGT]?i?B)", text.strip())
    require(match is not None, "M7_MEMORY_SAMPLE_INVALID")
    return float(match[1]) * {"B":1,"KB":1000,"MB":10**6,"GB":10**9,"TB":10**12,"KiB":1024,"MiB":1024**2,"GiB":1024**3,"TiB":1024**4}[match[2]]


def pg(path):
    result = {}
    for line in path.read_text().splitlines():
        name, calls, ms = line.split("\t");result[name] = {"calls": int(calls), "executionMs": float(ms)}
    return result


def measurements(directory, manifest):
    windows = {}
    complete = True
    for name in ("idle-disabled", "idle", "load"):
        folder = directory / name
        before = json.loads((folder / "before-cgroups.json").read_text())
        after = json.loads((folder / "after-cgroups.json").read_text())
        seconds = after["at"] - before["at"]
        require(math.isfinite(seconds) and seconds > 0,"M7_WINDOW_INVALID")
        rows, load_generators = {}, {}
        for role in sorted(set(before["roles"]) | set(after["roles"])):
            value = after["roles"].get(role, {})
            first = before["roles"].get(role, {})
            if role == "k6":
                load_generators[role] = {"source": "docker-stats-window", "processRssKiBAfter": value.get("processRssKiB", "UNMEASURED"), "snapshotCpu": "UNMEASURED"}
                continue
            # A restart resets CPU counters; identify this rather than subtract
            # counters from different containers/process lifetimes.
            if not value or not first or value.get("unavailable") or first.get("unavailable") or value.get("id") != first.get("id"):
                rows[role] = {"measurement": "NO-MEASUREMENT"};complete = False;continue
            def cgroup(raw):
                cpu = int(re.search(r"^usage_usec (\d+)$",raw,re.M)[1])
                anon = int(re.search(r"^anon (\d+)$",raw,re.M)[1])
                current = [int(line) for line in raw.splitlines() if line.isdigit()][0]
                return cpu, anon, current
            a, b = cgroup(first["cgroup"]), cgroup(value["cgroup"])
            rss=value.get("processRssKiB","")
            lines=rss.strip().splitlines() if isinstance(rss,str) else []
            complete = complete and len(lines)>=2 and lines[0].split()==['PID','COMMAND','RSS'] and all(re.fullmatch(r'\s*[0-9]+\s+.+?\s+[0-9]+\s*',line) for line in lines[1:])
            delta = b[0] - a[0]
            complete = complete and delta >= 0
            rows[role] = {"cpuUsecDelta": delta if delta >= 0 else None, "cpuCoresMean": delta / 1e6 / seconds if delta >= 0 else None,
                          "counterReset": delta < 0, "processRssKiBAfter": value.get("processRssKiB"), "anonBytesAfter": b[1], "memoryCurrentBytesAfter": b[2]}
        if name != "idle-disabled":
            with (folder / "docker-stats.tsv").open() as source:
                samples = [r for r in csv.DictReader(source, delimiter="\t") if before["at"] <= float(r["t"]) <= after["at"]]
            complete = complete and len(samples) > 0
            for sample in samples:
                role = sample["container"].removeprefix(manifest["project"] + "-").removesuffix("-1")
                if role == "k6":
                    row = load_generators.setdefault(role, {"source": "docker-stats-window", "processRssKiBAfter": "UNMEASURED", "snapshotCpu": "UNMEASURED"})
                else:
                    if role not in rows:
                        rows[role] = {"measurement": "NO-MEASUREMENT", "reason": "serving-snapshot-missing"};complete = False
                    row = rows[role]
                row.setdefault("cpuPctSamples", []).append(float(sample["cpu_pct"].rstrip('%')))
                row.setdefault("dockerMemoryBytesSamples", []).append(memory(sample["mem"].split("/")[0]))
            for row in list(rows.values()) + list(load_generators.values()):
                values = row.pop("cpuPctSamples", [])
                resident = row.pop("dockerMemoryBytesSamples", [])
                row.update({"sampleCount": len(values), "cpuPctMean": sum(values)/len(values) if values else None,
                            "cpuPctMax": max(values) if values else None, "dockerMemoryBytesMax": max(resident) if resident else None})
            complete = complete and all(row.get("sampleCount",0)>0 for row in rows.values())
            with (folder / "pg-activity.tsv").open() as source:
                activity = [r for r in csv.DictReader(source, delimiter="\t") if before["at"] <= float(r["t"]) <= after["at"]]
            complete = complete and len(activity) > 0
            wait = {}
            for row in activity:
                key = (row["role"], row["state"], row["wait_event_type"], row["wait_event"])
                wait[key] = wait.get(key, 0) + int(row["n"])
            pg_waits = [{"role":key[0],"state":key[1],"type":key[2],"event":key[3],"backendObservations":value} for key,value in wait.items()]
        else:
            pg_waits = None
        first, last = pg(folder / "before-pg-role.tsv"), pg(folder / "after-pg-role.tsv")
        costs = {role: {key: value[key]-first.get(role, {}).get(key,0) for key in value} for role,value in last.items()}
        for value in costs.values():
            value["callsPerTenantMinute"] = value["calls"] / manifest["tenants"] / seconds * 60
            value["executionMsPerTenantMinute"] = value["executionMs"] / manifest["tenants"] / seconds * 60
        for value in rows.values():
            cores=value.get("cpuCoresMean")
            value["cpuMsPerTenantMinute"]=cores*60000/manifest["tenants"] if cores is not None else None
            value["anonBytesPerTenant"]=value["anonBytesAfter"]/manifest["tenants"] if value.get("anonBytesAfter") is not None else None
        windows[name] = {"seconds":seconds,"roles":rows,"loadGenerators":load_generators,"pgStatements":costs,"pgWaits":pg_waits}
    raw = json.loads((directory / "load/k6-summary.json").read_text())["metrics"]
    shapes = {}
    for key,value in raw.items():
        match = re.fullmatch(r"http_req_duration\{shape:(\w+)\}",key)
        if match:
            data=value.get("values",value)
            shapes[match[1]] = {"p50":data.get("med"),"p95":data.get("p(95)"),"p99":data.get("p(99)"),"count":data.get("count")}
    complete = complete and len(shapes)==7 and all(value["count"] and all(value[k] is not None for k in ("p50","p95","p99")) for value in shapes.values())
    return {"complete":bool(complete),"windows":windows,"httpShapes":shapes,
            "loadgen": "k6 container in docker-stats; host probe process PID/CPU/RSS captured separately in loadgen.jsonl",
            "samplingCaveat":"docker MemUsage is cgroup usage; anon and memory.current snapshots are retained separately; neither is claimed JS heap"}
