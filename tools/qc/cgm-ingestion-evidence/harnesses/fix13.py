P="/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/30-design/maintainer-release-brief-2026-09-15.md"
s=open(P,encoding="utf-8").read()
def rep(old,new,label):
    global s
    n=s.count(old); assert n==1, f"{label}: {n} occurrences"
    s=s.replace(old,new); print("OK",label)

rep("""> 3. **What BF-32 does still fix** is the other non-value operators on typed fields: `$type`,
>    `$regex` and friends were being run through `parseInt` on the ten walker-covered fields, so
>    `find[sgv][$type]=number` reached the driver as `NaN`. Those are now passed through.""",
"""> 3. **What BF-32 does still fix, and this part holds:** the other non-value operators on the ten
>    numeric walker-covered fields were being run through `parseInt`. Measured by executing both
>    copies of `query.js`: `find[sgv][$type]=number` reached the driver as `NaN` on `dev` and as
>    `"number"` on the branch; `find[sgv][$regex]=^1` as `NaN` on `dev` and as `"^1"` on the branch.
>    So the branch is right to stop coercing operands; only the *headline example* chosen for it was
>    wrong.""","D-item3")

open(P,"w",encoding="utf-8").write(s)
print("done")
