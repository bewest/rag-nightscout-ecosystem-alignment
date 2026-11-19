"""Record the real scheduler outcome for an observed, run-owned Pod."""

def outcome(pod):
    meta = pod['metadata']
    status = pod.get('status', {})
    scheduled = next((c for c in status.get('conditions', []) if c['type'] == 'PodScheduled'), {})
    node = pod.get('spec', {}).get('nodeName')
    if node:
        verdict = 'Scheduled'
    elif scheduled.get('status') == 'False' and scheduled.get('reason') == 'Unschedulable':
        verdict = 'Unschedulable'
    else:
        verdict = 'Pending'
    return {'pod': meta['name'], 'uid': meta['uid'], 'phase': status.get('phase'),
            'placement': verdict, 'node': node, 'condition': scheduled}


def failed_events(pod, events):
    uid = pod['metadata']['uid']
    return [{'reason': event['reason'], 'message': event.get('message'),
             'lastObserved': event.get('lastTimestamp') or event.get('eventTime')}
            for event in events.get('items', [])
            if event.get('reason') == 'FailedScheduling' and event.get('involvedObject', {}).get('uid') == uid]
