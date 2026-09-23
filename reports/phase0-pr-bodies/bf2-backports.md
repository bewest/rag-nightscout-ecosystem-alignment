# `bf2/backports`: two security fixes from the modernization branch, onto dev

**DRAFT. Pushed, not opened.** Branch `bf2/backports` on `origin/dev` `74fc6619`, tip `b5038500`,
two commits. Written in the same withheld style as #8744 and #8745: these fix defects present in
15.0.8. The detail stays in the private notes until a release containing the fixes ships. Posting
copy: everything below the line.

---

> **Details withheld.** These are security fixes. No release contains them yet, so this description is kept short on purpose. The full description will be added once a fixed release is out.

### Summary

Two fixes, each a cherry-pick (`-x`) of a commit already on `chore/nightscout-modernization` (#8605), so that when #8605 is rebased onto `dev` it finds the same change rather than a second implementation.

- **Alarm subscriptions no longer write credentials to the server log** (from `31c354d8`). This affects any install whose logs are kept or shared.
- **Two shared read routes now check the per-collection read permission** that the rest of the API already checks (from `d3ac8026`).
  - **Default install (`AUTH_DEFAULT_ROLES=readable`):** nothing changes for clients.
  - **Installs that have turned off anonymous access and use tokens limited to particular collections:** those routes now refuse a token that lacks the permission, as the other routes already do.

The library changes apply verbatim. The alarm test was adapted to `dev`'s socket, which already carries #8745 and #8746. The modernization branch's docs hunk was dropped, because that file does not exist on `dev`.

### Evidence

- `tests/api3.alarm-logging.test.js` (10 cases) and `tests/storage-read-permissions.test.js` (2 cases). With `dev`'s library code, 7 of the 12 fail.
- Suite, Node 22.23.2: 2386 → 2398 passing, 3 pending, 0 failing.
- Independent of #8748: the branches touch different files.
