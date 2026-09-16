P="/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/30-design/maintainer-release-brief-2026-09-15.md"
s=open(P,encoding="utf-8").read()
def rep(old,new,label):
    global s
    n=s.count(old); assert n==1, f"{label}: {n} occurrences"
    s=s.replace(old,new); print("OK",label)

rep("""the branch's diff touches none of those files. I did not re-run that. (2) **This branch's commit is
contained in `bf/reads`**, and I ran the full `./tests/*.test.js` tree there today:
**2076 passing, 3 pending, 0 failing.** So `bf/coercion`'s code *is* covered green by a full-tree
run — as merged with `bf/reads`, not in isolation. See §11.""",
"""the branch's diff touches none of those files. That run was not repeated; the port being down was
re-confirmed during adversarial review. (2) **This branch's commit is contained in `bf/reads`**, and
the full `./tests/*.test.js` tree was run there twice today, by two agents:
**2076 passing, 3 pending, 0 failing**, exit 0 both times. So `bf/coercion`'s code *is* covered green
by a full-tree run — as merged with `bf/reads`, not in isolation. See §11.""","D-tests")

open(P,"w",encoding="utf-8").write(s)
print("done")
