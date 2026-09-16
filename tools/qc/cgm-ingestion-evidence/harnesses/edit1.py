import io,sys
p='docs/30-design/phase0-pr-sequencing-2026-09-15.md'
s=io.open(p,encoding='utf-8').read()
def rep(old,new):
    global s
    if s.count(old)!=1:
        sys.exit("NOT UNIQUE (%d): %r" % (s.count(old), old[:70]))
    s=s.replace(old,new)

# A. the section's opening claim
rep("""**The pin move turned out to be a security fix, and BF-34 is the smaller half of it.**""",
"""**The pin move was framed as a security fix. That framing is withdrawn below and the rationale that
survives is nameability, reviewability and three behavioural fixes.** See the correction two
sub-sections down, and the resolved contradiction immediately after the commit list.""")

# B. the contradicting paragraph
rep("""So **15.0.9 as currently pinned ships without three log-redaction fixes.** Making debug logging
opt-in (`234d47c`, the one commit the pin *does* have) narrows *when* those leaks can happen; it
does not stop them happening when an operator turns logging on to diagnose a problem — which is
precisely when they do it.""",
"""So **15.0.9 as currently pinned ships without three log-redaction fixes.**

> **CONTRADICTION FOUND AND RESOLVED HERE, 2026-09-16 (adversarial review).** This paragraph used to
> continue: *"Making debug logging opt-in (`234d47c`, the one commit the pin does have) narrows when
> those leaks can happen; it does not stop them happening when an operator turns logging on to
> diagnose a problem."* That is **the same sentence this section later calls refuted** — see the
> two-corrections block below — so the document was asserting in its own voice, three paragraphs
> earlier, a claim it then withdrew. Reproduced with `git show --stat 234d47c8`: that commit is
> **18 files, +379/−146**, and it *rewrites* the logging call sites rather than gating them, so
> "it only narrows *when* the leak happens" is wrong about what the commit does.
> **What survives:** `dev`'s pin genuinely lacks the three named redaction commits, which is a real
> coverage gap — but `dev`'s pin is among the *safest* in flight and `master`'s `v0.0.13` is the
> leaking one. **The pin move is not primarily a security fix.** The rationale that stands is
> nameability, reviewability, BF-34, the MiniMed contract fix, the listener-release fix, and
> v0.0.14 being the first ref carrying both redaction lines.""")
io.open(p,'w',encoding='utf-8').write(s)
print("ok")
