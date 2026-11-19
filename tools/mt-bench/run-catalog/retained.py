"""Project allowlisted aggregates from retained local and Kubernetes run files."""

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import zlib

import latency

SHA = re.compile(r"[a-f0-9]{64}")
COMMIT = re.compile(r"[a-f0-9]{40}")
IMAGE = re.compile(r"sha256:[a-f0-9]{64}")
CODE = re.compile(r"[A-Z][A-Z0-9_]{1,95}")
HTTP_SHAPES = (
    "w_sgv", "w_devicestatus", "w_treatments_v3", "r_sgv", "r_devicestatus",
    "r_treatments", "r_status",
)
SIGNALS = {
    "client.frame.p95": ("ms", "matched probe client frame", "sparse probe write to matched client frame"),
    "clinical.durable-upper.p95": ("ms", "observed probe write", "sparse probe write to durable observation upper bound"),
    "backlog.probe.pending": ("writes", "accepted probe write", "sparse probe observation end"),
    "backlog.evaluator.pending": ("tenants", "tenant with fixed input boundary", "post-writer bounded evaluator drain"),
    "db.lock-wait.samples": ("fraction", "sampled PostgreSQL backend observation", "load-window PostgreSQL wait samples"),
    "http.pooled.p95": ("ms", "scenario HTTP latency sample", "pooled steady-window scenario HTTP"),
}


