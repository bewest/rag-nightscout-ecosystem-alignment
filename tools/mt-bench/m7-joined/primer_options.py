"""Selections and source compatibility for the native DATA primer."""

import hashlib
import json

import workload_inputs


FIELD = 'primerOptions'
PROTOCOL_FIELD = 'primerOptionProtocol'
PROTOCOL = 'positive-safe-integer-v1'
SOURCE_PATH = 'bindings/compose/multitenant/prime.js'
DEFAULT_CONCURRENCY = 1
DEFAULT_MAX_TENANTS = 10000
LEGACY_CONCURRENCY_MAX = 32

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
    return (value.get('concurrency', DEFAULT_CONCURRENCY) > LEGACY_CONCURRENCY_MAX
            or value.get('maxTenants', DEFAULT_MAX_TENANTS) > DEFAULT_MAX_TENANTS)


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


def probe_image(command, image, raw, options, need):
    protocol = source_protocol(raw)
    require_source(options, protocol, need)
    sha = hashlib.sha256(raw).hexdigest()
    result = json.loads(command(['docker', 'run', '--rm', '--pull=never', '--network', 'none', '--read-only',
                                 '--entrypoint', 'node', image, '-e', image_probe(),
                                 json.dumps(argv(options, include_serial=True)), sha]))
    expected = {'concurrency': options.get('concurrency', DEFAULT_CONCURRENCY),
                **({'maxTenants': options['maxTenants']} if 'maxTenants' in options else {})}
    need(result == {'sha256': sha, 'protocol': protocol, 'options': expected},
         'PRIMER_OPTION_IMAGE_SOURCE_CHANGED')
    return result
