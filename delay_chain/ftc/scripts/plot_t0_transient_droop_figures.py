#!/usr/bin/env python3
"""Generate the reproducible T0-8 figures and manifest.

The T0-2 STOP is intentional.  Consequently the later phase tables contain
an explicit ``BLOCKED`` row rather than invented measurements.  This plotter
still emits all five required figure slots so reviewers can distinguish an
unmeasured result from a silently omitted result.
"""

import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

if os.environ.get("CONDA_DEFAULT_ENV") != "DL":
    raise RuntimeError("T0 plotting requires CONDA_DEFAULT_ENV=DL")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image

# The container provides a checked-in system font rather than a conda-local
# font package.  Selecting it explicitly keeps Chinese labels complete and
# makes headless PDF/PNG rendering deterministic across T0 invocations.
_CJK_FONT = "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"
font_manager.fontManager.addfont(_CJK_FONT)
matplotlib.rcParams["font.family"] = "Noto Sans CJK JP"
matplotlib.rcParams["axes.unicode_minus"] = False


FTC_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = FTC_ROOT / "analysis" / "t0_transient_droop"
FIGURES = ANALYSIS / "figures"


def sha256_file(path: Path) -> str:
    """Hash every compact input consumed by a formal figure."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(path: Path) -> List[Dict[str, str]]:
    """Read a task-owned CSV while retaining blocked rows."""

    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def blocked(axis: plt.Axes, title: str, reason: str) -> None:
    """Render an explicit blocked panel instead of an empty misleading plot."""

    axis.set_title(title)
    axis.text(0.5, 0.5, "BLOCKED\n{}".format(reason), ha="center", va="center", transform=axis.transAxes)
    axis.set_xticks([])
    axis.set_yticks([])


def save(stem: str, figure: plt.Figure, sources: List[Path], manifest: List[Dict[str, Any]]) -> None:
    """Write PDF and 600 dpi PNG, then verify dimensions and metadata."""

    FIGURES.mkdir(parents=True, exist_ok=True)
    pdf = FIGURES / (stem + ".pdf")
    png = FIGURES / (stem + ".png")
    figure.savefig(pdf, bbox_inches="tight")
    figure.savefig(png, dpi=600, bbox_inches="tight")
    plt.close(figure)
    with Image.open(png) as image:
        width, height = image.size
        dpi = image.info.get("dpi", (0.0, 0.0))
    if width < 1200 or height < 800 or min(float(dpi[0]), float(dpi[1])) < 590.0:
        raise RuntimeError("T0 figure QA failed: {} {}x{} dpi={}".format(stem, width, height, dpi))
    manifest.append({
        "figure_stem": stem,
        "pdf": str(pdf),
        "png": str(png),
        "source_sha256": {str(path): sha256_file(path) for path in sources},
        "plot_script_sha256": sha256_file(Path(__file__)),
        "python_executable": sys.executable,
        "matplotlib_version": matplotlib.__version__,
        "conda_env": os.environ["CONDA_DEFAULT_ENV"],
        "png_width_px": width,
        "png_height_px": height,
        "png_dpi": [float(dpi[0]), float(dpi[1])],
    })


def main() -> int:
    """Create T0-1 through T0-5 figure slots from compact evidence only."""

    smoke = ANALYSIS / "reports" / "t0_1_smoke.csv"
    long_pulse = ANALYSIS / "long_pulse_consistency" / "long_pulse_results.csv"
    blocked_files = [
        ANALYSIS / "phase_window" / "phase_window.csv",
        ANALYSIS / "amplitude_duration" / "amplitude_duration.csv",
        ANALYSIS / "phase_coverage" / "phase_coverage.csv",
        ANALYSIS / "cadence" / "cadence.csv",
    ]
    smoke_rows = rows(smoke)
    long_rows = rows(long_pulse)
    manifest: List[Dict[str, Any]] = []

    # T0-1: the exact PWL stimulus is reconstructed from the recorded scenario
    # parameters; crossing markers are measured HSPICE scalars, not invented
    # analog traces.  This distinction matters because post=0 intentionally
    # keeps large transient waveform files out of the repository.
    figure, axes = plt.subplots(2, 1, figsize=(8.0, 5.2), sharex=True)
    if smoke_rows:
        row = next((item for item in smoke_rows if float(item["DeltaV_mv"]) > 0), smoke_rows[0])
        base = float(row["baseline_vdd_v"])
        low = float(row["Vdroop_v"])
        start = 1.49 + float(row["phase_ps"]) / 1000.0
        fall = float(row["t_fall_ps"]) / 1000.0
        hold = float(row["t_hold_ps"]) / 1000.0
        rise = float(row["t_rise_ps"]) / 1000.0
        times = [0.0, start, start + fall, start + fall + hold, start + fall + hold + rise, 7.5]
        values = [base, base, low, low, base, base]
        axes[0].plot(times, values, color="black", linewidth=1.4, label="VDD_MONITORED PWL")
        axes[0].set_ylabel("VDD (V)")
        axes[0].legend(loc="best", fontsize=8)
        for key, label, color in (("t_xor_rise_s", "XOR rise", "tab:blue"), ("t_xor_fall_s", "XOR fall", "tab:orange"), ("t_ck_rise_s", "CK rise", "tab:green")):
            value = float(row[key]) * 1e9
            axes[0].axvline(value, color=color, linestyle="--", linewidth=0.9, label=label)
        axes[0].legend(loc="best", fontsize=7)
        # The two points use the fixed M0 read instants (3.79 ns and 3.99 ns);
        # their vertical values are measured DFF rails, not a proxy waveform.
        axes[1].plot([3.79, 3.99], [float(row["q_sample_1_v"]), float(row["q_sample_2_v"])], marker="o", color="tab:red", label="真实 DFF Q 双采样")
        axes[1].set_ylabel("Q (V)")
        axes[1].set_xlabel("时间 (ns，测量标记)")
        axes[1].set_xticks([3.79, 3.99])
        axes[1].legend(loc="best", fontsize=8)
    else:
        blocked(axes[0], "图 T0-1：代表性瞬态波形", "没有紧凑试跑数据")
        blocked(axes[1], "真实 DFF Q", "没有紧凑试跑数据")
    save("fig_t0_1_representative_waveform", figure, [smoke], manifest)

    # T0-2: the phase table is unavailable because the T0-2 hard gate stopped
    # before phase exploration.  The blocked panel is itself reviewable proof.
    for stem, title, path in (
        ("fig_t0_2_phase_window", "图 T0-2：单 probe 相位敏感窗口", blocked_files[0]),
        ("fig_t0_3_amplitude_duration_boundary", "图 T0-3：跌落深度—持续时间边界", blocked_files[1]),
        ("fig_t0_4_margin_duration_comparison", "图 T0-4：裕量与最短持续时间", blocked_files[2]),
        ("fig_t0_5_cadence_coverage", "图 T0-5：检测间隔与时间覆盖率", blocked_files[3]),
    ):
        figure, axis = plt.subplots(figsize=(7.2, 4.2))
        blocked(axis, title, "T0-2 长脉冲一致性硬门失败")
        save(stem, figure, [path, long_pulse], manifest)

    write_path = ANALYSIS / "figures" / "figure_manifest.json"
    write_path.write_text(json.dumps({"schema_version": 1, "study": "ftc_t0_transient_voltage_droop_characterization_v1", "figures": manifest}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
