#!/usr/bin/env python3
"""Joined M7 instrument. No operation attaches to or tears down an existing stack."""
import argparse
import gzip
import contextlib
import contextvars
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
from contract import (COUNTS, REPLICAS, PILOT_COUNTS, CADENCE, OWNER, SHA, require, digest, labels_match, owned,
                      tenant_projection, metric, oracle, serving_mounts, campaign_check, pilot_check, host_identity, receipt_scope, diagnostic_check)
from probe import generate
from workload import generate as generate_workload
import profile_provenance
import evaluator_progress
import evaluator_idle
BASE = ROOT / "tools/mt-bench/compose-baseline"
REUSED = ["tools/mt-bench/capacity/probe.js", "tools/mt-bench/capacity/k6/workload.js",
          "tools/mt-bench/compose-baseline/probes/sample.sh", "tools/mt-bench/compose-baseline/oracle/disk.sh"]


def runtime_env(extra=None):
    # Ambient NS_*/NODE_OPTIONS/BENCH_* must not silently alter a paired run.
    names=("PATH","HOME","USER","LANG","XDG_RUNTIME_DIR","DOCKER_HOST","DOCKER_CONTEXT","DOCKER_CONFIG","SSH_AUTH_SOCK")
    return {**{key:os.environ[key] for key in names if key in os.environ}, **(extra or {})}


_PRIVATE_COMMANDS=contextvars.ContextVar('m7_private_commands',default=None)


@contextlib.contextmanager
def private_commands(directory):
    directory=Path(directory);directory.mkdir(mode=0o700,parents=True,exist_ok=True);directory.chmod(0o700)
    token=_PRIVATE_COMMANDS.set({'directory':directory,'sequence':0})
    try:yield
    finally:_PRIVATE_COMMANDS.reset(token)


def command(argv, *, cwd=None, env=None, input=None, file=None, timeout=120, binary=False, phase=None):
    # Raw output belongs only in private phase artifacts; never argv/env in
    # public exceptions. Capture begins before prepared=true or state exists.
    capture=_PRIVATE_COMMANDS.get();prefix=None;started=time.time()
    if capture is not None:
        capture['sequence']+=1
        prefix=capture['directory']/(str(capture['sequence']).zfill(4)+'-'+Path(str(argv[0])).name)
    result=None;failure=None;stdout=b'';stderr=b''
    try:
        if prefix is None:
            result=subprocess.run([str(a) for a in argv],cwd=cwd,env=runtime_env() if env is None else env,input=input,
                                  stdout=file or subprocess.PIPE,stderr=subprocess.STDOUT if file else subprocess.PIPE,timeout=timeout)
            stdout=result.stdout or b'';stderr=result.stderr or b''
        else:
            with prefix.with_suffix('.stdout').open('wb') as out,prefix.with_suffix('.stderr').open('wb') as err:
                prefix.with_suffix('.stdout').chmod(0o600);prefix.with_suffix('.stderr').chmod(0o600)
                result=subprocess.run([str(a) for a in argv],cwd=cwd,env=runtime_env() if env is None else env,input=input,stdout=out,stderr=err,timeout=timeout)
            stdout=prefix.with_suffix('.stdout').read_bytes();stderr=prefix.with_suffix('.stderr').read_bytes()
            if file:file.write(stdout);file.write(stderr)
        if result.returncode:
            error=RuntimeError('M7_COMMAND_FAILED:'+Path(str(argv[0])).name);error.stderr=stderr;error.returncode=result.returncode
            raise error
        return None if file else stdout if binary else stdout.decode()
    except Exception as error:
        failure=type(error).__name__
        raise
    finally:
        if prefix is not None:
            write(prefix.with_suffix('.json'),{'program':Path(str(argv[0])).name,'phase':phase or Path(str(argv[0])).name,
                  'startedAt':started,'elapsedSeconds':time.time()-started,'returncode':result.returncode if result else None,
                  'timeoutSeconds':timeout,'failureType':failure,'stdout':prefix.with_suffix('.stdout').name,'stderr':prefix.with_suffix('.stderr').name,
                  'scope':'PRIVATE; raw output may contain credentials; do not publish'})


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


def frozen(m,operation):
    require(Path(m["freeze"]).is_file(),"M7_FROZEN_OR_DIAGNOSTIC_RECEIPT_REQUIRED")
    return receipt_scope(m,document(m["freeze"]),operation)


