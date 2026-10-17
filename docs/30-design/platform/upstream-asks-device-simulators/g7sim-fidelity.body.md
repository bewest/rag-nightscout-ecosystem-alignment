**Title:** Emulator strictness and anomaly controls: worth having?

A question rather than a bug. g7sim is the first G7 emulator we know of, and we're looking at how simulators across the ecosystem could cover the same failure cases ([notes](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/10-domain/g7sim-deep-dive.md), §1.3 and §9).

**Strictness.** At `7c039de`, g7sim is more permissive than a real sensor in two places, so a client bug there would pair with g7sim and fail against hardware:
- `g7/handler.go` calls `SetClientRound` for rounds 0 and 1 and does not act on the verdict, so the client's EC-JPAKE round proofs are not enforced (a wrong code still fails later, at the AES challenge, as with a real sensor). G7SensorKit's tests record a constraint the real sensor places on the client's third round (`testRound3UsesTheFixedRandomizer`) that g7sim does not check.
- The display-signature check in the key-challenge step is logged and not enforced ("Advisory for now … so a verification quirk cannot block pairing").

Would a `-strict` flag that rejects these, as the sensor does, be welcome? It could stay off by default.

**Anomaly controls.** faketandem's harness API has a controllable clock and faults armed per message (dropped, delayed or corrupted frames). g7sim has sensor-state controls but not these. Are frame-level faults and a skewable clock in scope?

**Minor:** `simulator/build-impossible.sh` targets `arm64-apple-ios15.0-simulator` only, so Intel Macs are not covered.
