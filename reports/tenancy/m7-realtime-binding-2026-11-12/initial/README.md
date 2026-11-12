# Fixed realtime binding: initial focused boundary

Fixed on local binding `62afa90728d2b844ca34e313dc416cd4c7e2a31f`, metadata pin
`072a55d15d5b228596215060f436bb4038a87397`, with core
`079a3b4c9a6ece9610b32025a0826f756fbb23f0`. The source/delta identity gate passes
all five reduced fixture files. [Attribution and hashes](artifacts.json).

The optional fixed worker roster has an explicitly selected logical shard count;
the default remains unsharded. Durable registry resolution selects the canonical
tenant before the streaming socket edge selects a configured owner. Maintenance
uses every fixed worker, including idle workers. Backend assignment and admitted
edge/alarm routes are separate directory-mounted atomic files. The private host
operator requests platform stop/start over a bounded pipe to the product publisher;
no Docker daemon socket is exposed to the publisher.

[Focused checks](focused.txt): 47 pass, including actual source parsers, the
registry resolver, real HTTP/WebSocket forwarding, stock polling, private-file
and operator input controls. [Product parser control](product-parsers.txt) rejects
missing worker coverage and restores successfully. The explicit deployment coverage
check additionally compares each declared worker's actual fixed endpoint to the
selected placement. Removing the old singular realtime alias was necessary for
these instance declarations to pass the product parser.

Two source ablations discriminate behavior:

- [Wrong tenant destination](wrong-route-control.txt): the Host for synthetic A
  reaches B's fixture instead of A's; the check fails on the response witness.
- [Five-second response-header deadline](polling-timeout-control.txt): a real stock
  polling client disconnects during a quiet interval before the fixture's next
  heartbeat. Restoring a 60-second header deadline with a separate five-second
  connect deadline preserves the idle session in the focused campaign. Stream,
  socket and target errors are handled without introducing a global error handler.

[Actual Compose configuration](compose-projection.json) resolves both API config
mounts, both realtime config mounts, shared read-only placement directories, the
operator mount and socket edge. This proves configuration, not role initialization.
The socket fixtures do not claim actual clinical projection, alarm or restore
acceptance.

Still open: actual fresh shipping-role composition and moves, plus explicit
post-publication recovery when the host stops before boot metadata activation.
The latter intentionally fails closed in this initial binding; it must not be
reported as accepted. Dedicated composition and recovery lanes continue on this
committed boundary. Final full/browser/enabled-corpus and capacity campaigns wait
for their coherent joined candidate.