def get(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def number(value):
    return value if type(value) in (int, float) and 0 <= value <= 1e30 else None


def count(value):
    return value if type(value) is int and 0 <= value <= 2**53 else None


def token(value, pattern=CODE):
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def key_digest(value):
    if value is not None:
        return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return None


def pair(value):
    return {key: token(get(value, key), COMMIT) for key in ("core", "deploy")}


def sum_known(values):
    values = list(values)
    return sum(values) if values and None not in values else None


def first_known(*values):
    return next((value for value in values if value is not None), None)


def verdict(value):
    value = get(value, "verdict") if isinstance(value, dict) else value
    if value in ("PASS", "GREEN", "FAIL", "FAILED", "RED", "PARTIAL", "NOT_EXERCISED",
                 "NOT_RUN", "UNMEASURED", "NO-INSTRUMENT", "OBSERVED", "CAPTURED"):
        return value
    return "UNMEASURED"


def finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite JSON")
    return parsed


def reject_constant(_):
    raise ValueError("non-finite JSON")


class Evidence:
    def __init__(self, root):
        self.root = root
        self.files = {}
        self.issues = []
        self.loaded = {}

    def note(self, path, code):
        self.issues.append({"path": path, "code": code})

    def file(self, name, *, digest=False):
        path = self.root / name
        try:
            if path.resolve() != path or not path.is_file():
                return None
            self.files[name] = {"path": name}
            if digest:
                with path.open("rb") as handle:
                    self.files[name]["sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
            return path
        except OSError:
            self.note(name, "EVIDENCE_UNREADABLE")
            return None

    def obj(self, name):
        if name not in self.loaded:
            self.loaded[name] = self.read_obj(name)
        return self.loaded[name]

    def array(self, name):
        return self.read_obj(name, list)

    def read_obj(self, name, expected=dict):
        path = self.file(name)
        if path is None:
            return {}
        try:
            with path.open("rb") as handle:
                data = handle.read(32 * 1024 * 1024 + 1)
            if len(data) > 32 * 1024 * 1024:
                raise ValueError("oversize JSON")
            value = json.loads(data, parse_constant=reject_constant, parse_float=finite_float)
            if not isinstance(value, expected):
                raise ValueError("unexpected JSON document type")
            return value
        except (OSError, UnicodeError, ValueError, RecursionError):
            self.note(name, "EVIDENCE_MALFORMED")
            return {}

    def digest(self, name):
        self.file(name, digest=True)
        return get(self.files, name, "sha256")


def observation(value, unit, denominator, scope, evidence, size=None):
    value = number(value)
    return {
        "status": "MEASURED" if value is not None else "UNMEASURED",
        "value": value, "unit": unit, "denominator": denominator,
        "scope": scope, "population": number(size),
        "evidence": evidence if value is not None else None,
    }


def signal(signals, name, value, evidence, size=None):
    signals[name] = observation(value, *SIGNALS[name], evidence, size)


def percentiles(signals, probe, evidence):
    for name, key in (("client.frame.p95", "matchedClientMs"),
                      ("clinical.durable-upper.p95", "durableUpperMs")):
        stats = get(probe, key)
        samples = count(get(stats, "n"))
        signal(signals, name, get(stats, "p95") if samples else None, evidence, samples)
    pending = count(get(probe, "pendingAccepted"))
    witnesses = count(get(probe, "witnesses"))
    refused = count(get(probe, "refused"))
    accepted = witnesses - refused if None not in (witnesses, refused) and witnesses >= refused else None
    signal(signals, "backlog.probe.pending", pending if accepted and pending is not None
           and pending <= accepted else None, evidence, accepted)


def provenance(source, tool, image, config, workload, allocation):
    return {
        "source": pair(source), "tool": token(tool, SHA), "image": token(image, IMAGE),
        "config": token(config, SHA), "workload": token(workload, SHA),
        "allocation": token(allocation, SHA),
    }


def cadence(value):
    fields = ("accel", "hotFactor", "warmupSeconds", "idleSeconds", "loadSeconds",
              "drainSeconds", "setupSeconds", "offeredRps", "workloadScale", "driverShards",
              "logicalPollingClients", "socketsPerTenant", "probeEveryMs", "samplerIntervalSeconds")
    result = {key: number(get(value, key)) for key in fields if get(value, key) is not None}
    restart = get(value, "restart")
    if type(restart) is bool:
        result["restart"] = restart
    mix = get(value, "workloadMix")
    if token(mix, re.compile(r"[a-z][a-z0-9-]{0,40}")):
        result["workloadMix"] = mix
    return result or None


def source_conflicts(evidence, *pins):
    for field, validate in (
        ("pair", lambda value: pair(value) if all(pair(value).values()) else None),
        ("instrument", lambda value: token(get(value, "sha256") if isinstance(value, dict) else value, SHA)),
        ("imageId", lambda value: token(value, IMAGE)),
    ):
        known = []
        for path, document in pins:
            raw = get(document, field)
            if raw is None:
                continue
            parsed = validate(raw)
            if parsed is None:
                evidence.note(path, "PROVENANCE_INVALID")
            else:
                known.append((path, parsed))
        for path, actual in known[1:]:
            if actual != known[0][1]:
                evidence.note(path, "PROVENANCE_MISMATCH")


def journal_history(evidence, result, owner):
    journal = evidence.obj("history.json")
    prior = journal.get("previousObservations")
    runtime = token(journal.get("runtime")) or token(result.get("runtime"))
    if runtime is None and owner.get("prepared") is True and owner.get("attached") is not True:
        if evidence.file("execution.json"):
            runtime = "FRESH"
            prior = []
    return {
        "runtime": runtime,
        "priorObservations": len(prior) if isinstance(prior, list) else None,
        "priorPlan": key_digest(prior) if isinstance(prior, list) else None,
        "elapsedSeconds": number(journal.get("elapsedSessionSeconds")),
        "declaredSha256": key_digest(journal["declared"]) if isinstance(journal.get("declared"), dict) else None,
    }


def local_sql(signals, evidence, windows, scenario, summary, info):
    bookend = get(windows, "pgStatements")
    if not isinstance(bookend, dict):
        return
    # Match the existing instrument's explicit service/lifetime SQL identities.
    # Shared roles are omitted from these quotients.
    progress = get(summary, "evaluatorProgress", "load")
    completed = sum_known(count(get(progress, key)) for key in ("completedWorkDelta", "completedTimeDelta"))
    rt_file = "fixture/cost-companion-assessment.json"
    deliveries = get(evidence.obj(rt_file), "phases", "load", "realtime", "services", "realtime", "deliveryDelta")
    units = {
        "api": (count(get(scenario, "attempts")), "scenario HTTP attempt"),
        "evaluator": (completed, "completed evaluator work or time cycle"),
        "realtime": (count(get(deliveries, "counterDelta", "completed")) if
                     get(deliveries, "status") == "MEASURED" else None, "completed realtime delivery"),
    }
    for role, (size, denominator) in units.items():
        for signal_name, stat, unit in (("statements", "calls", "statements/unit"),
                                        ("execution", "executionMs", "ms/unit")):
            total = sum_known(number(get(bookend, pg_role, stat))
                              for pg_role in (f"nsdemo_{role}", f"nsdemo_lifetime_{role}"))
            value = total / size if total is not None and size else None
            signals[f"db.{role}.{signal_name}"] = observation(
                value, unit, denominator,
                "load-window service and lifetime pg_stat_statements rows",
                [info, rt_file] if role == "realtime" else [info], size)


def local_signals(evidence, summary, owner, driver, driver_path="fixture/load/driver-accounting.json"):
    signals = {}
    info = "fixture/summary.json"
    probe_path = "fixture/load/probe.json"
    probe = get(evidence.obj(probe_path), "durableOutputObservation") or get(summary, "probe", "durableOutputObservation")
    percentiles(signals, probe, [probe_path] if probe_path in evidence.files else [info])

    catchup_path = "fixture/load/evaluator-catchup.json"
    classifications = evidence.obj(catchup_path).get("classifications")
    if isinstance(classifications, dict):
        size = sum_known(count(value) for value in classifications.values())
        signal(signals, "backlog.evaluator.pending", count(classifications.get("PENDING")), [catchup_path], size)

    windows = get(summary, "measurements", "windows", "load")
    waits = get(windows, "pgWaits")
    if isinstance(waits, list) and waits and all(
        isinstance(get(row, "type"), str) and count(get(row, "backendObservations")) is not None
        for row in waits
    ):
        population = sum(row["backendObservations"] for row in waits)
        if population:
            locked = sum(row["backendObservations"] for row in waits if row["type"] == "Lock")
            signal(signals, "db.lock-wait.samples", locked / population, [info], population)

    roles = get(windows, "roles")
    limits = get(owner, "runConfiguration", "resources", "profile", "services")
    if isinstance(roles, dict):
        for role, measured in roles.items():
            if not token(role, re.compile(r"[a-z][a-z0-9-]{0,38}")):
                continue
            millicpus = count(get(limits, role, "millicpus"))
            mean = number(get(measured, "cpuCoresMean"))
            valid_mean = mean if get(measured, "counterReset") is False else None
            if owner.get("composeLimitMode") == "uncapped-services":
                signals[f"cpu.{role}.cores"] = observation(
                    valid_mean, "cores", "load-window elapsed seconds", "load-window cgroup bookends",
                    [info], number(get(windows, "seconds")))
            value = valid_mean * 1000 / millicpus if valid_mean is not None and millicpus else None
            signals[f"cpu.{role}.quota"] = observation(
                value, "fraction", "configured role CPU quota", "load-window cgroup bookends",
                [info, "fixture/owner.json"], number(get(windows, "seconds")))
    for shape in HTTP_SHAPES:
        latency = get(summary, "measurements", "httpShapes", shape)
        size = count(get(latency, "count"))
        if size:
            signals[f"http.{shape}.p95"] = observation(
                get(latency, "p95"), "ms", "per-shape scenario HTTP timing sample",
                "local single-generator retained k6 summary", [info], size)
    local_sql(signals, evidence, windows, get(summary, "httpAccounting", "scenario"), summary, info)
    add_pooled(evidence, signals, driver, get(summary, "cadence") or owner.get("cadence"),
               "fixture/load", driver_path)
    return signals



def setup_observations(evidence, probe_path, deployment_path):
    observations = {}
    steps = evidence.array(deployment_path)
    if isinstance(steps, list):
        primer = next((row for row in steps if get(row, "name") == "prime"), None)
        duration = number(get(primer, "seconds"))
        if duration is not None:
            observations["deploymentPrimer"] = {
                "seconds": duration, "status": token(get(primer, "status")),
                "evidence": deployment_path,
            }
    probe = evidence.obj(probe_path)
    for name, milliseconds in (("socketPriming", get(probe, "prime", "ms")),
                               ("probeCredentialExchange", probe.get("exchangeMs"))):
        if number(milliseconds) is not None:
            observations[name] = {"seconds": milliseconds / 1000, "evidence": probe_path}
    return observations


def local(evidence):
    result = evidence.obj("result.json")
    config = evidence.obj("config.json")
    owner = evidence.obj("fixture/owner.json")
    summary = evidence.obj("fixture/summary.json")
    partial = get(result, "partial")
    host_path = "fixture/load-before-host.json"
    host = evidence.obj(host_path)
    setup = setup_observations(evidence, "fixture/load/probe.json", "fixture/deployment-stages.json")
    offered = get(summary, "rateOffer")
    http = get(summary, "httpAccounting") or evidence.obj("fixture/load/http-accounting.json")
    raw_k6 = evidence.obj("fixture/load/k6-summary.json")
    scenario = get(http, "scenario")
    # Retained runs before driver-sized-from-offer named this file driver-vu-assessment.json.
    driver_path = next((path for path in ("fixture/load/driver-accounting.json", "fixture/load/driver-vu-assessment.json")
                        if evidence.obj(path)), "fixture/load/driver-accounting.json")
    driver = evidence.obj(driver_path)
    totals = get(driver, "totals") if driver.get("kind") == "m7-configured-driver-accounting" else None
    checks = get(summary, "strictChecks") or get(partial, "strictChecks")
    phase = token(str(result.get("phase", "")).upper())
    traffic_phase = token(get(partial, "trafficPhase"))
    options = get(config, "prepare")
    configured = get(summary, "cadence") or get(owner, "cadence")
    resources = get(owner, "runConfiguration", "resources")
    if resources is None and owner.get("composeLimitMode") == "uncapped-services":
        resources = {"composeMode": "uncapped-services"}
    tier = config.get("tier") or get(owner, "runPurpose") or get(options, "run-purpose")
    if tier == "strict":
        tier = "acceptance"
    declared = {
        "pair": {"core": get(options, "core-commit"), "deploy": get(options, "deploy-commit")},
        "imageId": get(options, "image-id"),
    }
    # Early attempts can retain a config before the adapter writes its owner;
    # declared pins are kept separately from the observed tuple.
    if all(pair(declared["pair"]).values()):
        source_conflicts(evidence, ("config.json", declared), ("fixture/owner.json", owner),
                         ("fixture/summary.json", summary))
    else:
        source_conflicts(evidence, ("fixture/owner.json", owner), ("fixture/summary.json", summary))
    if driver:
        source_conflicts(evidence, ("fixture/owner.json", owner), (driver_path, driver))
    for name in ("cleanup.json", "fixture/deployment-stages.json", "fixture/runtime-readiness.json",
                 "fixture/terminal-before-cleanup.json", "fixture/terminal-capture-unavailable.json",
                 "fixture/compose-limits-readback.json", "smoke.json"):
        evidence.file(name)
    return {
        "producer": "local",
        **({"setupObservations": setup} if setup else {}),
        "tier": tier if tier in ("smoke", "discovery", "acceptance") else None,
        "runStatus": token(result.get("status")), "phase": phase or traffic_phase,
        "trafficPhase": traffic_phase,
        "failureCode": token(get(result, "failure", "code")) or token(result.get("code")),
        "finishedAt": number(result.get("finishedAt")),
        **({"elapsedSeconds": result["elapsedSeconds"]} if number(result.get("elapsedSeconds")) is not None else {}),
        "provenance": provenance(owner.get("pair") or summary.get("pair"),
                                 get(owner, "instrument", "sha256") or summary.get("instrument"),
                                 owner.get("imageId") or summary.get("imageId"), evidence.digest("config.json"),
                                 get(owner, "workload", "adaptedSha256"), key_digest(resources)),
        "declaredSource": pair(declared["pair"]), "declaredImage": token(declared["imageId"], IMAGE),
        "environment": {
            "host": token(owner.get("hostIdentity") or summary.get("hostIdentity"), SHA),
            "contention": "SHARED" if isinstance(host.get("scope"), str)
                          and host["scope"].startswith("shared-host diagnostic") else None,
            "cores": count(host.get("cores")),
            "loadAverage1m": number(host["load"][0]) if isinstance(host.get("load"), list) and host["load"] else None,
        },
        "limits": {"requestedSha256": key_digest(resources),
                   "nativeReadback": [name for name in ("fixture/load/before-cgroups.json",
                                      "fixture/load/after-cgroups.json", "runtime-before.json",
                                      "fixture/compose-limits-readback.json")
                                      if evidence.file(name)],
                   **({"composeMode": owner["composeLimitMode"]} if owner.get("composeLimitMode") in
                      ("uncapped-services", "configured") else {})},
        "population": count(first_known(owner.get("tenants"), summary.get("tenants"), get(options, "tenants"))),
        "replicas": count(first_known(owner.get("replicas"), summary.get("replicas"), get(options, "replicas"))),
        "cadence": cadence(configured),
        "history": journal_history(evidence, result, owner),
        "work": {
            "scope": "scenario HTTP attempts; JWT setup and probe writes excluded",
            "planned": count(get(totals, "planned")),
            **({"offeredExpectedIterations": number(get(totals, "offered"))} if totals else {}),
            "offeredRatePerSecond": number(first_known(get(offered, "effectiveScenarioRps"),
                                                      get(configured, "offeredRps"))),
            "issued": count(first_known(get(totals, "issued"), get(scenario, "attempts"), get(partial, "scenarioAttempts"))),
            "completed": count(first_known(get(totals, "completed"), get(scenario, "completed"))),
            "dropped": count(first_known(get(totals, "dropped"), get(raw_k6, "metrics", "dropped_iterations", "count"))),
        },
        "oracles": {
            "cleanup": "PASS" if evidence.obj("cleanup.json").get("status") == "ABSENT" else "UNMEASURED",
            "stored": verdict(summary.get("oracle")),
            "clinical": verdict(summary.get("completedOutput")),
            "isolation": verdict(summary.get("isolation")),
            "ownership": "PASS" if summary.get("ownershipVerified") is True else "UNMEASURED",
            "authority": verdict(summary.get("authority")),
            "restore": verdict(summary.get("recovery")),
            "clientFrames": verdict(summary.get("viewerFrames")),
            "settings": verdict(summary.get("settingsFingerprintObservation")),
            "readiness": verdict(get(checks, "readiness")),
            "idle": verdict(get(checks, "idle")),
            "load": verdict(get(checks, "load")),
            "http": verdict(get(http, "httpVerdict")),
        },
        "signals": local_signals(evidence, summary, owner, driver, driver_path),
    }



def pooled_signal(evidence, driver, configured, directory):
    # Scope comes from the same completed scenario counts used by the driver
    # reducer. JWT setup has an empty scenario and is excluded.
    shard_count = count(get(configured, "driverShards")) or 1
    shards = get(driver, "shards")
    if not isinstance(shards, list) or len(shards) != shard_count or shard_count > 16:
        return None
    paths = []
    inputs = []
    total_bytes = 0
    for index, shard in enumerate(shards):
        plan = get(shard, "plan")
        if get(plan, "observer") != "scheduling-v1" or get(plan, "shardIndex") != index:
            return None
        by_scenario = get(shard, "byScenario")
        if not isinstance(by_scenario, dict) or not set(by_scenario) <= set(HTTP_SHAPES):
            return None
        expected = {key: count(get(row, "completed")) for key, row in by_scenario.items()}
        if sum_known(expected.values()) is None:
            return None
        for suffix in (f"-{index}", "") if shard_count == 1 else (f"-{index}",):
            name = f"{directory}/k6-scheduling{suffix}.csv.gz"
            path = evidence.file(name)
            if path:
                break
        if not path:
            return None
        try:
            total_bytes += path.stat().st_size
        except OSError:
            return None
        if total_bytes > latency.MAX_TRACE_BYTES:
            evidence.note(name, "LATENCY_TRACE_BUDGET")
            return None
        paths.append(name)
        inputs.append((path, expected))
    try:
        upper, size = latency.pooled_histogram(inputs)
        return upper, size, paths
    except (OSError, ValueError, TypeError, EOFError, KeyError, csv.Error, zlib.error):
        evidence.note(directory, "LATENCY_SAMPLES_UNRECONCILED")
        return None


def add_pooled(evidence, signals, driver, configured, path, source):
    pooled = pooled_signal(evidence, driver, configured, path)
    if pooled:
        upper, size, paths = pooled
        signals["http.pooled.p95"] = observation(
            upper, "ms", "scenario HTTP latency sample",
            "configured k6 scenario starts through drain completions; nearest-rank 1 ms upper bound",
            [source, *paths], size)


def kube(evidence):
    prefix = "runtime/packet/" if (evidence.root / "runtime/packet/run.json").is_file() else ""
    run_path = prefix + "run.json"
    run = evidence.obj(run_path)
    result_path = prefix + "experiment/result.json"
    load_path = prefix + "load/result.json"
    reduction_path = prefix + "experiment/observations/reduction.json"
    result = evidence.obj(result_path)
    first_failure = get(result, "firstFailure") or evidence.obj("runtime/first-failure.json")
    load = evidence.obj(load_path) or get(result, "load") or {}
    reduction = evidence.obj(reduction_path)
    pins = run.get("pins")
    reduced_pins = get(reduction, "source", "pins")
    load_pins = get(load, "pins")

    def common(value):
        return {"pair": get(value, "pair"), "instrument": get(value, "instrument"), "imageId": get(value, "appImageId")}

    source_conflicts(evidence, (run_path, common(pins)), (load_path, common(load_pins)),
                     (reduction_path, common(reduced_pins)))
    config_hash = token(run.get("experimentSha256"), SHA)
    result_hash = token(result.get("experimentSha256"), SHA)
    if config_hash and result_hash and config_hash != result_hash:
        evidence.note(result_path, "CONFIG_MISMATCH")
    allocation = evidence.obj(prefix + "experiment/allocation.json")
    startup = evidence.obj("environment.json")
    inventory = evidence.obj("inventory.json")
    intent = evidence.obj("intent.json")
    actual_source = {"core": inventory.get("sourceCommit"), "deploy": inventory.get("imageDeployCommit")}
    declared_source = {"core": startup.get("sourceCommit"), "deploy": startup.get("imageDeployCommit")}
    source_conflicts(evidence, ("inventory.json", {"pair": actual_source} if inventory else {}),
                     ("environment.json", {"pair": declared_source} if startup else {}))
    configured = get(reduction, "configured") or run.get("workload") or get(intent, "profile", "workload")
    tier = run.get("tier")
    if tier is None:
        tier = intent.get("tier")
    if tier is None and (startup.get("trialPurpose") == "scale-diagnostic" or result):
        tier = "discovery"
    driver = get(reduction, "configuredDriver") or get(load, "loadFunctionalChecks", "configuredDriver")
    totals = get(driver, "totals")
    replicas = count(get(driver, "apiReplicas"))
    roles = run.get("roles")
    if replicas is None and isinstance(roles, dict):
        replicas = sum(role == "api" or role.startswith("api-") for role in roles)
    history_mode = get(intent, "profile", "history", "mode")
    fresh = history_mode == "existing-provisioner-only" and evidence.file("runtime/custody.json") is not None
    signals = {}
    percentiles(signals, get(reduction, "backlog", "recordedProbe"), [reduction_path])
    add_pooled(evidence, signals, driver, configured, prefix + "load", reduction_path if reduction else load_path)
    for name in ("load/before.json", "load/after.json", "load/driver.json", "load/window.json",
                 "experiment/observations/first-failure.json", "experiment/cleanup.json"):
        evidence.file(prefix + name)
    return {
        "producer": "kubernetes",
        "tier": tier if tier in ("smoke", "discovery", "acceptance") else None,
        "runStatus": ("FAILED" if first_failure else
                      token(result.get("verdict")) or token(result.get("status")) or token(load.get("verdict"))),
        "phase": ("SCENARIO" if count(get(totals, "issued")) else "STARTUP" if first_failure else None),
        "failureCode": token(get(first_failure, "code")) or token(result.get("code")),
        "finishedAt": number(result.get("finishedAt")),
        "provenance": provenance(get(pins, "pair") or actual_source, get(pins, "instrument"),
                                 get(pins, "appImageId") or get(inventory, "candidateContract", "imageConfigId"),
                                 config_hash or get(startup, "experimentManifest", "sha256"),
                                 key_digest(run.get("workload") or get(intent, "profile", "workload")),
                                 key_digest(allocation.get("accounting") or startup.get("resources"))),
        "declaredSource": pair(get(pins, "pair") or declared_source),
        "declaredImage": token(get(pins, "appImageId"), IMAGE),
        "environment": {
            "host": key_digest(run["context"]) if isinstance(run.get("context"), str) else None,
            "contention": {name: get(run, name, "sharedHost") if type(get(run, name, "sharedHost")) is bool
                           else None for name in ("driver", "observer")},
            "driverHostSha256": key_digest(get(run, "driver", "hostId")),
            "observerHostSha256": key_digest(get(run, "observer", "hostId")),
        },
        "limits": {"requestedSha256": token(allocation.get("sha256"), SHA),
                   "nativeReadback": [prefix + name for name in ("load/before.json", "load/after.json", "load/driver.json")
                                      if prefix + name in evidence.files]},
        "population": count(first_known(run.get("tenants"), startup.get("tenantCount"))),
        "replicas": replicas,
        "cadence": cadence(configured),
        "history": {"runtime": "FRESH" if fresh else None, "priorObservations": 0 if fresh else None,
                    "priorPlan": key_digest([]) if fresh else None, "elapsedSeconds": None},
        "work": {
            "scope": "configured scenario HTTP scheduling; separate JWT setup and drain",
            "planned": count(get(totals, "planned")),
            "offeredRatePerSecond": None,
            "offeredExpectedIterations": number(get(totals, "offered")),
            "issued": count(first_known(get(totals, "issued"), get(reduction, "issued", "attempts"))),
            "completed": count(first_known(get(totals, "completed"), get(reduction, "issued", "completed"))),
            "dropped": count(get(totals, "dropped")),
        },
        "oracles": {
            "cleanup": "PASS" if evidence.obj("runtime/absence.json").get("verifiedAt") else "UNMEASURED",
            "stored": verdict(get(load, "storedWrites")),
            "clinical": verdict(get(load, "clinical")),
            "isolation": verdict(get(load, "isolation")),
            "authority": verdict(get(load, "authority")),
            "restore": verdict(get(load, "restore")),
            "clientFrames": verdict(get(load, "frames")),
            "evaluatorProgress": verdict(get(load, "evaluatorProgress")),
            "http": verdict(get(driver, "httpVerdict")),
            "settings": verdict(get(load, "loadFunctionalChecks", "settingsFingerprint")),
        },
        "signals": signals,
    }


def project(root, run_id):
    evidence = Evidence(root)
    record = kube(evidence) if any((root / name).is_file() for name in
                                  ("run.json", "experiment/result.json", "runtime/first-failure.json",
                                   "runtime/packet/run.json")) else local(evidence)
    signals = record["signals"]
    for name, (unit, denominator, scope) in SIGNALS.items():
        signals.setdefault(name, observation(None, unit, denominator, scope, None))
    return {
        "version": 1, "id": run_id, "evidenceRoot": str(Path(root)),
        "basis": "read-derived from retained experiment outputs",
        **record, "evidence": evidence.files, "issues": evidence.issues,
    }