def experiment_host(d,m,phase):
    if m.get("profile")=="fresh-image-diagnostic":
        host=inventory(m["owner"]);host["scope"]="diagnostic-only; not quiet-host capacity"
        write(d/(phase+"-host.json"),host)
    else:quiet(d,m,phase)


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
    profile_provenance.selection(getattr(args,'diagnostics','off'),getattr(args,'diagnostics_interval_ms',5000))
    require(os.getuid()==1000 and os.getgid()==1000,"M7_HOST_RUNTIME_UID_REQUIRED")
    if args.profile=="fresh-image-diagnostic":require(1<=args.tenants<=10 and 1<=args.replicas<=2,"M7_DIAGNOSTIC_LIMIT_INVALID")
    require(1<=args.tenants<=10000 and args.replicas in REPLICAS and args.profile in CADENCE, "M7_CAPACITY_CELL_INVALID")
    require(math.isfinite(args.quiet_load) and 0 <= args.quiet_load <= (os.cpu_count() or 1), "M7_QUIET_BOUND_INVALID")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{1,255}", args.image), "M7_IMAGE_REFERENCE_INVALID")
    target = Path(args.directory).resolve()
    require(re.fullmatch(r"/[A-Za-z0-9_./-]+", str(target)), "M7_PRIVATE_PATH_INVALID")
    require(not target.exists() and not any(p in (".git", "node_modules") for p in target.parts), "M7_TARGET_MUST_BE_NEW")
    for repo in (args.core_repo, args.deploy_repo):
        commit(repo, args.core_commit if repo == args.core_repo else args.deploy_commit)
    progress_contract=json.loads(git(args.core_repo,"show",args.core_commit+":lib/server/internal-api/contracts/evaluator-inspection.json"))
    require(progress_contract.get("version")==2,"M7_EVALUATOR_PROGRESS_SOURCE_REQUIRED")
    due=progress_contract['operations']['inspectEvaluator']['response']['properties']['tenants']['items']
    require(all(key in due.get('properties',{}) and key in due.get('required',[]) for key in ('dueAt','dueReason')),'M7_EVALUATOR_DUE_SOURCE_REQUIRED')
    require('jobs' in due.get('properties',{}) and 'jobs' in due.get('required',[]),'M7_EVALUATOR_IDLE_SOURCE_REQUIRED')
    pinned = instrument()
    target.mkdir(parents=True, mode=0o700)
    try:
        with private_commands(target/'prepare-commands'):
            return prepare_staged(args,target,pinned)
    except Exception as error:
        text=str(error)
        write(target/'prepare-failure.json',{'kind':'source-preparation-failure','prepared':False,'pair':{'core':args.core_commit,'deploy':args.deploy_commit},
              'instrument':pinned['sha256'],'publicCode':text if re.fullmatch(r'M7_[A-Z_]+(?::[a-zA-Z0-9_.-]+)?',text) else 'M7_PREPARE_REFUSED',
              'privateArtifacts':'prepare-commands','fullAcceptance':'NOT_RUN','capacity':'NO-MEASUREMENT'})
        raise


def prepare_staged(args,target,pinned):
    nonce = uuid.uuid4().hex
    m = {"version": 1, "directory": str(target), "owner": nonce, "project": "nsm7-" + nonce[:12] + "-n" + str(args.tenants) + "-a" + str(args.replicas),
         "pair": {"core": args.core_commit, "deploy": args.deploy_commit}, "coreRepository": str(Path(args.core_repo).resolve()),
         "deployRepository": str(Path(args.deploy_repo).resolve()), "instrument": pinned, "image": args.image,
         "tenants": args.tenants, "replicas": args.replicas, "port": port(), "quietLoad": args.quiet_load,
         "freeze": str(Path(args.freeze).resolve()), "profile":args.profile,"cadence":CADENCE[args.profile]}
    m["diagnostics"]=profile_provenance.selection(getattr(args,"diagnostics","off"),getattr(args,"diagnostics_interval_ms",5000))
    m["hostIdentity"]=host_identity(inventory(nonce))
    write(target / "owner.json", m)
    # Refuse preexisting project resources; no broad cleanup/nearest substitute.
    require(not resources(m), "M7_PROJECT_EXISTS")
    core = target / "core"
    git(args.core_repo, "worktree", "add", "--detach", str(core), args.core_commit)
    overlay = core / "deploy/multitenant"
    shutil.rmtree(overlay)
    overlay.mkdir(parents=True)
    archive = command(["git", "-C", args.deploy_repo, "archive", args.deploy_commit + ":bindings/compose/multitenant"],binary=True,phase="deploy-archive")
    command(["tar", "-x", "-C", overlay], input=archive)
    write(overlay / ".overlay.json", {"version": 1, "deployRepository": m["deployRepository"], "deployCommit": args.deploy_commit})
    for name in ("commission-restore.js","publish-primer.js"):
        require((overlay/name).is_file(),"M7_BINDING_COMMISSION_CAPABILITY_MISSING")
    env = runtime_env({"NS_API_REPLICAS": str(args.replicas)})
    command(["node", overlay / "prepare.js", "--state", target / "state", "--port", str(m["port"])], cwd=overlay,env=env,phase="product-prepare")
    shutil.move(overlay / ".env", target / "env")
    with (target / "env").open("a") as output:
        output.write("NS_DEMO_IMAGE=" + args.image + "\nNS_DEMO_TENANTS=" + str(args.tenants) + "\nNS_API_REPLICAS=" + str(args.replicas) + "\n")
    source_files = [overlay / "compose.yaml", *sorted((target / "state").glob("compose.*.yaml"))]
    base_args = ["docker", "compose", "-p", m["project"], "--env-file", target / "env"]
    for file in source_files:
        base_args.extend(["-f", file])
    config = json.loads(command([*base_args, "--profile", "ops", "config", "--format", "json"],phase="compose-config"))
    serving_mounts(config)
    profile_provenance.select_environment(config,m["diagnostics"])
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
    shutil.copyfile(HERE / "restart.cjs", target / "restart.cjs")
    m["restartHelperSha256"]=digest(target / "restart.cjs")
    m["probe"] = generate(ROOT, target / "probe.js")
    m["workload"] = generate_workload(ROOT, target / "k6/workload.js")
    write(target / "owner.json", m)
    print(json.dumps({"prepared": m["project"], "pair": m["pair"], "tenants": args.tenants, "replicas": args.replicas}))


