# Re-Frequency Eligibility

**Decision: GO**

The earliest preserved C3 violation is `CK_LOW_WIDTH` on
`tb_ftc_vcs_xa_autonomous.u_controller.\u_fsm/fail_reason_q_reg[2]`.  The VCS model requires 1000 ps
and reports 500 ps for the relevant conditional clock
pulse.  The violation is frequency-dependent because the 1 GHz source has a
500 ps half-period; RF2 must still confirm the complete sequential-cell family
and Liberty/VCS consistency before selecting a clock.
