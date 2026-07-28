# Split Audit V1

- Corpus SHA256: `d795e6f3f29812c0fe32985e031541f3518594211f58ef0489c0efb7b59ae290`
- Traces / base waveforms: 96 / 80
- Split counts: {'iid_test': 16, 'ood_test': 16, 'train': 48, 'validation': 16}
- Base-waveform leakage: none
- Hard pairs: 4 complete pairs, all in OOD test
- OOD families excluded from train: ['asymmetric_double_peak', 'glitch_cluster', 'partial_recovery_second_collapse', 'random_walk_collapse', 'rlc_ringing']
- Background coverage: {'bursty': 24, 'busy': 24, 'mixed': 24, 'randomizer_like': 24}
- Event-duty coverage: {'0.01': 7, '0.05': 7, '0.1': 26, '0.25': 26, 'None': 30}
