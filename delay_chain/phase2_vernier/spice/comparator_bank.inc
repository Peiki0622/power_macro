* PHASE2_COMPARATOR port contract:
*   Q       : captured comparator bit on the VDD_REF/VSS_REF logic domain.
*   VDD_REF : DFF supply and n-well rail; the DFF is not powered from VDD_A.
*   VSS_REF : DFF return and p-well rail.
*   D       : sense-domain S_i input; cross-domain reliability is verified
*             separately before this wrapper is accepted in the final macro.
*   CK      : reference-chain R_i edge, positive-edge sampling.
*   R       : active-high asynchronous clear shared by the comparator bank.
*
* DFFRPQ_X0P5M_A9TR40 positional ports: Q VDD VNW VPW VSS CK D R.
.subckt PHASE2_COMPARATOR Q VDD_REF VSS_REF D CK R
XDFF Q VDD_REF VDD_REF VSS_REF VSS_REF CK D R DFFRPQ_X0P5M_A9TR40
.ends PHASE2_COMPARATOR
