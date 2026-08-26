# B-FE2-CAL0 capture-safe repair report

Gate: `BFE2_CAL0_CAPTURE_SAFE_WINDOW_BLOCKED`
Blocking reason: `NO_CAPTURE_SAFE_INTERVALS_NEAR_NOMINAL`.

Normal-only 0.95 V evidence; no L2, no dense sweep, no circuit/geometry/control change.
The old event-free intervals were re-evaluated by subtracting measured per-tap D→Q in-flight windows.
Q event direction is derived from Q state before/after each event; safe_d_v is not used for direction.

| Legacy point | sample_close (ps) | G close (ps) | START | END | LEN | CENTER | LEFT/RIGHT_HEADROOM | Q[29:0] | Ones | Corrected source-free | Corrected unresolved | mid-rail | tail | post-close safe_d→Q |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---|---|---|---|
| LEFT | 522.695728450 | 1522.695728450 | 515.519619746 | 529.871837153 | 14.352217407 | 522.695728450 | 7.176108704/7.176108704 | `000000000000001111111111111000` | 13 | [27] | [27] | [] | [] | [] |
| CENTER | 534.524618567 | 1534.524618567 | 529.871837153 | 538.568650583 | 8.696813430 | 534.220243868 | 4.652781414/4.044032016 | `000000000000001111111111111100` | 14 | [] | [] | [] | [] | [] |
| RIGHT | 553.068573070 | 1553.068573070 | 538.568650583 | 567.568495557 | 28.999844974 | 553.068573070 | 14.499922487/14.499922487 | `000000000000000111111111111110` | 14 | [29] | [29] | [] | [] | [] |

Capture-safe intervals in the old LEFT/CENTER/RIGHT local envelope: `[]`.
Selected capture-safe points: `[]`; new VCS+XA scenarios launched: `0`.

Corrected LEFT tap27 events: `[{'time_ps': 1528.0, 'q_v': 0.474999994, 'q_state_before': 0, 'q_state_after': 1, 'direction': 'rise', 'classification': 'source-backed', 'source_event': {'direction': 'rise', 'logic_state': 1, 'time_ps': 1498.554093337465}, 'delay_ps': 29.44590666253498}, {'time_ps': 1544.0, 'q_v': 0.474999994, 'q_state_before': 1, 'q_state_after': 0, 'direction': 'fall', 'classification': 'source-free', 'source_event': None, 'delay_ps': None}]`.
Corrected RIGHT tap29 events: `[{'time_ps': 1562.0, 'q_v': 0.474999994, 'q_state_before': 0, 'q_state_after': 1, 'direction': 'rise', 'classification': 'source-backed', 'source_event': {'direction': 'rise', 'logic_state': 1, 'time_ps': 1529.8718371533118}, 'delay_ps': 32.128162846688156}, {'time_ps': 1565.0, 'q_v': 0.474999994, 'q_state_before': 1, 'q_state_after': 0, 'direction': 'fall', 'classification': 'source-free', 'source_event': None, 'delay_ps': None}]`.

The in-flight windows overlap across the nominal neighborhood, so no representative point was eligible for a new XA run. This repair stage stops here; no self-calibration, runtime detection, FSM, M/F reuse, or later phase is authorized.