def verify(d, m):
    require(host_identity(inventory(m["owner"]))==m["hostIdentity"],"M7_HOST_IDENTITY_CHANGED")
    require(git(d / "core", "rev-parse", "HEAD") == m["pair"]["core"], "M7_OWN_CORE_HEAD_CHANGED")
    require(digest(d / "frozen.compose.json") == m["composeSha256"], "M7_COMPOSE_CHANGED")
    profile_provenance.verify_environment(document(d/"frozen.compose.json"),m["diagnostics"])
    profile_provenance.state_environment(d/"state",document(d/"frozen.compose.json"),m["diagnostics"])
    require(digest(d / "restart.cjs")==m["restartHelperSha256"], "M7_RESTART_HELPER_CHANGED")
    require(digest(d / "probe.js") == m["probe"]["adaptedSha256"], "M7_PROBE_CHANGED")
    require(m['probe'].get('recoveryHelpers') and all(digest(d/name)==sha for name,sha in m['probe']['recoveryHelpers'].items()),'M7_RECOVERY_HELPER_CHANGED')
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


def deployment_plan(config):
    roster=service_roster(config)
    apis=[name for name in roster if config["services"][name]["command"][-1]=="api"]
    remaining=[name for name in roster if name not in apis]
    start=["up","-d","--no-build","--pull","never","--wait","--wait-timeout","1200"]
    return [
        ("infrastructure","compose",[*start,"postgres","vault"]),
        ("bootstrap","compose",["--profile","ops","run","--rm","bootstrap"]),
        ("admin-feed","compose",[*start,"admin","feed-reader"]),
        ("provision","compose",["--profile","ops","run","--rm","primer","node","deploy/multitenant/prime.js","provision"]),
        ("commission","compose",["--profile","ops","run","--rm","--no-deps","bootstrap","node","deploy/multitenant/commission-restore.js"]),
        ("apis","compose",[*start,*apis]),
        ("prime","compose",["--profile","ops","run","--rm","--no-deps","primer","node","deploy/multitenant/prime.js","prime"]),
        ("publish-primer","local",["publish-primer.js"]),
        ("remaining-roles","compose",[*start,*remaining,"ui","nginx"])]


def generator_tools():
    result={}
    for name in ("node","npm"):
        found=shutil.which(name);require(found,"M7_GENERATOR_TOOL_MISSING:"+name)
        executable=Path(found).resolve()
        result[name]={"path":str(executable),"sha256":digest(executable),"version":command([executable,"--version"]).strip()}
    return result


def generator_client(d,tools):
    # createRequire bypasses ambient NODE_PATH and proves the actual stock SDK
    # resolves inside this cell, rather than a peer checkout or fixture factory.
    script="""const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=fs.realpathSync(process.argv[1]),r=createRequire(path.join(root,'package.json'));
const entry=fs.realpathSync(r.resolve('socket.io-client'));
if(!entry.startsWith(path.join(root,'node_modules')+path.sep))throw Error('M7_GENERATOR_CLIENT_OUTSIDE_OWN_TREE');
const client=r('socket.io-client');if(typeof client.io!=='function')throw Error('M7_GENERATOR_CLIENT_INVALID');
console.log(JSON.stringify({entry,version:r('socket.io-client/package.json').version}));"""
    value=json.loads(command([tools['node']['path'],'-e',script,d/'dependencies'],phase='generator-client-preflight'))
    value['entrySha256']=digest(value['entry'])
    return value


def setup_generator(d,m):
    root=d/'dependencies';root.mkdir(mode=0o700)
    for name in ('package.json','package-lock.json'):
        (root/name).write_bytes(command(['git','-C',d/'core','show',m['pair']['core']+':'+name],binary=True))
    tools=generator_tools();lock=digest(root/'package-lock.json')
    (root/'.npmrc').write_text('');(root/'.npmrc').chmod(0o600)
    npm_env=runtime_env({'NPM_CONFIG_USERCONFIG':str(root/'.npmrc'),'NPM_CONFIG_GLOBALCONFIG':'/dev/null','NPM_CONFIG_CACHE':str(root/'.npm-cache')})
    with private_commands(d/'generator-commands'):
        command([tools['npm']['path'],'ci','--include=dev','--omit=optional','--ignore-scripts','--force'],cwd=root,env=npm_env,timeout=1200,phase='generator-npm-ci')
        client=generator_client(d,tools)
    require(digest(root/'package-lock.json')==lock,'M7_GENERATOR_LOCK_CHANGED')
    m['generator']={'kind':'owned-lockfile-install','tools':tools,'pair':m['pair'],'packageSha256':digest(root/'package.json'),'lockSha256':lock,'client':client,
                    'installFlags':['ci','--include=dev','--omit=optional','--ignore-scripts','--force'],'servingImageId':m['imageId']}
    write(d/'generator-provenance.json',m['generator']);write(d/'owner.json',m)


def verify_generator(d,m):
    expected=m.get('generator');require(expected,'M7_GENERATOR_PROVENANCE_REQUIRED')
    require(generator_tools()==expected['tools'],'M7_GENERATOR_TOOL_CHANGED')
    require(digest(d/'dependencies/package.json')==expected['packageSha256'] and digest(d/'dependencies/package-lock.json')==expected['lockSha256'],'M7_DEPENDENCIES_CHANGED')
    with private_commands(d/'generator-verifications'/uuid.uuid4().hex):
        require(generator_client(d,expected['tools'])==expected['client'],'M7_GENERATOR_CLIENT_CHANGED')


