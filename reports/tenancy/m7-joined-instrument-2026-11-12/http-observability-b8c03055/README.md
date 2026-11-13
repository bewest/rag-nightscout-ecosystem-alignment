# Diagnostic request context and CLI cleanup

[Exact source/instrument, controls and scope](proof.json) preserve historical668
and remoteD attribution. The original remote refusal remains unclassified because
its HTTP status/typed error were not retained. API warming timing does not prove
that cause. The new private request trail preserves the first actual response
without credential-bearing URLs, paths, queries, bodies, hosts or tenant identifiers.

Reproduced: actual spawned CLI with a connected frameless stock socket printed
HTTP_REFUSED but lingered after either503 or401. Removing only the owned-agent
late-request shutdown gate reproduces both failures; restoring it exits with
original code1 promptly. No forced process exit or deadline extension is used.
Real HTTP controls distinguish exact warming, authorization, unknown and untyped
service failures and stop at the fourth explicit request with no writes/restart.
Python retains safe terminal instrument codes and separates termination/exit timeout.

Tests use the existing owned exact-lock npm generator, verified against coreD5's
identical package manifests and actual client resolution. They are functional
HTTP/Socket.IO fixtures, not shipping product, cloud or capacity acceptance. SQL,
frame/recovery and acceptance distinctions remain intact. Retry policy is absent.
A future typed-warming policy requires explicit accounting and preserves the
first response, existing global deadline and all refusal/authority controls.
