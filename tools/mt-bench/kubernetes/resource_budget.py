"""Kubernetes scheduling requests and optional usage limits are separate facts.

No cluster calls or allocations. Legacy fixtures account limits; requests-v1 is
an explicit discovery choice and never claims a hard upper bound on usage.
"""
import copy
from decimal import Decimal, DecimalException, ROUND_CEILING, localcontext
import re

LIMITS = 'limits-v1'
REQUESTS = 'requests-v1'
DIMENSIONS = (('cpu', 'millicpus'), ('memory', 'memoryBytes'),
              ('ephemeral-storage', 'ephemeralBytes'))


def selection(config, need):
    value = config.get('resourceAccounting', LIMITS)
    need(value in (LIMITS, REQUESTS), 'RESOURCE_ACCOUNTING_UNSUPPORTED')
    return value


def exact_quantity(value, cpu, need):
    """Keep exact units for request/limit comparisons before integer accounting."""
    text = str(value)
    match = re.fullmatch(r'([+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)(Ki|Mi|Gi|Ti|Pi|Ei|[numkKMGTPE])?', text)
    need(match is not None, 'RESOURCE_QUANTITY_UNSUPPORTED')
    suffix = match[2] or ''
    factors = {'': 1, 'n': Decimal('1e-9'), 'u': Decimal('1e-6'),
               'm': Decimal('1e-3'), 'k': 1000, 'K': 1000,
               **{s: 1000**i for i, s in enumerate('MGTPE', 2)},
               **{s+'i': 1024**i for i, s in enumerate('KMGTPE', 1)}}
    try:
        with localcontext() as context:
            context.prec = max(80, len(text) + 20)
            result = Decimal(match[1]) * factors[suffix] * (1000 if cpu else 1)
            # Kubernetes quantities use signed 64-bit integer values. Check
            # before integer conversion so an invalid exponent cannot expand.
            need(result.is_finite() and 0 <= result <= 2**63-1, 'RESOURCE_QUANTITY_UNSUPPORTED')
            return result
    except (DecimalException, OverflowError, ValueError):
        need(False, 'RESOURCE_QUANTITY_UNSUPPORTED')


def quantity(value, cpu, need):
    """Round scheduling quantities up to millicpus or whole bytes."""
    return int(exact_quantity(value, cpu, need).to_integral_value(rounding=ROUND_CEILING))


def equivalent_quantities(expected, actual, need):
    """Compare exact resource values while retaining the declared dimension set."""
    if not isinstance(expected, dict) or not isinstance(actual, dict) or set(expected) != set(actual):
        return False
    if not set(expected) <= {resource for resource, _ in DIMENSIONS}:
        return False
    return all(exact_quantity(expected[key], key == 'cpu', need) ==
               exact_quantity(actual[key], key == 'cpu', need) for key in expected)


def equivalent_resources(expected, actual, need):
    """Only absent and empty limits share an unbounded meaning; no cap is dropped."""
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return False
    if not set(expected) <= {'requests', 'limits'} or not set(actual) <= {'requests', 'limits'}:
        return False
    def groups(value):
        return {key for key in value if key != 'limits' or value[key] != {}}
    keys = groups(expected)
    return keys == groups(actual) and all(
        equivalent_quantities(expected[key], actual[key], need) for key in keys)


def readback_projection(expected, actual, need):
    """Project equivalent API quantity spellings for comparison, never observation.

    Kubernetes canonicalizes quantities. Preserve actual raw objects and replace
    only resource fields in this comparison copy after exact equivalence checks.
    """
    value = copy.deepcopy(actual)
    need(actual.get('resources', {}) == expected.get('resources', {}) and
         not actual.get('resources') and not expected.get('resources'), 'POD_BUDGET_CHANGED')
    need(equivalent_quantities(expected.get('overhead', {}), actual.get('overhead', {}), need),
         'POD_BUDGET_CHANGED')
    if 'overhead' in expected:
        value['overhead'] = copy.deepcopy(expected['overhead'])
    else:
        value.pop('overhead', None)
    for section in ('containers', 'initContainers'):
        want, got = expected.get(section, []), actual.get(section, [])
        need(isinstance(want, list) and isinstance(got, list) and len(want) == len(got), 'POD_SPEC_CHANGED')
        for index, (left, right) in enumerate(zip(want, got)):
            need(left.get('name') == right.get('name') and
                 left.get('restartPolicy') == right.get('restartPolicy') and
                 equivalent_resources(left.get('resources', {}), right.get('resources', {}), need),
                 'POD_BUDGET_CHANGED')
            if 'resources' in left:
                value[section][index]['resources'] = copy.deepcopy(left['resources'])
            else:
                value[section][index].pop('resources', None)
    return value


def validate_container(container, mode, need):
    budget = container.get('resources', {})
    need(isinstance(budget, dict), 'UNBUDGETED_CONTAINER')
    for group in ('requests', 'limits'):
        values = budget.get(group, {})
        need(isinstance(values, dict), 'UNBUDGETED_CONTAINER')
        need(set(values) <= {r for r, _ in DIMENSIONS}, 'RESOURCE_DIMENSION_UNSUPPORTED')
        for resource, _ in DIMENSIONS:
            if group == 'requests' or mode == LIMITS:
                need(resource in values, 'UNBUDGETED_CONTAINER')
            if resource in values:
                need(quantity(values[resource], resource == 'cpu', need) > 0, 'UNBUDGETED_CONTAINER')
    for resource, _ in DIMENSIONS:
        if resource in budget.get('limits', {}):
            need(exact_quantity(budget['requests'][resource], resource == 'cpu', need) <=
                 exact_quantity(budget['limits'][resource], resource == 'cpu', need), 'LIMIT_BELOW_REQUEST')


def pod_budget(spec, mode, need):
    """Use one init/sidecar/steady/overhead calculation for either group."""
    need(mode in (LIMITS, REQUESTS), 'RESOURCE_ACCOUNTING_UNSUPPORTED')
    # Pod-level resources change scheduling semantics. This instrument currently
    # supports container-level inputs and refuses an unaccounted Pod budget.
    need(not spec.get('resources'), 'POD_LEVEL_RESOURCE_ACCOUNTING_UNSUPPORTED')
    group = 'requests' if mode == REQUESTS else 'limits'
    result = {}
    for resource, dimension in DIMENSIONS:
        def amount(container):
            values = container.get('resources', {}).get(group, {})
            need(resource in values, 'UNBUDGETED_CONTAINER')
            return quantity(values[resource], resource == 'cpu', need)
        sidecars = peak = 0
        for container in spec.get('initContainers', []):
            phase = sidecars + amount(container)
            peak = max(peak, phase)
            if container.get('restartPolicy') == 'Always':
                sidecars = phase
        steady = sidecars + sum(amount(container) for container in spec['containers'])
        overhead = quantity(spec.get('overhead', {}).get(resource, 0), resource == 'cpu', need)
        result[dimension] = max(peak, steady) + overhead
    return result


def scope(mode):
    return ('scheduling requests with init/sidecar/steady peaks and Pod overhead; '
            'not a hard usage bound; optional limits and actual usage remain separate'
            if mode == REQUESTS else
            'per-Pod peak limits over init/sidecar/steady phases and Pod overhead')
