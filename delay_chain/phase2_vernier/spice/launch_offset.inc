* PHASE2_LAUNCH_BUFFER port contract:
*   Y/VDD_REF/VSS_REF/A follow the standard non-inverting buffer interface.
* The ideal-arrival phase drives the selected launch delay with a separate
* PULSE source.  This wrapper is reserved for the later real MUX/tap network
* and is kept on the reference rail so calibration never tracks VDD_A droop.
.subckt PHASE2_LAUNCH_BUFFER Y VDD_REF VSS_REF A
XBUF_LAUNCH Y VDD_REF VDD_REF VSS_REF VSS_REF A BUF_X0P7M_A9TR40
.ends PHASE2_LAUNCH_BUFFER
