"""Selections and source compatibility for the native DATA primer."""

import hashlib
import json
import re
import subprocess
import time
import uuid

from contract import OWNER
import workload_inputs


FIELD = 'primerOptions'
PROTOCOL_FIELD = 'primerOptionProtocol'
PROTOCOL = 'positive-safe-integer-v1'
SOURCE_PATH = 'bindings/compose/multitenant/prime.js'
DEFAULT_CONCURRENCY = 1
DEFAULT_MAX_TENANTS = 10000
LEGACY_CONCURRENCY_MAX = 32
_PROBE_SECONDS = 30
# The short option probe container's own bound (formerly the primer reference size).
_PROBE_CPUS, _PROBE_MEMORY = '0.25', 512 * 1024 * 1024
_CLEANUP_SECONDS = 10
_PROBE_LABEL = 'org.nightscout.m7.primer-option-probe'
_CONTAINER_ID = re.compile(r'[0-9a-f]{64}')
_DOCKER_ERRORS = (OSError, RuntimeError, subprocess.SubprocessError)

_DECLARATION = b"const PRIMER_OPTION_PROTOCOL = 'positive-safe-integer-v1';\n"
_LEGACY_VALIDATOR = (b'!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 32 || '
                     b'!Number.isInteger(maxTenants) || maxTenants < 1 || maxTenants > 10000 ||')
_VALIDATOR = (b'!Number.isSafeInteger(concurrency) || concurrency < 1 || '
              b'!Number.isSafeInteger(maxTenants) || maxTenants < 1 ||')


def selection(value, need):
    need(isinstance(value, dict) and value and set(value) <= {'concurrency', 'maxTenants'}, 'PRIMER_OPTIONS')
    for key, code in (('concurrency', 'PRIMER_CONCURRENCY_INVALID'), ('maxTenants', 'PRIMER_MAX_TENANTS_INVALID')):
        if key in value:
            need(workload_inputs.concurrency(value[key]), code)
    return value


def from_profile(profile, need):
    phases = profile.get('phases', {})
    return selection(phases[FIELD], need) if FIELD in phases else None


def from_manifest(manifest):
    return {'concurrency': manifest.get('primerConcurrency', DEFAULT_CONCURRENCY),
            **({'maxTenants': manifest['primerMaxTenants']} if 'primerMaxTenants' in manifest else {})}


def requires_extended(value):
    # No tenant-count ceiling: only the legacy concurrency bound selects the protocol.
    return value.get('concurrency', DEFAULT_CONCURRENCY) > LEGACY_CONCURRENCY_MAX


def source_protocol(raw):
    return PROTOCOL if _DECLARATION in raw.splitlines(keepends=True) else None


def legacy_source_digest(raw):
    """Check the reviewed cap-only change against an existing full source pin."""
    if raw.count(_DECLARATION) != 1 or raw.count(_VALIDATOR) != 1 or raw.count(b', PRIMER_OPTION_PROTOCOL };') != 1:
        return None
    legacy = raw.replace(_DECLARATION, b'').replace(_VALIDATOR, _LEGACY_VALIDATOR)
    legacy = legacy.replace(b', PRIMER_OPTION_PROTOCOL };', b' };')
    return hashlib.sha256(legacy).hexdigest()


def require_source(value, protocol, need):
    need(not requires_extended(value) or protocol == PROTOCOL, 'PRIMER_OPTION_SOURCE_UNSUPPORTED')


def argv(selected, *, include_serial=False):
    concurrency = selected.get('concurrency', DEFAULT_CONCURRENCY)
    args = ['--concurrency', str(concurrency)] if include_serial or concurrency != DEFAULT_CONCURRENCY else []
    if 'maxTenants' in selected:
        args.extend(['--max-tenants', str(selected['maxTenants'])])
    return args


def image_probe():
    """Read only the selected image's primer bytes and its no-I/O option parser."""
    return """
const fs = require('node:fs'), crypto = require('node:crypto');
const file = '/opt/app/deploy/multitenant/prime.js';
const sha256 = crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
if (sha256 !== process.argv[2]) throw Error('PRIMER_OPTION_IMAGE_SOURCE_CHANGED');
const source = require(file);
const options = source.parsePrimeOptions(JSON.parse(process.argv[1]));
console.log(JSON.stringify({sha256, protocol: source.PRIMER_OPTION_PROTOCOL, options}));
"""


