#!/usr/bin/env python3
"""Sweep RC reference islands under a PWL sense-domain 765 MHz-scale droop."""
import argparse, csv, json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/"power_macro/delay_chain/phase1/scripts"))
import run_dc_sweep  # noqa: E402

def read(path):
    with path.open() as f: return json.load(f)

def render(config, phase1, r_ohm, c_pf):
    """Attach real reference stages/DFF clocks to an RC-isolated reference rail.

    VDD_A is driven by a controlled PWL 1.10-to-1.04747 V pulse.  The 32
    reference stages and comparator DFF clock pins load VDD_REF through RISO;
    their supplies and wells never connect to VDD_A.
    """
    cdl=ROOT/phase1["cell_cdl"]; model=phase1["model_library"]; inc=ROOT/"power_macro/delay_chain/phase2_vernier/spice"
    lines=["* RC reference island with real standard-cell reference/DFF load", ".option post=0 nomod measform=3 runlvl=3", ".temp 25",'.include "{}"'.format(cdl),'.lib "{}" tt'.format(model),'.include "{}"'.format(inc/"reference_stage.inc"),'.include "{}"'.format(inc/"comparator_bank.inc"),
    "V_UP upstream 0 DC=1.1", "V_REF_GND vss_ref 0 DC=0", "R_ISO upstream vdd_ref {:.12e}".format(r_ohm), "C_REF vdd_ref vss_ref {:.12e}".format(c_pf*1e-12),
    "V_A vdd_a 0 PWL(0 1.1 9e-10 1.1 1e-9 1.047473942801 2e-9 1.047473942801 2.1e-9 1.1 4e-9 1.1)",
    "V_RESET reset vss_ref PWL(0 1.1 5e-10 1.1 5.1e-10 0 4e-9 0)",
    "V_START start_ref vss_ref PULSE(0 1.1 1e-9 1e-11 1e-11 1e-7 2e-7)"]
    prev="start_ref"
    for i in range(32):
        y="ref_{:03d}".format(i); lines.append("XREF_{:03d} {} vdd_ref vss_ref {} PHASE2_REFERENCE_STAGE_D1".format(i,y,prev)); lines.append("XCOMP_{:03d} q_{:03d} vdd_ref vss_ref vss_ref {} reset PHASE2_COMPARATOR".format(i,i,y)); prev=y
    lines += [".tran 1e-12 4e-9", ".measure tran a_min MIN v(vdd_a) FROM=9e-10 TO=2.2e-9", ".measure tran ref_min MIN v(vdd_ref,vss_ref) FROM=9e-10 TO=2.2e-9", ".measure tran ref_recover FIND v(vdd_ref,vss_ref) AT=3.5e-9", ".measure tran upstream_peak MAX par('-i(V_UP)') FROM=9e-10 TO=2.2e-9", ".end", ""]
    return "\n".join(lines)

def main():
 p=argparse.ArgumentParser(); p.add_argument("--config",required=True,type=Path); p.add_argument("--output-dir",required=True,type=Path); a=p.parse_args(); cfg=read(a.config); p1=read(ROOT/cfg["phase1_config_path"]); out=a.output_dir.resolve(); out.mkdir(parents=True,exist_ok=True); rows=[]
 for r in cfg["reference_island_r_ohm"]:
  for c in cfg["reference_island_c_pf"]:
   d=out/"scenarios"/("r{}_c{}".format(r,c)); d.mkdir(parents=True,exist_ok=False); (d/"island.sp").write_text(render(cfg,p1,r,c),encoding="ascii"); z=subprocess.run([p1["hspice"],"island.sp","-o","island"],cwd=str(d),stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=180)
   if z.returncode: raise RuntimeError(z.stderr)
   run_dc_sweep.validate_listing(d/"island.lis"); m=run_dc_sweep.parse_measurements(run_dc_sweep.find_measurement_file(d,"island")); rows.append({"r_ohm":r,"c_pf":c,"a_min_v":m["a_min"],"ref_min_v":m["ref_min"],"ref_recover_v":m["ref_recover"],"upstream_peak_a":m["upstream_peak"]})
 with (out/"reference_island_metrics.csv").open("w",newline="") as f: w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 selected=min(rows,key=lambda x:(1.1-x["ref_min_v"],abs(x["ref_recover_v"]-1.1),x["upstream_peak_a"]))
 (out/"reference_island_selection.json").write_text(json.dumps({"status":"PASS","selected":selected},indent=2)+"\n")
 (out/"completion.rpt").write_text("status=PASS\nscenario_count={}\n".format(len(rows)))
if __name__=="__main__": main()
