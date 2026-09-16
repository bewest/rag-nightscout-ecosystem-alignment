P="/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/30-design/maintainer-release-brief-2026-09-15.md"
s=open(P,encoding="utf-8").read()
def rep(old,new,label):
    global s
    n=s.count(old); assert n==1, f"{label}: {n} occurrences"
    s=s.replace(old,new); print("OK",label)

rep("""*Measured* by `git merge-base --is-ancestor <commit> <pin>` for each of the six commits
(`9fa2c3c`, `5349d47`, `77e2396`, `8406edf`, `51b6e6e`, `c1cce2a`) against each pin, in
`externals/nightscout-connect`. **`v0.0.14` is the first ref that carries all six**, and the tarball
pin means **the tag push (decision 2), not the npm publish (decision 3), is what delivers it.**""",
"""*Measured* by `git merge-base --is-ancestor <commit> <pin>` for each of the six commits
(`9fa2c3c`, `5349d47`, `77e2396`, `8406edf`, `51b6e6e`, `c1cce2a`) against each pin, in
`externals/nightscout-connect`. **All five rows of the table above were re-measured independently
during adversarial review on 2026-09-15 and reproduce exactly**, including the five `package.json`
pin strings. **`v0.0.14` is the first ref that carries all six**, and the tarball pin means **the tag
push (decision 2), not the npm publish (decision 3), is what delivers it.**""","s2-meas")

open(P,"w",encoding="utf-8").write(s)
print("done")
