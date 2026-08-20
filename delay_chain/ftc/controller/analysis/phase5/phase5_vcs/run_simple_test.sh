#!/bin/bash

RTL_DIR="../../../rtl"
TB_DIR="../../../tb"

vcs -full64 -sverilog -lca -timescale=1ns/1ps \
    -debug_access+all \
    +lint=PCWM \
    ${RTL_DIR}/ftc_cal_pkg.sv \
    ${RTL_DIR}/ftc_q_sampler.sv \
    ${RTL_DIR}/ftc_operation_sequencer.sv \
    ${TB_DIR}/tb_simple_seq_test.sv \
    -o simv_simple \
    -l compile_simple.log

if [ $? -ne 0 ]; then
    echo "=== Compilation failed ==="
    exit 1
fi

./simv_simple -l sim_simple.log
