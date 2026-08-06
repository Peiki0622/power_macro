"""Full-binary no-FC detector building blocks and deployment utilities."""

from power_macro.tcn_detection.bnn.input_encoding import (
    THERMOMETER_WIDTH,
    encode_code,
    encode_codes,
    encode_windows,
)

__all__ = [
    "THERMOMETER_WIDTH",
    "encode_code",
    "encode_codes",
    "encode_windows",
]
