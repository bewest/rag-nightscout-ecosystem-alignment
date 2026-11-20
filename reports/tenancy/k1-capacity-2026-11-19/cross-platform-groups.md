# Case counts for the K=1 figure

Each row groups independent traffic-bearing runs with the same configuration. Rates are ordinary requests per steady load second. Each case contributes its own accepted-to-durable p95 upper bound to the figure. Timed counts include accepted inputs with a durable upper bound. Deadline-unknown inputs can have an upper bound above the deadline. Both product and HTTP must pass for a case to count in the final column.

| Platform | Tenants | Fixture | Offer | Achieved min / median / max | Timed / accepted | Confirmed late | Deadline unknown | Product + HTTP passes / cases |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Compose | 500 | fresh | 6.94 | 6.95 / 6.95 / 6.95 | 2,189 / 2,189 | 0 | 0 | 1 / 1 |
| Compose | 500 | fresh | 13.89 | 13.89 / 13.89 / 13.89 | 4,357 / 4,357 | 0 | 0 | 1 / 1 |
| Compose | 1,000 | fresh | 13.89 | 13.89 / 13.89 / 13.89 | 8,711 / 8,711 | 0 | 0 | 2 / 2 |
| Compose | 1,000 | fresh | 41.67 | 41.67 / 41.67 / 41.67 | 13,024 / 13,024 | 0 | 0 | 1 / 1 |
| Compose | 1,000 | fresh | 55.56 | 55.56 / 55.56 / 55.56 | 17,357 / 17,357 | 0 | 0 | 1 / 1 |
| Compose | 1,000 | fresh | 83.33 | 83.33 / 83.33 / 83.33 | 26,024 / 26,024 | 0 | 0 | 1 / 1 |
| Compose | 1,000 | fresh | 97.22 | 97.22 / 97.22 / 97.22 | 91,071 / 91,071 | 0 | 0 | 3 / 3 |
| Compose | 1,000 | fresh | 111.11 | 111.09 / 111.11 / 111.11 | 104,069 / 104,069 | 128 | 10,681 | 2 / 3 |
| Compose | 1,000 | fresh | 120.00 | 119.99 / 120.00 / 120.00 | 112,390 / 112,390 | 207 | 23,084 | 1 / 3 |
| Compose | 1,000 | fresh | 180.00 | 179.74 / 179.89 / 180.00 | 140,702 / 168,476 | 833 | 109,325 | 0 / 3 |
| Compose | 1,000 | fresh | 210.00 | 210.00 / 210.00 / 210.00 | 55,223 / 65,544 | 277 | 43,515 | 0 / 1 |
| Compose | 1,000 | fresh | 240.00 | 201.63 / 201.63 / 201.63 | 41,186 / 61,078 | 304 | 50,015 | 0 / 1 |
| Compose | 3,000 | fresh | 13.89 | 13.89 / 13.89 / 13.89 | 4,358 / 4,358 | 0 | 0 | 1 / 1 |
| Compose | 3,000 | fresh | 41.67 | 41.67 / 41.67 / 41.67 | 13,022 / 13,022 | 0 | 0 | 1 / 1 |
| Compose | 5,000 | fresh | 13.89 | 13.89 / 13.89 / 13.89 | 4,358 / 4,358 | 0 | 0 | 1 / 1 |
| Compose | 5,000 | fresh | 69.44 | 69.45 / 69.45 / 69.45 | 21,690 / 21,690 | 0 | 0 | 1 / 1 |
| Compose | 10,000 | fresh | 13.89 | 13.89 / 13.89 / 13.89 | 4,358 / 4,358 | 0 | 0 | 1 / 1 |
| Compose | 10,000 | fresh | 138.89 | 138.88 / 138.88 / 138.88 | 43,354 / 43,354 | 0 | 0 | 1 / 1 |
| Kubernetes | 1,000 | fresh | 13.89 | 13.89 / 13.89 / 13.89 | 4,357 / 4,357 | 0 | 0 | 1 / 1 |
| Kubernetes | 1,000 | reused | 13.89 | 13.82 / 13.86 / 13.89 | 8,690 / 8,690 | 0 | 0 | 1 / 2 |
| Kubernetes | 1,000 | reused | 27.78 | 27.54 / 27.78 / 27.78 | 25,990 / 25,990 | 0 | 0 | 3 / 3 |
| Kubernetes | 1,000 | reused | 41.67 | 41.12 / 41.16 / 41.16 | 38,511 / 38,511 | 0 | 0 | 0 / 3 |

The [case aggregates](case-aggregates.csv) include the offered, issued, completed and successful rates, full-window missed starts, outcomes and drain counts. The [operation aggregates](operation-aggregates.csv) give the seven REST shapes. Repeat counts describe the plotted workload. The campaign retains separate receipts for historical runs, fixture capture and pretraffic setup attempts.
