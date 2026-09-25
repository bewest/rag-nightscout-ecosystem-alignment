# `rt/trust-one-source` → `bf2/auth-hardening`: bring #8764 into #8754

**DRAFT. Not opened.** Head `rt/trust-one-source` at `efcd26b1` (the merge of #8764), base
`bf2/auth-hardening` at `708af170` (#8754's head, which already has #8763). #8764 was merged into
`rt/trust-one-source` at 01:04:25Z on 2026-09-25, two minutes after #8763 had been merged into
`bf2/auth-hardening` (01:02:28Z), so #8754 does not have it. This PR brings exactly its three files.
Merges clean; the merged tree is identical to `71987bb4`'s. Decided 2026-09-24 (maintainer): the
change ships in 15.0.9 with #8754. The posting copy is the text below the line.

---

Brings #8764 into #8754. #8764 was merged into `rt/trust-one-source` just after that branch had been merged here as #8763, so it did not come along.

**What it changes:** Loop remote commands carry the sender's address as `TRUST_PROXY` resolves it (`clientIPFor(env)`), instead of the connecting address, which on most hosted sites is the hosting proxy's. Loop saves it on remote overrides, so **the caregiver's address is stored in treatments**, readable by anyone who can read the site's data. Whether a command is accepted does not depend on it.

Files: `lib/api2/index.js` (passes `env`), `lib/api2/notifications-v2.js`, `tests/notifications-v2.test.js`. The full description and break-it results are in #8764.

Full suite on the merged tree (identical to `71987bb4`'s), Node 24.15.0, MongoDB 7: 2577 passing, 3 pending, 0 failing.
