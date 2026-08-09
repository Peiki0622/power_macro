# FTC Cell Discovery

This is an FTC-style RVT/LVT reproduction: the original HVT path is mapped to RVT because no HVT library is selected.

| Role | Cell | Vt | CDL ports | Function |
|---|---|---|---|---|
| delay_rvt | `BUF_X0P7M_A9TR40` | RVT | `Y VDD VNW VPW VSS A` | Y = A |
| delay_lvt | `BUF_X0P7M_A9TL40` | LVT | `Y VDD VNW VPW VSS A` | Y = A |
| xor2 | `XOR2_X0P5M_A9TR40` | RVT | `Y VDD VNW VPW VSS A B` | Y = A XOR B |
| latch | `LATQ_X0P5M_A9TR40` | RVT | `Q VDD VNW VPW VSS D G` | Q follows D while G is high |
| dff | `DFFRPQ_X0P5M_A9TR40` | RVT | `Q VDD VNW VPW VSS CK D R` | Q samples D on CK rising edge; R asynchronously clears Q |

All supply and well pins map to the sole FTC rail pair: `VDD/VNW -> VDD_A`, `VPW/VSS -> VSS_A`.
The latch is a real active-high transparent latch; the DFF is a real positive-edge, active-high asynchronous-clear register.
