# FTC-Style RVT/LVT Reproduction Result

## Scope

The paper uses HVT/LVT delay paths.  SMIC40LL provides no selected HVT cell,
so this standalone reproduction maps the paper's high-Vt path to RVT and
retains LVT for the low-Vt path.  It preserves the dual delay lines,
corresponding-tap XORs, transparent latches, post-latch FFs, and longest-1
start/end encoder.  It is not a device-exact HVT/LVT reproduction and is not
a Phase-3 comparison.

## Selected Physical Structure

The selected cells are `BUF_X0P7M_A9TR40` (RVT), `BUF_X0P7M_A9TL40` (LVT),
`XOR2_X0P5M_A9TR40`, `LATQ_X0P5M_A9TR40`, and `DFFRPQ_X0P5M_A9TR40`.
The final characterization setting is four RVT initial buffers, zero LVT
initial buffers, 30 observable stages per path, a 6 ns sampling period, a
300 ps latch-close phase, and a FF edge 200 ps later.  The capture schedule is
a target-process implementation choice because the paper does not publish a
gate-level sampling-clock generator.

## Physical Results

The mechanism-only nominal window was stages 14--22.  Real XOR loading moved
the nominal window but retained an internal 9-bit run.  In the selected
integrated 300 ps sweep, every point in the formal 0.75--1.10 V range captured
a valid word: 1.10 V=`10--18`, 1.05 V=`9--16`, 1.00 V=`7--14`, 0.95 V=`6--12`,
0.90 V=`4--10`, 0.85 V=`3--8`, 0.80 V=`1--5`, and 0.75 V=`0--3`.
The 0.75 V word is a valid left-boundary run; 0.70 V is outside the revised
range and is not included in this conclusion.

The 10 mV static sweep contains 36 valid points and 21 distinct `(start,end)`
states.  The longest measured stable plateau is 1.03--1.01 V (20 mV, state
`8--15`).  The response moves systematically toward lower indices as VDD falls.
No observation requires a global sub-10 mV rerun.  Phase perturbation by the
measured 13.718435 ps step produced maximum start/end movement of 1/2 stages
at 1.10 V, 1/2 at 0.90 V, and 0/1 at 0.75 V.

The nine representative 1.10 V glitch cases produced seven changed captured
states and two blind placements.  This establishes observed sensitivity only;
it does not claim universal glitch coverage.

## Hardware And Conclusion

The packaged structure contains 34 RVT buffers (four initial plus 30
observable), 30 LVT buffers, 30 XORs, 30 latches, 30 FFs, no added sampling
support cells, and one 30-bit longest-run encoder.  It uses one `VDD_A/VSS_A`
rail pair and no reference rail.

Within the revised 0.75--1.10 V range, the real-cell SMIC40LL FTC-style
RVT/LVT sensor reproduces a usable fault-to-time/XOR/capture response: the
captured start/end result is valid and nonconstant with supply voltage.
