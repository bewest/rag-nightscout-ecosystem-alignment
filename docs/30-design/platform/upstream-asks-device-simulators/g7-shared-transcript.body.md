**Where:** NightscoutFoundation/xDrip Discussions (Ideas). Afterwards, a one-line pointer to the discussion in LoopKit/G7SensorKit, LoopKit/g7sim, JohanDegraeve/xdripswift (Discussions), xdrip-js/xdrip-js and j-kaltes/Juggluco (Discussions).

**Title:** One shared test transcript for G7 pairing (EC-JPAKE)

Six code bases now authenticate to G7 / ONE+ / Stelo sensors or play the sensor side: xDrip (`libkeks`), xdrip-js (a port of libkeks), xdripswift, Juggluco, LoopKit/G7SensorKit (`next-dev`) and LoopKit/g7sim (sensor side). None of their tests checks the EC-JPAKE exchange against the same bytes as any other; the only pairing vectors two of them share are two AES-challenge known answers, in G7SensorKit and g7sim. Where tests exist, they check that a client and a sensor written in the same repository agree with each other ([survey](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/60-research/programme/device-simulators-2026-10-17.md#5-the-census-picture-updated)).

**Idea:** one transcript with fixed randomness (the inputs, every message of a complete exchange, and the derived key), kept as a plain file that each implementation's tests replay from either side. pumpX2 does this for Tandem (`SecureRandomMock`), and OpenMinimed's JavaSake replays PythonSake's recorded handshake for Medtronic. g7sim could generate one from its sensor side, and any implementation could check it.

Is this useful to xDrip's maintainers? Where would you want such a file to live?
