"""Narrow M4 caller for the verbatim approved endpoint helper; stdlib, no live I/O."""
import hashlib
import importlib.util
import copy
import re
import ipaddress
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
helper = HERE / 'endpoint_profile.py'
if hashlib.sha256(helper.read_bytes()).hexdigest() != 'a37601bee57751c0bab58afbf57bfb5de624c12ce1aa068f5dc632d023d3f4b2':
    raise ValueError('M4_ENDPOINT_HELPER_PIN_MISMATCH')
spec = importlib.util.spec_from_file_location('m4_approved_endpoint_profile', helper)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def inactive_configured(row, endpoint, lifecycle):
    state = row.get('State')
    if type(state) is not dict or state.get('Status') not in ['exited', 'created']:
        return False
    if any(type(state.get(field)) is not bool or state[field] for field in ['Running', 'Restarting', 'Paused', 'Dead']):
        return False
    if lifecycle['SandboxID'] != '' or lifecycle['SandboxKey'] != '':
        return False
    if any(type(endpoint.get(field)) is not str or endpoint[field] != '' for field in ['EndpointID', 'MacAddress', 'IPAddress', 'Gateway', 'IPv6Gateway', 'GlobalIPv6Address']):
        return False
    return all(type(endpoint.get(field)) is int and endpoint[field] == 0 for field in ['IPPrefixLen', 'GlobalIPv6PrefixLen'])


def destination_ordered_mounts(mounts):
    # Mount list presentation order is not configuration. Keep every complete
    # object/unknown field; a unique valid Destination is the identity key.
    if type(mounts) is not list:
        raise ValueError('M4_CONTAINER_MOUNTS_SHAPE')
    destinations = set()
    for mount in mounts:
        destination = mount.get('Destination') if type(mount) is dict else None
        if (type(destination) is not str or not destination.startswith('/') or
                len(destination) > 4096 or any(ord(c) < 32 for c in destination) or
                destination in destinations):
            raise ValueError('M4_CONTAINER_MOUNT_DESTINATION')
        destinations.add(destination)
    return sorted(mounts, key=lambda mount: mount['Destination'])


def runtime_observations(row):
    # Observations are not an admission bypass. Inactive membership is checked
    # against raw State above; persist only typed lifecycle/health scalars.
    state = row.get('State')
    if type(state) is not dict:
        raise ValueError('M4_CONTAINER_STATE_SHAPE')
    selected = {}
    for key in ['Running', 'Paused', 'Restarting', 'OOMKilled', 'Dead']:
        if key in state:
            if type(state[key]) is not bool:
                raise ValueError('M4_CONTAINER_STATE_BOOLEAN')
            selected[key] = state[key]
    if 'Status' in state:
        if state['Status'] not in ['created', 'running', 'paused', 'restarting', 'removing', 'exited', 'dead']:
            raise ValueError('M4_CONTAINER_STATE_STATUS')
        selected['Status'] = state['Status']
    for key in ['Pid', 'ExitCode']:
        if key in state:
            if type(state[key]) is not int:
                raise ValueError('M4_CONTAINER_STATE_INTEGER')
            selected[key] = state[key]
    if 'Health' in state:
        health = state['Health']
        if type(health) is not dict:
            raise ValueError('M4_CONTAINER_HEALTH_SHAPE')
        selected['Health'] = {}
        if 'Status' in health:
            if health['Status'] not in ['none', 'starting', 'healthy', 'unhealthy']:
                raise ValueError('M4_CONTAINER_HEALTH_STATUS')
            selected['Health']['Status'] = health['Status']
        if 'FailingStreak' in health:
            if type(health['FailingStreak']) is not int or health['FailingStreak'] < 0:
                raise ValueError('M4_CONTAINER_HEALTH_STREAK')
            selected['Health']['FailingStreak'] = health['FailingStreak']
    result = {'State': selected}
    if 'RestartCount' in row:
        if type(row['RestartCount']) is not int or row['RestartCount'] < 0:
            raise ValueError('M4_CONTAINER_RESTART_COUNT')
        result['RestartCount'] = row['RestartCount']
    return result

