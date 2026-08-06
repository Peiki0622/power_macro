# CNN Microarchitecture Search

## Status

`SELECTED`

The Stage 1 search binds the frozen [18,8,18] W8/A8 package and does not add RTL, permutation, PRNG, or numerical changes.

## Frozen Inputs

| Item | Value |
| --- | --- |
| Checkpoint SHA256 | `2ee30cdac4ee114c1b2a50d34289ecc84a2c885409b9a386032f56a03cca8c4d` |
| Package manifest SHA256 | `553f6093092724c767b416678f9db1ac33fd1825b6f7f592af1ce2d4aa8086fd` |
| Search configuration SHA256 | `b5c60786036b9a1c4ae62ed1df73cd217289c71bcc70ffcf97f87fecddc1fd8f` |
| Source Git commit | `4f1fccd68bcc829fc2d5382e2773e00b436669f3` |
| Model | channels [18,8,18], kernels [5,5,5], L32, W8/A8 |

## Dataflow Evidence

The NumPy integer replay matched all 8 exported golden windows.  A sliding update changes every logical input position; same padding and the folded Conv1 [18,32] position-dependent bias require all 32 Conv1, Conv2, and Conv3 positions to be recomputed.

| Mode | Conv1 positions | Conv2 positions | Conv3 positions | Pool work | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Full L32 | 32 | 32 | 32 | 32 | Reference schedule |
| Sliding incremental | 32 | 32 | 32 | 32 | Bit-exact only with full-window work |

## MAC Search

The original stride set [1,2,4,8,16,32] was tested first, followed by the frozen extension [64,128,256,512,1024].  At a 2 ns compute period and 4 ns sample period, the latency and II budget is `2 * stride` cycles.

| MACs | Fastest candidate | Latency | II |
| ---: | --- | ---: | ---: |
| 16 | `m16_o2_p8_f1_b16_w16` | 3565 | 3566 |
| 32 | `m32_o2_p16_f1_b16_w16` | 1813 | 1814 |
| 64 | `m64_o2_p32_f1_b16_w16` | 937 | 938 |
| 128 | `m128_o4_p32_f1_b16_w16` | 527 | 528 |

## Selected Microarchitecture

The first feasible target is stride 512 (1024 cycles).  The selected candidate is on that target's Pareto frontier and has the lowest frozen equal-weight normalized resource score; ties are broken by MAC count, latency, storage, and candidate ID.

| Field | Selected value |
| --- | --- |
| Candidate | `m64_o2_p32_f1_b1_w2` |
| MAC count | 64 |
| Output-channel parallelism | 2 |
| Position parallelism | 32 |
| Fan-in parallelism | 1 |
| Conv weight banks / read width | 1 banks / 2 W8 words per bank cycle |
| Conv1 / Conv2 / Conv3 cycles | 90 / 380 / 405 |
| Pool / classifier cycles | 3 / 59 |
| Latency / II | 937 / 938 cycles |
| MAC utilization | 0.818236 |
| Average / peak weight bandwidth | 1.748132 / 2 words per cycle |
| Total parameter storage | 22008 bits (2751 bytes ceiling) |
| Conv W8 / bias / requant / classifier bits | 12240 / 8604 / 300 / 902 |
| Area / energy proxy | 2817 / 112082 relative units |

The area and energy fields are scheduling proxies only.  They are not synthesis area, timing signoff, or physical power results.

## Stage Gate

- Cycle model runs with explicit ROM, requantization, writeback, pooling, and classifier events.
- Full-window and sliding-incremental modes were both evaluated; the latter has no work reduction for this frozen model.
- MAC count, parallelism, bank count, and read width are selected from exhaustive model results rather than legacy RTL cycles.
- Latency and II meet the selected stride-512 budget of 1024 cycles.
- Stage 2 may proceed with this selected configuration and must preserve the same W8/A8 contract.
