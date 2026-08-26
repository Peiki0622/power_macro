#!/usr/bin/env python3
"""Run one independent VD2 voltage point for bounded parallel execution."""

import argparse
import json
from pathlib import Path

import run_bfe3_vd2_minimum_operating_voltage as vd2


def main():
    parser = argparse.ArgumentParser(description="B-FE3-VD2 single real HSPICE/XA point")
    parser.add_argument("--voltage", type=float, required=True)
    args = parser.parse_args()
    config = vd2.vd1.load_json(vd2.FTC_ROOT / "ftc_config.json")
    cells = vd2.vd1.load_json(vd2.FTC_ROOT / "discovery" / "selected_cells.json")
    result = vd2.run_point(round(args.voltage, 2), config, cells)
    out = vd2.ROOT / "point_{}.json".format(vd2.token(args.voltage))
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("VD2_POINT voltage={:.2f} functional_pass={} failures={}".format(args.voltage, result["functional_pass"], result["failure_reasons"]))
    return 0 if result["functional_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
