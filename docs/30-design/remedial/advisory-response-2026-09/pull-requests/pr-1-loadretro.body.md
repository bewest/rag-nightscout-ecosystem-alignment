> **Details withheld.** This PR fixes a security issue that is tracked in a private GitHub security advisory. The fix is merged into `dev`, but no release contains it yet. We removed the detailed description on purpose, and will restore it once a fixed release is out and the advisory is published.

### Summary

A Socket.IO handler on the main namespace now applies the same read authorization as the rest of the API. The decision comes from `AUTH_DEFAULT_ROLES`, through the existing `verifyAuthorization()` path, so this adds no new policy.

- **Default install (`AUTH_DEFAULT_ROLES=readable`):** nothing changes for clients.
- **Installs that have turned off anonymous access:** the socket now refuses unauthorized clients, just as the REST routes already do.

### Evidence

- `tests/websocket.loadretro-authorization.test.js`: 4 cases, covering both authorization arms. With the fix reverted, the two negative cases fail and the two positive cases still pass.
- Suite: 2311 → 2315 passing, 3 pending, 0 failing.
- Cherry-picks cleanly onto `v15.0.8`. The suite there goes 1533 → 1588 passing, 0 failing, if we want a backport.

Independent of #8745: the two PRs touch different files and merge cleanly in either order.

