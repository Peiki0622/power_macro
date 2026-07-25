* Differential Vernier top-level integration contract.
*
* The Python deck generator unrolls M stage instances because HSPICE subcircuit
* definitions do not provide a portable integer generate-loop mechanism.  It
* includes sense_stage.inc and reference_stage.inc, connects S_i to DFF D and
* R_i to DFF CK only in the real-comparator deck, and retains every crossing
* name for CSV audit.  This file documents that boundary without copying the
* foundry CDL or introducing a transistor-level substitute.
