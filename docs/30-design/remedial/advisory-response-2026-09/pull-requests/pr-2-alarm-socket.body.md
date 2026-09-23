> **Details withheld.** This PR fixes security issues that are tracked in a private GitHub security advisory. The fix is merged into `dev`, but no release contains it yet. We removed the detailed description on purpose, and will restore it once a fixed release is out and the advisory is published.

### Summary

The API v3 alarm socket now applies the same read authorization as the REST API before it delivers any notification. It uses a room, `AlarmReceivers`, that mirrors `DataReceivers` on the main namespace. A second commit adds the missing permission check on the socket's acknowledgement path.

- **Default install (`AUTH_DEFAULT_ROLES=readable`):** connected clients receive alarms exactly as before. A socket is let in when it connects if the anonymous default role already allows reading, and the decision is checked again on `subscribe`. We chose this shape so that follower clients that never subscribe don't silently stop getting alarms.
- **Installs that have turned off anonymous access:** delivery requires `api:*:read`, the same permission as REST.
- **Web client:** after a viewer authenticates in the page, it now subscribes again, so an authenticated viewer on a locked-down site keeps receiving alarms.

### Known cost

Delivery now goes through the existing failed-login delay, which is keyed by remote address. After recent failed logins from the same address, alarms can arrive a few seconds late. Measured on the fixed build: 5 s per failure, cumulative. No version of this fix avoids that. Narrowing the throttle is a separate change.

### Evidence

- `tests/api3.alarm-socket.security.test.js` (49 cases) and `tests/api3.alarm-socket.ack.test.js` (2 cases).
- Suite: 2311 → 2362 passing, 3 pending, 0 failing. Five separate ablations each fail the expected subset of cases.
- Cherry-picks cleanly onto `v15.0.8` if we want a backport.

The advisory's reporter found this issue and reported it responsibly, and will be credited on the advisory.

Independent of #8744: the two PRs touch different files and merge cleanly in either order.

