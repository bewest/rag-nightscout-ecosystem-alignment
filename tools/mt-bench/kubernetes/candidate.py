"""Terminal Job condition, and the pgstream acknowledgement owner check."""

def job_condition(job):
    terminal = {row['type'] for row in job.get('status', {}).get('conditions', [])
                if row.get('status') == 'True'}
    if terminal & {'Failed', 'FailureTarget'}:
        return 'Failed'
    if 'Complete' in terminal:
        return 'Complete'
    return None


def verify_ack_owner(k, c, observed):
    receipt = c.get('producerAckReadback')
    if receipt is None:
        return
    name, container = k.selected_pod(c, observed, 'pgstream')
    pod = observed['pods'][name]
    k.need(receipt['namespaceUid'] == observed['namespace']['uid'] and receipt['podUid'] == pod['uid']
           and receipt['containerId'] == pod['containers'][container]['containerID'], 'PGSTREAM_ACK_OWNER_CHANGED')
    return name, container
