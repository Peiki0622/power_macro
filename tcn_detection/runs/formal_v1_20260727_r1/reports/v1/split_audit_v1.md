# Split Audit V1

- Corpus SHA256: `d566f2978188c793012bc39e6cb56a3c4de7f35d67dc603bcefa2e5e74f45899`
- Traces / base waveforms: 240 / 224
- Split counts: {'iid_test': 40, 'ood_test': 40, 'train': 120, 'validation': 40}
- Base-waveform leakage: none
- Hard pairs: 12 complete pairs, all in OOD test
- OOD families excluded from train: ['asymmetric_double_peak', 'glitch_cluster', 'hard_pair_same_amplitude_different_hold', 'hard_pair_same_current_code_future_trend', 'hard_pair_same_minimum_different_fall_rate', 'hard_pair_same_saturation_different_duration', 'hard_pair_same_slope_different_future', 'partial_recovery_second_collapse', 'random_walk_collapse', 'rlc_ringing']
- Background coverage: {'bursty': 64, 'busy': 64, 'mixed': 64, 'randomizer_like': 24, 'unseen_multiscale_bursty': 24}
- Event-duty coverage: {'0.01': 17, '0.05': 17, '0.1': 74, '0.25': 74, 'None': 58}
