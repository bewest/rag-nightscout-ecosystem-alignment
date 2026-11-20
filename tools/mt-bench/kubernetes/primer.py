#!/usr/bin/env python3
"""Run the source-owned primer in the commissioned waiting Job and privately export DATA custody."""
import argparse
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import kube_adapter as k
from contract import tenant_projection
import commissioning_wal
import primer_storage
import primer_options
from primer_progress import ProgressWindow


STATE_READBACK = '''const fs=require('node:fs'),crypto=require('node:crypto');
const dir='/run/ns-primer',m=fs.statfsSync(dir),config=fs.readFileSync(dir+'/config.json');
const sizes={};
for(const name of ['config.json','expected-verification.json','verified.json',
  'prime.lock','tenants.json','tenants.json.new']){
  try{sizes[name]=fs.statSync(dir+'/'+name).size;}catch(error){if(error.code!=='ENOENT')throw error;}
}
console.log(JSON.stringify({type:m.type,bytes:m.bsize*m.blocks,freeBytes:m.bsize*m.bavail,
  freeInodes:m.ffree,configBytes:config.length,configSha256:crypto.createHash('sha256').update(config).digest('hex'),sizes}));'''


def storage_readback(c, client, target):
    value = json.loads(client.call(['exec',target,'-c','done','--','node','-e',STATE_READBACK],read=False))
    receipt = c['primerStorageReceipt']
    k.need(value.get('type')==0x01021994 and value.get('bytes')==c[primer_storage.FIELD]['stateMiB']*primer_storage.MIB and
           value.get('configBytes')==receipt['configBytes'] and value.get('configSha256')==receipt['configSha256'],
           'PRIMER_STORAGE_READBACK_CHANGED')
    return value


def require_roster(d, c, baseline):
    output = d / 'primer'
    path = output / 'tenants.json'
    k.need(c['primerOutput'] == str(output) and c['tenantsFile'] == str(path) and
           not output.is_symlink() and (output / 'result.json').is_file(), 'PRIMER_RECEIPT_REQUIRED')
    receipt = k.document(output / 'result.json')
    pods = [p for p in baseline['pods'].values() if p['workload'] == 'Job/primer']
    if not pods and baseline.get('completedPrimer'):
        initial = k.document(d/'observation.initial.json')
        pods = [p for p in initial['pods'].values() if p['workload'] == 'Job/primer' and
                p['uid'] == baseline['completedPrimer']['uid']]
    k.need(len(pods) == 1 and receipt.get('verdict') == 'OBSERVED' and
           receipt.get('runSha256') == k.digest(d / 'run.json') and
           receipt.get('namespaceUid') == baseline['namespace']['uid'] and
           receipt.get('jobUid') == baseline['objects']['Job/primer']['uid'] and
           receipt.get('podUid') == pods[0]['uid'] and
           receipt.get('containerId') == pods[0]['containers']['done']['containerID'] and
           receipt.get(primer_options.FIELD) == c.get(primer_options.FIELD) and
           receipt.get('sourceResult') == {'state':'synthetic-tenants-usable', 'tenants':c['tenants']} and
           receipt.get('dataTenants') == c['tenants'] and
           path.is_file() and not path.is_symlink() and receipt.get('rosterSha256') == k.digest(path),
           'PRIMER_ROSTER_CHANGED')
    return pods[0]


