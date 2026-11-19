"""Original configured driver/CSV through finite native artifact custody.

The optional real binary test uses a synthetic loopback HTTP server and the
cached image's extracted binaries, never a Kubernetes or Docker actor.
"""
import copy
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import threading
import time
import unittest

import native_load as n
import native_files as f
import kube_adapter as k
import workload
import workload_runtime
from test_native_load import control, TENANTS, OPTIONS


def configured():
    c, job = control()
    c['workload'].update(loadSeconds=2, offeredRps=28, driverPlan=dict(version=1,
        observer='scheduling-v1', maxAggregateVUs=56, maxTraceBytes=4*1024**2, maxTraceRows=100000,
        scenarios={shape: dict(preAllocatedVUs=4, maxVUs=8, gracefulStopSeconds=1)
                   for shape in workload_runtime.SHAPES}))
    c['roles']['api'] = {'workload': 'Deployment/api', 'container': 'api'}
    resources = copy.deepcopy(job['spec']['template']['spec']['containers'][0]['resources'])
    contract = {'classification': 'reproduced', 'image': job['spec']['template']['spec']['containers'][0]['image'],
                'shell': '/bin/sh', 'k6': '/usr/bin/k6', 'fileLimitBlockBytes': 512, 'evidenceSha256': '1'*64}
    options = dict(OPTIONS, seconds=30, setup_seconds=5, run_start_ms=int(time.time()*1000),
                   exporter_resources=resources, shell_contract=contract)
    return c, job, options