def deploy(d, m):
    frozen(m,"deploy");experiment_host(d,m,"deploy-before");verify(d,m)
    m["imageId"] = image(m)
    setup_generator(d,m)
    config = document(d / "frozen.compose.json")
    for spec in config["services"].values():
        if "build" in spec:spec["image"] = m["imageId"]
    write(d / "frozen.compose.json", config);m["composeSha256"] = digest(d / "frozen.compose.json");write(d / "owner.json", m)
    stages=[]
    for name,scope,args in deployment_plan(config):
        before=time.monotonic()
        with (d/(name+".log")).open("wb") as output:
            if scope=="local":command(["node",d/"core/deploy/multitenant"/args[0],d/"state"],file=output)
            else:compose(d,*args,file=output,timeout=1800)
        stages.append({"name":name,"seconds":time.monotonic()-before})
        write(d/"deployment-stages.json",stages)
        if name=="infrastructure":psql(d,"CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")
        if name=="bootstrap":
            fingerprint=json.loads(command(["node",HERE/"fingerprint.cjs",d/"core",m["pair"]["core"],d/"state/primer/config.json",str(m["tenants"])],phase="settings-fingerprint"))
            m["settingsFingerprint"]=fingerprint
            m["profileSelection"]=profile_provenance.identity(fingerprint,m["diagnostics"],config)
            profile_provenance.state_environment(d/"state",config,m["diagnostics"])
            write(d/"owner.json",m)
            layout=document(d/"state/bootstrap/layout.json")
            require(all(layout.get("namespaces",{}).get(kind)=="nsdemo_"+kind for kind in ("entries","devicestatus","treatments","clock","eval_checkpoint")),"M7_ORACLE_SCHEMA_CONTRACT_CHANGED")
            # Raw restart is not a valid controlled-placement replacement.
            # The coordinator must supply the committed sharding helper seam.
            for name in service_roster(config):
                file=d/"state"/name/"env.json"
                if file.exists():require(not document(file).get("MULTITENANT_REALTIME_PLACEMENT"),"M7_SHARDED_RESTART_HELPER_REQUIRED")
    candidates=[file for file in (d/"state/primer/tenants.json",d/"state/ops/tenants.json") if file.exists()]
    require(candidates,"M7_PRIMER_OUTPUT_MISSING")
    projections=[tenant_projection(document(file),m["tenants"]) for file in candidates]
    require(all(value==projections[0] for value in projections),"M7_PRIMER_OUTPUT_CONFLICT")
    write(d/"tenants.private.json",projections[0])
    profile_provenance.runtime_environment(resources(m),m["diagnostics"],config)
    m["restartRoles"]=service_roster(config)
    write(d/"owner.json",m);write(d/"deployment.json",{"stages":stages,"pair":m["pair"],"imageId":m["imageId"]})


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


def job_record(file,process,owner,group=False):
    raw=Path('/proc/'+str(process.pid)+'/stat').read_text().split(')',1)[1].split()
    write(file,{'owner':owner,'pid':process.pid,'startTicks':raw[19],'group':group,'completed':False})


def stop_job(file,owner):
    if not file.exists():return
    job=document(file)
    require(job.get('owner')==owner and isinstance(job.get('pid'),int) and job['pid']>1,'M7_HOST_JOB_NOT_OWNED')
    if job.get('completed'):return
    proc=Path('/proc/'+str(job['pid'])+'/stat')
    if proc.exists():
        raw=proc.read_text().split(')',1)[1].split()
        require(raw[19]==job['startTicks'],'M7_HOST_JOB_IDENTITY_CHANGED')
        if raw[0]!='Z':
            if job['group']:
                require(os.getpgid(job['pid'])==job['pid'],'M7_HOST_JOB_GROUP_CHANGED')
                os.killpg(job['pid'],signal.SIGTERM)
            else:os.kill(job['pid'],signal.SIGTERM)
    job['completed']=True;write(file,job)


@contextlib.contextmanager
def sampling(d, out):
    m = document(d / "owner.json")
    out.mkdir(parents=True, exist_ok=True)
    # Reuse source-owned sampler with the already frozen merged Compose file;
    # empty second file replaces the old bootstrap source-mount overlay.
    empty = d / "empty.compose.json";write(empty, {"services": {}})
    log = (out / "sampler.log").open("wb")
    process = subprocess.Popen([str(BASE / "probes/sample.sh"), m["project"], str(d / "env"), str(d / "frozen.compose.json"), str(empty), str(out)], stdout=log, stderr=log, start_new_session=True)
    job=out/"sampler-job.json";job_record(job,process,m["owner"],group=True)
    before = time.monotonic()
    cpu_before = resource.getrusage(resource.RUSAGE_SELF)
    try:
        yield
    finally:
        stop_job(job,m["owner"])
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
    out = d / "load";metrics = document(out / ("client-acks.json" if document(d/"owner.json").get("profile")=="fresh-image-diagnostic" else "k6-summary.json"))["metrics"]
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


def progress_services(d):
    config=document(d/"frozen.compose.json")
    services=sorted(name for name,spec in config["services"].items() if isinstance(spec.get("command"),list) and spec["command"][-1:]==["evaluator"])
    evaluator_progress.need(1<=len(services)<=evaluator_progress.POLICY['maxInstances'],"M7_EVALUATOR_PROGRESS_INSTANCE_BOUND")
    return services


