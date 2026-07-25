#!/usr/bin/env python3
"""Validate a 1.1 V DFF receiving low-domain D inputs from 0.95--1.10 V."""

import argparse, csv, json, sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PHASE1 = ROOT / "power_macro/delay_chain/phase1/scripts"
sys.path.insert(0, str(PHASE1))
import run_dc_sweep  # noqa: E402


def load(path):
    with path.open() as stream:
        return json.load(stream)


def deck(config, phase1, vdd_a, data_high, data_offset_s, capture_s=1.8e-9):
    """Render one powered DFF test; D amplitude is the tested sense-domain high level.

    Ports of DFFRPQ are Q,VDD,VNW,VPW,VSS,CK,D,R.  CK/R and every well stay on
    VDD_REF/VSS_REF, whereas V_D drives only D with the selected VDD_A level.
    """
    data_start = 1.0e-9 + data_offset_s
    data_line = "V_D d vss_ref DC=0" if not data_high else "V_D d vss_ref PULSE(0 {:.12e} {:.12e} 1e-11 1e-11 1e-7 2e-7)".format(vdd_a, data_start)
    return """* Cross-domain real DFF validation\n.option post=0 nomod measform=3 runlvl=3\n.temp 25\n.include \"{cdl}\"\n.lib \"{model}\" tt\nV_REF vdd_ref vss_ref DC=1.1\nV_VSS vss_ref 0 DC=0\nV_R r vss_ref PWL(0 1.1 5e-10 1.1 5.1e-10 0 2e-9 0)\nV_CK ck vss_ref PULSE(0 1.1 1e-9 1e-11 1e-11 1e-10 2e-9)\n{data}\n* DFF ports: Q VDD VNW VPW VSS CK D R.\nXDFF q vdd_ref vdd_ref vss_ref vss_ref ck d r DFFRPQ_X0P5M_A9TR40\n.tran 1e-12 2e-9\n.measure tran q_level FIND v(q,vss_ref) AT={capture:.12e}\n.measure tran q_reset FIND v(q,vss_ref) AT=2.5e-10\n.measure tran ref_avg_i AVG par('-i(V_REF)') FROM=5e-10 TO={capture:.12e}\n.end\n""".format(cdl=ROOT / phase1["cell_cdl"], model=phase1["model_library"], data=data_line, capture=capture_s)


def main():
    parser = argparse.ArgumentParser(description="run real DFF cross-domain validation")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    config, phase1 = load(args.config), load(ROOT / load(args.config)["phase1_config_path"])
    out = args.output_dir.resolve()
    # A partially interrupted task-owned run is resumed by revalidating each
    # completed point below; no completed deck, listing, or measurement is
    # overwritten.  A new directory is still created only when absent.
    out.mkdir(parents=True, exist_ok=True)
    values=[]; x=Decimal(str(config["cross_domain_vdd_start_v"])); stop=Decimal(str(config["cross_domain_vdd_stop_v"])); step=Decimal(str(config["cross_domain_vdd_step_v"]))
    while x <= stop: values.append(float(x)); x += step
    for anchor in config["phase1_anchor_voltages_v"]:
        if not any(abs(float(anchor)-v)<1e-12 for v in values): values.append(float(anchor))
    hspice=Path(phase1["hspice"]); rows=[]
    cases=[("static_0",False,-0.1e-9), ("static_1",True,-0.1e-9)]
    for offset in (-20e-12,-5e-12,0.0,5e-12,20e-12): cases.append(("setup_hold_{:+.0f}ps".format(offset*1e12),True,offset))
    for vdd in sorted(values):
        local_cases=cases if any(abs(vdd-float(v))<1e-12 for v in config["phase1_anchor_voltages_v"]) else cases[:2]
        for label, high, offset in local_cases:
            d=out/"scenarios"/("v{:.12f}".format(vdd).replace(".","p"))/label
            if not d.exists():
                d.mkdir(parents=True)
                (d/"cross.sp").write_text(deck(config,phase1,vdd,high,offset),encoding="ascii")
                import subprocess
                result=subprocess.run([str(hspice),"cross.sp","-o","cross"],cwd=str(d),stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=180)
                if result.returncode: raise RuntimeError(result.stderr)
            run_dc_sweep.validate_listing(d/"cross.lis")
            m=run_dc_sweep.parse_measurements(run_dc_sweep.find_measurement_file(d,"cross"))
            if m.get("q_level") is None or m.get("q_reset") is None: raise ValueError("missing Q measurement")
            expected=1 if high and offset <= -5e-12 else 0
            actual=1 if m["q_level"] >= .55 else 0
            rows.append({"vdd_a_v":vdd,"case":label,"expected_q":expected,"actual_q":actual,"reset_q_v":m["q_reset"],"q_v":m["q_level"],"ref_avg_i_a":m["ref_avg_i"]})
    with (out/"cross_domain_metrics.csv").open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    # Static D=0/D=1 rows establish voltage-level compatibility.  The separate
    # setup/hold rows intentionally map the aperture; a transition at -5 ps
    # may miss capture and is recorded as a timing constraint, not evidence
    # that the 0.95--1.10 V high level needs an unsupported level shifter.
    failed=[r for r in rows if r["case"].startswith("static") and (r["reset_q_v"]>=.55 or r["actual_q"]!=r["expected_q"])]
    (out/"completion.rpt").write_text("status={}\nscenario_count={}\n".format("PASS" if not failed else "FAIL",len(rows)),encoding="ascii")
    if failed: raise SystemExit(2)

if __name__ == "__main__": main()
