# M7 edge admission boundary

Reproduced 2026-11-11 against committed nightscout-deploy
`40d3d87e16e4855518a7829e6e045f1e20ba2c84`, with the pinned nginx and Node
images recorded in [capture.json](capture.json). Instrument:
[proof.py](../../../tools/lab/m7-edge-boundary/proof.py); its execution-time
SHA-256 is retained in the capture. Disposable mock upstreams exercise actual
nginx admission. This is not actual application, client or capacity acceptance.

All six properties pass: baseline routing, new-handshake budget refusal,
established-session exemption from that handshake budget, per-IP concurrent
request refusal, the removed-rate control, and restored default service. Under
the low synthetic budget the handshake sequence is 200,200,429,429,429,429;
established session requests all return 200. Three overlapping requests return
two 200 responses and one 429. Removing the handshake limit makes all six new
handshakes return 200: the refusal check turns red because the effect disappears.
Restoring the template restores the admitted service behavior. All owned
container/network cleanup commands exit zero.

The initial setup prototype put the published edge only on an internal Docker
network; the loopback port was unreachable. That was a setup failure, not an
application measurement. The instrument now creates a separate ingress network
and a private upstream network. It never operates on an existing deployment.
No production budget, viewer count, hot-tenant fairness or reconnect envelope
is established by this capture.

Run from this alignment tree, using a clean deployment checkout:

```bash
python3 tools/lab/m7-edge-boundary/proof.py --deploy /path/to/nightscout-deploy --out /tmp/new-edge-capture.json
```

The output must not already exist. A changed edge template, placement renderer
or admission policy requires a new capture; do not relabel this one.
