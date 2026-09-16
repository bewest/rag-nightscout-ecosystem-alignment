import io,sys
p='docs/30-design/phase0-pr-sequencing-2026-09-15.md'
s=io.open(p,encoding='utf-8').read()
def rep(old,new):
    global s
    if s.count(old)!=1:
        sys.exit("NOT UNIQUE (%d): %r" % (s.count(old), old[:70]))
    s=s.replace(old,new)

rep("""10. **Worktree mongod isolation is not what the handoff notes claim.** Measured: `crm-bf-food`,
    `crm-bf-merge` and `crm-bf-parms` all name port **27033**; `crm-bf-coercion` names 27030 and
    `crm-bf-alarms` names 27034 with nothing listening on either; `crm-bf-connect-pin` has no
    `my.test.env` at all.""",
"""10. **Worktree mongod isolation is not what the handoff notes claim.** Re-measured 2026-09-16:
    **four** worktrees share port **27033** — `crm-bf-cache`, `crm-bf-food`, `crm-bf-merge` and
    `crm-bf-parms` (`crm-bf-cache` was missing from the earlier list of three); `crm-bf-coercion`
    names 27030 and `crm-bf-alarms` names 27034 **with nothing listening on either** (confirmed by
    connecting to each port); `crm-bf-auth` 27031 and `crm-bf-reads` 27032 are up;
    `crm-bf-connect-pin` has no `my.test.env` at all.""")

rep("""lib/client/index.js:52             var token = client.browserUtils.queryParms().token;   // first real statement""",
"""lib/client/index.js:50             client.browserUtils = require('./browser-utils')($);
lib/client/index.js:52             var token = client.browserUtils.queryParms().token;   // first use of a parsed param""")
io.open(p,'w',encoding='utf-8').write(s)
print("ok")
