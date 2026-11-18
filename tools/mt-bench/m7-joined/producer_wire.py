"""The synthetic pgstream notifier's wire fields shared by Compose and Kubernetes."""
import json


ACK_BUDGET = 'pgstreamNotifierAckTimeoutMs'
WIRE_DIRECTORY = '/run/ns-stream'
WIRE_NAME = 'pgstream.yaml'


def valid_timeout(value):
    # pgstream converts milliseconds to a signed nanosecond Go duration.
    return type(value) is int and 0 < value <= (2**63 - 1) // 1_000_000


def load_wire(raw):
    try:
        config = json.loads(raw)
        notifier = config['target']['webhooks']['notifier']
        if (type(notifier['worker_count']) is int and notifier['worker_count'] == 1
                and notifier['strict_mode'] is True
                and notifier['backoff'] == {'constant': {'max_retries': 1, 'interval': 50}}
                and valid_timeout(notifier['client_timeout'])):
            return config, notifier
    except (ValueError, TypeError, KeyError):
        pass
    raise RuntimeError('M7_PGSTREAM_ACK_WIRE_SHAPE')
