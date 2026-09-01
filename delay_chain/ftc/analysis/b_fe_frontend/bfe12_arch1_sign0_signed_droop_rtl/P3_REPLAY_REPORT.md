# BFE12 P3 Retained Replay Pack

Gate: `BFE12_SIGN0_P3_RETAINED_REPLAY_PACK_FROZEN`

The offline builder validated all 30 RISE/FALL calibration epochs with the
frozen `(sum4 >> 2)` arithmetic and emitted 690 deterministic events: 240
healthy FPR, 360 healthy signed-RISE audit, and 30 each for D01, D02, and D04.
It recomputed signed error and strict `T_POS_RISE=18/19` expectations directly
from the retained rows.  The frozen coverage, healthy FPR, signed maximum, and
recovered seed lists all matched exactly.  No simulator or physical tool was
invoked in P3.

The machine-readable contract is `P3_REPLAY_MANIFEST.csv` plus its summary
`P3_REPLAY_MANIFEST.json`; the generator is
`p3_replay/build_bfe12_replay_pack.py`.
