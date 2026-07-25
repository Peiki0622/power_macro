* PHASE2_SENSE_STAGE port contract:
*   Y       : non-inverting stage output and the observable S_i tap.
*   VDD_A   : chiplet-A local positive rail; VNW is tied to this same rail.
*   VSS_A   : chiplet-A local return rail; VPW is tied to this same rail.
*   A       : stage input.  This revision adds no artificial sense-side load.
*
* The parent deck includes the foundry CDL before this reusable wrapper.  The
* positional INV ports below are explicitly documented to prevent VNW/VPW
* swaps: Y, VDD, VNW, VPW, VSS, A.
.subckt PHASE2_SENSE_STAGE Y VDD_A VSS_A A
XINV_SENSE_A PHASE2_SENSE_MID VDD_A VDD_A VSS_A VSS_A A INV_X0P5M_A9TR40
XINV_SENSE_B Y                VDD_A VDD_A VSS_A VSS_A PHASE2_SENSE_MID INV_X0P5M_A9TR40
.ends PHASE2_SENSE_STAGE
