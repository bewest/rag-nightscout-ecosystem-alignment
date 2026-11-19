"""Observe accepted inputs through the owned Kubernetes PostgreSQL connection."""
import time

import kube_adapter as k
import clinical_sql


def observer(d, c, objects, client, runid, ids):
    import accepted_inputs

    baseline = k.active_baseline(d)
    def postgres():
        return clinical_sql.observe(c, objects, client, baseline, continuity_verdict='UNMEASURED')

    def fetch(query, timeout):
        # The observation cutoff covers both ownership checks and the SQL read.
        with k.observation_deadline(time.time() + timeout):
            pod, container = postgres()
            remaining = k.deadline(c)
            statement_ms = max(1, int(remaining * 1000))
            try:
                result = k.postgres_read(client, pod, container,
                                         f'SET LOCAL statement_timeout={statement_ms};\n' + query,
                                         timeout=remaining)
            finally:
                postgres()
            k.deadline(c)
            return result

    return accepted_inputs.Observer(config=c['completion'], run_id=runid, ids=ids, fetch=fetch)
