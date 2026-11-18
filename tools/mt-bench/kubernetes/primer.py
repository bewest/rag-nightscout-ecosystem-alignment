#!/usr/bin/env python3
"""Run the source-owned primer in the commissioned waiting Job and privately export DATA custody."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import adapter as k
from contract import tenant_projection


def require_roster(d, c, baseline):
    output = d / 'primer'
    path = output / 'tenants.json'
    k.need(c['primerOutput'] == str(output) and c['tenantsFile'] == str(path) and
           not output.is_symlink() and (output / 'result.json').is_file(), 'PRIMER_RECEIPT_REQUIRED')
    receipt = k.document(output / 'result.json')
    pods = [p for p in baseline['pods'].values() if p['workload'] == 'Job/primer']
    k.need(len(pods) == 1 and receipt.get('verdict') == 'OBSERVED' and
           receipt.get('runSha256') == k.digest(d / 'run.json') and
           receipt.get('namespaceUid') == baseline['namespace']['uid'] and
           receipt.get('jobUid') == baseline['objects']['Job/primer']['uid'] and
           receipt.get('podUid') == pods[0]['uid'] and
           receipt.get('containerId') == pods[0]['containers']['done']['containerID'] and
           receipt.get('sourceResult') == {'state':'synthetic-data-primed', 'tenants':c['tenants']} and
           receipt.get('dataTenants') == c['tenants'] and
           path.is_file() and not path.is_symlink() and receipt.get('rosterSha256') == k.digest(path),
           'PRIMER_ROSTER_CHANGED')


def prime(directory, output, concurrency):
    d, c, objects = k.load(directory)
    k.need('candidate' in c['pins'] and 1 <= concurrency <= 32, 'PRIMER_INPUT')
    k.need(output.is_absolute(), 'NEW_ABSOLUTE_OUTPUT_REQUIRED')
    if 'primerOutput' in c:
        k.need(str(output) == c['primerOutput'] == str(d / 'primer'), 'PRIMER_OUTPUT_CHANGED')
    output.mkdir(mode=0o700, exist_ok=False)
    result = {'verdict': 'UNMEASURED', 'capacityAcceptance': 'NOT_GRANTED'}
    try:
        k.candidate.require(k, d, c)
        client = k.Client(c)
        initial = k.active_baseline(d)
        before = k.observe(c, objects, client, initial)
        for role in c['roles']:
            k.selected_pod(c, before, role)
        waiting = [p for p in before['pods'].values() if p['workload'] == 'Job/primer' and p['containers']['done']['ready']]
        k.need(len(waiting) == 1, 'PRIMER_WAIT_REQUIRED')
        pod = waiting[0]
        target = pod['name']
        result.update(podUid=pod['uid'], containerId=pod['containers']['done']['containerID'],
                      namespaceUid=before['namespace']['uid'], jobUid=before['objects']['Job/primer']['uid'])
        policy = k.document(d/'policy.json')
        k.need(policy.get('verdict') == 'PASS' and policy.get('pins') == c['pins'] and
               policy.get('namespaceUid') == result['namespaceUid'] and
               policy.get('adminServiceUid') == before['objects']['Service/admin']['uid'] and
               [s.get('outcome') for s in policy['observations']] == ['connected', 'timeout', 'connected'] and
               all(s.get('podUid') == pod['uid'] and s.get('containerId') == result['containerId']
                   for s in policy['observations'][::2]), 'PRIMER_POLICY_CHANGED')
        def private_file(name):
            return client.call(['exec', target, '-c', 'done', '--', 'cat', '/run/ns-primer/'+name], read=False)
        proof = private_file('verified.json')
        k.need(json.loads(proof) == k.document(d/'candidate-verification.json')['proof'], 'PRIMER_PROOF_CHANGED')
        contract = objects['ConfigMap/provision-scripts']['data']['source-contract.json'].encode()
        job = client.get('Job', 'primer')
        k.need(job['metadata']['uid'] == result['jobUid'] and job['status'].get('active') == 1 and
               not any(row.get('status') == 'True' and row.get('type') in ('Failed','Complete')
                       for row in job['status'].get('conditions', [])), 'PRIMER_JOB_INACTIVE')
        cutoff = min(k.timestamp(c['deadlines']['workUntil']),
                     k.timestamp(job['status']['startTime']) + job['spec']['activeDeadlineSeconds'])
        args = [c['namespace'], c['runId'], hashlib.sha256(contract).hexdigest(),
                hashlib.sha256(proof).hexdigest(), str(int(cutoff*1000)), str(c['tenants']), str(concurrency)]
        result['cutoffEpochMs'] = int(cutoff*1000)
        remaining = cutoff - time.time()
        k.need(remaining > 0, 'PRIMER_DEADLINE', 'UNMEASURED')
        # The ordinary observation client bounds short reads to 15 seconds.
        # This actor has its own in-container hard stop at the same absolute cutoff.
        command = [c['kubectl'], '--context', c['context'], '--namespace', c['namespace'],
                   '--request-timeout='+str(max(1, int(remaining)+1))+'s',
                   'exec', '-i', target, '-c', 'done', '--', 'node', '-', *args]
        try:
            actor = subprocess.run(command, input=Path(__file__).with_suffix('.cjs').read_bytes(), capture_output=True,
                                   check=False, timeout=remaining)
        except (OSError, subprocess.TimeoutExpired):
            raise k.Refused('K8S_PRIMER_EXEC_OUTCOME_UNMEASURED', 'UNMEASURED') from None
        # Only the pinned actor's bounded, classified stdout is evidence. The
        # transport's stderr may contain arbitrary endpoint details.
        try:
            native = json.loads(actor.stdout) if len(actor.stdout) <= 4096 else None
        except ValueError:
            native = None
        k.need(isinstance(native, dict) and set(native) <= {
            'error','errorClass','requestClass','notReady','connectionCause','responseError',
            'state','tenants','remaining'}, 'PRIMER_EXEC_OUTCOME_UNMEASURED', 'UNMEASURED')
        result.update(sourceResult=native, actorExitCode=actor.returncode)
        k.need(actor.returncode == 0 and native == {'state': 'synthetic-data-primed', 'tenants': c['tenants']},
               'PRIMER_INCOMPLETE', 'UNMEASURED' if native.get('state') == 'synthetic-data-prime-partial' else 'FAIL')
        projected = tenant_projection(json.loads(private_file('tenants.json')), c['tenants'])
        k.observe(c, objects, client, initial)
        k.write(output/'tenants.json', projected)
        result.update(verdict='OBSERVED', dataTenants=len(projected), runSha256=k.digest(d/'run.json'),
                      rosterSha256=k.digest(output/'tenants.json'))
    except k.Refused as error:
        result.update(verdict=error.verdict, code=str(error))
    except RuntimeError as error:
        result['code'] = str(error) if str(error) in {'M7_PRIMER_SHAPE', 'M7_PRIMER_COUNT', 'M7_PRIMER_DATA_TOKEN_REQUIRED', 'M7_PRIMER_DUPLICATE'} else 'K8S_PRIMER_CUSTODY_UNMEASURED'
    except (KeyError, ValueError, OSError, TypeError):
        result['code'] = 'K8S_PRIMER_CUSTODY_UNMEASURED'
    finally:
        k.write(output/'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('commissioning_packet')
    parser.add_argument('new_output', type=Path)
    parser.add_argument('--concurrency', type=int, default=1)
    args = parser.parse_args()
    try:
        status = prime(args.commissioning_packet, args.new_output, args.concurrency)
        print(json.dumps(status))
        sys.exit(0 if status['verdict'] == 'OBSERVED' else 1)
    except (k.Refused, OSError, ValueError, KeyError):
        sys.exit('K8S_PRIMER_ENTRY_REFUSED')
