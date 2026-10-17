**Where:** comment on mickeyl/ImpossiBLE#6.

Context for reviewing #2–#6, in case it helps: two simulators now serve apps in the iOS Simulator through ImpossiBLE, LoopKit/g7sim (a Dexcom G7 emulator) and LoopKit/pod (an Omnipod DASH emulator), and g7sim's `impossible-mux` runs both against one app. g7sim builds ImpossiBLE 3.1.0 (`58fe38d`) with these PRs applied as patches (`simulator/impossible-patches/0001`–`0006`), so with them merged it could build from a release. They are used to exercise diabetes-device drivers (Loop) in the Simulator without hardware. Thanks for ImpossiBLE.
