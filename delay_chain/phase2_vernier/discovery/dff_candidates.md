# DFF Candidates

| Cell | CDL ports | Selection | Reason |
|---|---|---|---|
| `DFFRPQ_X0P5M_A9TR40` | `Q VDD VNW VPW VSS CK D R` | selected | smallest Q-output positive-edge DFF with one asynchronous clear pin |
| `DFFQ_X0P5M_A9TR40` | `Q VDD VNW VPW VSS CK D` | not selected | no asynchronous reset port |
| `DFFSRPQ_X0P5M_A9TR40` | `Q VDD VNW VPW VSS CK D R SN` | not selected | adds an unnecessary asynchronous set input |
