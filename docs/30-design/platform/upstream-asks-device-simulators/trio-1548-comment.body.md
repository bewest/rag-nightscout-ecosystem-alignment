**Where:** comment on nightscout/Trio#1548 (a short version can go to Trio Discord first).

Thanks for this. A suggestion that would let this PR be exercised without a sensor: the G7SensorKit branch it pins, loopandlearn/G7SensorKit `feat/trio-g7-direct` (`5c0fc07`), has the direct connection (`7da3b69`) but not LoopKit/G7SensorKit #89 (`8fa9c73`, "Pair for real in the Simulator when a Bluetooth bridge is injected"); the branch is 4 commits behind `next-dev` there.

With #89, a Trio Simulator build could pair with LoopKit/g7sim, which plays the sensor side (EC-JPAKE pairing, reconnect, backfill, warm-up and expiry). #89 only changes behaviour when the bridge is injected. Notes: [g7sim](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/10-domain/g7sim-deep-dive.md) §6–§7.
