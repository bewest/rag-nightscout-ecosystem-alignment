# O2 across all client-address header families, socket handshake, AR topologies (2026-09-30)

Tree `7000eb18`. The probe header rides the socket.io handshake; the observation is the
address recorded for a wrong-secret `authorize`. "protected" = no probe moved it.
"unsendable" = the polling transport cannot send that header, so that probe says
nothing for that transport. Probe detail is private. AR-L4 uses 2, the closest setting.

| topology | TRUST_PROXY | transports | O2 |
|---|---|---|---|
| AR-PP3 | UNSET | `polling` | not protected |
| AR-PP3 | UNSET | `polling,websocket` | not protected |
| AR-PP3 | UNSET | `websocket` | not protected |
| AR-PP3 | 3 | `polling` | protected |
| AR-PP3 | 3 | `polling,websocket` | protected |
| AR-PP3 | 3 | `websocket` | protected |
| AR-PP2 | UNSET | `polling` | not protected |
| AR-PP2 | UNSET | `polling,websocket` | not protected |
| AR-PP2 | UNSET | `websocket` | not protected |
| AR-PP2 | 2 | `polling` | protected |
| AR-PP2 | 2 | `polling,websocket` | protected |
| AR-PP2 | 2 | `websocket` | protected |
| AR-L4 | UNSET | `polling` | not protected |
| AR-L4 | UNSET | `polling,websocket` | not protected |
| AR-L4 | UNSET | `websocket` | not protected |
| AR-L4 | 2 | `polling` | protected |
| AR-L4 | 2 | `polling,websocket` | protected |
| AR-L4 | 2 | `websocket` | protected |
| AR-L4PP | UNSET | `polling` | not protected |
| AR-L4PP | UNSET | `polling,websocket` | not protected |
| AR-L4PP | UNSET | `websocket` | not protected |
| AR-L4PP | 2 | `polling` | protected |
| AR-L4PP | 2 | `polling,websocket` | protected |
| AR-L4PP | 2 | `websocket` | protected |
