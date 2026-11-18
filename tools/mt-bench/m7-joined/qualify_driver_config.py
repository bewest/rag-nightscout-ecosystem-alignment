#!/usr/bin/env python3
"""Bounded native k6 qualification on an owned synthetic loopback HTTP target.

No application, database, source receipt, provider or capacity acceptance. Uses
workload.generate and discovery.k6_command, including the actual shard launcher.
"""
import argparse
from collections import Counter
import concurrent.futures
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from types import SimpleNamespace
import uuid

import discovery
import driver_shards
import driver_vu_diagnostic as driver
import workload
from contract import require

ROOT = Path(__file__).resolve().parents[3]


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def synthetic_status():
    s = {'units': 'mg/dl', 'enable': [], 'thresholds': dict.fromkeys(
        ('bgHigh','bgTargetTop','bgTargetBottom','bgLow'), 1)}
    for key in ('timeFormat','dayStart','dayEnd','alarmTimeagoWarnMins','alarmTimeagoUrgentMins','focusHours','heartbeat'):
        s[key] = 1
    for key in ('nightMode','showSeconds','editMode','alarmUrgentHigh','alarmHigh','alarmLow','alarmUrgentLow','alarmTimeagoWarn','alarmTimeagoUrgent','alarmPumpBatteryLow','showClockDelta','showClockLastTime','authenticationPromptOnLoad'):
        s[key] = False
    for key in ('alarmUrgentHighMins','alarmHighMins','alarmLowMins','alarmUrgentLowMins','alarmUrgentMins','alarmWarnMins'):
        s[key] = []
    return {'status':'ok', 'settings':s, 'extendedSettings':{'devicestatus':{'advanced':False, 'days':1}}}


class Target(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, delay):
        super().__init__(('127.0.0.1', 0), Handler)
        self.delay = delay
        self.counts = Counter()
        self.lock = threading.Lock()
        self.status = synthetic_status()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *_): pass
    def do_POST(self): self.respond()
    def do_GET(self): self.respond()
    def respond(self):
        size = int(self.headers.get('Content-Length', 0))
        require(size <= 65536, 'M7_DRIVER_FIXTURE_BODY_BOUND')
        self.rfile.read(size)
        setup = '/authorization/request/' in self.path
        if not setup and self.server.delay: time.sleep(self.server.delay)
        body = json.dumps({'token':'synthetic-driver-token'} if setup else
                          self.server.status if '/status.json' in self.path else []).encode()
        with self.server.lock: self.server.counts['jwt' if setup else 'ordinary'] += 1
        self.send_response(200); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body))); self.end_headers()
        self.wfile.write(body)


