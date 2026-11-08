"""Pure endpoint comparison and exact-owned mutation predicates; no I/O."""
import copy
import hashlib
import json
import math
import ipaddress
import re

PROFILE = 'network-endpoint-stable-v1'
FIELDS = frozenset({'Name', 'EndpointID', 'MacAddress', 'IPv4Address', 'IPv6Address'})
VOLATILE = frozenset({'MacAddress', 'EndpointID'})
KINDS = frozenset({'containers', 'volumes', 'networks'})
OPERATIONS = {'containers': frozenset({'stop', 'remove'}), 'volumes': frozenset({'remove'}), 'networks': frozenset({'remove'})}


class ProfileRefusal(ValueError):
    """Stable reason only; callers must keep raw maps private."""


def refuse(reason):
    raise ProfileRefusal(reason)


def exact_equal(left, right):
    """JSON structural equality with exact types, including bool versus int."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(exact_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(exact_equal(a, b) for a, b in zip(left, right))
    return left == right


def validate_endpoint_maps(value):
    if type(value) is not dict:
        refuse('NETWORK_MAP_NOT_OBJECT')
    for network, endpoints in value.items():
        if type(network) is not str or not re.fullmatch('[a-f0-9]{64}', network) or type(endpoints) is not dict:
            refuse('NETWORK_ID_OR_MEMBERS_SHAPE')
        for container, endpoint in endpoints.items():
            if type(container) is not str or not re.fullmatch('[a-f0-9]{64}', container):
                refuse('CONTAINER_ID_SHAPE')
            if type(endpoint) is not dict or set(endpoint) != FIELDS:
                refuse('ENDPOINT_EXACT_V1_FIELDS_REQUIRED')
            if any(type(endpoint[key]) is not str for key in FIELDS):
                refuse('ENDPOINT_FIELDS_MUST_BE_STRINGS')
            name = endpoint['Name']
            if not name or len(name) > 255 or any(ord(char) < 32 or ord(char) == 127 for char in name):
                refuse('ENDPOINT_NAME_SHAPE')
            if not re.fullmatch('[a-f0-9]{64}', endpoint['EndpointID']):
                refuse('ENDPOINT_ID_SHAPE')
            mac = endpoint['MacAddress']
            if mac and not re.fullmatch('(?:[a-fA-F0-9]{2}:){5}[a-fA-F0-9]{2}', mac):
                refuse('ENDPOINT_MAC_SHAPE')
            for field, version in [('IPv4Address', 4), ('IPv6Address', 6)]:
                address = endpoint[field]
                if not address:
                    continue
                try:
                    if '/' not in address or ipaddress.ip_interface(address).version != version:
                        refuse('ENDPOINT_IP_FAMILY_OR_CIDR')
                except ValueError:
                    refuse('ENDPOINT_IP_FAMILY_OR_CIDR')
    return value


def compare_endpoint_maps(before, after):
    """Return full private evidence; only two validated observations may vary."""
    validate_endpoint_maps(before)
    validate_endpoint_maps(after)
    if before.keys() != after.keys():
        refuse('NETWORK_MEMBERSHIP_CHANGED')
    differences = []
    for network, members in before.items():
        if members.keys() != after[network].keys():
            refuse('CONTAINER_MEMBERSHIP_CHANGED')
        for container, original in members.items():
            current = after[network][container]
            if any(original[key] != current[key] for key in FIELDS - VOLATILE):
                refuse('STABLE_ENDPOINT_FIELD_CHANGED')
            changed = {key: {'before': original[key], 'after': current[key]} for key in sorted(VOLATILE) if original[key] != current[key]}
            if changed:
                differences.append({'network': network, 'container': container, 'fields': changed})
    return {'profile': PROFILE, 'stableEquality': True, 'fullEquality': exact_equal(before, after),
            'volatileObservationsChanged': bool(differences), 'volatileDifferences': differences,
            'before': copy.deepcopy(before), 'after': copy.deepcopy(after),
            'meaning': 'Declared stable endpoint fields match; this does not claim unchanged full endpoints, quiescence or mutation authority.'}


def validate_baseline(baseline):
    if type(baseline) is not dict or set(baseline) != KINDS:
        refuse('COMPLETE_BASELINE_KINDS_REQUIRED')
    for kind, rows in baseline.items():
        if type(rows) is not dict:
            refuse('BASELINE_IDENTITY_MAP_REQUIRED')
        for identifier, identity in rows.items():
            if type(identifier) is not str or not identifier or type(identity) is not dict or type(identity.get('name')) is not str:
                refuse('BASELINE_IDENTITY_SHAPE')
            if identity.get('name' if kind == 'volumes' else 'id') != identifier:
                refuse('BASELINE_KEY_ID_MISMATCH')
    return baseline


def assert_initial_name_absent(kind, name, baseline, allowed_names):
    validate_baseline(baseline)
    if (type(kind) is not str or kind not in KINDS or type(name) is not str or not name or type(allowed_names) is not dict or set(allowed_names) != KINDS or
            any(type(rows) is not list or any(type(item) is not str for item in rows) or len(rows) != len(set(rows)) for rows in allowed_names.values()) or
            name not in allowed_names[kind]):
        refuse('EXPLICIT_RESOURCE_NAME_ALLOWLIST_REQUIRED')
    if any(identity['name'] == name for identity in baseline[kind].values()):
        refuse('INITIAL_RESOURCE_NAME_NOT_ABSENT')


def assert_owned_mutation(kind, operation, identifier, actual, retained, baseline, allowed_names):
    """Guard later exact-ID operations; never adopt from labels/prefix or state."""
    validate_baseline(baseline)
    if type(kind) is not str or kind not in KINDS or type(operation) is not str or operation not in OPERATIONS[kind]:
        refuse('OPERATION_NOT_ALLOWLISTED')
    if type(identifier) is not str or not identifier or identifier in baseline[kind]:
        refuse('BASELINE_OR_INVALID_ID_CANNOT_BE_MUTATED')
    if type(actual) is not dict or type(retained) is not dict or not retained:
        refuse('EXACT_RETAINED_IDENTITY_REQUIRED')
    identity_key = 'name' if kind == 'volumes' else 'id'
    if actual.get(identity_key) != identifier or retained.get(identity_key) != identifier:
        refuse('RETAINED_ID_MISMATCH')
    if not exact_equal(actual, retained):
        refuse('COMPLETE_RETAINED_IDENTITY_CHANGED')
    assert_initial_name_absent(kind, retained.get('name'), baseline, allowed_names)


def assert_non_target_metadata(before, after):
    """Compare the complete caller-approved static metadata; discard nothing."""
    validate_baseline(before)
    validate_baseline(after)
    if not exact_equal(before, after):
        refuse('NON_TARGET_IDENTITY_OR_CONFIGURATION_CHANGED')


def configuration_fingerprint(config, host_config):
    """Hash every supplied Config/HostConfig field; never return their values."""
    if type(config) is not dict or type(host_config) is not dict:
        refuse('COMPLETE_CONFIG_OBJECTS_REQUIRED')

    def valid(value):
        if value is None or type(value) in (str, bool, int):
            return
        if type(value) is float:
            if not math.isfinite(value):
                refuse('CONFIG_NONFINITE_NUMBER_REFUSED')
            return
        if type(value) is list:
            for item in value:
                valid(item)
            return
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                refuse('CONFIG_STRING_KEYS_REQUIRED')
            for item in value.values():
                valid(item)
            return
        refuse('CONFIG_NON_JSON_TYPE_REFUSED')

    value = {'Config': config, 'HostConfig': host_config}
    valid(value)
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')
    return {'profile': 'docker-config-hostconfig-canonical-v1', 'sha256': hashlib.sha256(encoded).hexdigest()}