def progress_fetch(d,service,ids,queries,budget):
    prefix="const M7_PROGRESS_IDS="+json.dumps(ids)+";const M7_PROGRESS_QUERY_BUDGET="+str(queries)+";const M7_PROGRESS_BYTE_BUDGET="+str(budget)+";\n"
    code=prefix+(HERE/"evaluator-progress.cjs").read_text()
    try:return compose(d,"exec","-T",service,"node","-",input=code.encode(),timeout=20)
    except Exception:raise evaluator_progress.Refused("M7_EVALUATOR_PROGRESS_UNAVAILABLE")


def progress_attribution(m):
    return {"pair":m["pair"],"imageId":m["imageId"],"instrument":m["instrument"]["sha256"],"profileSelection":m["profileSelection"]["sha256"],"tenants":m["tenants"],"replicas":m["replicas"],"profile":m["profile"],"hostIdentity":m["hostIdentity"]}


def write_progress(out,value,m):
    before=time.monotonic();cpu=time.process_time()
    packed={**(evaluator_idle.pack(value) if value.get("policy")==evaluator_idle.POLICY else evaluator_progress.pack(value)),"attribution":{"pair":m["pair"],"imageId":m["imageId"],"instrument":m["instrument"]["sha256"],"profileSelection":m["profileSelection"]["sha256"],"tenants":m["tenants"],"replicas":m["replicas"],"profile":m["profile"],"hostIdentity":m["hostIdentity"]}};raw=json.dumps(packed,separators=(',',':')).encode()+b'\n'
    file=out/'evaluator-progress.json';file.write_bytes(raw);file.chmod(0o600)
    compressed=out/'evaluator-progress.json.gz';compressed.write_bytes(gzip.compress(raw,mtime=0));compressed.chmod(0o600)
    write(out/'evaluator-progress-publication.json',{'wallSeconds':time.monotonic()-before,'processCpuSeconds':time.process_time()-cpu,'rawBytes':len(raw),'gzipBytes':compressed.stat().st_size,'scope':'serialization, gzip and primary-file writes; sidecar publication excluded'})


def progress_summary(out):
    value=document(out/'evaluator-progress.json');result={k:v for k,v in value.items() if k not in ('kind','columns','rounds','attribution')}
    return {**result,'rawSha256':digest(out/'evaluator-progress.json'),'gzipSha256':digest(out/'evaluator-progress.json.gz')}


def observe_progress(d,m,out,phase):
    ids=sorted(row['id'] for row in document(d/'tenants.private.json'))
    return (evaluator_idle.Observer if phase=='idle' else evaluator_progress.Observer)(progress_services(d),ids,lambda *args:progress_fetch(d,*args),m['cadence'][phase+'Seconds'],phase,lambda value:write_progress(out,value,m))


