**Title:** Bring the ImpossiBLE detection (#188) to dev

**Which OSAID app:** Loop and Trio (development builds in the iOS Simulator).

#188 (`e60e0ab`, "Talk to a simulated pod when the Simulator has Bluetooth") merged to `next-dev` on 2026-10-12. It is not on `dev` (`928bb79`) or `main` (`4e923d7`), and the OmnipodKit that LoopWorkspace and Trio pin (`928bb79` on their `dev`, `043b91d` in Loop v3.14.9 and Trio v1.0.2) mocks pod commands in the Simulator.

With it on `dev`, Simulator builds of both apps could talk to LoopKit/pod over ImpossiBLE (pod's `-transport impossible`, since pod #21), so driver code runs against a pod instead of the mocks. Outside the Simulator, and in the Simulator without the bridge, behaviour is unchanged (`mocksPod` only switches when `CBSPeripheral` is present).

Would a PR cherry-picking #188 to `dev` be welcome? Notes: [pod simulator](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/10-domain/omnipod-pod-simulator-deep-dive.md) §10.