def baseline_snapshot(raw_batches):
    rows = {kind: [row for batch in raw_batches[kind] for row in json.loads(batch)] for kind in ['containers', 'volumes', 'networks']}
    network = call({'operation': 'network-snapshot', 'rows': rows['networks']})
    maps = network['endpointMaps']
    identities = {'containers': {}, 'volumes': {}, 'networks': network['identities']}
    observations = {}
    for row in rows['containers']:
        cid = row['Id']
        if type(cid) is not str or not re.fullmatch('[a-f0-9]{64}', cid) or cid in identities['containers'] or type(row.get('Name')) is not str or type(row.get('Created')) is not str:
            raise ValueError('M4_CONTAINER_STATIC_SHAPE')
        ns = copy.deepcopy(row['NetworkSettings'])
        if type(ns) is not dict or type(ns.get('Ports')) is not dict or type(ns.get('Networks')) is not dict:
            raise ValueError('M4_CONTAINER_NETWORK_SETTINGS_SHAPE')
        lifecycle = {}
        for field in ['SandboxID', 'SandboxKey']:
            field_value = ns.pop(field)
            if type(field_value) is not str or len(field_value) > 4096 or any(ord(c) < 32 for c in field_value):
                raise ValueError('M4_CONTAINER_SANDBOX_TYPE')
            lifecycle[field] = field_value
        if lifecycle['SandboxID'] and not re.fullmatch('[a-f0-9]{64}', lifecycle['SandboxID']):
            raise ValueError('M4_CONTAINER_SANDBOX_ID')
        observed, live = {}, set()
        for name, endpoint in ns['Networks'].items():
            if type(name) is not str or not name or len(name) > 255 or any(ord(c) < 32 for c in name) or type(endpoint) is not dict or type(endpoint.get('NetworkID')) is not str:
                raise ValueError('M4_CONTAINER_NETWORK_SHAPE')
            nid = endpoint['NetworkID']
            if not re.fullmatch('[a-f0-9]{64}', nid) or nid in observed or (nid in maps and name != network['identities'][nid]['name']):
                raise ValueError('M4_CONTAINER_GLOBAL_MEMBERSHIP')
            if type(endpoint.get('Gateway')) is not str or (endpoint.get('Aliases') is not None and (type(endpoint['Aliases']) is not list or any(type(alias) is not str for alias in endpoint['Aliases']))):
                raise ValueError('M4_CONTAINER_GATEWAY_ALIAS_TYPE')
            if nid not in maps or cid not in maps[nid]:
                # Configured membership survives stop/create; no live endpoint
                # or authority is inferred. Keep ALL configured fields exact.
                if not inactive_configured(row, endpoint, lifecycle):
                    raise ValueError('M4_CONTAINER_INACTIVE_ENDPOINT_REFUSED')
                observed[nid] = {'mode': 'inactive-orphan-configured' if nid not in maps else 'inactive-configured', 'EndpointID': '', 'MacAddress': ''}
                continue
            live.add(nid)
            global_endpoint = maps[nid][cid]
            if global_endpoint['Name'] != row['Name'].removeprefix('/'):
                raise ValueError('M4_CONTAINER_GLOBAL_NAME')
            for field in ['EndpointID', 'MacAddress']:
                if type(endpoint.get(field)) is not str or endpoint[field] != global_endpoint[field]:
                    raise ValueError('M4_CONTAINER_GLOBAL_VOLATILE')
            for address, prefix, global_field, family in [('IPAddress', 'IPPrefixLen', 'IPv4Address', 4), ('GlobalIPv6Address', 'GlobalIPv6PrefixLen', 'IPv6Address', 6)]:
                if type(endpoint.get(address)) is not str or type(endpoint.get(prefix)) is not int:
                    raise ValueError('M4_CONTAINER_IP_TYPE')
                expected = global_endpoint[global_field]
                if expected:
                    interface = ipaddress.ip_interface(expected)
                    if interface.version != family or endpoint[address] != str(interface.ip) or endpoint[prefix] != interface.network.prefixlen:
                        raise ValueError('M4_CONTAINER_GLOBAL_IP')
                elif endpoint[address] != '' or endpoint[prefix] != 0:
                    raise ValueError('M4_CONTAINER_GLOBAL_IP')
            observed[nid] = {field: endpoint.pop(field) for field in ['EndpointID', 'MacAddress']}
        if live != {nid for nid, members in maps.items() if cid in members}:
            raise ValueError('M4_CONTAINER_GLOBAL_MEMBERSHIP')
        static = {key: value for key, value in row.items() if key not in ['Config', 'HostConfig', 'NetworkSettings', 'State', 'RestartCount', 'ExecIDs']}
        static['Mounts'] = destination_ordered_mounts(row['Mounts'])
        static['configurationFingerprint'] = p.configuration_fingerprint(row['Config'], row['HostConfig'])
        static['NetworkSettings'] = ns
        identities['containers'][cid] = {'id': cid, 'name': row['Name'], 'staticFingerprint': fingerprint(static)}
        observations[cid] = {'sandbox': lifecycle, 'endpoints': observed, 'runtime': runtime_observations(row)}
    for row in rows['volumes']:
        if type(row.get('Name')) is not str or row['Name'] in identities['volumes']:
            raise ValueError('M4_VOLUME_STATIC_SHAPE')
        identities['volumes'][row['Name']] = {'name': row['Name'], 'staticFingerprint': fingerprint(row)}
    known = set(identities['containers'])
    if any(cid not in known for members in maps.values() for cid in members):
        raise ValueError('M4_ENDPOINT_CONTAINER_NOT_IN_INVENTORY')
    return {'identities': identities, 'endpointMaps': maps, 'containerObservations': observations, 'endpointProfile': p.PROFILE}


