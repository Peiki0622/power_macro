#!/usr/bin/env python3
"""Publish the D0-0 runtime-probe timing feasibility budget without HSPICE.

This is deliberately a small, read-only analysis.  It consumes the frozen M0
single-probe event contract, the completed T0 cadence requirement, and the M1
handoff boundary.  It does not render a deck, import an HSPICE wrapper, or
modify any sensor/control contract.  Its sole purpose is to decide whether
those already-proven event separations can form a continuous D0 probe whose
successive ``S_CLK`` rising edges are no farther apart than T0 requires.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping


# All paths are rooted at ``delay_chain/ftc`` so this analysis remains
# relocatable with the repository.  The three inputs are published contracts,
# not live RTL or a simulator run directory: D0-0 must only reason from the
# completed evidence and must leave the frozen producers untouched.
FTC_ROOT = Path(__file__).resolve().parents[1]
M0_CONTRACT_PATH = FTC_ROOT / "analysis" / "m0_detection_margin_characterization" / "probe_contract" / "single_probe_contract.json"
T0_CONTRACT_PATH = FTC_ROOT / "analysis" / "t0_transient_droop" / "contract" / "T0_DOWNSTREAM_D0_TIMING_CONTRACT.json"
M1_HANDOFF_PATH = FTC_ROOT / "controller" / "m1_detection_margin" / "contract" / "M1_DOWNSTREAM_T0_D0_HANDOFF.json"

# D0-0 owns only this new evidence directory and report.  No existing T0
# contract is rewritten: T0 remains the authority for the 2.075 ns coverage
# requirement, while this artifact records whether the frozen single-probe
# timing can satisfy that downstream requirement continuously.
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "d0_runtime_timing"
OUTPUT_CONTRACT_PATH = ANALYSIS_ROOT / "contract" / "D0_0_RUNTIME_TIMING_BUDGET.json"
REPORT_PATH = FTC_ROOT / "reports" / "FTC_D0_RUNTIME_TIMING_FEASIBILITY.md"


def read_json(path: Path) -> Dict[str, Any]:
    """Load one required object contract and reject malformed evidence early."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("{} must contain one JSON object".format(path))
    return value


