# Final Compression Gate

Status: `CNN_COMPRESSION_V1_NO_FEASIBLE_CANDIDATE`

No validation-only candidate met both the fixed quality gates and the required 50% MAC reduction.

| Evidence | Result |
| --- | --- |
| Best observed MAC/window | 89708 |
| Best observed MAC reduction | 15.90% |
| Strict single-seed sub-50% candidates | 0 |
| Step 8 kernel crop | skipped: no strict quality margin |
| Step 9 three-seed validation | not run: no eligible candidate |
| Step 10 Teacher Assistant | skipped: assistant prerequisite absent |
| Step 11 float freeze | not frozen |
| Step 12 W8/A8 | not run: no frozen float candidate |

All reports used train/validation only; IID/OOD features and metrics were not loaded. Existing RTL, ROM, cycle model, and task-three power codebook were not modified.

## Required Conclusions

1. **Layer sensitivity and redundancy.** The short-recovery scan failed its
   Critical Recall gate at width 16 for every layer. Conv1 had the largest
   recall loss (0.959394), so it is the most sensitive under this contract.
   No layer can be called safely redundant; Conv2 had the smallest AP loss at
   width 16 but still failed the recall gate.
2. **Importance methods.** Taylor rankings were computed per Safe/Critical
   class and combined by the fixed normalized elementwise maximum. L1/L2
   filter norms were recorded as audit-only controls; they were not substituted
   for Taylor in any pruning decision.
3. **Recovery comparison.** Ordinary recovery reached AP/Recall
   `0.897373/0.962147` at `[16,16,18]`. The best logit-KD arm reached
   `0.897433/0.969030`; the best feature-KD arm reached
   `0.897354/0.972471`. Neither passed the strict single-seed gate.
4. **Complexity.** The best observed compact student has 2,960 parameters and
   89,708 MAC/window versus the Teacher's 3,494 parameters and 106,668
   MAC/window: reductions of 15.3% and 15.9%, below the required 50% MAC gate.
5. **Safety metrics.** The best observed Safe FAR was `0.011159`, lower than
   the Teacher's `0.012679`; this improvement does not offset the Critical
   Recall failure. No formal worst-seed Recall exists because Step 9 had no
   eligible candidate.
6. **Kernel and quantization decisions.** Kernel cropping was skipped because
   no candidate had strict-quality margin. W8/A8 was not run because no float
   candidate was frozen; therefore no quantized quality claim is made.
7. **Hardware handoff.** The result is evidence for a validation-only
   compression attempt, not a deployable model. A new RTL/ROM/latency and
   task-three power-codebook plan is required only after a future feasible
   floating-point candidate is found. No existing RTL or power codebook was
   changed here.