async def run_actor(command, cutoff, seconds, total, result, sample=None):
    """Watch the durable count across kubectl, including a silent or wedged exec."""
    window = ProgressWindow(seconds)
    first = True
    result['completedTenants'] = None
    native = None
    slot_sample = None
    sampled_at = None

    def remaining():
        if cutoff <= time.time():
            raise k.Refused('K8S_PRIMER_DEADLINE', 'UNMEASURED')
        stall_left = window.remaining()
        if not stall_left:
            raise k.Refused('K8S_PRIMER_PROGRESS_UNMEASURED' if first else 'K8S_PRIMER_STALLED', 'UNMEASURED')
        return min(stall_left, max(0, cutoff - time.time()))

    with Path(__file__).with_suffix('.cjs').open('rb') as script:
        actor = await asyncio.create_subprocess_exec(*command, stdin=script, stdout=asyncio.subprocess.PIPE,
                                                     stderr=subprocess.DEVNULL, limit=4096)
    try:
        while True:
            timeout = remaining()
            frame = await asyncio.wait_for(actor.stdout.readline(), timeout)
            if not frame:
                break
            value = json.loads(frame)
            k.need(isinstance(value, dict) and native is None, 'PRIMER_EXEC_OUTCOME_UNMEASURED', 'UNMEASURED')
            if set(value) != {'checkpoint'}:
                native = value
                continue
            count = value['checkpoint']
            k.need(type(count) is int and 0 <= count <= total, 'PRIMER_CHECKPOINT_INVALID')
            if first:
                window.completed = count  # existing custody on an explicit retry
                first = False
            else:
                window.observe(count)
            result['completedTenants'] = window.completed
            # Observe WAL in parallel so a slow SQL read cannot hold the
            # progress/timeout loop. The terminal observe() rechecks identities.
            if (sample and count < total and (slot_sample is None or slot_sample.done())
                    and (sampled_at is None or time.monotonic()-sampled_at >= 5)):
                if slot_sample is not None:
                    await slot_sample
                sampled_at = time.monotonic()
                slot_sample = asyncio.create_task(asyncio.to_thread(sample))
        timeout = remaining()
        code = await asyncio.wait_for(actor.wait(), timeout)
        return native, code
    except asyncio.TimeoutError:
        remaining()  # classify the work or stall deadline
        raise k.Refused('K8S_PRIMER_EXEC_OUTCOME_UNMEASURED', 'UNMEASURED') from None
    finally:
        if actor.returncode is None:
            try:
                actor.kill()
            except ProcessLookupError:
                pass
            await actor.communicate()
        if slot_sample is not None:
            await slot_sample


def prime(directory, output, concurrency=None, max_tenants=None):
    d, c, objects = k.load(directory)
    k.need('candidate' in c['pins'], 'PRIMER_INPUT')
    declared=c.get(primer_options.FIELD)
    supplied={key:value for key,value in (('concurrency',concurrency),('maxTenants',max_tenants)) if value is not None}
    if supplied:primer_options.selection(supplied,k.need)
    if declared is None:
        k.need(max_tenants is None and not primer_options.requires_extended(supplied), 'PRIMER_OPTIONS_UNBOUND')
        selected=supplied
    else:
        selected=primer_options.selection(declared,k.need)
        effective={'concurrency':primer_options.DEFAULT_CONCURRENCY, **selected}
        k.need(all(effective.get(key)==value for key,value in supplied.items()), 'PRIMER_OPTIONS_CHANGED')
    k.need(output.is_absolute(), 'NEW_ABSOLUTE_OUTPUT_REQUIRED')
    if 'primerOutput' in c:
        k.need(str(output) == c['primerOutput'] == str(d / 'primer'), 'PRIMER_OUTPUT_CHANGED')
    # Take an OS-released lock for this output. A failed attempt can be retried
    # against the same live fixture and private checkpoints.
    output.mkdir(mode=0o700, exist_ok=True)
    k.need(not output.is_symlink(), 'PRIMER_OUTPUT_CHANGED')
    lock = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise k.Refused('K8S_PRIMER_OUTPUT_IN_USE') from None
        if any(output.iterdir()):
            previous = k.document(output/'result.json')
            k.need(previous.get('verdict') != 'OBSERVED' and previous.get('runSha256') == k.digest(d/'run.json'),
                   'PRIMER_OUTPUT_CHANGED')
        return prime_owned(d, c, objects, output, declared, selected)
    finally:
        os.close(lock)


