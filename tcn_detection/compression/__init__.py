"""Validation-bounded tools for the binary CNN compression study.

The package intentionally contains only the small, task-specific pieces needed
to move the existing three-layer CNN through physical channel pruning,
validation-only recovery training, distillation, and numeric export.  It does
not replace the repository's dataset, metric, training, or fixed-point APIs.
"""
