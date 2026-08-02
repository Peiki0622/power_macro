"""Bit-true export support for the frozen Safe/Critical 1D-CNN.

The package is deliberately separate from training and IID evaluation code.
Its modules may read train/validation windows and the authoritative checkpoint,
but they never train a model, alter a split, or open frozen IID feature rows.
"""