def prime_owned(d, c, objects, output, declared, selected):
    result = {'verdict': 'UNMEASURED', 'capacityAcceptance': 'NOT_GRANTED', 'runSha256': k.digest(d/'run.json')}
    if declared is not None:
        result[primer_options.FIELD]=selected
    try:
        k.candidate.require(k, d, c)
        client = k.Client(c)
        initial = k.active_baseline(d)
        before = k.observe(c, objects, client, initial)
        for role in c['roles']:
            k.role_pods(c, before, role)
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
        job = client.get('Job', 'primer')
        k.need(job['metadata']['uid'] == result['jobUid'] and job['status'].get('active') == 1 and
               not any(row.get('status') == 'True' and row.get('type') in ('Failed','Complete')
                       for row in job['status'].get('conditions', [])), 'PRIMER_JOB_INACTIVE')
        cutoff = min(k.timestamp(c['deadlines']['workUntil']),
                     k.timestamp(job['status']['startTime']) + job['spec']['activeDeadlineSeconds'])
        seconds = c.get('dataPrimerSeconds', k.workload_inputs.KUBERNETES_STARTUP_DEFAULTS['dataPrimerSeconds'])
        k.need(k.workload_inputs.seconds(seconds), 'DATA_PRIMER_WINDOW')
        result['selectedDataPrimerSeconds'] = seconds
        context = [c['namespace'], c['runId']]
        options = [str(int(cutoff*1000)), str(c['tenants']),
                   str(selected.get('concurrency',primer_options.DEFAULT_CONCURRENCY))]
        proof = private_file('verified.json')
        k.need(json.loads(proof) == k.document(d/'candidate-verification.json')['proof'], 'PRIMER_PROOF_CHANGED')
        contract = objects['ConfigMap/provision-scripts']['data']['source-contract.json'].encode()
        args = [*context, hashlib.sha256(contract).hexdigest(), hashlib.sha256(proof).hexdigest(), *options]
        if 'maxTenants' in selected:args.append(str(selected['maxTenants']))
        result['cutoffEpochMs'] = int(cutoff*1000)
        remaining = cutoff - time.time()
        k.need(remaining > 0, 'PRIMER_DEADLINE', 'UNMEASURED')
        if primer_storage.FIELD in c:
            result['stateVolume'] = {'before':storage_readback(c, client, target)}
            remaining = cutoff - time.time()
            k.need(remaining > 0, 'PRIMER_DEADLINE', 'UNMEASURED')
        # The ordinary observation client bounds short reads to 15 seconds.
        # This actor has its own in-container hard stop at the same absolute cutoff.
        command = [c['kubectl'], '--context', c['context'], '--namespace', c['namespace'],
                   '--request-timeout='+str(max(1, int(remaining)+1))+'s',
                   'exec', '-i', target, '-c', 'done', '--', 'env', 'NS_PRIMER_STALL_SECONDS='+str(seconds), 'node', '-', *args]
        try:
            native, exit_code = asyncio.run(run_actor(command, cutoff, seconds, c['tenants'], result))
        except (OSError, ValueError):
            raise k.Refused('K8S_PRIMER_EXEC_OUTCOME_UNMEASURED', 'UNMEASURED') from None
        k.need(isinstance(native, dict) and set(native) <= {
            'error','errorClass','requestClass','notReady','connectionCause','responseError',
            'state','tenants','remaining'}, 'PRIMER_EXEC_OUTCOME_UNMEASURED', 'UNMEASURED')
        result.update(sourceResult=native, actorExitCode=exit_code)
        if type(native.get('tenants')) is int:
            result['completedTenants'] = native['tenants']
        k.need(native.get('error') != 'PRIMER_STALLED', 'PRIMER_STALLED', 'UNMEASURED')
        if primer_storage.FIELD in c:
            try:
                result['stateVolume']['after']=storage_readback(c, client, target)
            except k.Refused as error:
                result['stateVolume']['after']={'status':error.verdict, 'code':str(error)}
            except (ValueError, KeyError, OSError, TypeError):
                result['stateVolume']['after']={'status':'UNMEASURED'}
        partial = native.get('state') == 'synthetic-tenants-partial'
        k.need(exit_code == 0 and native == {'state': 'synthetic-tenants-usable', 'tenants': c['tenants']},
               'PRIMER_INCOMPLETE',
               'UNMEASURED' if partial else 'FAIL')
        if primer_storage.FIELD in c:
            k.need(result['stateVolume']['after'].get('status')!='FAIL', 'PRIMER_STORAGE_READBACK_CHANGED')
        projected = tenant_projection(json.loads(private_file('tenants.json')), c['tenants'])
        k.observe(c, objects, client, initial)
        k.write(output/'tenants.json', projected)
        result.update(verdict='OBSERVED', dataTenants=len(projected), runSha256=k.digest(d/'run.json'),
                      rosterSha256=k.digest(output/'tenants.json'))
        # Private custody and its identity-bound receipt must survive the Job.
        k.write(output/'result.json', result)
        try:
            client.call(['exec', target, '-c', 'done', '--', 'touch', '/run/ns-primer/.exported'], read=False)
            result['exportAcknowledgement'] = 'sent'
        except k.Refused as error:
            # The exec response can be lost when the acknowledged container exits.
            result['exportAcknowledgement'] = str(error)
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
    parser.add_argument('--concurrency', type=int)
    parser.add_argument('--max-tenants', type=int)
    args = parser.parse_args()
    try:
        status = prime(args.commissioning_packet, args.new_output, args.concurrency, args.max_tenants)
        print(json.dumps(status))
        sys.exit(0 if status['verdict'] == 'OBSERVED' else 1)
    except k.Refused as error:
        sys.exit(str(error))
    except (OSError, ValueError, KeyError):
        sys.exit('K8S_PRIMER_ENTRY_REFUSED')
