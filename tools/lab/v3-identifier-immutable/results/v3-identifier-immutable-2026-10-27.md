# v3-identifier-immutable lab results, 2026-10-27

*Contributor-facing. Synthetic data only; nothing here is from a real site.*

Produced by `tools/lab/v3-identifier-immutable/lab.sh up && lab.sh run` (see [README](../README.md)) with
`V3I_BUILDS="1509=c6a0d8ed:3981 dev=7abe1cf6:3982"` and the same `node_modules` as the
[record-identity run of the same day](../../record-identity/results/record-identity-2026-10-27.md).

One row differs: a v1 entries re-send with the same `identifier` and a time 60 s later is one record
on 16.0.0 (`7abe1cf6`, #8859) and two on 15.0.9. API v3 still answers 400 when a re-send with the same
`identifier` changes `date`, `device` or `eventType`, on both.

| case | 15.0.9 `c6a0d8ed` | 16.0.0 `7abe1cf6` |
|---|---|---|
| treatments e. identical re-send (control) | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| treatments a. same id, date +60 s, same device | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| treatments b. same id, other device, date +1.5 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| treatments b2. same id, other device, same date | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| treatments c. same id, other eventType | 201 identifier -> 400 "Field eventType cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 400 "Field eventType cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| treatments d. PUT by id, date +60 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| entries e. identical re-send (control) | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| entries a. same id, date +60 s, same device | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| entries b. same id, other device, date +1.5 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| entries b2. same id, other device, same date | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| entries d. PUT by id, date +60 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| devicestatus e. identical re-send (control) | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| devicestatus a. same id, date +60 s, same device | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| devicestatus b. same id, other device, date +1.5 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| devicestatus b2. same id, other device, same date | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| devicestatus d. PUT by id, date +60 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| v1 treatments: same identifier, created_at +60 s | 200 -> 200 \| stored n=1 [created_at=t-1740] | 200 -> 200 \| stored n=1 [created_at=t-1740] |
| v1 entries: same identifier, date +60 s | 200 -> 200 \| stored n=2 [date=t-1800; date=t-1740] | 200 -> 200 \| stored n=1 [date=t-1740] |
| treatments f. v1 record, then v3 same id + device, same time | 200 -> 200 identifier \| stored n=1 [date=t-1800 created_at=t-1800 device=loop://lab-phone] | 200 -> 200 identifier \| stored n=1 [date=t-1800 created_at=t-1800 device=loop://lab-phone] |
| treatments f2. v1 record, then v3 same id + device, time +60 s | 200 -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=undefined created_at=t-1800 device=undefined] | 200 -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=undefined created_at=t-1800 device=undefined] |
