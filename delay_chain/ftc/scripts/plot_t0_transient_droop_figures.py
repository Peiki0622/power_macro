#!/usr/bin/env python3
"""Render T0 evidence figures from compact, corrected T0 artifacts only.

The plotter never reads raw HSPICE run directories. It consumes checked
analysis CSV/JSON records, preserves blocked stages visibly, and writes only
the task-owned ``analysis/t0_transient_droop/figures`` outputs.
"""

import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

if os.environ.get("CONDA_DEFAULT_ENV") != "DL":
    raise RuntimeError("T0 plotting requires CONDA_DEFAULT_ENV=DL")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image


FTC_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = FTC_ROOT / "analysis" / "t0_transient_droop"
FIGURES = ANALYSIS / "figures"
_CJK_FONT = "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"
font_manager.fontManager.addfont(_CJK_FONT)
matplotlib.rcParams["font.family"] = "Noto Sans CJK JP"
matplotlib.rcParams["axes.unicode_minus"] = False


def sha256_file(path: Path) -> str:
    """Hash compact plotted evidence so every figure is reproducible."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(path: Path) -> List[Dict[str, str]]:
    """Read one rectangular T0 table without silently dropping rows."""

    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def save(stem: str, figure: plt.Figure, sources: List[Path], manifest: List[Dict[str, Any]]) -> None:
    """Write PDF plus 600 dpi PNG and record rendering provenance."""

    FIGURES.mkdir(parents=True, exist_ok=True)
    pdf, png = FIGURES / (stem + ".pdf"), FIGURES / (stem + ".png")
    figure.savefig(pdf, bbox_inches="tight")
    figure.savefig(png, dpi=600, bbox_inches="tight")
    plt.close(figure)
    with Image.open(png) as image:
        width, height, dpi = image.size[0], image.size[1], image.info.get("dpi", (0.0, 0.0))
    if width < 1200 or height < 800 or min(map(float, dpi)) < 590.0:
        raise RuntimeError("T0 figure QA failed: {}".format(stem))
    manifest.append({
        "figure_stem": stem, "pdf": str(pdf), "png": str(png),
        "source_sha256": {str(path): sha256_file(path) for path in sources},
        "plot_script_sha256": sha256_file(Path(__file__)), "python_executable": sys.executable,
        "matplotlib_version": matplotlib.__version__, "conda_env": "DL",
        "png_width_px": width, "png_height_px": height, "png_dpi": [float(dpi[0]), float(dpi[1])],
    })


def main() -> int:
    """Generate honest T0-1 through T0-5 figures after the T0-4 stop."""

    phase_csv = ANALYSIS / "phase_window" / "phase_window.csv"
    phase_json = ANALYSIS / "phase_window" / "summary.json"
    boundary_csv = ANALYSIS / "amplitude_duration" / "minimum_duration_boundary.csv"
    amplitude_json = ANALYSIS / "amplitude_duration" / "summary.json"
    phase_rows, boundary_rows = rows(phase_csv), rows(boundary_csv)
    manifest: List[Dict[str, Any]] = []

    # T0-1 uses a corrected L2 case. Markers are scalar measurements, never
    # invented analog traces, and all fields retain the original deck timing.
    row = next(item for item in phase_rows if item["baseline_vdd_v"] == "0.95" and item["phase_ps"] == "-250.0")
    base, low = float(row["baseline_vdd_v"]), float(row["Vdroop_v"])
    start = 1.49 + float(row["phase_ps"]) / 1000.0
    fall, hold, rise = (float(row[key]) / 1000.0 for key in ("t_fall_ps", "t_hold_ps", "t_rise_ps"))
    figure, axes = plt.subplots(2, 1, figsize=(8.0, 5.2), sharex=True)
    axes[0].plot([0, start, start + fall, start + fall + hold, start + fall + hold + rise, 7.5], [base, base, low, low, base, base], color="black", label="VDD_MONITORED")
    for key, label in (("t_xor_rise_s", "XOR rise"), ("t_ck_rise_s", "CK rise")):
        axes[0].axvline(float(row[key]) * 1e9, linestyle="--", label=label)
    axes[0].set_ylabel("VDD (V)"); axes[0].legend(fontsize=8)
    axes[1].plot([3.79, 3.99], [float(row["q_sample_1_v"]), float(row["q_sample_2_v"])], "o-", color="tab:red", label="真实 DFF Q")
    axes[1].set_xlabel("时间 (ns)"); axes[1].set_ylabel("Q (V)"); axes[1].legend(fontsize=8)
    save("fig_t0_1_representative_waveform", figure, [phase_csv], manifest)

    # T0-2 plots every sampled state so physically disconnected Q1 windows
    # cannot be collapsed into a misleading global phase range.
    figure, axis = plt.subplots(figsize=(7.4, 4.2))
    for baseline, color in ((0.95, "tab:blue"), (1.10, "tab:orange")):
        group = [item for item in phase_rows if float(item["baseline_vdd_v"]) == baseline]
        y = [1 if item["q_final"] == "1" and item["valid"] == "1" else 0 if item["q_final"] == "0" and item["valid"] == "1" else 0.5 for item in group]
        axis.scatter([float(item["phase_ps"]) for item in group], y, label="{:.2f} V".format(baseline), color=color)
    axis.set_xlabel("droop phase 相对 S_CLK (ps)"); axis.set_ylabel("Q 状态（1=检测，0=盲区，0.5=ambiguous）")
    axis.set_yticks([0, 0.5, 1]); axis.legend(); axis.set_title("图 T0-2：单 probe 相位敏感窗口")
    save("fig_t0_2_phase_window", figure, [phase_csv, phase_json], manifest)

    # T0-3/T0-4 show only resolved measurements. Missing values remain gaps;
    # titles explicitly retain the T0-4 STOP rather than asserting continuity.
    for stem, title, group_by_margin in (
        ("fig_t0_3_amplitude_duration_boundary", "图 T0-3：深度—持续时间观测（T0-4 STOP）", False),
        ("fig_t0_4_margin_duration_comparison", "图 T0-4：裕量与最短持续时间（仅已解析点）", True),
    ):
        figure, axis = plt.subplots(figsize=(7.4, 4.2))
        groups = sorted({(item["baseline_vdd_v"], item["margin_level"]) if group_by_margin else (item["baseline_vdd_v"],) for item in boundary_rows})
        for group in groups:
            selected = [item for item in boundary_rows if ((item["baseline_vdd_v"], item["margin_level"]) if group_by_margin else (item["baseline_vdd_v"],)) == group and item["minimum_detectable_hold_ps"]]
            if selected:
                axis.plot([float(item["DeltaV_mv"]) for item in selected], [float(item["minimum_detectable_hold_ps"]) for item in selected], "o-", label=" / ".join(group))
        axis.set_xlabel("跌落深度 ΔV (mV)"); axis.set_ylabel("最短可检 hold (ps)"); axis.set_title(title); axis.legend(fontsize=8)
        save(stem, figure, [boundary_csv, amplitude_json], manifest)

    # T0-5 must remain visibly blocked: T0-4 prevents coverage and cadence
    # inference, so leaving a blank or drawing a speculative curve is invalid.
    figure, axis = plt.subplots(figsize=(7.4, 4.2))
    axis.text(0.5, 0.5, "BLOCKED\nT0-4 ambiguous duration boundary\n未推导 coverage / cadence", ha="center", va="center", transform=axis.transAxes)
    axis.set_xticks([]); axis.set_yticks([]); axis.set_title("图 T0-5：检测间隔—时间覆盖率")
    save("fig_t0_5_cadence_coverage", figure, [amplitude_json], manifest)
    (FIGURES / "figure_manifest.json").write_text(json.dumps({"schema_version": 2, "study": "ftc_t0_transient_voltage_droop_characterization_v1", "figures": manifest}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
