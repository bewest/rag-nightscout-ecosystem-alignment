**Title:** Lab Nightscout, external device simulators, and run status

Thanks for the harness. Four things from reading it at `c3c1bfe` ([notes](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/10-domain/trio-test-harness-deep-dive.md)):

1. **A lab Nightscout.** Onboarding taps "Skip Nightscout Setup" (`harness/flows/trio.py`), and Trio keeps the URL and secret in the Keychain, which no `th` command writes, so a run uploads nothing. An option to point the app at a lab Nightscout would let a run's uploads (entries, treatments, devicestatus, profile) be checked on the server. We maintain lab tooling on the Nightscout side that could do that checking.
2. **External device simulators.** Runs use the apps' built-in simulators. LoopKit/g7sim and LoopKit/pod now serve the Simulator over ImpossiBLE (g7sim's `impossible-mux` runs both), and faketandem has a virtual transport; the faketandem lane's build hooks are still in `build.py` without CLI flags. Is attaching these in scope?
3. **Run status.** `run.json` says `passed` once the smoke stage passes, and that stands if the agent step fails or times out. Intended?
4. **Small:** `.github/workflows/e2e.yml` (line 242) calls this a "private repo"; it is public.
