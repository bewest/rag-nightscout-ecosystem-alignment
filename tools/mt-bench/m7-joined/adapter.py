#!/usr/bin/env python3
"""Joined M7 instrument. No operation attaches to or tears down an existing stack."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
import threading
import resource
import math

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from contract import (COUNTS, REPLICAS, OWNER, SHA, require, digest, labels_match, owned,
                      tenant_projection, metric, oracle, serving_mounts, campaign_check)
from probe import generate
from workload import generate as generate_workload
BASE = ROOT / "tools/mt-bench/compose-baseline"
REUSED = ["tools/mt-bench/capacity/probe.js", "tools/mt-bench/capacity/k6/workload.js",
          "tools/mt-bench/compose-baseline/probes/sample.sh", "tools/mt-bench/compose-baseline/oracle/disk.sh"]


def runtime_env(extra=None):
    # Ambient NS_*/NODE_OPTIONS/BENCH_* must not silently alter a paired run.
    names=("PATH","HOME","USER","LANG","XDG_RUNTIME_DIR","DOCKER_HOST","DOCKER_CONTEXT","DOCKER_CONFIG","SSH_AUTH_SOCK")
    return {**{key:os.environ[key] for key in names if key in os.environ}, **(extra or {})}


def command(argv, *, cwd=None, env=None, input=None, file=None, timeout=120):
    # All argument vectors; error messages never echo argv/environment/private URLs.
    result = subprocess.run([str(a) for a in argv], cwd=cwd, env=runtime_env() if env is None else env, input=input,
                            stdout=file or subprocess.PIPE, stderr=subprocess.STDOUT if file else subprocess.PIPE, timeout=timeout)
    if result.returncode:
        error = RuntimeError("M7_COMMAND_FAILED:" + Path(str(argv[0])).name)
        error.stderr = result.stderr
        error.returncode = result.returncode
        raise error
    return None if file else result.stdout.decode()


def document(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def git(repo, *args):
    return command(["git", "-C", repo, *args]).strip()


def commit(repo, value):
    require(SHA.fullmatch(value or ""), "M7_FULL_COMMIT_REQUIRED")
    require(git(repo, "rev-parse", "--verify", value + "^{commit}") == value, "M7_COMMIT_UNAVAILABLE")
    return value


def instrument():
    head = git(ROOT, "rev-parse", "HEAD")
    paths = git(ROOT, "ls-files", "tools/mt-bench/m7-joined").splitlines() + REUSED
    require(paths and "tools/mt-bench/m7-joined/adapter.py" in paths, "M7_INSTRUMENT_NOT_COMMITTED")
    require(not git(ROOT, "diff", "HEAD", "--", *paths), "M7_INSTRUMENT_DIRTY")
    hashes = {p: digest(ROOT / p) for p in sorted(set(paths))}
    return {"commit": head, "sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(), "files": hashes}


def load(directory):
    d = Path(directory).resolve()
    m = document(d / "owner.json")
    require(m.get("directory") == str(d) and re.fullmatch(r"[0-9a-f]{32}", m.get("owner", "")), "M7_OWNER_MANIFEST_INVALID")
    require(m.get("instrument", {}).get("sha256") == instrument()["sha256"], "M7_INSTRUMENT_CHANGED")
    return d, m


def compose(d, *args, file=None, input=None, timeout=120):
    return command(["docker", "compose", "-p", document(d / "owner.json")["project"], "--env-file", d / "env",
                    "-f", d / "frozen.compose.json", *args], file=file, input=input, timeout=timeout)


def resources(m, all_containers=True):
    flag = "-aq" if all_containers else "-q"
    ids = command(["docker", "ps", flag, "--filter", "label=com.docker.compose.project=" + m["project"]]).split()
    return json.loads(command(["docker", "inspect", *ids])) if ids else []


def assert_owned(m):
    for row in resources(m):
        owned(row, m["owner"])
    for kind in ("volume", "network"):
        ids = command(["docker", kind, "ls", "-q", "--filter", "label=com.docker.compose.project=" + m["project"]]).split()
        if ids:
            for row in json.loads(command(["docker", kind, "inspect", *ids])):
                owned(row, m["owner"])


def inventory(owner):
    endpoint = os.environ.get("DOCKER_HOST") or command(["docker","context","inspect","--format",'{{(index .Endpoints "docker").Host}}']).strip()
    require(endpoint.startswith("unix://"), "M7_LOCAL_DOCKER_REQUIRED")
    ids = command(["docker", "ps", "-q"]).split()
    containers = []
    if ids:
        for row in json.loads(command(["docker", "inspect", *ids])):
            labels = row.get("Config", {}).get("Labels", {}) or {}
            containers.append({"id": row["Id"], "name": row["Name"].lstrip("/"), "image": row["Image"],
                               "project": labels.get("com.docker.compose.project"), "owned": labels.get(OWNER) == owner})
    return {"at": time.time(), "load": list(os.getloadavg()), "cores": os.cpu_count(),
            "memory": dict(re.findall(r"^(MemTotal|MemAvailable):\s+(\d+)", Path("/proc/meminfo").read_text(), re.M)),
            "cpuModel":re.search(r"^model name\s+: (.+)$",Path("/proc/cpuinfo").read_text(),re.M)[1],
            "dockerDaemonId":command(["docker","info","--format","{{.ID}}"]).strip(),
            "kernel": os.uname().release, "dockerContext":command(["docker","context","show"]).strip(), "docker": command(["docker", "version", "--format", "{{.Server.Version}} "]).strip(),
            "compose": command(["docker", "compose", "version", "--short"]).strip(), "containers": containers,
            # Record process names/counters, never command arguments or environments.
            "processes": command(["ps", "-eo", "pid,ppid,comm,pcpu,rss"])}


def quiet(d, m, phase, check_load=True):
    host = inventory(m["owner"])
    write(d / (phase + "-host.json"), host)
    require(not any(not row["owned"] for row in host["containers"]), "M7_FOREIGN_ACTIVE_CONTAINERS:see_host_inventory")
    if check_load:
        require(host["load"][0] <= m["quietLoad"], "M7_HOST_NOT_QUIET")


def frozen(m):
    require(Path(m["freeze"]).is_file(), "M7_FROZEN_ACCEPTANCE_REQUIRED")
    receipt = document(m["freeze"])
    require(receipt.get("kind") == "joined-acceptance" and receipt.get("status") == "PASS" and receipt.get("pair") == m["pair"], "M7_FROZEN_ACCEPTANCE_REQUIRED")
    require(isinstance(receipt.get("evidenceSha256"), str) and re.fullmatch(r"[0-9a-f]{64}", receipt["evidenceSha256"]), "M7_ACCEPTANCE_EVIDENCE_REQUIRED")


def image(m):
    spec = json.loads(command(["docker", "image", "inspect", m["image"]]))[0]
    labels_match(spec.get("Config", {}).get("Labels", {}) or {}, **m["pair"])
    if m.get("imageId"):
        require(spec["Id"] == m["imageId"], "M7_IMAGE_ID_CHANGED")
    return spec["Id"]


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def prepare(args):
    require(args.tenants in COUNTS and args.replicas in REPLICAS, "M7_CAPACITY_CELL_INVALID")
    require(math.isfinite(args.quiet_load) and 0 <= args.quiet_load <= (os.cpu_count() or 1), "M7_QUIET_BOUND_INVALID")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{1,255}", args.image), "M7_IMAGE_REFERENCE_INVALID")
    target = Path(args.directory).resolve()
    require(re.fullmatch(r"/[A-Za-z0-9_./-]+", str(target)), "M7_PRIVATE_PATH_INVALID")
    require(not target.exists() and not any(p in (".git", "node_modules") for p in target.parts), "M7_TARGET_MUST_BE_NEW")
    for repo in (args.core_repo, args.deploy_repo):
        commit(repo, args.core_commit if repo == args.core_repo else args.deploy_commit)
    pinned = instrument()
    target.mkdir(parents=True, mode=0o700)
    nonce = uuid.uuid4().hex
    m = {"version": 1, "directory": str(target), "owner": nonce, "project": "nsm7-" + nonce[:12] + "-n" + str(args.tenants) + "-a" + str(args.replicas),
         "pair": {"core": args.core_commit, "deploy": args.deploy_commit}, "coreRepository": str(Path(args.core_repo).resolve()),
         "deployRepository": str(Path(args.deploy_repo).resolve()), "instrument": pinned, "image": args.image,
         "tenants": args.tenants, "replicas": args.replicas, "port": port(), "quietLoad": args.quiet_load,
         "freeze": str(Path(args.freeze).resolve()), "cadence": {"accel": 1, "hotFactor": 10, "socketsPerTenant": 2, "idleSeconds": 600, "loadSeconds": 900}}
    write(target / "owner.json", m)
    # Refuse preexisting project resources; no broad cleanup/nearest substitute.
    require(not resources(m), "M7_PROJECT_EXISTS")
    core = target / "core"
    git(args.core_repo, "worktree", "add", "--detach", str(core), args.core_commit)
    overlay = core / "deploy/multitenant"
    shutil.rmtree(overlay)
    overlay.mkdir(parents=True)
    archive = subprocess.check_output(["git", "-C", args.deploy_repo, "archive", args.deploy_commit + ":bindings/compose/multitenant"])
    command(["tar", "-x", "-C", overlay], input=archive)
    write(overlay / ".overlay.json", {"version": 1, "deployRepository": m["deployRepository"], "deployCommit": args.deploy_commit})
    env = runtime_env({"NS_API_REPLICAS": str(args.replicas)})
    command(["node", overlay / "prepare.js", "--state", target / "state", "--port", str(m["port"])], cwd=overlay, env=env)
    shutil.move(overlay / ".env", target / "env")
    with (target / "env").open("a") as output:
        output.write("NS_DEMO_IMAGE=" + args.image + "\nNS_DEMO_TENANTS=" + str(args.tenants) + "\nNS_API_REPLICAS=" + str(args.replicas) + "\n")
    source_files = [overlay / "compose.yaml", *sorted((target / "state").glob("compose.*.yaml"))]
    base_args = ["docker", "compose", "-p", m["project"], "--env-file", target / "env"]
    for file in source_files:
        base_args.extend(["-f", file])
    config = json.loads(command([*base_args, "--profile", "ops", "config", "--format", "json"]))
    serving_mounts(config)
    for spec in config["services"].values():
        for volume in spec.get("volumes", []):
            if volume.get("type")=="bind":
                require(Path(volume["source"]).resolve().is_relative_to(target / "state"), "M7_FOREIGN_STATE_MOUNT_REFUSED")
    require(all(name in config["services"] for name in ("postgres", "vault", "admin", "primer", "feed-reader", "api", "realtime", "evaluator", "tenant-admin", "ui", "nginx")), "M7_BINDING_CAPABILITY_MISSING")
    # Runtime product source is always its paired image. Only preserve the
    # binding's own existing private-state mounts. No bootstrap or lib overlay.
    for name, spec in config["services"].items():
        spec.setdefault("labels", {})[OWNER] = nonce
    for kind in ("volumes", "networks"):
        for spec in config.get(kind, {}).values():
            require(not spec.get("external") and spec.get("name", "").startswith(m["project"]+"_"), "M7_EXTERNAL_OR_SHARED_RESOURCE_REFUSED")
            spec.setdefault("labels", {})[OWNER] = nonce
    pg = config["services"]["postgres"]
    require(isinstance(pg.get("command"), list) and pg["command"][0] == "postgres", "M7_POSTGRES_COMMAND_SHAPE_CHANGED")
    pg["command"].extend(["-c", "shared_preload_libraries=pg_stat_statements", "-c", "pg_stat_statements.track=top", "-c", "track_io_timing=on"])
    require(not any("shared_preload_libraries" in str(x) for x in pg["command"][:-6]), "M7_POSTGRES_PRELOAD_ALREADY_SELECTED")
    write(target / "frozen.compose.json", config)
    m["prepared"] = True
    m["sourceCompose"] = {str(f.relative_to(target)): digest(f) for f in source_files}
    m["composeSha256"] = digest(target / "frozen.compose.json")
    m["probe"] = generate(ROOT, target / "probe.js")
    m["workload"] = generate_workload(ROOT, target / "k6/workload.js")
    write(target / "owner.json", m)
    print(json.dumps({"prepared": m["project"], "pair": m["pair"], "tenants": args.tenants, "replicas": args.replicas}))


def verify(d, m):
    require(git(d / "core", "rev-parse", "HEAD") == m["pair"]["core"], "M7_OWN_CORE_HEAD_CHANGED")
    require(digest(d / "frozen.compose.json") == m["composeSha256"], "M7_COMPOSE_CHANGED")
    require(digest(d / "probe.js") == m["probe"]["adaptedSha256"], "M7_PROBE_CHANGED")
    require(digest(d / "k6/workload.js") == m["workload"]["adaptedSha256"], "M7_WORKLOAD_CHANGED")
    for file, sha in m["sourceCompose"].items():
        require(digest(d / file) == sha, "M7_SOURCE_COMPOSE_CHANGED")
    # Shipping build admission checks every input against the two commits.
    code = "require('./deploy/multitenant/build').assertCleanSource(process.cwd(),process.argv[1])"
    command(["node", "-e", code, m["pair"]["core"]], cwd=d / "core")
    assert_owned(m)


def psql(d, sql, database="postgres"):
    return compose(d, "exec", "-T", "postgres", "psql", "-X", "-q", "-At", "-F", "\t", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database, input=sql.encode())


def service_roster(config):
    return [name for name, spec in config["services"].items()
            if isinstance(spec.get("command"), list) and spec["command"][-1:] and spec["command"][-1] in ("api", "realtime", "evaluator", "tenant-admin")]


def deploy(d, m):
    frozen(m);quiet(d, m, "deploy-before");verify(d, m)
    m["imageId"] = image(m)
    config = document(d / "frozen.compose.json")
    for spec in config["services"].values():
        if "build" in spec:
            spec["image"] = m["imageId"]
    write(d / "frozen.compose.json", config);m["composeSha256"] = digest(d / "frozen.compose.json");write(d / "owner.json", m)
    stages = []
    def stage(name, *argv):
        before = time.monotonic()
        with (d / (name + ".log")).open("wb") as output:
            compose(d, *argv, file=output, timeout=1800)
        stages.append({"name": name, "seconds": time.monotonic() - before})
    stage("infrastructure", "up", "-d", "--no-build", "--pull", "never", "--wait", "postgres", "vault")
    psql(d, "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")  # Maintenance DB only.
    stage("bootstrap", "--profile", "ops", "run", "--rm", "bootstrap")
    layout = document(d / "state/bootstrap/layout.json")
    require(all(layout.get("namespaces", {}).get(kind) == "nsdemo_" + kind for kind in ("entries","devicestatus","treatments","clock","eval_checkpoint")), "M7_ORACLE_SCHEMA_CONTRACT_CHANGED")
    stage("admin", "up", "-d", "--no-build", "--pull", "never", "--wait", "admin")
    stage("provision", "--profile", "ops", "run", "--rm", "primer", "node", "deploy/multitenant/prime.js", "provision")
    roster = service_roster(config)
    stage("roles", "up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "1200", "feed-reader", *roster, "ui", "nginx")
    stage("prime", "--profile", "ops", "run", "--rm", "primer", "node", "deploy/multitenant/prime.js", "prime")
    candidates = [file for file in (d / "state/primer/tenants.json", d / "state/ops/tenants.json") if file.exists()]
    require(candidates, "M7_PRIMER_OUTPUT_MISSING")
    projections = [tenant_projection(document(file), m["tenants"]) for file in candidates]
    require(all(value == projections[0] for value in projections), "M7_PRIMER_OUTPUT_CONFLICT")
    write(d / "tenants.private.json", projections[0])
    # Host probe dependencies are extracted from this exact paired image,
    # never borrowed from a peer checkout or copied into a serving container.
    name = m["project"] + "-dependencies"
    cid = command(["docker", "create", "--name", name, "--label", OWNER + "=" + m["owner"], m["imageId"]]).strip()
    try:
        (d / "dependencies").mkdir()
        command(["docker", "cp", cid + ":/opt/app/node_modules", d / "dependencies"], timeout=120)
        command(["docker", "cp", cid + ":/opt/app/package-lock.json", d / "dependencies/package-lock.json"])
    finally:
        owned(json.loads(command(["docker", "inspect", cid]))[0], m["owner"])
        command(["docker", "rm", cid])
    m["dependencyImage"] = m["imageId"];m["dependencyLockSha256"] = digest(d / "dependencies/package-lock.json")
    m["restartRoles"] = roster
    write(d / "owner.json", m);write(d / "deployment.json", {"stages": stages, "pair": m["pair"], "imageId": m["imageId"]})


def phase_snapshot(d, out, name):
    rows = resources(document(d / "owner.json"), False)
    result = {}
    for row in rows:
        role = row["Config"]["Labels"].get("com.docker.compose.service", row["Name"])
        try:
            raw = command(["docker", "exec", row["Id"], "cat", "/sys/fs/cgroup/cpu.stat", "/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.stat"])
            processes = command(["docker", "top", row["Id"], "-eo", "pid,comm,rss"])
            result[role] = {"id": row["Id"], "cgroup": raw, "processRssKiB": processes}
        except RuntimeError:
            result[role] = {"id": row["Id"], "unavailable": True}
    write(out / (name + "-cgroups.json"), {"at": time.time(), "roles": result})
    sql = "SELECT r.rolname,sum(s.calls),sum(s.total_exec_time) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid GROUP BY 1 ORDER BY 1;"
    (out / (name + "-pg-role.tsv")).write_text(psql(d, sql))
    (out / (name + "-pg-statements.tsv")).write_text(psql(d, "SELECT r.rolname,s.calls,s.total_exec_time,left(regexp_replace(s.query,'\\s+',' ','g'),500) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid ORDER BY total_exec_time DESC LIMIT 50;"))


@contextlib.contextmanager
def sampling(d, out):
    m = document(d / "owner.json")
    out.mkdir(parents=True, exist_ok=True)
    # Reuse source-owned sampler with the already frozen merged Compose file;
    # empty second file replaces the old bootstrap source-mount overlay.
    empty = d / "empty.compose.json";write(empty, {"services": {}})
    log = (out / "sampler.log").open("wb")
    process = subprocess.Popen([str(BASE / "probes/sample.sh"), m["project"], str(d / "env"), str(d / "frozen.compose.json"), str(empty), str(out)], stdout=log, stderr=log, start_new_session=True)
    before = time.monotonic()
    cpu_before = resource.getrusage(resource.RUSAGE_SELF)
    try:
        yield
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
        log.close()
        write(out / "sampler.json", {"cadenceSeconds": 2, "wallSeconds": time.monotonic()-before, "pid": process.pid,
                                    "source": "compose-baseline/probes/sample.sh", "controllerCpuSeconds": resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime - cpu_before.ru_utime - cpu_before.ru_stime,
                                    "overhead": "included in host/PG cgroup figures; compare sampler-disabled idle control"})


def stored(d, runid):
    require(re.fullmatch(r"[a-z0-9-]{1,120}", runid), "M7_RUN_ID_INVALID")
    sql = "\nUNION ALL\n".join("SELECT tenant_id::text,'" + kind + "',count(*) FROM nsdemo_" + kind + "." + kind + " WHERE doc->>'" + field + "'='" + runid + suffix + "' GROUP BY 1" for kind, field, suffix in [("entries","device",""),("devicestatus","device",""),("treatments","enteredBy",""),("entries","device","-probe")]) + ";"
    # Distinguish probe rows without changing the SQL's independent role.
    sql = sql.rsplit("'entries'", 1)[0] + "'probe'" + sql.rsplit("'entries'", 1)[1]
    rows = {}
    for line in psql(d, sql, "nightscout_compose_test").splitlines():
        tenant, kind, count = line.split("\t");rows.setdefault(tenant, {})[kind] = int(count)
    return rows


def count_oracle(d, strict=True):
    out = d / "load";metrics = document(out / "k6-summary.json")["metrics"]
    probes = document(out / "fanout.json")["probeWrites"]["byTenant"]
    values = stored(d, (out / "runid").read_text().strip())
    write(out / "stored-counts.json", values)
    result = oracle(values, metrics, probes, document(d / "tenants.private.json"), strict=strict)
    write(out / "oracle.json", result)
    return result


def control(d, m):
    verify(d, m)
    return oracle_control(d)


def oracle_control(d):
    assert_owned(document(d / "owner.json"))
    require(count_oracle(d)["verdict"] == "GREEN", "M7_CONTROL_BASELINE_NOT_GREEN")
    marker = (d / "load/runid").read_text().strip()
    require(re.fullmatch(r"[a-z0-9-]{1,120}", marker), "M7_RUN_ID_INVALID")
    mutate = "BEGIN; SELECT set_config('app.current_tenant_id',(SELECT tenant_id::text FROM nsdemo_entries.entries WHERE doc->>'device'='{old}' LIMIT 1),true); UPDATE nsdemo_entries.entries SET doc=jsonb_set(doc,'{{device}}',to_jsonb('{new}'::text)) WHERE ctid=(SELECT ctid FROM nsdemo_entries.entries WHERE doc->>'device'='{old}' AND tenant_id=current_setting('app.current_tenant_id')::uuid LIMIT 1) RETURNING _id;COMMIT;"
    baseline = count_oracle(d)
    changed = False
    try:
        result = psql(d, mutate.format(old=marker, new=marker + "-control"), "nightscout_compose_test")
        require(result.strip(), "M7_CONTROL_NO_VICTIM")
        changed = True
        broken = count_oracle(d)
        require(broken["verdict"] == "RED", "M7_CONTROL_DID_NOT_FAIL")
    finally:
        if changed:
            psql(d, mutate.format(old=marker + "-control", new=marker), "nightscout_compose_test")
    restored = count_oracle(d)
    require(restored["verdict"] == "GREEN", "M7_CONTROL_NOT_RESTORED")
    write(d / "load/oracle-control.json", {"baseline": baseline["verdict"], "broken": broken["verdict"], "restored": restored["verdict"]})


def readiness(d, m):
    script = "require('./deploy/multitenant/load-env');const own=require('./lib/server/internal-api/listener-config').resolve(['evaluator'],process.env);require('./lib/server/internal-api/clients').evaluatorInspection(own.peer('evaluator',{maxBytes:16777216,timeoutMs:5000})).inspectEvaluator({}).then(v=>console.log(JSON.stringify(v))).catch(()=>{process.exitCode=1;});"
    deadline = time.monotonic() + 1200
    observations = []
    while time.monotonic() < deadline:
        before = time.monotonic()
        raw = compose(d, "exec", "-T", "evaluator", "node", "-e", script)
        view = json.loads(raw)
        require(isinstance(view.get("tenants"), list), "M7_EVALUATOR_NO_INSTRUMENT")
        ready = sum(row.get("ready") is True and row.get("cycles", 0) > 0 for row in view["tenants"])
        observations.append({"at":time.time(),"ready":ready,"expected":m["tenants"],"bytes":len(raw.encode()),"wallSeconds":time.monotonic()-before})
        write(d / "runtime-readiness.json", {"observations":observations,"cadenceSeconds":15,"meaning":"runtime acquisition confirmed; not clinical-equivalence proof"})
        if ready == m["tenants"]:return
        time.sleep(15)
    raise RuntimeError("M7_RUNTIME_NOT_READY")


@contextlib.contextmanager
def loadgen_process(d, process):
    stopped = threading.Event()
    def observe():
        with (d / "load/loadgen.jsonl").open("w") as output:
            while not stopped.is_set() and process.poll() is None:
                try:
                    raw = Path("/proc/"+str(process.pid)+"/stat").read_text().split(")",1)[1].split()
                    status = Path("/proc/"+str(process.pid)+"/status").read_text()
                    rss = re.search(r"^VmRSS:\s+(\d+)",status,re.M)
                    output.write(json.dumps({"at":time.time(),"pid":process.pid,"cpuTicks":int(raw[11])+int(raw[12]),"clockTicksPerSecond":os.sysconf('SC_CLK_TCK'),"rssKiB":int(rss[1]) if rss else None})+"\n")
                    output.flush()
                except (OSError,IndexError):break
                stopped.wait(2)
    thread=threading.Thread(target=observe,daemon=True);thread.start()
    try:yield
    finally:stopped.set();thread.join(timeout=3)


def run(d, m, k6_image):
    frozen(m);quiet(d, m, "run-before", check_load=False);verify(d, m);image(m)
    require((d / "deploy-before-host.json").exists(), "M7_DEPLOY_QUIET_RECORD_REQUIRED")
    require(digest(d / "dependencies/package-lock.json") == m["dependencyLockSha256"], "M7_DEPENDENCIES_CHANGED")
    readiness(d, m)
    k6_id = json.loads(command(["docker", "image", "inspect", k6_image]))[0]["Id"]
    write(d / "loadgen-image.json", {"k6": k6_id, "probeDependencyImage": m["dependencyImage"]})
    # Sparse once-per-phase cgroups/PG snapshots plus a sampler-disabled idle
    # window make collection overhead observable independently of tenant work.
    out = d / "idle-disabled";out.mkdir()
    psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before");time.sleep(60);phase_snapshot(d, out, "after")
    for name, seconds in (("idle", m["cadence"]["idleSeconds"]),):
        out = d / name;out.mkdir();quiet(d, m, name + "-before", check_load=False)
        psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before")
        with sampling(d, out):time.sleep(seconds)
        phase_snapshot(d, out, "after")
    out = d / "load";out.mkdir()
    runid = "m7-" + m["owner"][:12];(out / "runid").write_text(runid)
    spec = m["project"] + "|" + str(d / "env") + "|" + str(d / "frozen.compose.json")
    probe_env = runtime_env({"NODE_PATH": str(d / "dependencies/node_modules"), "M7_RESTART_ROLES": json.dumps(m["restartRoles"]), "STOCK_MS": "300000", "RECOVERY_MS": "120000"})
    psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before-prime")
    probe_log = (out / "probe.log").open("wb")
    with sampling(d, out):
        probe_process = subprocess.Popen(["node", str(d / "probe.js"), "--base", "http://127.0.0.1:" + str(m["port"]), "--tenants", str(d / "tenants.private.json"), "--compose", spec,
            "--runid", runid, "--per", "2", "--open", "5", "--window", str(m["cadence"]["loadSeconds"]), "--probeEvery", "3000", "--restart", "1", "--evalTimeout", "900", "--out", str(out / "probe.json"), "--signal", str(out / ".window")], env=probe_env, stdout=probe_log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 600
            while not (out / ".window").exists():
                require(probe_process.poll() is None and time.monotonic() < deadline, "M7_PROBE_NOT_PRIMED")
                time.sleep(1)
            quiet(d, m, "load-before", check_load=False)
            phase_snapshot(d, out, "after-prime")
            psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before")
            monitor = loadgen_process(d, probe_process);monitor.__enter__()
            with (out / "k6.log").open("wb") as output:
                command(["docker", "run", "--rm", "--name", m["project"] + "-k6", "--label", OWNER + "=" + m["owner"], "--label", "com.docker.compose.project=" + m["project"], "--label", "com.docker.compose.service=k6",
                    "--network", "host", "-u", str(os.getuid()) + ":" + str(os.getgid()), "-v", str(d / "k6") + ":/scripts:ro", "-v", str(out) + ":/out", "-v", str(d / "tenants.private.json") + ":/tenants.private.json:ro",
                    "-e", "BASE_URL=http://127.0.0.1:" + str(m["port"]), "-e", "TENANTS_FILE=/tenants.private.json", "-e", "RUN_ID=" + runid,
                    "-e", "RUN_START=" + str(int(time.time()*1000)), "-e", "DURATION=" + str(m["cadence"]["loadSeconds"]), "-e", "ACCEL=1", "-e", "HOT_FACTOR=10",
                    "-e", "SHAPES=w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status", k6_id, "run", "--quiet", "--summary-export", "/out/k6-summary.json", "/scripts/workload.js"], file=output, timeout=m["cadence"]["loadSeconds"]+600)
            phase_snapshot(d, out, "after")
            (out / ".restart").touch()
            require(probe_process.wait(timeout=1500) == 0, "M7_PROBE_FAILED")
        finally:
            if probe_process.poll() is None:probe_process.terminate();probe_process.wait(timeout=10)
            if "monitor" in locals():monitor.__exit__(None,None,None)
            probe_log.close()
    phase_snapshot(d, out, "after-reconnect")
    result = count_oracle(d)
    control(d, m)
    host = inventory(m["owner"]);write(d / "run-after-host.json", host)
    result_probe = document(out / "probe.json")
    correctness = [result["verdict"] == "GREEN", result["uncertain"] == 0, not any(not r["owned"] for r in host["containers"]),
                   result_probe["prime"]["primed"] == 2*m["tenants"], result_probe["window"]["deliveredFrames"] == result_probe["window"]["expectedFrames"],
                   result_probe["restart"]["stockRecovered"] == 2*m["tenants"], result_probe["restart"]["runtimeAcquisitionObservation"]["missing"] == 0,
                   metric(document(out / "k6-summary.json")["metrics"], "writes_refused") == 0,
                   metric(document(out / "k6-summary.json")["metrics"], "http_req_failed", "rate") == 0,
                   metric(document(out / "k6-summary.json")["metrics"], "dropped_iterations") == 0,
                   result_probe["window"]["writes"]["failed"] == 0]
    summary = {"pair": m["pair"], "instrument": m["instrument"]["sha256"], "tenants": m["tenants"], "replicas": m["replicas"],
               "imageId":m["imageId"], "verdict": "PASS" if all(correctness) else "FAIL", "correctness": correctness, "cadence": m["cadence"],
               "oracle": {key: value for key, value in result.items() if key != "rows"}, "probe": result_probe,
               "performanceThresholds": "none invented; raw latency/CPU/RSS/PG metrics are measurements, not predeclared capacity limits"}
    from reduce import measurements
    summary["measurements"] = measurements(d, m)
    require(summary["measurements"]["complete"], "M7_NO_MEASUREMENT")
    write(d / "summary.json", summary)
    metrics = document(out / "k6-summary.json")["metrics"]
    require(metric(metrics,"writes_refused")==0 and metric(metrics,"responses_refused")==0,"M7_FUNCTIONAL_REQUEST_REFUSAL")
    require(summary["verdict"] == "PASS", "M7_CORRECTNESS_GROWTH_GATE_FAILED")


def down(d, m):
    assert_owned(m)
    if m.get("prepared"):
        verify(d, m)
        compose(d, "--profile", "ops", "down", "--volumes", "--remove-orphans", timeout=120)
    else:
        require(not resources(m), "M7_PARTIAL_PREPARE_HAS_RESOURCES")
    core = d / "core"
    if core.exists():
        require(git(core,"rev-parse","HEAD") == m["pair"]["core"], "M7_OWN_CORE_HEAD_CHANGED")
        git(m["coreRepository"], "worktree", "remove", "--force", str(core))
    for file in (d / "state", d / "dependencies"):
        if file.exists():shutil.rmtree(file)
    (d / "tenants.private.json").unlink(missing_ok=True)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    for name in ("directory", "core-repo", "core-commit", "deploy-repo", "deploy-commit", "image", "freeze"):prep.add_argument("--"+name, required=True)
    prep.add_argument("--tenants", type=int, choices=COUNTS, required=True);prep.add_argument("--replicas", type=int, choices=REPLICAS, required=True);prep.add_argument("--quiet-load", type=float, default=3)
    for cmd in ("verify", "build", "deploy", "run", "control", "down"):
        own = sub.add_parser(cmd);own.add_argument("directory")
        if cmd == "run":own.add_argument("--k6-image", required=True)
    check = sub.add_parser("check-campaign");check.add_argument("summary")
    return p


def main():
    args = parser().parse_args()
    if args.command == "prepare":return prepare(args)
    if args.command == "check-campaign":campaign_check(document(args.summary));return print("M7_CAMPAIGN_COMPLETE")
    d, m = load(args.directory)
    if args.command == "verify":verify(d, m);image(m);print("M7_PAIR_AND_INSTRUMENT_PINNED")
    elif args.command == "build":
        frozen(m);quiet(d, m, "build-before");verify(d, m)
        overlay = d / "core/deploy/multitenant"
        shutil.copyfile(d / "env", overlay / ".env")
        try:command(["node", overlay / "build.js"], cwd=overlay, timeout=1800)
        finally:(overlay / ".env").unlink(missing_ok=True)
    elif args.command == "deploy":deploy(d, m)
    elif args.command == "run":run(d, m, args.k6_image)
    elif args.command == "control":control(d, m)
    elif args.command == "down":down(d, m)

if __name__ == "__main__":
    try:main()
    except Exception as error:
        message = str(error)
        print(message if re.fullmatch(r"M7_[A-Z_]+(?::[a-zA-Z0-9_.-]+)?", message) else "M7_ADAPTER_REFUSED", file=sys.stderr)
        sys.exit(1)
