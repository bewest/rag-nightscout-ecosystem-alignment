# M7 focused deployment rehearsal

Reproduced 2026-11-11 in owned disposable Compose projects. This is startup
and provisioning diagnosis, not final image, restore, client or capacity
acceptance. PostgreSQL and Vault images are pinned by the deployment tree.
The previous image `nsauthz:5c60aec6-d1c7aca` supplies dependencies and its old
browser bundle; read-only mounts supply the explicitly identified application
and deployment code. Final acceptance must build the frozen source pair.

| Input / effect | Observation |
|---|---|
| First setup attempt | Image-inherited source environment named the old application despite mounted new code. Attribution invalid; excluded from measurements. Owned project removed, peer services untouched. |
| Core `17bf3a6064d0c9318a17d4c77f0f141f165e0bed`, deploy `007700958af5895a9900d0bceea63fe55d9b896c` | Infrastructure bootstrap completes with explicit source environment. Private admin exits 78: wildcard `0.0.0.0:1342` is refused by the internal-listener boundary. Feed reader starts. |
| Core `e79fc1e0afd5051f57a18cc8809befcf62af343e`, deploy `eab5967681fbfb792abacdc0b06be53f6fffad81` | Fresh owned state. Admin uses private Docker address `admin`, with explicit private-network acknowledgement, no published port; admin and feed reader become healthy. Private REST provisioning creates both synthetic tenants. |
| Same source pair, two API processes | Both refuse startup. Sanitized source-frame diagnosis identifies `lib/server/serve/index.js:97`: generated participant resources include `nsdemo_control`, but the launcher excludes its selected operation-control namespace from protected data resources. No API readiness or data workflow claimed. |

The binding repair removes that extra namespace and makes its generator check
match the actual launcher. A planted extra control schema fails with deployment
participant namespace mismatch; restored documents pass. The generator/parser
check does not establish actual repaired process startup. Other planned source
changes join before the next fresh rehearsal.

Private state, root custody and credentials remain local. No source-identity
completion marker is edited to reuse another source pair. The independent
[edge proof](../m7-edge-boundary-2026-11-11/README.md) exercises real nginx with
mock upstreams and retains its smaller scope.
