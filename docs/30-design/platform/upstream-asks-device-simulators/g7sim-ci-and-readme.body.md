**Title:** Run the tests in CI, and four README corrections

Thanks for g7sim. We read it closely for a test-tooling survey of the Nightscout ecosystem ([g7sim notes](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/10-domain/g7sim-deep-dive.md)), and two small things came up.

**CI.** At `7c039de` the suite needs no radio, Mac or network: `go test ./...` passes 33 of 33 offline on Go 1.23 (linux/amd64), clean under `-race` and `go vet`, and the linux/arm (GOARM=6) and darwin/arm64 cross-builds succeed. There is no `.github/` yet. A workflow like LoopKit/pod's `ci.yml` (`go test ./...`) would run all of it on every change. Happy to open that PR if you'd like it.

**README**, at `7c039de`:
1. Line 220 names `simulator/impossible-delegate-queue.patch`, which is no longer in the tree. The same fix looks like `simulator/impossible-patches/0001-Report-the-initial-state-on-the-central-s-queue-not-.patch`.
2. Line 332 says the `paypal/gatt` fixes are "noted in the README's library-changes notes"; there is no such section.
3. Line 314 says fresh pairing has not "been run end to end against the app", while the status table (line 30) says "Loop pairs, reads and reconnects in the Simulator". One of the two is out of date.
4. Line 25 lists the calibration offset (and walk glucose and expiry) as "unit tested"; no test touches calibration, walk mode or expiry.