def probe_constructor(command, image, script, arguments, need):
    """Run one offline constructor under the existing owned probe policy."""
    need(image.startswith('sha256:') and _CONTAINER_ID.fullmatch(image[7:]), 'PRIMER_OPTION_IMAGE_ID')
    owner = uuid.uuid4().hex
    name = 'ns-primer-option-probe-' + owner
    container = None
    docker = ['docker', 'container']
    selector = [*docker, 'ls', '--all', '--quiet', '--no-trunc', '--filter']
    by_name = [*selector, 'name=^/' + name + '$']
    by_owner = [*selector, 'label=' + OWNER + '=' + owner]
    identity_format = ('[{{json .Id}},{{json .Name}},{{json .Image}},'
                       '{{json (index .Config.Labels "' + OWNER + '")}},'
                       '{{json (index .Config.Labels "' + _PROBE_LABEL + '")}}]')

    def bounded(seconds, code):
        deadline = time.monotonic() + seconds

        def run(args):
            remaining = deadline - time.monotonic()
            need(remaining > 0, code)
            return command(args, timeout=remaining)

        return run

    def owned_container(run):
        ids = run(by_name).splitlines()
        if not ids:
            need(not run(by_owner).strip(), 'PRIMER_OPTION_PROBE_OWNER_CHANGED')
            return None
        need(len(ids) == 1 and _CONTAINER_ID.fullmatch(ids[0]) and container in (None, ids[0]),
             'PRIMER_OPTION_PROBE_OWNER_CHANGED')
        candidate = ids[0]
        try:
            observed = json.loads(run([*docker, 'inspect', '--format', identity_format, candidate]))
        except _DOCKER_ERRORS:
            # Auto-remove may win the race between the list and inspect.
            if not run(by_name).strip() and not run(by_owner).strip():
                return None
            raise
        need(observed == [candidate, '/' + name, image, owner, 'v1'], 'PRIMER_OPTION_PROBE_OWNER_CHANGED')
        return candidate

    active = bounded(_PROBE_SECONDS, 'PRIMER_OPTION_PROBE_TIMEOUT')
    try:
        # Keep Node below PID 1 so the in-container timer can stop it even
        # when the attached Docker client or the fixture controller has exited.
        created = active([*docker, 'create', '--rm', '--name', name, '--label', OWNER + '=' + owner,
                          '--label', _PROBE_LABEL + '=v1', '--pull', 'never', '--network', 'none', '--read-only', '--init',
                          '--cpus', _PROBE_CPUS, '--memory', str(_PROBE_MEMORY), '--memory-swap', str(_PROBE_MEMORY),
                          '--pids-limit', '64', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                          '--entrypoint', '/bin/busybox', image, 'timeout', '-s', 'KILL', str(_PROBE_SECONDS),
                          'node', '-e', script, *arguments]).strip()
        need(_CONTAINER_ID.fullmatch(created), 'PRIMER_OPTION_PROBE_CONTAINER_ID')
        container = created
        need(owned_container(active) == container, 'PRIMER_OPTION_PROBE_OWNER_CHANGED')
        result = json.loads(active([*docker, 'start', '--attach', container]))
    except subprocess.TimeoutExpired:
        need(False, 'PRIMER_OPTION_PROBE_TIMEOUT')
    finally:
        cleanup = bounded(_CLEANUP_SECONDS, 'PRIMER_OPTION_PROBE_CLEANUP_UNMEASURED')
        try:
            owned = owned_container(cleanup)
            if owned:
                try:
                    cleanup([*docker, 'rm', '--force', owned])
                except _DOCKER_ERRORS:
                    # The actor can also remove itself on its independent cutoff.
                    pass
                while owned_container(cleanup):
                    time.sleep(.05)
        except (OSError, subprocess.SubprocessError):
            need(False, 'PRIMER_OPTION_PROBE_CLEANUP_UNMEASURED')
        except RuntimeError as error:
            if hasattr(error, 'returncode') or str(error) == 'M7_COMMAND_DEADLINE':
                need(False, 'PRIMER_OPTION_PROBE_CLEANUP_UNMEASURED')
            raise
    return result


def probe_image(command, image, raw, options, need):
    protocol = source_protocol(raw)
    require_source(options, protocol, need)
    sha = hashlib.sha256(raw).hexdigest()
    result = probe_constructor(command, image, image_probe(),
                               [json.dumps(argv(options, include_serial=True)), sha], need)
    expected = {'concurrency': options.get('concurrency', DEFAULT_CONCURRENCY),
                **({'maxTenants': options['maxTenants']} if 'maxTenants' in options else {})}
    need(result == {'sha256': sha, 'protocol': protocol, 'options': expected},
         'PRIMER_OPTION_IMAGE_SOURCE_CHANGED')
    return result
