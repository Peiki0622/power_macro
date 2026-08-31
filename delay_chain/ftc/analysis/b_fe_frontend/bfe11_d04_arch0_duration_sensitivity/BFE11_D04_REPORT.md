# BFE11 D04 ARCH0 duration sensitivity

Gate: `BFE11_D04_ARCH0_DURATION_SENSITIVITY_FROZEN`

| Metric | D04 60 mV / 0.6 ns | D02 60 mV / 3.0 ns frozen baseline |
|---|---:|---:|
| Detection coverage | 24/30 | 30/30 |
| Headroom min / median | -2 / 10.5 | 19 / 38 M-codes |
| First-alarm latency median / worst | 19.334524618567 / 19.334524618567 ns | 20.534524618566998 / 20.534524618566998 ns |

Common ARCH0 margins: RISE=22, FALL=24 M-codes.
Common held-out healthy FPR: 1/240 observed events.
D04 latency is attack-onset referenced. Its approximately 1.2 ns difference from D02 comes from the later D04 onset; the fixed TIM0 capture-to-alarm pipeline remains seven probe edges (E4 to E7 is 7.5 ns).
Interpretation class: PARTIAL_SHORT_PULSE_COVERAGE.
RTL replay gate: BFE11_D04_P6_BOUNDARY_RTL_REPLAY_PASS.

This package freezes only the paired 60 mV duration comparison. It does not implement ARCH1 or authorize waveform/margin retuning.
