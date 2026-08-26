# B-FE2-CAL0 report

Gate: `BFE2_CAL0_SAMPLE_CLOSE_NOT_CALIBRATABLE`

Normal-only VCS W-2024.09 + PrimeSim XA W-2024.09 validation. No L2, M/F code table, FSM, circuit, or sensing-geometry change.
The offline stage used only the accepted normal safe_d crossing ledger and selected three event-free intervals; no dense close grid was simulated.

| Point | sample_close (ps) | G close (ps) | START | END | LEN | CENTER | LEFT_HEADROOM | RIGHT_HEADROOM | Q[29:0] | Ones | source-free | unresolved | mid-rail | tail | post-close safe_d→Q |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|---|---|
| LEFT | 522.695728450 | 1522.695728450 | 515.519619746 | 529.871837153 | 14.352217407 | 522.695728450 | 7.176108704 | 7.176108704 | `000000000000001111111111111000` | 13 | [27] | [27] | [] | [] | [] |
| CENTER | 534.524618567 | 1534.524618567 | 529.871837153 | 538.568650583 | 8.696813430 | 534.220243868 | 4.652781414 | 4.044032016 | `000000000000001111111111111100` | 14 | [] | [] | [] | [] | [] |
| RIGHT | 553.068573070 | 1553.068573070 | 538.568650583 | 567.568495557 | 28.999844974 | 553.068573070 | 14.499922487 | 14.499922487 | `000000000000000111111111111110` | 14 | [29] | [29] | [] | [] | [] |

Ordered ones sequence LEFT/CENTER/RIGHT: `[13, 14, 14]`; local monotonic feature: `True`.
Positive-width stable-window candidates: `True`.
Failure classification: `CAPTURE_SEMANTICS_FAIL` (capture semantics is evaluated separately from spatial discrimination).

LEFT tap27 post-close Q events: `[{'time_ps': 1528.0, 'q_v': 0.474999994, 'classification': 'source-backed', 'direction': 'rise', 'source_event': {'direction': 'rise', 'logic_state': 1, 'time_ps': 1498.554093337465}, 'delay_ps': 29.44590666253498}, {'time_ps': 1544.0, 'q_v': 0.474999994, 'classification': 'source-free', 'direction': 'rise', 'source_event': None, 'delay_ps': None}]`.
CENTER tap27 post-close Q events: `[]`.
RIGHT tap27 post-close Q events: `[]`.
RIGHT tap29 post-close Q events: `[{'time_ps': 1562.0, 'q_v': 0.474999994, 'classification': 'source-backed', 'direction': 'rise', 'source_event': {'direction': 'rise', 'logic_state': 1, 'time_ps': 1529.8718371533118}, 'delay_ps': 32.128162846688156}, {'time_ps': 1565.0, 'q_v': 0.474999994, 'classification': 'source-free', 'direction': 'rise', 'source_event': None, 'delay_ps': None}]`.

Tap24-29 post-close safe_d/Q evidence is retained in the JSON analysis for every point; all post-close safe_d→Q tap lists are expected empty for a capture-semantics pass.

This CAL0 stage stops here regardless of Gate; no self-calibration controller, old M/F reuse, runtime detection, or later phase is authorized.
