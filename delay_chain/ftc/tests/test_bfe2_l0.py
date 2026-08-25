"""Contract checks for the fixed-close B-FE2-L0 evidence package."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
L0 = ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "l0"


def test_l0_manifest_is_fixed_pair_and_zero_hspice():
    manifest = json.loads((L0 / "BFE2_L0_ANALYSIS.json").read_text())
    assert manifest["scenario_ids"] == ["BFE2L-095-N", "BFE2L-095-L2"]
    assert manifest["fixed_sample_close_ps"] == 534.524618567
    assert manifest["new_hspice_scenarios"] == 0
    assert manifest["gate"] == "BFE2_L0_SAFE_DOMAIN_PASS"
    assert manifest["vcs_execution"]["status"] == "passed"
    assert manifest["xa_execution"]["status"] == "passed"


def test_l0_ideal_replay_has_no_post_close_crossing_and_is_distinguishable():
    analysis = json.loads((L0 / "BFE2_L0_ANALYSIS.json").read_text())
    assert analysis["final_q_hamming_distance"] > 0
    for result in analysis["results"]:
        assert result["all_q_full_swing"]
        assert result["q_stable"]
        assert result["post_close_q_crossings"] == []
