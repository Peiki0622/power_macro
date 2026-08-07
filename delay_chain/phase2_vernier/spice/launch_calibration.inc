* PHASE2_LAUNCH_CAL port contract:
*   START_REF : physically balanced reference launch that drives the reference chain.
*   START_SENSE : selected physical launch output that drives the sense chain.
*   VDD_REF/VSS_REF : supply and well rails for every BUF/MXT2 calibration cell.
*   START_REQ : unmodified launch request and input of the seven-buffer tap chain.
*   SEL0/SEL1/SEL2 : static physical CAL_SEL bits, least-significant first.
*
* This subcircuit intentionally mirrors rtl/vernier_launch_cal_struct.sv:
* seven BUF_X0P7M_A9TR40 cells create taps 1 through 7, and a balanced tree
* of seven MXT2_X0P5M_A9TR40 cells selects exactly one of taps 0 through 7.
* A three-MUX non-inverting reference balance path removes the common selector
* latency from the differential result.  Every balance-MUX A/B pair
* is tied to START_REQ, so these cells are delay matching only, never a hidden
* reference tap choice.  All standard-cell positional ports are listed in full
* as Y, VDD, VNW, VPW, VSS, A[, B, S0] to prevent well-pin swaps.
.subckt PHASE2_LAUNCH_CAL START_REF START_SENSE VDD_REF VSS_REF START_REQ SEL0 SEL1 SEL2

* Fixed reference balance: exactly three MUX propagation arcs.  The MUX tree
* is non-inverting, so REF_MUX_L3 is the reference-chain input in the RTL too.
* A private MXT2 data input loads the final MUX level.  It is the one
* HSPICE-characterized capacitive adjustment for the CAL_SEL=2 code-15 point.
XMUX_REF_BAL_0 REF_MUX_L1 VDD_REF VDD_REF VSS_REF VSS_REF START_REQ  START_REQ  SEL0 MXT2_X0P5M_A9TR40
XMUX_REF_BAL_1 REF_MUX_L2 VDD_REF VDD_REF VSS_REF VSS_REF REF_MUX_L1 REF_MUX_L1 SEL1 MXT2_X0P5M_A9TR40
XMUX_REF_BAL_2 START_REF  VDD_REF VDD_REF VSS_REF VSS_REF REF_MUX_L2 REF_MUX_L2 SEL2 MXT2_X0P5M_A9TR40
XREF_BAL_DUMMY REF_BAL_DUMMY_Y VDD_REF VDD_REF VSS_REF VSS_REF START_REF START_REQ SEL0 MXT2_X0P5M_A9TR40

* Tap 0 is the direct launch request.  Each following tap adds one actual
* reference-domain buffer; no fixed delay value is represented in this model.
XBUF_0 TAP_1 VDD_REF VDD_REF VSS_REF VSS_REF START_REQ BUF_X0P7M_A9TR40
XBUF_1 TAP_2 VDD_REF VDD_REF VSS_REF VSS_REF TAP_1     BUF_X0P7M_A9TR40
XBUF_2 TAP_3 VDD_REF VDD_REF VSS_REF VSS_REF TAP_2     BUF_X0P7M_A9TR40
XBUF_3 TAP_4 VDD_REF VDD_REF VSS_REF VSS_REF TAP_3     BUF_X0P7M_A9TR40
XBUF_4 TAP_5 VDD_REF VDD_REF VSS_REF VSS_REF TAP_4     BUF_X0P7M_A9TR40
XBUF_5 TAP_6 VDD_REF VDD_REF VSS_REF VSS_REF TAP_5     BUF_X0P7M_A9TR40
XBUF_6 TAP_7 VDD_REF VDD_REF VSS_REF VSS_REF TAP_6     BUF_X0P7M_A9TR40

* Level 1 resolves adjacent tap pairs using CAL_SEL[0].
XMUX_L1_0 MUX_L1_0 VDD_REF VDD_REF VSS_REF VSS_REF START_REQ TAP_1 SEL0 MXT2_X0P5M_A9TR40
XMUX_L1_1 MUX_L1_1 VDD_REF VDD_REF VSS_REF VSS_REF TAP_2     TAP_3 SEL0 MXT2_X0P5M_A9TR40
XMUX_L1_2 MUX_L1_2 VDD_REF VDD_REF VSS_REF VSS_REF TAP_4     TAP_5 SEL0 MXT2_X0P5M_A9TR40
XMUX_L1_3 MUX_L1_3 VDD_REF VDD_REF VSS_REF VSS_REF TAP_6     TAP_7 SEL0 MXT2_X0P5M_A9TR40

* Level 2 resolves the lower or upper four-tap group with CAL_SEL[1].
XMUX_L2_0 MUX_L2_0 VDD_REF VDD_REF VSS_REF VSS_REF MUX_L1_0 MUX_L1_1 SEL1 MXT2_X0P5M_A9TR40
XMUX_L2_1 MUX_L2_1 VDD_REF VDD_REF VSS_REF VSS_REF MUX_L1_2 MUX_L1_3 SEL1 MXT2_X0P5M_A9TR40

* Level 3 chooses between the two four-tap groups with CAL_SEL[2].
XMUX_L3 START_SENSE VDD_REF VDD_REF VSS_REF VSS_REF MUX_L2_0 MUX_L2_1 SEL2 MXT2_X0P5M_A9TR40
.ends PHASE2_LAUNCH_CAL
