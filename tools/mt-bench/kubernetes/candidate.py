"""Terminal Job condition."""

def job_condition(job):
    terminal = {row['type'] for row in job.get('status', {}).get('conditions', [])
                if row.get('status') == 'True'}
    if terminal & {'Failed', 'FailureTarget'}:
        return 'Failed'
    if 'Complete' in terminal:
        return 'Complete'
    return None

