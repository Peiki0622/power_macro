#!/usr/bin/env python3
"""Physical k=5 to k=3 center-tap migration for the reviewed CNN graph."""

from __future__ import print_function

from collections import OrderedDict

import torch

from power_macro.tcn_detection.models.cnn1d import CNN1D


def validate_kernel_transition(source_kernels, target_kernels):
    """Allow only [5,5,5], [5,5,3], or [5,3,3] transitions."""

    source = tuple(int(value) for value in source_kernels)
    target = tuple(int(value) for value in target_kernels)
    if source != (5, 5, 5) or target not in ((5, 5, 5), (5, 5, 3), (5, 3, 3)):
        raise ValueError("unsupported kernel transition")
    return source, target


def crop_state_dict(state_dict, source_kernels, target_kernels):
    """Physically retain center taps for every stage changed to k=3."""

    source, target = validate_kernel_transition(source_kernels, target_kernels)
    result = OrderedDict((key, value.clone()) for key, value in state_dict.items())
    for stage, (old_kernel, new_kernel) in enumerate(zip(source, target)):
        if new_kernel == old_kernel:
            continue
        key = "features.{}.weight".format(stage * 3)
        if key not in state_dict or tuple(state_dict[key].shape[-1:]) != (old_kernel,):
            raise ValueError("state dict kernel does not match source contract")
        # For a same-padded k=5 convolution, indices 1:4 preserve the center
        # receptive field and produce a physical k=3 tensor.
        result[key] = state_dict[key][..., 1:4].clone()
    return result


def crop_model(model, target_kernels):
    """Construct a k-cropped CNN with inherited center-tap weights."""

    if not isinstance(model, CNN1D) or model.pooling_contract != "multistat_average_max_endpoint":
        raise ValueError("kernel surgery requires the three-stage multistat CNN")
    _, target = validate_kernel_transition(model.kernel_sizes, target_kernels)
    compact = CNN1D(
        input_channels=model.features[0].in_channels,
        class_count=model.classifier.out_features,
        channels=list(model.channels), kernel_sizes=list(target),
        dropout=model.features[2].p,
        pooling_contract=model.pooling_contract,
        dilations=[model.features[index].dilation[0] for index in (0, 3, 6)])
    compact.load_state_dict(crop_state_dict(model.state_dict(), model.kernel_sizes, target), strict=True)
    return compact
