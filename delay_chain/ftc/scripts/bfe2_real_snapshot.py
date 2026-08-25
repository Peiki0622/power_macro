#!/usr/bin/env python3
"""Run the bounded B-FE2.2 real-latch single-close snapshot experiment."""
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

FTC_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(FTC_ROOT/"scripts"))
import bfe2_latch_load as load  # noqa: E402
import bfe1_frontend  # noqa: E402
import run_dc_sweep  # noqa: E402

RUN_ROOT=FTC_ROOT/"runs"/"b_fe_frontend"/"bfe2_real_latch"/"real_snapshot"
OUT=FTC_ROOT/"analysis"/"b_fe_frontend"/"bfe2_real_latch"/"real_snapshot"
LOAD_PAIR=FTC_ROOT/"analysis"/"b_fe_frontend"/"bfe2_real_latch"/"latch_load"/"BFE2_1_PAIRWISE_DISCRIMINATION.json"

def read(path): return json.loads(path.read_text(encoding="utf-8"))
def write(path,value): path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def seed_by_baseline():
    """Select center points from B-FE2.1, never from B-FE1R absolute times."""
    pairs=read(LOAD_PAIR)["pairs"]; result={}
    for pair in pairs:
        choices=[x for x in pair["candidate_platforms"] if x["normal"]["run_count"]==1 and x["l2"]["run_count"]==1]
        best=max(choices,key=lambda x:(x["interval_width_ps"],x["hamming_distance"]))
        result[float(pair["baseline_v"])]=round((best["interval_start_ps"]+best["interval_end_ps"])/2.0,6)
    return result

def render(cells,scenario,close_ps):
    """Render 30 real latches with one finite, common high-to-low G edge."""
    text=load.render_deck(cells,scenario)
    close_s=(bfe1_frontend.LAUNCH_S+close_ps*1e-12)
    edge=1e-12
    old="V_LATCH_G latch_g vss_a DC='VDD_VALUE'"
    new="* Common G stays transparent through wavefront, then closes once.\nV_LATCH_G latch_g vss_a PWL(0 'VDD_VALUE' {} 'VDD_VALUE' {} 0 {} 0)".format(bfe1_frontend.spice(close_s-edge/2),bfe1_frontend.spice(close_s+edge/2),bfe1_frontend.spice(bfe1_frontend.STOP_S))
    if old not in text: raise ValueError("transparent-load G source missing")
    return text.replace(old,new)

def validate(text):
    """Confirm B-FE2.2 has exactly one finite G falling edge and no DFF."""
    net="\n".join(x.split("*",1)[0] for x in text.splitlines())
    if net.count("XLATCH_")!=30 or "DFF" in net.upper() or "DC='VDD_VALUE'" in net:
        raise ValueError("invalid B-FE2.2 snapshot topology")
    if "V_LATCH_G latch_g vss_a PWL" not in net: raise ValueError("missing finite G close")

def main():
    if read(FTC_ROOT/"analysis"/"b_fe_frontend"/"bfe2_real_latch"/"latch_load"/"BFE2_1_GATE_STATUS.json")["gate"]!="BFE2_1_LATCH_LOAD_GO": raise RuntimeError("BFE2.1 not GO")
    cfg=read(FTC_ROOT/"ftc_config.json"); cells=read(FTC_ROOT/"discovery"/"selected_cells.json"); hp=Path(cfg["hspice"]); version=run_dc_sweep.hspice_version(hp); seeds=seed_by_baseline(); results=[]
    for s in load.SCENARIOS:
        close=seeds[float(s["baseline_v"])]; d=RUN_ROOT/"scenarios"/s["scenario_id"].lower().replace("-","_"); d.mkdir(parents=True,exist_ok=False)
        import shutil; shutil.copyfile(FTC_ROOT/"spice"/"empty_subckt.sp_cal",d/"empty_subckt.sp_cal")
        deck=render(cells,s,close); validate(deck); (d/"bfe2s.sp").write_text(deck,encoding="ascii")
        import subprocess; r=subprocess.run([str(hp),"bfe2s.sp","-o","bfe2s"],cwd=str(d),stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=600)
        (d/"hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(r.returncode,r.stdout,r.stderr),encoding="utf-8")
        if r.returncode: raise RuntimeError("snapshot failed "+s["scenario_id"])
        run_dc_sweep.validate_listing(d/"bfe2s.lis"); tr=bfe1_frontend.parse_ascii_tr0(d/"bfe2s.tr0")
        if tr["record_width"]!=124: raise ValueError("snapshot probe contract changed")
        evidence={"scenario_id":s["scenario_id"],"baseline_v":s["baseline_v"],"droop_v":s["droop_v"],"close_ps":close,"record_width":tr["record_width"],"record_count":tr["record_count"],"hspice_version":version,"run_disposition":"new"}; write(d/"scenario_evidence.json",evidence); results.append(evidence)
    OUT.mkdir(parents=True,exist_ok=True); write(OUT/"BFE2_2_SCENARIO_MANIFEST.json",{"stage":"B-FE2.2","seed_source":"B-FE2.1 common discrimination platforms","authorized_new_scenarios":4,"scenarios":results})
    print("BFE2_2_REAL_SNAPSHOT_MATRIX_COMPLETE new=4")
if __name__=="__main__": main()