class NativeFiles(unittest.TestCase):
    def test_real_exporter_hash_acknowledgement_bounds_and_deadline_controls(self):
        script = k.HERE/'native-artifacts.cjs'
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch); payload = b'synthetic-private-csv-bytes'
            (root/'sample.gz').write_bytes(payload); (root/'exit-code').write_text('0\n')
            cfg = dict(seconds=5, runId='synthetic', sourceSha256='1'*64,
                       driverWrapperSha256='2'*64, files={'sample.gz':128})
            (root/'config.json').write_text(json.dumps(cfg))
            env = dict(os.environ, NS_NATIVE_OUTPUT=str(root), NS_NATIVE_EXPORT_CONFIG=str(root/'config.json'))
            hold = subprocess.Popen(['node',script,'hold'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                until = time.monotonic()+3
                while not (root/'artifacts.json').exists() and time.monotonic()<until: time.sleep(.01)
                raw = (root/'artifacts.json').read_bytes()
                def read(*args):
                    return subprocess.run(['node',script,*args],env=env,capture_output=True,timeout=3)
                self.assertEqual(read('read','sample.gz').stdout,payload)
                (root/'sample.gz').write_bytes(b'X'*len(payload))
                failed = read('read','sample.gz')
                self.assertEqual(failed.returncode,78); self.assertEqual(failed.stdout,b'')
                self.assertIn(b'ARTIFACT_CHANGED',failed.stderr)
                (root/'sample.gz').write_bytes(b'X'*129)
                oversized = read('read','sample.gz')
                self.assertEqual(oversized.returncode,78); self.assertEqual(oversized.stdout,b'')
                self.assertIn(b'ARTIFACT_BOUND',oversized.stderr)
                (root/'sample.gz').write_bytes(payload)
                self.assertEqual(read('read','sample.gz').stdout,payload)
                self.assertEqual(read('ack','0'*64).returncode,78)
                self.assertIsNone(hold.poll())
                self.assertEqual(read('ack',n.sha(raw)).returncode,0)
                self.assertEqual(hold.wait(timeout=3),0)
            finally:
                if hold.poll() is None: hold.terminate(); hold.wait(timeout=3)
                hold.stderr.close()
            (root/'artifacts.json').unlink(); (root/'exit-code').unlink(); (root/'exported').unlink()
            cfg['seconds'] = 1; (root/'config.json').write_text(json.dumps(cfg))
            expired = subprocess.run(['node',script,'hold'],env=env,capture_output=True,timeout=3)
            self.assertEqual(expired.returncode,78)
            self.assertFalse((root/'artifacts.json').exists())

    @unittest.skipUnless(os.environ.get('NS_NATIVE_IMAGE_BUSYBOX') and os.environ.get('NS_NATIVE_IMAGE_LOADER'),
                         'selected image shell required')
    def test_selected_image_shell_enforces_the_measured_file_limit(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch)/'bounded'
            code = 'import os; f=os.open('+repr(str(target))+',os.O_CREAT|os.O_WRONLY,0o600);os.write(f,b"x"*4096);os.write(f,b"x"*4096)'
            result = subprocess.run([os.environ['NS_NATIVE_IMAGE_LOADER'],os.environ['NS_NATIVE_IMAGE_BUSYBOX'],
                                     'sh','-c','ulimit -f 3; /usr/bin/python3 -c '+shlex.quote(code)],
                                    capture_output=True,timeout=3)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(target.stat().st_size,1536)
    def test_exact_wrapper_csv_bound_and_finite_tokenless_exporter(self):
        c, job, options = configured()
        rendered, secret, receipt = n.package(c, job, b'// source control\n', TENANTS, **options)
        pod = rendered['spec']['template']['spec']; main, exporter = pod['containers']
        self.assertEqual(secret['stringData']['k6-vu-driver.js'], (k.M7/'k6-vu-driver.js').read_text())
        self.assertEqual(secret['stringData']['workload.js'], '// source control\n')
        self.assertIn('--out csv=/out/k6-scheduling.csv.gz', main['command'][2])
        self.assertIn('ulimit -f 8192', main['command'][2])
        self.assertEqual(receipt['fileLimitBytes'], 4*1024**2)
        self.assertEqual(receipt['captureMode'], 'owned-exec-files')
        self.assertEqual(exporter['image'], c['pins']['appImage'])
        self.assertEqual([v['name'] for v in exporter['volumeMounts']], ['inputs', 'artifacts'])
        self.assertNotIn('env', exporter)
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertNotIn('ttlSecondsAfterFinished', rendered['spec'])
        self.assertEqual(receipt['outcomeGate'], 'UNMEASURED')

    def test_missing_shell_or_resource_measurement_refuses_before_actor_creation(self):
        c, job, options = configured()
        for key, bad, code in [('shell_contract', None, 'SHELL_CONTRACT_REQUIRED'),
                               ('exporter_resources', {}, 'UNBUDGETED_CONTAINER')]:
            changed = dict(options, **{key: bad})
            with self.assertRaisesRegex(k.Refused, code):
                n.package(c, job, b'// source control\n', TENANTS, **changed)
            n.package(c, job, b'// source control\n', TENANTS, **options)

    @unittest.skipUnless(os.environ.get('NS_NATIVE_K6_IMAGE_BINARY') and os.environ.get('NS_NATIVE_IMAGE_BUSYBOX')
                         and os.environ.get('NS_NATIVE_IMAGE_LOADER'), 'selected image binaries required')
    def test_real_seven_shape_scheduling_wrapper_raw_csv_and_existing_reducer(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                body = {'token': 'synthetic-jwt'} if '/authorization/request/' in self.path else {'settings': {}} if '/status' in self.path else []
                raw = json.dumps(body).encode(); self.send_response(200)
                self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                raw = b'{"identifier":"synthetic"}'; self.send_response(200)
                self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        c, job, options = configured()
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch); inputs = root/'inputs'; inputs.mkdir(); output = root/'native'; output.mkdir()
            stage = root/'load'; stage.mkdir()
            workload.generate(k.ROOT, root/'workload.js')
            script = (root/'workload.js').read_bytes()
            env = dict(os.environ, NS_NATIVE_OUTPUT=str(output), NS_NATIVE_EXPORT_CONFIG=str(inputs/'export.json'))
            exporter_script = k.HERE/'native-artifacts.cjs'
            class Kube:
                def __init__(self): self.created = []; self.k6 = self.exporter = None; self.acked = False
                def call(self, args, **kw):
                    if args[0] == 'create':
                        value = json.loads(kw['data']); self.created.append(value)
                        if value['kind'] == 'Secret':
                            for name, data in value['stringData'].items(): (inputs/name).write_text(data)
                        else:
                            main = value['spec']['template']['spec']['containers'][0]
                            selected = {row['name']:row['value'] for row in main['env']}
                            selected.update(BASE_URL='http://127.0.0.1:'+str(server.server_port),
                                            TENANTS_FILE=str(inputs/'tenants.json'))
                            command = main['command'][2].replace('/usr/bin/k6', os.environ['NS_NATIVE_K6_IMAGE_BINARY'])
                            command = command.replace('/out/', str(output)+'/').replace('/inputs/', str(inputs)+'/')
                            # Disable the local REST listener; the fixture only needs its loopback HTTP server.
                            command = command.replace('--address=127.0.0.1:0', '--address=')
                            self.k6 = subprocess.Popen([os.environ['NS_NATIVE_IMAGE_LOADER'], os.environ['NS_NATIVE_IMAGE_BUSYBOX'],
                                                        'sh', '-c', command], env=dict(env, **selected))
                            self.exporter = subprocess.Popen(['node', exporter_script, 'hold'], env=env,
                                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        value = copy.deepcopy(value); value['metadata']['uid'] = 'owned-job'
                        return json.dumps(value)
                    if args[0] == 'exec':
                        mode = args[args.index('--')+3:]
                        result = subprocess.run(['node', exporter_script, *mode], env=env,
                                                capture_output=True, timeout=kw.get('timeout', 10))
                        if result.returncode: raise RuntimeError(result.stderr.decode())
                        if mode[0] == 'ack': self.acked = True
                        return result.stdout
                    if args[0] == 'wait':
                        self.exporter.wait(timeout=kw['timeout']); self.k6.wait(timeout=kw['timeout']); return ''
                    raise AssertionError(args)
                def json(self, args, **kw):
                    if args[:2] == ['get', 'namespace']:
                        return {'metadata': {'name':c['namespace'], 'uid':'owned-ns',
                                             'labels':{c['ownerLabel']:c['runId']}}}
                    actual = copy.deepcopy(self.created[-1]); actual['metadata']['uid'] = 'owned-job'
                    rc = self.k6.poll() if self.k6 else None
                    done = self.exporter.poll() if self.exporter else None
                    if done == 0 and rc == 0:
                        actual['status'] = {'succeeded':1,'conditions':[{'type':'Complete','status':'True',
                                                                     'lastTransitionTime':'2026-11-19T00:00:00Z'}]}
                    if args[:2] == ['get', 'job']: return actual
                    statuses = []
                    for name, result in [('k6',rc),('artifact-exporter',done)]:
                        statuses.append({'name':name,'restartCount':0,'containerID':'containerd://'+name,
                                         'imageID':'containerd://sha256:'+'9'*64,
                                         'state':{'running':{}} if result is None else {'terminated':{'exitCode':result}}})
                    pod = {'kind':'Pod','metadata':{'name':'k6-owned','namespace':c['namespace'],'uid':'owned-pod',
                        'labels':{c['ownerLabel']:c['runId']},'ownerReferences':[
                            {'kind':'Job','name':'k6','uid':'owned-job','controller':True}]},
                        'spec':copy.deepcopy(actual['spec']['template']['spec']),
                        'status':{'phase':'Succeeded' if done == 0 and rc == 0 else 'Running','containerStatuses':statuses}}
                    return {'items':[pod]} if args[:2] == ['get','pods'] else pod
                def close(self):
                    for process in (self.k6,self.exporter):
                        if process and process.poll() is None: process.terminate(); process.wait(timeout=5)
                        if process:
                            for stream in (process.stdout, process.stderr):
                                if stream: stream.close()
            kube = Kube()
            try:
                try:
                    receipt = n.run(kube,c,job,script,TENANTS,stage,**options)
                except Exception:
                    if kube.exporter and kube.exporter.poll() is not None:
                        print('EXPORTER_CONTROL', kube.exporter.stderr.read().decode())
                    if (output/'k6.log').is_file(): print('K6_CONTROL', (output/'k6.log').read_text()[-1600:])
                    raise
                self.assertTrue(kube.acked)
                self.assertEqual(receipt['capture'],'CAPTURED')
                self.assertEqual((stage/'k6-scheduling.csv.gz').read_bytes(),(output/'k6-scheduling.csv.gz').read_bytes())
                self.assertTrue(gzip.decompress((stage/'k6-scheduling.csv.gz').read_bytes()).startswith(b'metric_name,'))
                accounting = k.document(stage/'driver-accounting.json')
                self.assertEqual(accounting['offeredWorkVerdict'],'PASS')
                self.assertEqual(accounting['httpVerdict'],'PASS')
                self.assertEqual(len(accounting['shards'][0]['byScenario']),7)
                # The existing reducer sees the bounded original CSV. Truncation
                # cannot become a summary-only pass; restore the same bytes.
                import driver_vu_diagnostic as driver
                raw = (stage/'k6-scheduling.csv.gz').read_bytes()
                (stage/'k6-scheduling.csv.gz').write_bytes(raw[:20])
                with self.assertRaises((OSError, EOFError, RuntimeError)):
                    driver.retain(root, receipt['driverManifest'])
                (stage/'k6-scheduling.csv.gz').write_bytes(raw)
                self.assertEqual(driver.retain(root, receipt['driverManifest'])['offeredWorkVerdict'],'PASS')
            finally:
                kube.close()


if __name__ == '__main__': unittest.main()