def readiness(d, m):
    ids=sorted(row['id'] for row in document(d/'tenants.private.json'));services=progress_services(d)
    deadline=time.monotonic()+1200;observations=[];queries=0;bytes_seen=0
    while time.monotonic()<deadline and len(observations)<evaluator_progress.POLICY['readinessMaxRounds']:
        value=None
        try:
            value=evaluator_progress.round_view(services,ids,lambda *args:progress_fetch(d,*args),warming=True)
            queries+=value['queries'];bytes_seen+=value['bytes']
            evaluator_progress.need(queries<=evaluator_progress.POLICY['readinessMaxQueries'] and bytes_seen<=evaluator_progress.POLICY['readinessMaxBytes'],'M7_EVALUATOR_PROGRESS_READINESS_BUDGET')
            evaluator_progress.need(all(row['completedAcquisitions']>0 for row in value['owners'].values()),'M7_EVALUATOR_PROGRESS_WARMING')
            evaluator_progress.need(all(row['failedCompletions']==0 for row in value['owners'].values()),'M7_EVALUATOR_PROGRESS_ERROR','FAIL')
            observations.append({'verdict':'PASS','queries':value['queries'],'bytes':value['bytes'],'wallSeconds':value['wallSeconds']})
            write(d/'runtime-readiness.json',{'verdict':'PASS','policy':evaluator_progress.POLICY,'observations':observations,'meaning':'completed fresh-window acquisitions; legacy cycles alone are insufficient'})
            return
        except evaluator_progress.Refused as error:
            cost=getattr(error,'collection',{})
            if value is None:queries+=cost.get('queries',0);bytes_seen+=cost.get('bytes',0)
            else:cost={k:value[k] for k in ('queries','bytes','wallSeconds')}
            observations.append({'verdict':error.verdict,'code':str(error),'collection':cost})
            if queries>evaluator_progress.POLICY['readinessMaxQueries'] or bytes_seen>evaluator_progress.POLICY['readinessMaxBytes']:
                error=evaluator_progress.Refused('M7_EVALUATOR_PROGRESS_READINESS_BUDGET')
            write(d/'runtime-readiness.json',{'verdict':error.verdict,'policy':evaluator_progress.POLICY,'observations':observations})
            if error.verdict=='FAIL' or str(error) not in ('M7_EVALUATOR_PROGRESS_WARMING','M7_EVALUATOR_PROGRESS_ERROR','M7_EVALUATOR_PROGRESS_GATE','M7_EVALUATOR_PROGRESS_COVERAGE'):raise
        time.sleep(15)
    raise evaluator_progress.Refused('M7_RUNTIME_NOT_READY')


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
    require(m.get("profile")!="fresh-image-diagnostic","M7_DIAGNOSTIC_CANNOT_RUN_CAPACITY")
    frozen(m,"run");quiet(d,m,"run-before",check_load=False);verify(d,m);image(m)
    require((d / "deploy-before-host.json").exists(), "M7_DEPLOY_QUIET_RECORD_REQUIRED")
    verify_generator(d,m)
    readiness(d, m)
    k6_id = json.loads(command(["docker", "image", "inspect", k6_image]))[0]["Id"]
    write(d / "loadgen-image.json", {"k6": k6_id, "generator": m["generator"]})
    # Sparse once-per-phase cgroups/PG snapshots plus a sampler-disabled idle
    # window make collection overhead observable independently of tenant work.
    out = d / "idle-disabled";out.mkdir()
    psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before");time.sleep(60);phase_snapshot(d, out, "after")
    for name, seconds in (("idle", m["cadence"]["idleSeconds"]),):
        out = d / name;out.mkdir();quiet(d, m, name + "-before", check_load=False)
        psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before")
        with sampling(d, out), observe_progress(d,m,out,'idle') as idle_progress:time.sleep(seconds)
        phase_snapshot(d, out, "after")
    out = d / "load";out.mkdir()
    runid = "m7-" + m["owner"][:12];(out / "runid").write_text(runid)
    spec = m["project"] + "|" + str(d / "env") + "|" + str(d / "frozen.compose.json")
    probe_env = runtime_env({"NODE_PATH": str(d / "dependencies/node_modules"), "M7_RESTART_ROLES": json.dumps(m["restartRoles"]), "M7_EVALUATOR_SERVICES": json.dumps(progress_services(d)), "M7_PROGRESS_PYTHON": sys.executable, "M7_PROGRESS_ATTRIBUTION":json.dumps(progress_attribution(m)), "STOCK_MS": "300000", "RECOVERY_MS": "120000"})
    psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before-prime")
    probe_log = (out / "probe.log").open("wb")
    with sampling(d, out):
        probe_process = subprocess.Popen([m["generator"]["tools"]["node"]["path"], str(d / "probe.js"), "--base", "http://127.0.0.1:" + str(m["port"]), "--tenants", str(d / "tenants.private.json"), "--compose", spec,
            "--runid", runid, "--per", "2", "--open", "5", "--window", str(m["cadence"]["loadSeconds"]), "--probeEvery", "3000", "--restart", "1", "--evalTimeout", "900", "--out", str(out / "probe.json"), "--signal", str(out / ".window")], env=probe_env, stdout=probe_log, stderr=subprocess.STDOUT)
        job_record(out/"probe-job.json",probe_process,m["owner"])
        try:
            deadline = time.monotonic() + 600
            while not (out / ".window").exists():
                require(probe_process.poll() is None and time.monotonic() < deadline, "M7_PROBE_NOT_PRIMED")
                time.sleep(1)
            quiet(d, m, "load-before", check_load=False)
            phase_snapshot(d, out, "after-prime")
            psql(d, "SELECT pg_stat_statements_reset();");phase_snapshot(d, out, "before")
            monitor = loadgen_process(d, probe_process);monitor.__enter__()
            with observe_progress(d,m,out,'load') as load_progress, (out / "k6.log").open("wb") as output:
                command(["docker", "run", "--rm", "--name", m["project"] + "-k6", "--label", OWNER + "=" + m["owner"], "--label", "com.docker.compose.project=" + m["project"], "--label", "com.docker.compose.service=k6",
                    "--network", "host", "-u", str(os.getuid()) + ":" + str(os.getgid()), "-v", str(d / "k6") + ":/scripts:ro", "-v", str(out) + ":/out", "-v", str(d / "tenants.private.json") + ":/tenants.private.json:ro",
                    "-e", "BASE_URL=http://127.0.0.1:" + str(m["port"]), "-e", "TENANTS_FILE=/tenants.private.json", "-e", "RUN_ID=" + runid,
                    "-e", "SETTINGS_FINGERPRINT=" + m["settingsFingerprint"]["sha256"],
                    "-e", "RUN_START=" + str(int(time.time()*1000)), "-e", "DURATION=" + str(m["cadence"]["loadSeconds"]), "-e", "ACCEL=1", "-e", "HOT_FACTOR=10",
                    "-e", "SHAPES=w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status", k6_id, "run", "--quiet", "--summary-export", "/out/k6-summary.json", "/scripts/workload.js"], file=output, timeout=m["cadence"]["loadSeconds"]+600)
            phase_snapshot(d, out, "after")
            (out / ".restart").touch()
            require(probe_process.wait(timeout=1500) == 0, "M7_PROBE_FAILED")
        finally:
            stop_job(out/"probe-job.json",m["owner"])
            probe_process.wait(timeout=10)
            if "monitor" in locals():monitor.__exit__(None,None,None)
            probe_log.close()
    phase_snapshot(d, out, "after-reconnect")
    result = count_oracle(d)
    control(d, m)
    host = inventory(m["owner"]);write(d / "run-after-host.json", host)
    result_probe = document(out / "probe.json")
    fingerprint_result=profile_provenance.fingerprint_check(document(out/"k6-summary.json")["metrics"])
    correctness = [result["verdict"] == "GREEN", result["uncertain"] == 0, not any(not r["owned"] for r in host["containers"]),
                   result_probe["prime"]["primed"] == 2*m["tenants"], result_probe["window"]["deliveredFrames"] == result_probe["window"]["expectedFrames"],
                   result_probe["restart"]["stockRecovered"] == 2*m["tenants"], result_probe["restart"]["runtimeAcquisitionObservation"].get("verdict") == "PASS" and result_probe["restart"]["runtimeAcquisitionObservation"]["missing"] == 0,
                   metric(document(out / "k6-summary.json")["metrics"], "writes_refused") == 0,
                   metric(document(out / "k6-summary.json")["metrics"], "http_req_failed", "rate") == 0,
                   metric(document(out / "k6-summary.json")["metrics"], "dropped_iterations") == 0,
                   result_probe["window"]["writes"]["failed"] == 0, fingerprint_result["verdict"]=="PASS", idle_progress.result["verdict"]=="PASS", load_progress.result["verdict"]=="PASS"]
    summary = {"pair": m["pair"], "hostIdentity":m["hostIdentity"], "profile":m["profile"], "instrument": m["instrument"]["sha256"], "tenants": m["tenants"], "replicas": m["replicas"],
               "imageId":m["imageId"], "verdict": "PASS" if all(correctness) else "FAIL", "correctness": correctness, "cadence": m["cadence"],
               "oracle": {key: value for key, value in result.items() if key != "rows"}, "probe": result_probe,
               "profileSelection":m["profileSelection"],"settingsFingerprint":m["settingsFingerprint"],"settingsFingerprintObservation":fingerprint_result,
               "evaluatorProgressCollectionCosts":{**{phase:document(d/phase/"evaluator-progress-publication.json") for phase in ("idle","load")},"recovery":document(out/"evaluator-recovery.private.json.publication.json")},
               "evaluatorProgress":{**{phase:progress_summary(d/phase) for phase in ("idle","load")},"recovery":{**{k:v for k,v in result_probe["restart"]["runtimeAcquisitionObservation"].items() if k not in ("baselineObservation","evidence")},**result_probe["restart"]["runtimeAcquisitionObservation"]["evidence"]}},
               "performanceThresholds": "none invented; raw latency/CPU/RSS/PG metrics are measurements, not predeclared capacity limits"}
    from reduce import measurements
    summary["measurements"] = measurements(d, m)
    require(summary["measurements"]["complete"], "M7_NO_MEASUREMENT")
    write(d / "summary.json", summary)
    metrics = document(out / "k6-summary.json")["metrics"]
    require(metric(metrics,"writes_refused")==0 and metric(metrics,"responses_refused")==0,"M7_FUNCTIONAL_REQUEST_REFUSAL")
    require(fingerprint_result["verdict"]=="PASS","M7_FUNCTIONAL_SETTINGS_FINGERPRINT")
    require(summary["verdict"] == "PASS", "M7_CORRECTNESS_GROWTH_GATE_FAILED")


