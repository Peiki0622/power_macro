"""Deterministic sensor-code to thermometer-bit encoders.

The online detector receives only an integer sensor code in the inclusive
range 0..32.  This module is deliberately stateless: a caller owns the
causal window and decides whether an invalid capture is accepted.  Keeping
that state outside the encoder makes it impossible for encoding convenience
code to silently insert an invalid or future sample.
"""

from __future__ import print_function

import numpy as np


THERMOMETER_WIDTH = 32
SENSOR_CODE_MIN = 0
SENSOR_CODE_MAX = THERMOMETER_WIDTH


def _validated_codes(codes):
    """Return integer-valued codes after enforcing the sensor lattice.

    ``np.asarray`` accepts floats and strings too easily for a hardware-facing
    boundary.  Explicit finiteness and integral-value checks prevent a caller
    from getting a silently rounded thermometer word.
    """

    values = np.asarray(codes)
    if values.ndim == 0:
        values = values.reshape(())
    if not np.issubdtype(values.dtype, np.number):
        raise TypeError("sensor codes must be numeric integers")
    floating = values.astype(np.float64, copy=False)
    if (not np.all(np.isfinite(floating))
            or not np.all(floating == np.rint(floating))):
        raise ValueError("sensor codes must be finite integers")
    integer = floating.astype(np.int64)
    if np.any(integer < SENSOR_CODE_MIN) or np.any(integer > SENSOR_CODE_MAX):
        raise ValueError("sensor code outside legal range 0..32")
    return integer


def encode_codes(codes):
    """Encode scalar or arbitrary-shaped code arrays as trailing-bit words.

    The returned array has shape ``codes.shape + (32,)`` and uses uint8 values
    so it can be packed without a numerical convention change.  Bit ``j`` is
    one exactly when ``j < sensor_code``; therefore the thermometer word has
    exactly ``sensor_code`` asserted bits, including the two boundary codes.
    """

    values = _validated_codes(codes)
    positions = np.arange(THERMOMETER_WIDTH, dtype=np.int64)
    return (positions < np.expand_dims(values, axis=-1)).astype(np.uint8)


def encode_code(sensor_code):
    """Encode one legal code and return a stable one-dimensional bit word."""

    encoded = encode_codes(sensor_code)
    if encoded.shape != (THERMOMETER_WIDTH,):
        raise ValueError("one code must produce exactly 32 thermometer bits")
    return encoded


def encode_windows(codes):
    """Encode chronological ``[N,L]`` or ``[L]`` code windows.

    Model tensors use channel-first ``[N,32,L]`` layout while CSV windows are
    chronological.  The transpose is kept here as the single deterministic
    representation change, avoiding per-model copies of the input contract.
    """

    values = _validated_codes(codes)
    one_window = values.ndim == 1
    if values.ndim not in (1, 2):
        raise ValueError("code windows must have shape [L] or [N,L]")
    words = encode_codes(values)
    if one_window:
        return np.transpose(words, (1, 0)).copy()
    return np.transpose(words, (0, 2, 1)).copy()
