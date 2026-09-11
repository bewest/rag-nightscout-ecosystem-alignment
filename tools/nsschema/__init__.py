"""nsschema — evidence-driven schema tooling for the Nightscout document model.

Pipeline:

    corpus.py   discover raw Nightscout JSON snapshots on disk
    redact.py   de-identification policy applied to every recorded value
    census.py   walk the corpus, emit a per-field evidence census
    tiers.py    classify census fields into evidence tiers
    diff.py     reconcile the census against specs/openapi/
    emit/       generate deliverables from the reconciled schema

Nothing in this package writes a raw field value to an output artifact
without passing it through ``redact.scrub``; see that module for the policy.
"""

__version__ = "0.1.0"