def diagnostic_observed_code(out):
    try:
        file=out/'diagnostic-observations.json'
        if file.stat().st_size>1048576:return 'M7_DIAGNOSTIC_CLIENT_REFUSED'
        value=document(file);code=value.get('failureCode') if isinstance(value,dict) else None
        if isinstance(code,str) and re.fullmatch(r'M7_DIAGNOSTIC_[A-Z_]{1,64}',code):return code
    except (OSError,ValueError):pass
    return 'M7_DIAGNOSTIC_CLIENT_REFUSED'


def diagnose(d,m):
    require(m.get("profile")=="fresh-image-diagnostic","M7_DIAGNOSTIC_PROFILE_REQUIRED")
    scope=frozen(m,"diagnose");experiment_host(d,m,"diagnostic-before");verify(d,m);image(m)
    verify_generator(d,m)
    out=d/"load";out.mkdir()
    marker="diagnostic-"+m["owner"][:12];(out/"runid").write_text(marker)
    env=runtime_env({"NODE_PATH":str(d/"dependencies/node_modules")})
    failure=None;client_exit=None
    try:
        with (out/"diagnostic.log").open("wb") as log:
            process=subprocess.Popen([m["generator"]["tools"]["node"]["path"],str(HERE/"diagnostic.cjs"),str(d),str(scope["trafficSeconds"])],env=env,stdout=log,stderr=subprocess.STDOUT)
            job=out/"diagnostic-job.json";job_record(job,process,m["owner"])
            try:
                try:client_exit=process.wait(timeout=scope["trafficSeconds"]+15)
                except subprocess.TimeoutExpired:raise RuntimeError('M7_DIAGNOSTIC_CLIENT_EXIT_TIMEOUT')
                require(client_exit>=0,'M7_DIAGNOSTIC_CLIENT_TERMINATED')
                require(client_exit==0,diagnostic_observed_code(out))
            finally:stop_job(job,m["owner"]);process.wait(timeout=10)
        counted=count_oracle(d)
        require(counted["verdict"]=="GREEN","M7_ORACLE_DIAGNOSTIC_RED")
        oracle_control(d)
        outcome=document(out/"diagnostic-observations.json")
        result={"kind":"m7-joined-fresh-image-diagnostic","profile":m["profile"],"pair":m["pair"],"instrument":m["instrument"]["sha256"],
                "hostIdentity":m["hostIdentity"],"imageId":m["imageId"],"tenants":m["tenants"],"replicas":m["replicas"],"verdict":"PASS",
                "profileSelection":m["profileSelection"],"settingsFingerprintObservation":"UNMEASURED; diagnostic is not k6 capacity",
                "checks":outcome["checks"],"acceptedWrites":outcome["acceptedWrites"],"dataHttpRequests":outcome["dataHttpRequests"],**{key:outcome[key] for key in ("httpAccountingVersion","criterionHttpRequests","physicalHttpRequests","warmProbeHttpRequests","trailRecords","trailBytes")},"oracle":counted["verdict"],"oracleControl":document(out/"oracle-control.json"),
                "fullAcceptance":"NOT_RUN","capacity":"NO-MEASUREMENT","trafficDeadlineSeconds":scope["trafficSeconds"]}
        diagnostic_check(result);write(d/"diagnostic.json",result)
        print("M7_DIAGNOSTIC_PASS_ONLY")
    except Exception as error:
        failure=str(error) if str(error).startswith("M7_") else "M7_DIAGNOSTIC_REFUSED"
        write(d/"diagnostic.json",{"kind":"m7-joined-fresh-image-diagnostic","pair":m["pair"],"instrument":m["instrument"]["sha256"],"imageId":m["imageId"],"hostIdentity":m["hostIdentity"],"verdict":"FAIL","error":failure,"clientExitCode":client_exit,"observedFailureCode":diagnostic_observed_code(out),"requestTrail":"load/diagnostic-http.json" if (out/"diagnostic-http.json").exists() else None,"fullAcceptance":"NOT_RUN","capacity":"NO-MEASUREMENT"})
        raise


