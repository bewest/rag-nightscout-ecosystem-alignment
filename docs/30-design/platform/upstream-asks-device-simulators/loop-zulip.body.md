**Stream/topic:** development › simulator rig: g7sim + pod in the iOS Simulator

g7sim and pod together are a big step: with `impossible-mux`, one Loop build in the iOS Simulator runs against a simulated G7 and a simulated DASH pod, with no radio. We wrote up how the pieces join ([record](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/60-research/programme/device-simulators-2026-10-17.md), §3) and have two questions.

**1. Path to dev.** The app side is on `next-dev` only: G7SensorKit's Simulator bridge (#89, `8fa9c73`) and direct connection, and OmnipodKit's ImpossiBLE detection (#188, `e60e0ab`). LoopWorkspace `dev` (`c1f5597`) and v3.14.9 pin G7SensorKit `dd91f46` and OmnipodKit `928bb79` / `043b91d`, none of which has them. Is #454 the intended route, and would bringing just the two Simulator-detection changes to `dev` earlier make sense? They only change behaviour when the bridge is present.

**2. pod fidelity** (pod has issues off, so asking here). At `a491a5e`: basal and temp basal do not draw down the reservoir (only boluses do), so the reservoir Loop reports, and uploads to Nightscout, follows boluses only; and commands are still applied while the pod is faulted. Would PRs for either be welcome?

Why we care on the Nightscout side: a Loop run against these simulators, uploading to a lab Nightscout, would give us real Loop upload shapes with no person's data, which our server tests currently approximate by hand.
