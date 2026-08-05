#!/usr/bin/env python3
"""Physically remove CNN channels while transferring inherited weights.

The compression plan permits only structured channel deletion.  This module
therefore slices tensors and constructs a smaller ``CNN1D``; it never applies
runtime masks or leaves pruned dimensions in the exported state dictionary.
The implementation is intentionally limited to the reviewed three-stage
multistat graph, whose classifier input order is Average, Maximum, Endpoint.
"""

from __future__ import print_function

from collections import OrderedDict

import torch

from power_macro.tcn_detection.models.cnn1d import CNN1D


def validate_keep_indices(channels, keep_indices):
    """Validate one stable, strictly increasing index list per CNN stage."""

    widths = tuple(int(value) for value in channels)
    if len(widths) != 3 or any(value < 1 for value in widths):
        raise ValueError("channel surgery requires three positive stages")
    if len(keep_indices) != 3:
        raise ValueError("one keep-index list is required per stage")
    normalized = []
    for width, values in zip(widths, keep_indices):
        values = [int(value) for value in values]
        if not values:
            raise ValueError("each stage must retain at least one channel")
        if values != sorted(values) or len(set(values)) != len(values):
            raise ValueError("keep indices must be strictly increasing")
        if values[0] < 0 or values[-1] >= width:
            raise ValueError("keep index is outside its source stage")
        normalized.append(values)
    return tuple(normalized)


def compact_state_dict(state_dict, channels, keep_indices):
    """Return a physically compact state dict with no pruned tensor rows.

    Conv stage ``i`` keeps output rows from ``keep_indices[i]`` and input
    columns from the preceding stage's keep list.  Conv1 retains all input
    sensor channels.  For Conv3's classifier, the three independently pooled
    slices are rebuilt from the same final keep list in the frozen order.
    """

    keep = validate_keep_indices(channels, keep_indices)
    result = OrderedDict((key, value.clone()) for key, value in state_dict.items())
    previous = None
    for stage, current in enumerate(keep):
        prefix = "features.{}".format(stage * 3)
        weight_key = prefix + ".weight"
        bias_key = prefix + ".bias"
        if weight_key not in state_dict or bias_key not in state_dict:
            raise ValueError("state dict is missing {} convolution".format(prefix))
        input_indices = (list(range(state_dict[weight_key].shape[1]))
                         if previous is None else previous)
        result[weight_key] = state_dict[weight_key].index_select(
            0, torch.as_tensor(current, dtype=torch.long)).index_select(
                1, torch.as_tensor(input_indices, dtype=torch.long)).clone()
        result[bias_key] = state_dict[bias_key].index_select(
            0, torch.as_tensor(current, dtype=torch.long)).clone()
        previous = current

    classifier_weight = state_dict.get("classifier.weight")
    classifier_bias = state_dict.get("classifier.bias")
    if classifier_weight is None or classifier_bias is None:
        raise ValueError("state dict is missing classifier tensors")
    final = keep[-1]
    source_width = int(channels[-1])
    classifier_columns = final + [source_width + value for value in final]
    classifier_columns += [2 * source_width + value for value in final]
    result["classifier.weight"] = classifier_weight.index_select(
        1, torch.as_tensor(classifier_columns, dtype=torch.long)).clone()
    return result


def compact_model(model, keep_indices):
    """Construct a smaller CNN and transfer all inherited parameters.

    The source model must be the three-stage multistat contract.  Dropout
    probabilities and per-stage kernel sizes are copied so surgery changes
    only channel dimensions, not regularization or receptive fields.
    """

    if not isinstance(model, CNN1D):
        raise TypeError("channel surgery expects a CNN1D source model")
    if model.pooling_contract != "multistat_average_max_endpoint":
        raise ValueError("channel surgery requires multistat pooling")
    if len(model.channels) != 3:
        raise ValueError("channel surgery requires exactly three stages")
    keep = validate_keep_indices(model.channels, keep_indices)
    convolutions = [model.features[index] for index in (0, 3, 6)]
    compact = CNN1D(
        input_channels=convolutions[0].in_channels,
        class_count=model.classifier.out_features,
        channels=[len(values) for values in keep],
        kernel_sizes=list(model.kernel_sizes),
        dropout=model.features[2].p,
        pooling_contract=model.pooling_contract,
        dilations=[convolution.dilation[0] for convolution in convolutions],
    )
    compact.load_state_dict(compact_state_dict(
        model.state_dict(), model.channels, keep), strict=True)
    return compact


def surgery_metadata(source_sha256, source_channels, keep_indices):
    """Create serializable provenance for a physically compact checkpoint."""

    keep = validate_keep_indices(source_channels, keep_indices)
    return {
        "source_teacher_sha256": str(source_sha256),
        "source_channels": [int(value) for value in source_channels],
        "keep_indices": [[int(value) for value in values] for values in keep],
        "target_channels": [len(values) for values in keep],
        "physical_channel_deletion": True,
        "pooling_order": ["average", "maximum", "endpoint"],
    }


def verify_surgery_equivalence(source, compact, keep_indices, inputs,
                               absolute_tolerance=1.0e-6):
    """Compare a compact graph with the source graph's removed channels zeroed.

    The reference executes the unmodified source modules and inserts explicit
    output masks after every stage.  A passing comparison proves that tensor
    slicing changed dimensions only; it did not randomly initialize retained
    parameters or disturb the three classifier slices.
    """

    keep = validate_keep_indices(source.channels, keep_indices)
    source_was_training, compact_was_training = source.training, compact.training
    source.eval()
    compact.eval()
    try:
        with torch.no_grad():
            features = inputs
            for stage, retained in enumerate(keep):
                start = stage * 3
                for offset in range(3):
                    features = source.features[start + offset](features)
                mask = torch.zeros(features.shape[1], dtype=features.dtype,
                                   device=features.device)
                mask[retained] = 1.0
                features = features * mask.view(1, -1, 1)
            reference = source.classifier(source._summary(features))
            actual = compact(inputs)
    finally:
        source.train(source_was_training)
        compact.train(compact_was_training)
    maximum_error = float(torch.max(torch.abs(reference - actual)).cpu())
    if not torch.allclose(reference, actual, rtol=0.0,
                          atol=float(absolute_tolerance)):
        raise ValueError("channel surgery logits differ by {}".format(maximum_error))
    return maximum_error