def down(d, m):
    for file in list(d.glob("*/sampler-job.json"))+list(d.glob("*/probe-job.json"))+list(d.glob("*/diagnostic-job.json")):stop_job(file,m["owner"])
    assert_owned(m)
    if m.get("prepared"):
        verify(d, m)
        config=document(d/"frozen.compose.json")
        try:captured=profile_provenance.capture_logs(d/"role-logs",config,lambda role:["docker","compose","-p",m["project"],"--env-file",str(d/"env"),"-f",str(d/"frozen.compose.json"),"logs","--no-color","--no-log-prefix","--tail","1000",role])
        except Exception:captured={"version":1,"scope":"PRIVATE","error":"capture-failed","complete":False}
        write(d/"role-logs/manifest.json",captured)
        compose(d, "--profile", "ops", "down", "--volumes", "--remove-orphans", timeout=120)
        for row in resources(m):
            owned(row,m["owner"]);command(["docker","rm","--force","--volumes",row["Id"]])
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
    for name in ("directory", "core-repo", "core-commit", "deploy-repo", "deploy-commit", "image"):prep.add_argument("--"+name, required=True)
    prep.add_argument("--freeze","--receipt",dest="freeze",required=True)
    prep.add_argument("--diagnostics",choices=("off","on"),default="off")
    prep.add_argument("--diagnostics-interval-ms",type=int,default=5000)
    prep.add_argument("--profile",choices=tuple(CADENCE),default="capacity")
    prep.add_argument("--tenants", type=int, required=True);prep.add_argument("--replicas", type=int, choices=REPLICAS, required=True);prep.add_argument("--quiet-load", type=float, default=3)
    for cmd in ("verify", "build", "deploy", "run", "diagnose", "control", "down", "host-identity"):
        own = sub.add_parser(cmd);own.add_argument("directory")
        if cmd == "run":own.add_argument("--k6-image", required=True)
    check = sub.add_parser("check-campaign");check.add_argument("summary")
    check = sub.add_parser("check-pilot");check.add_argument("summary")
    check = sub.add_parser("check-diagnostic");check.add_argument("summary")
    sub.add_parser("manifest")
    sub.add_parser("capabilities")
    return p


def main():
    args = parser().parse_args()
    if args.command == "capabilities":return print(json.dumps(document(HERE/"capabilities.json"),sort_keys=True))
    if args.command == "manifest":return print(json.dumps(instrument(),indent=2))
    if args.command == "prepare":return prepare(args)
    if args.command == "check-campaign":campaign_check(document(args.summary));return print("M7_CAMPAIGN_COMPLETE")
    if args.command == "check-pilot":pilot_check(document(args.summary));return print("M7_REMOTE_PILOT_COMPLETE")
    if args.command == "check-diagnostic":diagnostic_check(document(args.summary));return print("M7_DIAGNOSTIC_PASS_ONLY")
    d, m = load(args.directory)
    if args.command == "host-identity":
        observed=inventory(m["owner"]);write(d/"host-identity-inventory.json",observed)
        require(host_identity(observed)==m["hostIdentity"],"M7_HOST_IDENTITY_CHANGED")
        return print(json.dumps({"hostIdentity":m["hostIdentity"],"pair":m["pair"],"instrument":m["instrument"]["sha256"]}))
    if args.command == "verify":verify(d, m);image(m);print("M7_PAIR_AND_INSTRUMENT_PINNED")
    elif args.command == "build":
        frozen(m,"build");experiment_host(d,m,"build-before");verify(d,m)
        overlay = d / "core/deploy/multitenant"
        shutil.copyfile(d / "env", overlay / ".env")
        try:command(["node", overlay / "build.js"], cwd=overlay, timeout=1800)
        finally:(overlay / ".env").unlink(missing_ok=True)
    elif args.command == "deploy":deploy(d, m)
    elif args.command == "run":run(d,m,args.k6_image)
    elif args.command == "diagnose":diagnose(d,m)
    elif args.command == "control":control(d, m)
    elif args.command == "down":down(d, m)

if __name__ == "__main__":
    try:main()
    except Exception as error:
        message = str(error)
        print(message if re.fullmatch(r"M7_[A-Z_]+(?::[a-zA-Z0-9_.-]+)?", message) else "M7_ADAPTER_REFUSED", file=sys.stderr)
        sys.exit(1)
