"""Classify bounded startup convergence for the owned producer Deployment."""

import re

HARD_WAITING = {
    'ImagePullBackOff', 'ErrImagePull', 'ErrImageNeverPull', 'InvalidImageName',
    'CreateContainerConfigError', 'CreateContainerError', 'RunContainerError',
}
CODES = re.compile(rb'\b(?:K8S_CANDIDATE_|EVALUATOR_|CLINICAL_|M7_|PRIMER_|BOOTSTRAP_|PLATFORM_|PGSTREAM_|ECONN|VAULT_)[A-Z0-9_]{1,90}\b')
TERMINAL_CODES = {'PGSTREAM_CONFIG_INVALID', 'PGSTREAM_SOURCE_MISMATCH', 'PGSTREAM_ARGUMENT_INVALID', 'OBSERVED_PRODUCER_CONFIG_LOAD_ERROR'}


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
