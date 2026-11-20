"""Check the privately exported DATA roster receipt, and watch a streamed primer actor."""
import asyncio
import json
from pathlib import Path
import subprocess
import time

import kube_adapter as k
import commissioning_wal
import primer_options
from primer_progress import ProgressWindow


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