def sha256_file(path: Path) -> str:
    """Return the content hash used to bind the budget to its exact inputs."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def seconds_to_ps(value_s: float) -> float:
    """Convert a contract timestamp to a stable picosecond contract value.

    The source times are decimal nanosecond quantities.  Rounding only the
    binary conversion residue to six decimal ps keeps JSON deterministic while
    preserving far more precision than any frozen event separation requires.
    """

    return round(float(value_s) * 1.0e12, 6)


def require_number(mapping: Mapping[str, Any], key: str, context: str) -> float:
    """Read one mandatory numeric event timestamp with an actionable error."""

    value = mapping.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError("{} is missing numeric {}".format(context, key))
    return float(value)


def build_budget() -> Dict[str, Any]:
    """Derive the D0-0 decision solely from the published frozen contracts.

    The calculation intentionally does *not* claim that 3.20 ns is a verified
    continuous cadence.  It is merely the most optimistic serial-reset lower
    bound before asking whether the unverified 2.70 ns recovery tail can
    overlap the following probe.  A requirement below that lower bound cannot
    be repaired by a D0 FSM, because it demands a new ``S_CLK`` rise before
    the current probe has completed its frozen Q/reset protocol.
    """

    m0 = read_json(M0_CONTRACT_PATH)
    t0 = read_json(T0_CONTRACT_PATH)
    m1 = read_json(M1_HANDOFF_PATH)

    timing_s = m0.get("timing_s")
    q_decision = m0.get("q_decision")
    if not isinstance(timing_s, dict) or not isinstance(q_decision, dict):
        raise ValueError("M0 single-probe contract lacks timing_s or q_decision")
    if q_decision.get("two_samples_required") is not True:
        raise ValueError("D0-0 requires M0's frozen two-sample Q decision")
    if q_decision.get("trip_decision") != "stable_real_dff_q_equals_1":
        raise ValueError("D0-0 requires the frozen real-DFF Q decision")

    runtime = t0.get("runtime_probe_period")
    control_clock = t0.get("control_clock_reference")
    if not isinstance(runtime, dict) or not isinstance(control_clock, dict):
        raise ValueError("T0 downstream contract lacks cadence definitions")
    if control_clock.get("is_runtime_probe_cadence") is not False:
        raise ValueError("T0 control clock must remain distinct from runtime probes")
    required_period_ps = float(runtime["maximum_period_ps"])

    # Translate the published absolute one-probe timestamps to offsets from
    # the current probe's S_CLK rise.  This makes the continuous-cadence
    # contradiction independent of M0's arbitrary 1 ns simulation prelude.
    reset_release_ps = seconds_to_ps(require_number(timing_s, "reset_release_s", "M0 timing_s"))
    sclk_rise_ps = seconds_to_ps(require_number(timing_s, "launch_time_s", "M0 timing_s"))
    q1_ps = seconds_to_ps(require_number(timing_s, "q_read_time_s", "M0 timing_s"))
    q2_ps = seconds_to_ps(require_number(timing_s, "q_read_late_time_s", "M0 timing_s"))
    reset_assert_start_ps = seconds_to_ps(require_number(timing_s, "reset_assert_start_s", "M0 timing_s"))
    reset_assert_end_ps = seconds_to_ps(require_number(timing_s, "reset_assert_end_s", "M0 timing_s"))
    sclk_fall_ps = seconds_to_ps(require_number(timing_s, "sclk_fall_s", "M0 timing_s"))
    recovery_end_ps = seconds_to_ps(require_number(timing_s, "recovery_end_s", "M0 timing_s"))

    offsets = {
        "reset_release": reset_release_ps - sclk_rise_ps,
        "sclk_rise": 0.0,
        "q_sample_1": q1_ps - sclk_rise_ps,
        "q_sample_2": q2_ps - sclk_rise_ps,
        "reset_assert_start": reset_assert_start_ps - sclk_rise_ps,
        "reset_assert_end": reset_assert_end_ps - sclk_rise_ps,
        "sclk_fall": sclk_fall_ps - sclk_rise_ps,
        "recovery_end": recovery_end_ps - sclk_rise_ps,
    }

    # A valid next probe needs its own reset release before its own S_CLK rise.
    # The current probe first completes the required Q2 sample, then its reset
    # is asserted for the recorded pulse width.  Adding the same frozen
    # release-to-rise separation gives the *optimistic* serial-reset lower
    # bound.  It deliberately excludes recovery, so failing it is conclusive.
    reset_release_to_rise_ps = sclk_rise_ps - reset_release_ps
    q2_to_reset_assert_ps = reset_assert_start_ps - q2_ps
    reset_assert_width_ps = reset_assert_end_ps - reset_assert_start_ps
    q2_completion_lower_bound_ps = offsets["q_sample_2"]
    reset_serial_lower_bound_ps = (
        offsets["q_sample_2"]
        + q2_to_reset_assert_ps
        + reset_assert_width_ps
        + reset_release_to_rise_ps
    )

    # These two additional constraints are recorded separately rather than
    # folded into the serial-reset bound.  S_CLK remains high until 3.00 ns,
    # so a second rise at 2.075 ns would not be an electrical rising edge.
    # Recovery ends only at 5.70 ns; existing one-probe evidence cannot claim
    # that a following probe may overlap that tail.
    sclk_high_width_ps = offsets["sclk_fall"]
    full_recovery_reference_ps = offsets["recovery_end"]

    # At the requested maximum period, all values below are positive elapsed
    # amounts *after* the requested next rise.  They show exactly which frozen
    # current-probe operations would still be unfinished at that moment.
    unfinished_at_deadline_ps = {
        "q_sample_1_after_next_rise_ps": offsets["q_sample_1"] - required_period_ps,
        "q_sample_2_after_next_rise_ps": offsets["q_sample_2"] - required_period_ps,
        "reset_assert_start_after_next_rise_ps": offsets["reset_assert_start"] - required_period_ps,
        "sclk_fall_after_next_rise_ps": offsets["sclk_fall"] - required_period_ps,
        "recovery_end_after_next_rise_ps": offsets["recovery_end"] - required_period_ps,
    }

    if any(value <= 0.0 for value in unfinished_at_deadline_ps.values()):
        raise ValueError("published M0/T0 inputs no longer demonstrate the expected D0-0 conflict")
    if reset_serial_lower_bound_ps <= required_period_ps:
        raise ValueError("frozen serial-reset lower bound no longer blocks the T0 cadence")

    return {
        "schema_version": 1,
        "study": "ftc_d0_runtime_timing_feasibility_v1",
        "stage": "D0-0",
        "decision": "ARCHITECTURE_REVIEW",
        "decision_basis": "zero_hspice_frozen_contract_timing_budget",
        "input_sha256": {
            "m0_single_probe_contract": sha256_file(M0_CONTRACT_PATH),
            "t0_downstream_d0_timing_contract": sha256_file(T0_CONTRACT_PATH),
            "m1_downstream_t0_d0_handoff": sha256_file(M1_HANDOFF_PATH),
        },
        "input_paths": {
            "m0_single_probe_contract": str(M0_CONTRACT_PATH.relative_to(FTC_ROOT)),
            "t0_downstream_d0_timing_contract": str(T0_CONTRACT_PATH.relative_to(FTC_ROOT)),
            "m1_downstream_t0_d0_handoff": str(M1_HANDOFF_PATH.relative_to(FTC_ROOT)),
        },
        "scope": {
            "frozen_contracts_modified": [],
            "m1_output_configuration": "STATIC_UNMODIFIED",
            "m1_boundary_condition": m1.get("entry_condition_for_t0_d0"),
            "forbidden_implementations": [
                "d0_fsm",
                "alarm",
                "heartbeat",
                "timeout",
                "sensor_or_m_f_topology_change",
                "h0_m0_m1_t0_rerun",
            ],
        },
        "runtime_requirement": {
            "probe_reference_event": "successive S_CLK rising edges",
            "maximum_period_ps": required_period_ps,
            "maximum_period_s": required_period_ps * 1.0e-12,
            "source_status": runtime.get("status"),
            "control_clock_is_runtime_probe_cadence": False,
            "control_clock_period_ps": float(control_clock["period_ps"]),
        },
        "frozen_single_probe_evidence": {
            "q_decision": {
                "two_samples_required": True,
                "trip_decision": q_decision["trip_decision"],
                "q_high_ratio": float(q_decision["q_high_ratio"]),
                "q_low_ratio": float(q_decision["q_low_ratio"]),
            },
            "event_offsets_from_sclk_rise_ps": offsets,
            "verified_event_intervals_ps": {
                "reset_release_to_sclk_rise": reset_release_to_rise_ps,
                "sclk_rise_to_q_sample_1": offsets["q_sample_1"],
                "q_sample_1_to_q_sample_2": offsets["q_sample_2"] - offsets["q_sample_1"],
                "q_sample_2_to_reset_assert_start": q2_to_reset_assert_ps,
                "reset_assert_width": reset_assert_width_ps,
                "reset_assert_end_to_sclk_fall": offsets["sclk_fall"] - offsets["reset_assert_end"],
                "sclk_fall_to_recovery_end": offsets["recovery_end"] - offsets["sclk_fall"],
            },
        },
        "timing_budget": {
            "q2_completion_lower_bound_ps": q2_completion_lower_bound_ps,
            "q2_completion_shortfall_to_requirement_ps": q2_completion_lower_bound_ps - required_period_ps,
            "sclk_high_width_lower_bound_ps": sclk_high_width_ps,
            "sclk_high_width_shortfall_to_requirement_ps": sclk_high_width_ps - required_period_ps,
            "optimistic_serial_reset_to_next_rise_lower_bound_ps": reset_serial_lower_bound_ps,
            "serial_reset_shortfall_to_requirement_ps": reset_serial_lower_bound_ps - required_period_ps,
            "full_recovery_nonoverlap_reference_ps": full_recovery_reference_ps,
            "full_recovery_shortfall_to_requirement_ps": full_recovery_reference_ps - required_period_ps,
            "unfinished_current_probe_events_at_required_next_rise_ps": unfinished_at_deadline_ps,
        },
        "candidate_microsequence": {
            "available": False,
            "reason": "No <= 2075 ps sequence can preserve the frozen two-Q-sample, reset, and S_CLK event order: the optimistic serial-reset lower bound alone is 3200 ps.",
            "why_no_multi_probe_hspice": "A valid <= 2075 ps waveform cannot be constructed from the frozen single-probe separations. HSPICE is therefore not used to guess a changed waveform; defining such a waveform requires the architecture review first.",
        },
        "architecture_review": {
            "blocking_structure": "single real DFF capture path with one S_CLK waveform, two required stable Q observations, and reset between probes",
            "required_question": "Provide a physically justified capture/reset architecture or revised timing contract that can complete two independent Q observations and a reset cycle within 2075 ps before any new multi-probe simulation is proposed.",
            "not_a_digital_logic_fix": True,
        },
        "simulation_accounting": {
            "hspice_scenarios": 0,
            "new_hspice_scenarios": 0,
            "reused_hspice_scenarios": 0,
            "rerun_t0_3_or_t0_4": 0,
            "method": "published_contract_arithmetic_only",
        },
    }


def build_report(budget: Mapping[str, Any]) -> str:
    """Render the human-readable D0-0 conclusion from the same JSON values."""

    offsets = budget["frozen_single_probe_evidence"]["event_offsets_from_sclk_rise_ps"]
    timing = budget["timing_budget"]
    required = budget["runtime_requirement"]["maximum_period_ps"]
    unfinished = timing["unfinished_current_probe_events_at_required_next_rise_ps"]
    return """# FTC D0-0 运行时 probe 微时序可行性

