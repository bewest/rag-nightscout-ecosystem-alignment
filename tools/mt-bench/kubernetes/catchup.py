"""Kubernetes transport for the shared accepted-input collector (m7-joined/accepted_inputs.py)."""
import kube_adapter as k
import clinical_sql


def observer(d, c, objects, client, runid, ids):
    import accepted_inputs

    baseline = k.active_baseline(d)

    def fetch(query, timeout):
        # A PostgreSQL restart is judged as datastore health from the Pod bookends, not here.
        pod, container = clinical_sql.observe(c, objects, client, baseline, continuity_verdict='UNMEASURED')
        remaining = min(timeout, k.deadline(c))
        return k.postgres_read(client, pod, container,
                               f'SET LOCAL statement_timeout={max(1, int(remaining * 1000))};\n' + query, timeout=remaining)

    return accepted_inputs.Observer(config=c['completion'], run_id=runid, ids=ids, fetch=fetch)
