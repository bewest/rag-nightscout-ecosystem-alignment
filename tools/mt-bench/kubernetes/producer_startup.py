"""Classify bounded startup convergence for the owned producer Deployment."""

import json
import re

HARD_WAITING = {
    'ImagePullBackOff', 'ErrImagePull', 'ErrImageNeverPull', 'InvalidImageName',
    'CreateContainerConfigError', 'CreateContainerError', 'RunContainerError',
}
CODES = re.compile(rb'\b(?:K8S_CANDIDATE_|EVALUATOR_|CLINICAL_|M7_|PRIMER_|BOOTSTRAP_|PLATFORM_|PGSTREAM_|ECONN|VAULT_)[A-Z0-9_]{1,90}\b')
TERMINAL_CODES = {'PGSTREAM_CONFIG_INVALID', 'PGSTREAM_SOURCE_MISMATCH', 'PGSTREAM_ARGUMENT_INVALID', 'OBSERVED_PRODUCER_CONFIG_LOAD_ERROR'}


def cohort_ready_seconds(phases, work_seconds):
    if 'cohortReadySeconds' not in phases:
        return 300
    selected = phases['cohortReadySeconds']
    if type(work_seconds) is not int or type(selected) is not int or not 1 <= selected <= work_seconds:
        raise ValueError('K8S_LIFECYCLE_COHORT_READY_WINDOW')
    return selected


def policy(value, work_seconds):
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'maxSeconds', 'stableReadySeconds'}
            or any(type(item) is not int or item < 1 for item in value.values())
            or not value['stableReadySeconds'] < value['maxSeconds'] <= work_seconds):
        raise ValueError('K8S_LIFECYCLE_PRODUCER_STARTUP_WINDOW')
    return value


def log_codes(raw):
    codes = {item.decode() for item in CODES.findall(raw)}
    for line in raw.lower().splitlines():
        if b'error: loading configuration:' in line:
            codes.add('OBSERVED_PRODUCER_CONFIG_LOAD_ERROR')
        if b'webhook' in line and (b'context deadline exceeded' in line or b'client.timeout exceeded' in line):
            codes.add('OBSERVED_PRODUCER_WEBHOOK_TIMEOUT')
        if b'notifier' in line and (b'shutting down' in line or b'shutdown' in line):
            codes.add('OBSERVED_PRODUCER_NOTIFIER_SHUTDOWN')
        if b'receiver' in line or b'webhook' in line:
            if re.search(rb'\b(?:http(?: status)?|status(?: code)?)[:= ]+503\b', line):
                codes.add('OBSERVED_PRODUCER_RECEIVER_HTTP_503')
            if b'connection refused' in line:
                codes.add('OBSERVED_PRODUCER_RECEIVER_CONNECTION_REFUSED')
    return sorted(codes)


def role_diagnostics(raw):
    """Keep the source's coded startup diagnosis without the log body."""
    found = []
    for match in re.finditer(rb'^(?:API|Evaluator|Realtime) startup refused (\{[^\n]*\})$', raw, re.M):
        try:
            row = json.loads(match[1])
        except (UnicodeDecodeError, ValueError):
            continue
        if (isinstance(row, dict) and set(row) == {'targetRole', 'checkPhase', 'causeCode'}
                and row['targetRole'] in (None, 'api', 'evaluator', 'realtime')
                and all(isinstance(row[key], str) and re.fullmatch('[A-Z0-9_]{1,90}', row[key])
                        for key in ('checkPhase', 'causeCode')) and row not in found):
            found.append(row)
    return found


def disposition(container, convergence):
    state = container['state']
    waiting = state.get('waiting', {}).get('reason')
    current = state.get('terminated')
    prior = container.get('previousTermination')
    if waiting in HARD_WAITING or any(
        item and (item.get('reason') == 'OOMKilled' or item.get('exitCode') == 137)
        for item in (current, prior)
    ):
        return 'HARD'
    failed = current and current.get('exitCode', 0) != 0
    prior_error = prior and prior.get('exitCode', 0) != 0
    if failed or waiting == 'CrashLoopBackOff' or convergence and prior_error:
        termination = current if failed else prior
        if (convergence and container['name'] == 'pgstream' and termination
                and termination.get('reason') == 'Error' and termination.get('exitCode') == 1):
            return 'RETRY'
        return 'HARD'
    return None


class StableReady:
    def __init__(self, seconds):
        self.seconds = seconds
        self.identity = None
        self.started = None

    def observe(self, identity, now):
        if identity != self.identity or identity is None:
            self.identity = identity
            self.started = now
        return identity is not None and now - self.started >= self.seconds


def replica_identity(identities, want):
    """Several replicas (evaluator slices) are ready together only when all `want` are Ready."""
    return tuple(sorted(identities)) if len(identities) >= want else None


def milestones(status):
    conditions = sum(c.get('status')=='True' for c in status.get('conditions', [])
                     if c.get('type') in ('PodScheduled','PodReadyToStartContainers','Initialized'))
    count = conditions
    for container in status.get('initContainerStatuses', []) + status.get('containerStatuses', []):
        state = container.get('state', {})
        if state.get('terminated', {}).get('exitCode') == 0:
            count += 3
        elif 'running' in state:
            count += 1 + int(container.get('started') is True) + int(container.get('ready') is True)
    return count


def vault_sealed(value):
    health = value.get('data') if isinstance(value, dict) and 'data' in value else value
    return isinstance(health, dict) and health.get('initialized') is True and health.get('sealed') is True
