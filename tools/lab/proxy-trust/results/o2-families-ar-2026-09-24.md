# O2 across all client-address header families, AR topologies (2026-09-24)

Tree `81623f9b`. "protected" = no probe in the private set moved the resolved
address on any attempt. Probe detail is private. AR-L4 has no setting that
resolves the real client; its second row uses 2, the closest.

| topology | TRUST_PROXY | O2 |
|---|---|---|
| AR-PP3 | UNSET | not protected |
| AR-PP3 | 3 | protected |
| AR-PP2 | UNSET | not protected |
| AR-PP2 | 2 | protected |
| AR-L4 | UNSET | not protected |
| AR-L4 | 2 | protected |
| AR-L4PP | UNSET | not protected |
| AR-L4PP | 2 | protected |
