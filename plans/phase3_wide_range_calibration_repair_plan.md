# Phase 3 Wide-Range Calibration Repair and Debug Plan

## Objective

Repair the current Phase 3 wide-range sparse Vernier implementation so that the physical DFF thermometer operates inside a useful transition window instead of remaining at the all-zero endpoint.

The current remote result at commit `1a9b05e8b20570c1905fd46390080cba8130a7bd` has already established several useful facts and they must be reused directly:

```text
selected sparse