def call(value):
    operation = value['operation']
    if operation == 'baseline-snapshot':
        return baseline_snapshot(value['rawBatches'])
    if operation == 'compare-baseline':
        before, after = value['before'], value['after']
        p.assert_non_target_metadata(before['identities'], after['identities'])
        result = p.compare_endpoint_maps(before['endpointMaps'], after['endpointMaps'])
        result['containerObservations'] = {'before': before['containerObservations'], 'after': after['containerObservations']}
        return result
    if operation == 'compare-endpoints':
        return p.compare_endpoint_maps(value['before'], value['after'])
    if operation == 'configuration':
        return p.configuration_fingerprint(value['Config'], value['HostConfig'])
    if operation == 'network-snapshot':
        # Containers alone is the approved endpoint boundary. Every other
        # supplied network field, including unknown fields/types, is static.
        static, maps = {}, {}
        for row in value['rows']:
            if type(row) is not dict or type(row.get('Id')) is not str or type(row.get('Name')) is not str:
                raise ValueError('M4_NETWORK_INSPECT_SHAPE')
            nid = row['Id']
            if nid in static or 'Containers' not in row:
                raise ValueError('M4_NETWORK_DUPLICATE_OR_MEMBERS_MISSING')
            metadata = {key: field for key, field in row.items() if key != 'Containers'}
            encoded = json.dumps(metadata, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
            static[nid] = {'id': nid, 'name': row['Name'], 'staticFingerprint': hashlib.sha256(encoded).hexdigest()}
            maps[nid] = row['Containers']
        p.validate_endpoint_maps(maps)
        return {'identities': static, 'endpointMaps': maps, 'endpointProfile': p.PROFILE}
    raise ValueError('M4_ENDPOINT_OPERATION_REFUSED')


if __name__ == '__main__':
    try:
        result = call(json.load(sys.stdin))
        sys.stdout.write(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')
    except (ValueError, KeyError, TypeError):
        # Private raw maps/configuration never enter a diagnostic.
        sys.stderr.write('M4_ENDPOINT_PROFILE_REFUSED\n')
        sys.exit(2)
