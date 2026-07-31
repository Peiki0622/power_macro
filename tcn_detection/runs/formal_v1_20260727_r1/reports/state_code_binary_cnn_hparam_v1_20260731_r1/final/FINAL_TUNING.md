# Binary CNN Training Hyperparameter Tuning

This report uses train/validation artifacts only. It does not load, score, or rerun IID and therefore does not replace the existing one-shot release evaluation.

## Aggregate Validation Metrics

| Metric | Original lr=1e-3/wd=1e-4 | PR-AUC rank winner | Quality-feasible recommendation |
| --- | ---: | ---: | ---: |
| Median Critical PR-AUC | 0.833067 | 0.863615 | 0.851604 |
| Median Accuracy | 0.971215 | 0.982898 | 0.981432 |
| Median balanced accuracy | 0.920540 | 0.973239 | 0.969382 |
| Median Macro-F1 | 0.889535 | 0.934884 | 0.929364 |
| Worst-seed Critical recall | 0.861666 | 0.865795 | 0.951824 |
| Median Safe FAR | 0.021274 | 0.015860 | 0.016525 |
| Pass all frozen validation gates | False | False | True |

## Recommendation

- Optimizer: AdamW, learning rate `0.003`, weight decay `1e-05`.
- Unchanged: batch 256, max epochs 80, patience 12, natural CE.
- Representative seed: `20260725`; best epoch: `17`.
- Representative checkpoint SHA256: `3b690b8124d0ba4d5b4f6650a7ee348a5f2d0f2c8ea8dcf763bf9f89b562a2e9`.
- IID features loaded: `false`; IID metrics computed: `false`.
- This is a next-release validation candidate, not a new IID result.
