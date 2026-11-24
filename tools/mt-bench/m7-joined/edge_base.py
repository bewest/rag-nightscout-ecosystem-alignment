"""Which edge base URLs a run may address (lane nominal-ladder, 2026-11-23).

Workstation-attached runs reach the edge through a loopback `kubectl port-forward` (http://127.0.0.1:PORT). A campaign
controller running in the cluster (NS_CAMPAIGN_ATTACH_SCOPE=pod, set only in its Pod by campaign.py) addresses the edge
Service's ClusterIP (http://A.B.C.D:PORT, kubernetes/edge_access.py). Seeding posts to the loopback address only
(populated_history.post), so a seed still requires the loopback forward.
"""
import os
import re

LOOPBACK = re.compile(r'http://127\.0\.0\.1:([0-9]{1,5})')
IPV4 = re.compile(r'http://((25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}):([0-9]{1,5})')


def ok(base, *, seeding=False, env=None):
    env = os.environ if env is None else env
    if not isinstance(base, str):
        return False
    match = LOOPBACK.fullmatch(base)
    if match:
        return 0 < int(match[1]) <= 65535
    match = IPV4.fullmatch(base)
    return (not seeding and env.get('NS_CAMPAIGN_ATTACH_SCOPE') == 'pod' and match is not None
            and not match[1].startswith(('0.', '127.')) and 0 < int(match[5]) <= 65535)
