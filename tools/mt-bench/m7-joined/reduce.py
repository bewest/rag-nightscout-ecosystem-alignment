"""Reduce observable resource windows; absent samples are NO-MEASUREMENT."""
import csv
import math
import re
from pathlib import Path
from contract import require, metric
import json
import stream_topology
from pg_waits import reduce_phase as reduce_pg_waits


def memory(text):
    match = re.match(r"([\d.]+)([KMGT]?i?B)", text.strip())
    require(match is not None, "M7_MEMORY_SAMPLE_INVALID")
    return float(match[1]) * {"B":1,"KB":1000,"MB":10**6,"GB":10**9,"TB":10**12,"KiB":1024,"MiB":1024**2,"GiB":1024**3,"TiB":1024**4}[match[2]]


def pg(path):
    result = {}
    for line in path.read_text().splitlines():
        name, calls, ms = line.split("\t");result[name] = {"calls": int(calls), "executionMs": float(ms)}
    return result


def process_deltas(initial,final,seconds):
    processes={}
    for pid,b in final.items():
        a=initial.get(pid)
        if not a or a.get('unavailable') or b.get('unavailable') or a.get('startTicks')!=b.get('startTicks') or a.get('executable')!=b.get('executable') or a.get('clockTicksPerSecond')!=b.get('clockTicksPerSecond'):
            processes[pid]={'name':b['name'],'cpu':'UNMEASURED','reason':'missing-or-changed-process'};continue
        ticks=b['cpuTicks']-a['cpuTicks'];require(ticks>=0,'M7_PROCESS_CPU_COUNTER_RESET')
        processes[pid]={'name':b['name'],'component':b.get('component',b['name']),'cpuSeconds':ticks/b['clockTicksPerSecond'],'cpuCoresMean':ticks/b['clockTicksPerSecond']/seconds,'rssKiBAfter':b['rssKiB']}
    return processes


