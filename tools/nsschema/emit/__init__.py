"""Emitters: one reconciled model (``nsschema.model``) to many artifacts.

Every emitter in this package is a pure function of the IR. None of them
reads ``specs/openapi/`` or the census directly — that is what keeps the
four declarations of a field's type (spec, boundary validator, ODM schema,
column type) from drifting apart again, which is the failure mode the
multitenancy discussion §6.4 names.
"""