## 结论

**ARCHITECTURE_REVIEW**。在不修改冻结 `FTC_SENSOR`、H0、M1、T0 合同和既有物理证据的条件下，不能构造 `P_runtime <= {required:.0f} ps` 的连续 probe 微时序。D0-0 没有实现 FSM、alarm、heartbeat 或 timeout，也没有改变 M1 的静态 M/F 输出配置。

本结论是零 HSPICE 的合同算术，不把 400 MHz / 2.5 ns 控制时钟等同于 runtime probe，也不把现有 5.70 ns one-shot 参考直接压缩为新设计。

## 已复用的冻结证据

| 从本 probe 的 `S_CLK rise` 起 | 已验证事件 | 偏移 (ps) |
|---|---:|---:|
| -490 | reset release | {reset_release:.0f} |
| 0 | `S_CLK rise` | 0 |
| +{q1:.0f} | Q sample 1 | {q1:.0f} |
| +{q2:.0f} | Q sample 2 / 双采样判决完成 | {q2:.0f} |
| +{reset_assert_start:.0f} | reset assert start | {reset_assert_start:.0f} |
| +{reset_assert_end:.0f} | reset assert end | {reset_assert_end:.0f} |
| +{sclk_fall:.0f} | `S_CLK fall` | {sclk_fall:.0f} |
| +{recovery_end:.0f} | recovery end | {recovery_end:.0f} |

