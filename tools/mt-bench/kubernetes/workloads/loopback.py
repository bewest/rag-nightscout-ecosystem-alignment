#!/usr/bin/env python3
"""Run the actual generated workload against an owned tiny HTTP shape fixture.

This is an instrument control, with bounded cached k6 and no product/database.
It is not an alternative benchmark engine or a Kubernetes qualification.
"""
import argparse
import copy
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workloads import profile as profiles
from workloads import reduce as reduction


def shape_coverage(calls):
    expected = {('POST', '/api/v1/entries'), ('POST', '/api/v1/devicestatus'),
                ('POST', '/api/v3/treatments'), ('GET', '/api/v1/entries/sgv.json'),
                ('GET', '/api/v1/devicestatus.json'), ('GET', '/api/v1/treatments.json'),
                ('GET', '/api/v1/status.json')}
    observed = {(c['method'], c['path']) for c in calls if '/authorization/request/' not in c['path']}
    if observed != expected:
        raise ValueError('K8S_LOAD_REQUEST_SHAPE_COVERAGE')
    return {method + ' ' + path: sum(c['method'] == method and c['path'] == path for c in calls)
            for method, path in sorted(expected)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--k6-image', required=True, help='Existing immutable cached image ID; no pull')
    args = parser.parse_args()
    assert re.fullmatch(r'sha256:[a-f0-9]{64}', args.k6_image)
    output = args.output.resolve()
    p = profiles.read(profiles.HERE / 'small.json')
    profiles.dry(p, output)
    info = profiles.read(output / 'dry.json')
    inspect = json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.k6_image]))[0]
    assert inspect['Id'] == args.k6_image
    owner = uuid.uuid4().hex
    name = 'k8s-workload-control-' + owner[:12]
    status = {'status': 'ok', 'settings': {'units': 'mg/dl', 'enable': [],
              'thresholds': dict(bgHigh=260, bgTargetTop=180, bgTargetBottom=80, bgLow=55)},
              'extendedSettings': {'devicestatus': {'advanced': False, 'days': 1}}}
    for key in ('timeFormat', 'dayStart', 'dayEnd', 'alarmTimeagoWarnMins', 'alarmTimeagoUrgentMins', 'focusHours', 'heartbeat'):
        status['settings'][key] = 1
    for key in ('nightMode', 'showSeconds', 'editMode', 'alarmUrgentHigh', 'alarmHigh', 'alarmLow', 'alarmUrgentLow',
                'alarmTimeagoWarn', 'alarmTimeagoUrgent', 'alarmPumpBatteryLow', 'showClockDelta', 'showClockLastTime', 'authenticationPromptOnLoad'):
        status['settings'][key] = False
    for key in ('alarmUrgentHighMins', 'alarmHighMins', 'alarmLowMins', 'alarmUrgentLowMins', 'alarmUrgentMins', 'alarmWarnMins'):
        status['settings'][key] = []
    profiles.write(output / 'status.json', status)
    js = "const f=require(process.argv[1]),s=require(process.argv[2]);process.stdout.write(f.projection(s));"
    # Use the exact source-owned whitelist serialization (including key order).
    projection = subprocess.check_output(['node', '-e', js,
        str(profiles.ROOT / 'tools/mt-bench/m7-joined/fingerprint.cjs'), str(output / 'status.json')])
    fingerprint = hashlib.sha256(projection).hexdigest()
    calls = []
    lock = threading.Lock()

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 64

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass

        def respond(self, body):
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            path = self.path.split('?', 1)[0]
            with lock:
                calls.append({'method': 'GET', 'path': path, 'host': self.headers.get('Host'), 'atMs': time.time() * 1000})
            self.respond({'token': 'synthetic-loopback-jwt'} if '/authorization/request/' in path else status if '/status.json' in path else [])

        def do_POST(self):
            size = int(self.headers['Content-Length'])
            assert 0 < size < 16384
            body = json.loads(self.rfile.read(size))
            path = self.path.split('?', 1)[0]
            with lock:
                calls.append({'method': 'POST', 'path': path, 'host': self.headers.get('Host'), 'body': body,
                              'atMs': time.time() * 1000})
            self.respond([])

    server = Server(('127.0.0.1', 0), Handler)
    listener = threading.Thread(target=server.serve_forever, daemon=True)
    listener.start()
    env = info['environment']
    env.update(BASE_URL='http://127.0.0.1:' + str(server.server_port), TENANTS_FILE='/control/tenants.json',
               SETTINGS_FINGERPRINT=fingerprint, RUN_START=str(int(time.time() * 1000)))
    cmd = ['docker', 'run', '--rm', '--pull=never', '--name', name, '--label', 'k8s.load.control=' + owner,
           '--network', 'host', '--cpus', '0.5', '--memory', '512m', '--memory-swap', '512m',
           '--pids-limit', '128', '-u', f'{os.getuid()}:{os.getgid()}', '-v', str(output) + ':/control']
    for key, value in env.items():
        cmd += ['-e', key + '=' + value]
    cmd += [args.k6_image, 'run', '--quiet', '--summary-export', '/control/k6-summary.json', '/control/workload.js']
    try:
        with (output / 'k6.log').open('xb') as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            try:
                proc.wait(timeout=55)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise
        assert proc.returncode == 0, ('K6_REFUSED', proc.returncode)
        profiles.write(output / 'http-shapes.json', calls)
        metrics = profiles.read(output / 'k6-summary.json')['metrics']
        reduced = reduction.http_accounting.assess(metrics)
        assert reduced['httpVerdict'] == 'PASS' and reduced['offeredWorkVerdict'] == 'PASS', reduced
        ordinary = [c for c in calls if '/authorization/request/' not in c['path']]
        assert reduced['scenario']['attempts'] == len(ordinary)
        coverage = shape_coverage(calls)
        try:
            shape_coverage([c for c in calls if c['path'] != '/api/v3/treatments'])
        except ValueError as error:
            assert str(error) == 'K8S_LOAD_REQUEST_SHAPE_COVERAGE'
        else:
            raise AssertionError('MISSING_WRITE_SHAPE_CONTROL_GREEN')
        assert shape_coverage(calls) == coverage
        nominal = info['model']['nominalScenarioRequests']
        assert nominal <= len(ordinary) <= __import__('math').ceil(nominal) + len(profiles.SHAPES)
        paths = {c['path'] for c in ordinary}
        assert paths == {'/api/v1/entries', '/api/v1/devicestatus', '/api/v3/treatments',
                         '/api/v1/entries/sgv.json', '/api/v1/devicestatus.json', '/api/v1/treatments.json', '/api/v1/status.json'}
        assert len({c['host'] for c in ordinary}) == 2
        posts = [c for c in ordinary if c['method'] == 'POST']
        for c in posts:
            body = c['body']
            if c['path'] == '/api/v3/treatments':
                assert body['eventType'] == 'Temp Basal' and body['enteredBy'] == env['RUN_ID']
            else:
                assert isinstance(body, list) and len(body) == 1 and body[0]['device'] == env['RUN_ID']
                if c['path'].endswith('entries'):
                    assert body[0]['type'] == 'sgv' and isinstance(body[0]['date'], int)
                else:
                    assert len(body[0]['loop']['predicted']['values']) == 72
        broken = copy.deepcopy(metrics)
        broken['dropped_iterations']['count'] = 1
        assert reduction.http_accounting.assess(broken)['offeredWorkVerdict'] == 'FAIL'
        assert reduction.http_accounting.assess(metrics)['offeredWorkVerdict'] == 'PASS'
        result = {'basis': 'reproduced', 'scope': 'actual generated M7 workload, tiny synthetic loopback HTTP fixture only',
                  'http': reduced, 'listenerOrdinaryRequests': len(ordinary), 'writeRequests': len(posts),
                  'configuredSeconds': p['workload']['loadSeconds'], 'model': info['model'],
                  'shapeRequests': coverage,
                  'controls': {'droppedIteration': 'offeredWork FAIL',
                               'missingWriteShape': 'K8S_LOAD_REQUEST_SHAPE_COVERAGE', 'restored': 'PASS'},
                  'k6ImageId': args.k6_image, 'limits': {'cpuMillicpus': 500, 'memoryBytes': 512 * 1024**2},
                  'generator': info['generated'], 'productStorage': 'UNMEASURED',
                  'clinical': 'UNMEASURED', 'clientDelivery': 'UNMEASURED', 'capacityAcceptance': 'NOT_GRANTED'}
        profiles.write(output / 'result.json', result)
        print(json.dumps({k: result[k] for k in ('listenerOrdinaryRequests', 'writeRequests', 'controls', 'capacityAcceptance')}))
    finally:
        server.shutdown()
        server.server_close()
        listener.join(timeout=3)
        ids = subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$'], text=True).split()
        for cid in ids:
            row = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
            assert row['Config']['Labels'].get('k8s.load.control') == owner
            subprocess.run(['docker', 'rm', '-f', cid], check=True, stdout=subprocess.DEVNULL)
        profiles.write(output / 'cleanup.json', {'containerAbsent': not subprocess.check_output(
            ['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$'], text=True).strip(), 'listenerClosed': True})


if __name__ == '__main__':
    main()
