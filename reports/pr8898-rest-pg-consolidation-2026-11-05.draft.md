# DRAFT — multitenant REST preview with bounded PG mechanics consolidation

The explicit `nightscout multitenant api` preview composes selected shipping
legacy/API3 data handlers, derived reads, current persisted authority and Vault
with PostgreSQL/RLS. Default single keeps MongoDB. Management remains a separate
factory; owner/operator/realtime/evaluator roles are not enabled.

This continuation shares identical PG projection, identifying-read options/order
and after-owned-transaction event mechanics. Independent translators, source
natural ordering, validation, raw identities and write policy remain explicit.
Expanded real-port tests run on both unchanged baseline and extraction. New
actual Mongo/PG index-on races force two empty matches and competing real INSERTs,
observe duplicate errors and verify all resend-mode replies/stored results,
current grants and tenant invariance. The fixture selects the shipping intent
factory's mode; this is not deployment/config-parser or universal client acceptance.

Recorded on local `44331668038dca5bc23af24c4125052b9c8e5612` (R46): complete
nonbrowser7051passing/80pending/0failing; default browser684/0/0 on the preceding
revision with identical application source; archived common contract75/0/0.
Scopes overlap. Wrong ordering, missing included identity, premature event and
disabled duplicate retry each fail semantic assertions; restored gates pass.
Initial legacy-ID and UTC timestamp fixture assumptions were reproduced on the
baseline and corrected explicitly; production capability policy is unchanged.
Independent review, tier classification, lint and final prcheck pass.

Independent #8891 writer replay and frame inventory remain separately measured.
Broader portable helper/capability work, remaining REST side effects/settings/
actual clients, import/resources, owner identity/ceilings and production lifecycle/
durable recovery remain open. No milestone promotion, RC admission or role
activation follows. Fresh CI/CodeQL must cover this continuation after publication.

[Evidence and scope](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/30-design/remedial/rc-16.0.0-integration-record.md#r46---bounded-pg-consolidation-and-identifier-races-on-44331668-2026-11-05)