M0 的真实 DFF 判定仍是两次稳定 Q 采样都满足阈值后的 `stable_real_dff_q_equals_1`；本轮未以残余时间或数字推断替代它。

## 连续 probe 的最早合法关系

令当前 `S_CLK rise` 为 `t=0`。下一次 probe 自己的 reset release 必须先于下一次 `S_CLK rise` 490 ps。当前 probe 又必须先完成 Q2、随后 reset assert 200 ps、保持 reset 10 ps。因此在**甚至尚未要求 recovery 完成**的最乐观串行预算中：

```text
Q2 complete                  = 2500 ps
Q2 -> reset assert start     =  200 ps
reset assert width           =   10 ps
next reset release -> rise   =  490 ps
------------------------------------------------
next S_CLK rise earliest     = 3200 ps
```

这个 3200 ps 只是下界，不是已经验证的连续 cadence：现有 `S_CLK` 本身到 3000 ps 才 fall，内部 recovery 到 5700 ps 才结束。它们不能被当作可以免费重叠的时间。

若强制按 T0 要求在 {required:.0f} ps 发起下一次 rise，当前 probe 仍有下列动作尚未发生：

| 当前 probe 未完成事件 | 相对该错误 next rise 的滞后 (ps) |
|---|---:|
| Q sample 1 | {q1_late:.0f} |
| Q sample 2 | {q2_late:.0f} |
| reset assert start | {reset_assert_late:.0f} |
| `S_CLK fall` | {sclk_fall_late:.0f} |
| recovery end | {recovery_late:.0f} |