def native_case(out, image, count, rate, seconds, shards=1, observer='scheduling-v1',
                delay=0, vus=2, realistic=False, offset=False, subset=False):
    out.mkdir(mode=0o700); (out/'load').mkdir(); (out/'k6').mkdir()
    shapes = ('r_sgv',) if subset else driver.SHAPES
    cfg = {'version':1, 'observer':observer, 'maxAggregateVUs':len(shapes)*vus*shards,
           'maxTraceBytes':16*1024*1024, 'maxTraceRows':500000,
           'scenarios':{name:{'preAllocatedVUs':vus,'maxVUs':vus,'gracefulStopSeconds':2,
               **({'startTimeSeconds':1,'durationSeconds':seconds-1} if offset and name=='r_status' else {})} for name in shapes}}
    cadence = {'loadSeconds':seconds,'accel':1,'hotFactor':1,'warmupSeconds':1,'idleSeconds':1,
               'driverShards':shards, 'driverVuDiagnostic':'configured-v1'}
    cadence.update({'workloadMix':'realistic-v1','workloadScale':8} if realistic else {'offeredRps':rate})
    cadence['driverPlan'] = driver.configuration(cfg, cadence)
    project = 'nsdriver-' + uuid.uuid4().hex[:12]
    target = Target(delay); thread = threading.Thread(target=target.serve_forever, daemon=True); thread.start()
    m = {'tenants':count,'replicas':2 if shards>1 else 1,'cadence':cadence,
         'runPurpose':'discovery','project':project,'owner':uuid.uuid4().hex,'port':target.server_port,
         'settingsFingerprint':{'sha256':'0'*64},'pair':{},'imageId':'SYNTHETIC_LOOPBACK',
         'instrument':{'scope':'loopback driver bytes only'}}
    tenants = [{'id':'synthetic-%d'%i,'host':'synthetic-%d.invalid'%i,'token':'synthetic-token'} for i in range(count)]
    write(out/'tenants.private.json',tenants)
    workload.generate(ROOT,out/'k6'/'workload.js')
    # Compute exactly the whitelist projection; no product source is involved.
    fp = subprocess.check_output(['node','-e',
        "const p=require(process.argv[1]).projection;const c=require('crypto');console.log(c.createHash('sha256').update(p(JSON.parse(process.argv[2]))).digest('hex'));",
        str(Path(__file__).with_name('fingerprint.cjs')),json.dumps(target.status)],text=True).strip()
    m['settingsFingerprint']['sha256'] = fp
    write(out/'owner.json',m)
    def owned(value): require(value['project']==project and target.server_port==value['port'], 'M7_DRIVER_FIXTURE_OWNERSHIP')
    def bounded(argv): return [*argv[:2],'--cpus','1','--memory','1g','--memory-swap','1g','--pids-limit','128',*(v for v in argv[2:] if v != '--rm')]
    launch = SimpleNamespace(os=os,assert_owned=owned,bounded_k6_argv=bounded,
                             jwt_setup_env=lambda _: 'JWT_SETUP_CONCURRENCY=8',write=write)
    try:
        argv = discovery.k6_command(launch,out,m,image,'synthetic-driver')
        write(out/'command.json',argv)
        before = time.monotonic()
        with (out/'load'/'k6.log').open('wb') as log:
            r = subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=seconds+45)
        state = json.loads(subprocess.check_output(['docker','inspect',project+'-k6']))[0]
        write(out/'container-exit.json', {'returncode':r.returncode, 'state':state['State'],
            'limits':{k:state['HostConfig'][k] for k in ('Memory','MemorySwap','NanoCpus','PidsLimit','Ulimits')}})
        require(r.returncode==0,'M7_DRIVER_FIXTURE_K6_EXIT')
        if shards>1:
            rows = json.loads((out/'load'/'k6-shard-plan.json').read_text())['shards']
            require(driver_shards.collect(out/'load',rows)['merged'],'M7_DRIVER_FIXTURE_SHARDS')
        result = driver.retain(out,m)
        require(result['totals']['issued']==target.counts['ordinary'], 'M7_DRIVER_FIXTURE_INDEPENDENT_HTTP')
        require(sum(v['phases']['jwtSetupRequests'] for v in result['shards'])==target.counts['jwt'],
                'M7_DRIVER_FIXTURE_INDEPENDENT_JWT')
        result['nativeFixture']={'elapsedSeconds':time.monotonic()-before,'independentHttp':dict(target.counts),
            'driverLimit':{'millicpus':1000,'memoryBytes':1024*1024*1024,'pids':128},
            'target':'owned synthetic loopback; no storage, clinical or capacity qualification'}
        write(out/'assessment.json',result)
        return result
    finally:
        # Only this invocation's generated project name; no discovery/global cleanup.
        subprocess.run(['docker','rm','-f',project+'-k6'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        target.shutdown(); target.server_close(); thread.join(2)


def controls(root):
    positive = root/'small'; m = json.loads((positive/'owner.json').read_text())
    records = []
    def red(name, mutate, restore, expected):
        mutate()
        try:
            driver.retain(positive,m)
        except (RuntimeError, FileNotFoundError) as error:
            require(expected in str(error), 'M7_DRIVER_CONTROL_WRONG_FAILURE')
            records.append({'name':name,'broken':'FAIL','symptom':str(error)})
        else: raise RuntimeError('M7_DRIVER_CONTROL_VACUOUS')
        finally: restore()
        require(driver.retain(positive,m)['offeredWorkVerdict']=='PASS','M7_DRIVER_CONTROL_RESTORE')
        records[-1]['restored']='PASS'
    old_rate = m['cadence']['offeredRps']
    red('manifest/actual rate mismatch',lambda:m['cadence'].update(offeredRps=old_rate+5),
        lambda:m['cadence'].update(offeredRps=old_rate),'M7_DRIVER_MANIFEST_PLAN_MISMATCH')
    trace = positive/'load'/'k6-scheduling.csv.gz'; original = trace.read_bytes()
    def mix():
        import csv, io
        lines = list(csv.DictReader(io.StringIO(gzip.decompress(original).decode())))
        changed = 0
        for row in lines:
            if row['metric_name']=='scenario_request_attempts':
                row['timestamp']=str(m['cadence']['loadSeconds']); changed+=1; break
        require(changed==1,'M7_DRIVER_CONTROL_NOT_APPLIED')
        buf = io.StringIO(); writer=csv.DictWriter(buf,fieldnames=list(lines[0]));writer.writeheader();writer.writerows(lines)
        trace.write_bytes(gzip.compress(buf.getvalue().encode()))
    red('ordinary counter moved into setup',mix,lambda:trace.write_bytes(original),'M7_DRIVER_TRACE_PHASE')
    shard = root/'sharded'; sm = json.loads((shard/'owner.json').read_text())
    rc = shard/'load'/'k6-shard-1.rc'; value=rc.read_bytes();rc.unlink()
    try:
        driver.retain(shard,sm)
    except RuntimeError as e:
        require(str(e)=='M7_DRIVER_SHARD_MISSING','M7_DRIVER_CONTROL_WRONG_FAILURE')
        records.append({'name':'lost shard receipt','broken':'FAIL','symptom':str(e)})
    else: raise RuntimeError('M7_DRIVER_CONTROL_VACUOUS')
    finally: rc.write_bytes(value)
    require(driver.retain(shard,sm)['offeredWorkVerdict']=='PASS','M7_DRIVER_CONTROL_RESTORE')
    records[-1]['restored']='PASS'
    return records


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--k6-image',required=True)
    args=p.parse_args();require(re.fullmatch(r'sha256:[a-f0-9]{64}',args.k6_image) is not None,'M7_DRIVER_FIXTURE_IMAGE_PIN')
    root=Path(args.out).resolve();require(not root.exists(),'M7_DRIVER_FIXTURE_OUTPUT_EXISTS');root.mkdir(parents=True,mode=0o700)
    sources = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (Path(__file__),Path(driver.__file__),Path(discovery.__file__),Path(driver_shards.__file__),
         Path(workload.__file__),Path(driver.__file__).with_name(driver.SCRIPT),
         ROOT/'tools/mt-bench/capacity/k6/workload.js')}
    write(root/'driver-sources.json',sources)
    # Independent small cases fit at most 2 CPU / 2GiB driver reservation plus tiny HTTP targets.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(native_case,root/'small',args.k6_image,12,22,4)
        b=pool.submit(native_case,root/'sharded',args.k6_image,36,44,6,2,offset=True)
        small,sharded=a.result(),b.result()
    require(small['offeredWorkVerdict']==sharded['offeredWorkVerdict']=='PASS','M7_DRIVER_FIXTURE_BASELINE')
    realistic=native_case(root/'realistic',args.k6_image,500,None,4,observer='summary-v1',realistic=True)
    require(realistic['offeredWorkVerdict']=='PASS','M7_DRIVER_FIXTURE_REALISTIC')
    before=native_case(root/'delivery-before',args.k6_image,8,20,4,vus=1,subset=True)
    broken=native_case(root/'delivery-under',args.k6_image,8,20,4,vus=1,subset=True,delay=.2)
    restored=native_case(root/'delivery-restored',args.k6_image,8,20,4,vus=1,subset=True)
    require(before['offeredWorkVerdict']==restored['offeredWorkVerdict']=='PASS' and
            broken['offeredWorkVerdict']=='FAIL' and broken['totals']['dropped']>0 and
            broken['httpVerdict']=='PASS','M7_DRIVER_CONTROL_UNDERDELIVERY')
    checks=controls(root)
    checks.append({'name':'bounded slow target under-delivers offered work','before':'PASS','broken':'FAIL',
        'symptom':{'dropped':broken['totals']['dropped'],'issued':broken['totals']['issued'],
                   'completed':broken['totals']['completed'],'httpVerdict':broken['httpVerdict']},'restored':'PASS'})
    files={str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob('*') if path.is_file()}
    write(root/'qualification.json',{'basis':'reproduced','capability':'PASS','k6Image':args.k6_image,
        'cases':{name:json.loads((root/name/'assessment.json').read_text())['totals'] for name in
            ('small','sharded','realistic','delivery-before','delivery-under','delivery-restored')},
        'controls':checks,'files':files,'capacityAcceptance':'NOT_GRANTED','remote':'NOT_RUN / unsupported configured transport'})
    print(json.dumps({'capability':'PASS','controls':checks}))


if __name__=='__main__':main()