def memory_peak_observation(first, final):
    initial=first.get('memoryObservation',{});last=final.get('memoryObservation',{})
    scope='per-role container-cgroup lifetime peak; not phase peak or concurrent aggregate peak'
    if initial.get('status')!='MEASURED' or last.get('status')!='MEASURED':
        return {'status':'UNMEASURED','scope':scope,'reason':'missing-or-invalid-memory-peak'}
    require(isinstance(first.get('id'),str) and first['id'] and first['id']==final.get('id'),'M7_MEMORY_CONTAINER_CHANGED')
    births=[initial.get('birth'),last.get('birth')]
    if any(birth is None for birth in births):
        return {'status':'UNMEASURED','scope':scope,'reason':'container-birth-unavailable'}
    for row,birth in zip((first,final),births):
        require(isinstance(birth,dict) and set(birth)=={'containerId','startedAt','source','stableRead'} and birth['containerId']==row['id'] and birth['startedAt']==row.get('containerStartedAt') and isinstance(birth['startedAt'],str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z',birth['startedAt']) and birth['source']=='docker-inspect-state-started-at-v1' and birth['stableRead'] is True,'M7_MEMORY_BIRTH_PROVENANCE')
    before=initial.get('memoryPeakBytes');after=last.get('memoryPeakBytes')
    require(type(before)is int and type(after)is int and before>=0 and after>=0,'M7_MEMORY_PEAK_RESET')
    def start_order(value):
        whole,_,fraction=value.removesuffix('Z').partition('.')
        return whole,int(fraction.ljust(9,'0'))
    require(start_order(births[0]['startedAt'])<=start_order(births[1]['startedAt']),'M7_MEMORY_BIRTH_REWIND')
    if births[0]['startedAt']!=births[1]['startedAt']:
        return {'status':'UNMEASURED','scope':scope,'reason':'container-lifetime-changed','memoryPeakBytesBeforeLifetime':before,'memoryPeakBytesAfterLifetime':after,'birthBefore':births[0],'birthAfter':births[1],'memoryEventsDelta':'UNMEASURED','phaseGap':'UNMEASURED'}
    require(before<=after,'M7_MEMORY_PEAK_RESET')
    result={'status':'MEASURED','scope':scope,'memoryPeakBytesBefore':before,'memoryPeakBytesAfter':after}
    a,b=initial.get('memoryEvents'),last.get('memoryEvents')
    if isinstance(a,dict) and isinstance(b,dict) and a and set(a)==set(b):
        require(all(type(a[k])is int and type(b[k])is int and 0<=a[k]<=b[k] for k in a),'M7_MEMORY_EVENTS_RESET')
        result['memoryEventsDelta']={key:b[key]-a[key] for key in a}
    else:result['memoryEventsDelta']='UNMEASURED'
    return result


def rss_available(value):
    lines = value.strip().splitlines() if isinstance(value, str) else []
    return len(lines) >= 2 and lines[0].split() == ['PID', 'COMMAND', 'RSS'] and all(
        re.fullmatch(r'\s*[0-9]+\s+.+?\s+[0-9]+\s*', line) for line in lines[1:])


def availability(before, after, rows, manifest, sampled):
    """Explain independent criteria without promoting optional observations to gates."""
    criteria = {}
    def record(name, measured, reason, *, required=True, details=None):
        criteria[name] = {'status': 'MEASURED' if measured else 'UNMEASURED', 'required': required}
        if not measured:
            criteria[name]['reason'] = reason
            if details is not None:
                criteria[name]['details'] = details
    coverage = {edge: value.get('serviceCoverage', {'status': 'UNMEASURED', 'reason': 'not-captured'})
                for edge, value in [('before', before), ('after', after)]}
    record('serviceCoverage', all(v.get('status') == 'MEASURED' for v in coverage.values()),
           'service-coverage-unmeasured', required=any('serviceCoverage' in v for v in (before, after)), details=coverage)
    for key, predicate, reason in [
            ('containerCpu', lambda v: v.get('cpuCoresMean') is not None, 'missing-changed-container-or-reset-counter'),
            ('processRss', lambda v: rss_available(v.get('processRssKiBAfter')), 'missing-or-invalid-process-rss')]:
        missing = [role for role, value in rows.items() if not predicate(value)]
        record(key, bool(rows) and not missing, reason, details={'roles': missing})
    if manifest.get('profile') == 'pgstream-sample':
        missing = [{'service': role, 'component': component}
                   for role, components in stream_topology.expected_processes(manifest).items() for component in components
                   if not any(p.get('component', p.get('name')) == component and 'cpuSeconds' in p
                              for p in rows.get(role, {}).get('processes', {}).values())]
        record('requiredProcesses', not missing, 'missing-or-changed-required-process', details=missing)
    if sampled:
        missing = [role for role, value in rows.items() if value.get('sampleCount', 0) == 0]
        record('dockerStats', bool(rows) and not missing, 'missing-in-window-docker-stats', details={'roles': missing})
    for value in rows.values():
        value['availability'] = {
            'containerCpu': {'status': 'MEASURED' if value.get('cpuCoresMean') is not None else 'UNMEASURED'},
            'memoryPeak': {'status': value.get('memoryObservation', {}).get('status', 'UNMEASURED'), 'required': False,
                           'reason': value.get('memoryObservation', {}).get('reason')},
            'resourceLimits': {'status': value.get('resourceLimits', {}).get('status', 'UNMEASURED'), 'required': False}}
    return criteria


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
        if 'serviceCoverage' in before or 'serviceCoverage' in after:
            complete = complete and before.get('serviceCoverage',{}).get('status') == 'MEASURED' and after.get('serviceCoverage',{}).get('status') == 'MEASURED'

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
            complete = complete and rss_available(rss)
            delta = b[0] - a[0]
            complete = complete and delta >= 0
            rows[role] = {"cpuUsecDelta": delta if delta >= 0 else None, "cpuCoresMean": delta / 1e6 / seconds if delta >= 0 else None,
                          "memoryObservation":memory_peak_observation(first,value), "resourceLimits":value.get("resourceLimits",{"status":"UNMEASURED"}), **({"instance":value["instance"]} if "instance" in value else {}), "counterReset": delta < 0, "processRssKiBAfter": value.get("processRssKiB"), "anonBytesAfter": b[1], "memoryCurrentBytesAfter": b[2]}
        # Container totals include both evaluator Node and its pgstream child.
        # Keep process identity/start time when subtracting their own counters.
        for role,value in rows.items():
            initial=before['roles'].get(role,{}).get('hostProcesses',{})
            final=after['roles'].get(role,{}).get('hostProcesses',{})
            processes=process_deltas(initial,final,seconds)
            if initial or final:value['processes']=processes
        if manifest.get('profile')=='pgstream-sample':
            for role,components in stream_topology.expected_processes(manifest).items():
                processes=rows.get(role,{}).get('processes',{})
                complete=complete and all(any(p.get('component',p['name'])==component and 'cpuSeconds' in p for p in processes.values()) for component in components)
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
        windows[name]['availability'] = availability(before, after, rows, manifest, name != 'idle-disabled')
        if name != "idle-disabled":
            windows[name]['availability']['pgActivity'] = {'status': 'MEASURED' if activity else 'UNMEASURED', 'required': True,
                                                          **({} if activity else {'reason': 'missing-in-window-pg-activity'})}
            windows[name]["pgLockSampling"] = reduce_pg_waits(
                folder, manifest.get("owner"), before["at"], after["at"])
    raw_summary = json.loads((directory / "load/k6-summary.json").read_text())
    raw = raw_summary["metrics"]
    shard_statistics = raw_summary.get("m7DriverShards")
    shapes = {}
    for key,value in raw.items():
        match = re.fullmatch(r"http_req_duration\{shape:(\w+)\}",key)
        if match:
            data=value.get("values",value)
            shapes[match[1]] = {"p50":data.get("med"),"p95":data.get("p(95)"),"p99":data.get("p(99)"),"count":data.get("count")}
            if isinstance(shard_statistics, dict):
                ranges = shard_statistics.get('quantileBounds')
                shapes[match[1]].update(percentileMethod='largest-shard-statistic', pooledPercentiles='UNMEASURED',
                    shardPercentileRange=ranges.get(key) if isinstance(ranges, dict) else None,
                    percentileScope='Retained shard statistic/range; pooled percentile not established by summary-only reduction.')
    for name,row in shapes.items():
        failure=raw.get('http_req_failed{shape:'+name+'}',{});failure=failure.get('values',failure)
        row['failureRate']=failure.get('rate',failure.get('value'))
        row['failureMetricRaw']=failure or None
    complete = complete and len(shapes)==7 and all(value["count"] and all(value[k] is not None for k in ("p50","p95","p99")) for value in shapes.values())
    reasons = [{'phase': phase, 'criterion': key, **value} for phase, window in windows.items()
               for key, value in window['availability'].items() if value['required'] and value['status'] != 'MEASURED']
    if len(shapes) != 7 or any(not value['count'] or any(value[k] is None for k in ('p50', 'p95', 'p99')) for value in shapes.values()):
        reasons.append({'criterion': 'httpShapes', 'status': 'UNMEASURED', 'required': True, 'reason': 'missing-shape-count-or-percentiles'})
    return {"complete":bool(complete),"incompleteReasons":reasons,"windows":windows,"httpShapes":shapes,
            "loadgen": "k6 container in docker-stats; host probe process PID/CPU/RSS captured separately in loadgen.jsonl",
            "samplingCaveat":"docker MemUsage is cgroup usage; anon and memory.current snapshots are retained separately; neither is claimed JS heap"}