最直接的矛盾是 Q2 本身在 {q2:.0f} ps，已经比目标周期晚 {q2_shortfall:.0f} ps；完整的 reset→下一 rise 串行下界则比目标周期晚 {serial_shortfall:.0f} ps。因而无法用冻结单 capture DFF/控制时序得到一次真实、可重复的双采样判决和相邻 reset 周期。

## HSPICE 与范围边界

本轮 HSPICE = 0；没有重跑 T0-3、T0-4、M0、M1、H0、RF 或 XA。没有提出多 probe HSPICE deck，因为合同算术已表明没有一个保持冻结事件关系的 `<= {required:.0f} ps` 候选序列；在此之前人为猜测更早 fall、更早 reset 或重叠 capture 的波形，会先改变本阶段禁止改动的时序前提。

需要架构评审的具体瓶颈是：单一真实 DFF capture 路径需要一个 `S_CLK` 波形、两次独立稳定 Q 观察以及 probe 间 reset，而这些已验证事件在目标周期内无法串行完成。不能以更复杂的数字 FSM 掩盖这一物理/时序矛盾。

## Provenance

| 输入 | SHA-256 |
|---|---|
| M0 single-probe contract | `{m0_hash}` |
| T0 downstream D0 timing contract | `{t0_hash}` |
| M1 downstream handoff | `{m1_hash}` |

机器可读预算：[D0_0_RUNTIME_TIMING_BUDGET.json](../analysis/d0_runtime_timing/contract/D0_0_RUNTIME_TIMING_BUDGET.json)。
""".format(
        required=required,
        reset_release=offsets["reset_release"],
        q1=offsets["q_sample_1"],
        q2=offsets["q_sample_2"],
        reset_assert_start=offsets["reset_assert_start"],
        reset_assert_end=offsets["reset_assert_end"],
        sclk_fall=offsets["sclk_fall"],
        recovery_end=offsets["recovery_end"],
        q1_late=unfinished["q_sample_1_after_next_rise_ps"],
        q2_late=unfinished["q_sample_2_after_next_rise_ps"],
        reset_assert_late=unfinished["reset_assert_start_after_next_rise_ps"],
        sclk_fall_late=unfinished["sclk_fall_after_next_rise_ps"],
        recovery_late=unfinished["recovery_end_after_next_rise_ps"],
        q2_shortfall=timing["q2_completion_shortfall_to_requirement_ps"],
        serial_shortfall=timing["serial_reset_shortfall_to_requirement_ps"],
        m0_hash=budget["input_sha256"]["m0_single_probe_contract"],
        t0_hash=budget["input_sha256"]["t0_downstream_d0_timing_contract"],
        m1_hash=budget["input_sha256"]["m1_downstream_t0_d0_handoff"],
    )


def write_outputs(budget: Mapping[str, Any]) -> None:
    """Write only the dedicated D0-0 contract and report in stable form."""

    OUTPUT_CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_CONTRACT_PATH.write_text(
        json.dumps(budget, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(build_report(budget), encoding="utf-8")


def main() -> None:
    """Execute the read-only budget and publish its two deterministic outputs."""

    write_outputs(build_budget())


if __name__ == "__main__":
    main()
