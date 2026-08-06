#!/usr/bin/env python3
"""Train one Stage-1B width/seed through FP, W1A8, and W1A1 stages.

The command reads only train and validation rows from the frozen L32 window
CSV.  It converts the audited normalized scalar back to integer sensor codes,
applies the deterministic thermometer encoder, and never materializes IID
features in a process that can update weights.
"""

from __future__ import print_function

import argparse
import csv
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.bnn.input_encoding import encode_windows
from power_macro.tcn_detection.bnn.nofc_model import (
    BinaryNoFCModel,
    FPNoFCModel,
    validate_width,
)
from power_macro.tcn_detection.dataset.model_data import (
    filter_split,
    load_window_table,
    sha256_file,
)
from power_macro.tcn_detection.train.common import (
    configure_cpu,
    make_loader,
    read_json,
)
from power_macro.tcn_detection.train.train_binary_classifier import checkpoint_metrics
from power_macro.tcn_detection.train.train_classifier import save_checkpoint_atomic


def decode_code_windows(table):
    """Recover exact 0..32 codes from the approved ``(code-15)/17`` lattice."""

    if table.features.ndim != 3 or tuple(table.features.shape[1:]) != (1, 32):
        raise ValueError("BNN training requires normalized scalar L32 windows")
    values = table.features[:, 0, :].astype(np.float64, copy=False)
    reconstructed = values * 17.0 + 15.0
    codes = np.rint(reconstructed).astype(np.int16)
    encoded = (codes.astype(np.float64) - 15.0) / 17.0
    if (np.any(codes < 0) or np.any(codes > 32)
            or not np.allclose(values, encoded, rtol=0.0, atol=2.0e-6)):
        raise ValueError("window contains a value outside the sensor-code lattice")
    return codes


def load_training_arrays(windows):
    """Load train/validation only, then return thermometer tensors and labels."""

    table = load_window_table(windows, splits={"train", "validation"})
    if set(np.unique(table.labels)) != {0, 1}:
        raise ValueError("BNN training windows must contain Safe and Critical only")
    codes = decode_code_windows(table)
    encoded = encode_windows(codes).astype(np.float32, copy=False)
    train_indices = np.asarray([
        index for index, row in enumerate(table.metadata)
        if row["split"] == "train"], dtype=np.int64)
    validation_indices = np.asarray([
        index for index, row in enumerate(table.metadata)
        if row["split"] == "validation"], dtype=np.int64)
    if not len(train_indices) or not len(validation_indices):
        raise ValueError("both train and validation rows are required")
    return {
        "table": table,
        "train_features": encoded[train_indices],
        "train_labels": table.labels[train_indices],
        "validation_features": encoded[validation_indices],
        "validation_labels": table.labels[validation_indices],
        "validation_metadata": tuple(table.metadata[index]
                                      for index in validation_indices),
    }


def probabilities_from_scores(scores):
    """Convert one Critical logit per window to the project binary schema."""

    scores = np.asarray(scores, dtype=np.float64)
    if scores.ndim != 1 or not np.all(np.isfinite(scores)):
        raise ValueError("model scores must be finite [N] values")
    critical = 1.0 / (1.0 + np.exp(-scores))
    return np.stack((1.0 - critical, critical), axis=1)


def predict_scores(model, features, batch_size):
    """Run deterministic evaluation without retaining all layer tensors."""

    loader = make_loader(features, np.zeros(len(features), dtype=np.int64),
                         int(batch_size))
    model.eval()
    scores = []
    with torch.no_grad():
        for inputs, _ in loader:
            scores.append(model(inputs)["score"].cpu().numpy())
    return np.concatenate(scores).astype(np.float64, copy=False)


def write_validation_predictions(path, metadata, probabilities):
    """Persist validation-only scores with endpoint provenance, never features."""

    fields = ["window_id", "trace_id", "split", "end_index", "target_label",
              "prediction", "prob_safe", "prob_critical"]
    temporary = Path(path).with_suffix(Path(path).suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row, probability in zip(metadata, probabilities):
            if row["split"] != "validation":
                raise ValueError("validation writer received a non-validation row")
            writer.writerow({
                "window_id": row["window_id"], "trace_id": row["trace_id"],
                "split": row["split"], "end_index": row["end_index"],
                "target_label": row["target_label"],
                "prediction": int(np.argmax(probability)),
                "prob_safe": "{:.9g}".format(float(probability[0])),
                "prob_critical": "{:.9g}".format(float(probability[1])),
            })
    temporary.replace(path)


def _stage_model(stage, width):
    """Construct the exact model class required for one training stage."""

    return (FPNoFCModel(width) if stage == "fp_pretrain"
            else BinaryNoFCModel(width, "w1a8" if stage == "w1a8" else "w1a1"))


def train_stage(model, stage, arrays, training_config, seed, output_dir,
                model_config, windows):
    """Train one stage with validation-only checkpoint selection and early stop."""

    batch_size = int(training_config["batch_size"])
    max_epochs = int(training_config["max_epochs"])
    patience = int(training_config["early_stopping_patience"])
    if batch_size < 1 or max_epochs < 1 or patience < 1:
        raise ValueError("training limits must be positive")
    train_loader = make_loader(
        arrays["train_features"], arrays["train_labels"], batch_size,
        shuffle=True, seed=seed)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=float(training_config["learning_rate"]),
        weight_decay=float(training_config["weight_decay"]))
    criterion = torch.nn.BCEWithLogitsLoss()
    checkpoint_path = Path(output_dir) / "best_checkpoint.pt"
    history = []
    best_key = None
    best_epoch = 0
    stale = 0
    started = time.perf_counter()
    for epoch in range(1, max_epochs + 1):
        model.train()
        losses = []
        for inputs, targets in train_loader:
            optimizer.zero_grad(set_to_none=True)
            scores = model(inputs)["score"]
            loss = criterion(scores, targets.to(dtype=torch.float32))
            if not bool(torch.isfinite(loss)):
                raise FloatingPointError("non-finite BNN training loss")
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))

        validation_scores = predict_scores(
            model, arrays["validation_features"], batch_size)
        probabilities = probabilities_from_scores(validation_scores)
        metrics = checkpoint_metrics(arrays["validation_labels"], probabilities)
        selection_key = tuple(float(value) for value in metrics.pop("selection_key"))
        record = {"epoch": epoch, "train_loss": float(np.mean(losses)),
                  "selection_key": list(selection_key)}
        record.update(metrics)
        history.append(record)
        improved = best_key is None or selection_key > best_key
        if improved:
            best_key = selection_key
            best_epoch = epoch
            stale = 0
            save_checkpoint_atomic({
                "schema_version": 1,
                "task": "safe_critical_binary",
                "model": "fp_nofc" if stage == "fp_pretrain" else "bnn_nofc",
                "stage": stage,
                "mode": "fp" if stage == "fp_pretrain" else stage,
                "width": int(model.width), "window_length": 32,
                "seed": int(seed), "model_config": model_config,
                "training_config": training_config,
                "input_contract": "thermometer32_sensor_code_only",
                "state_dict": model.state_dict(),
                "best_epoch": int(epoch),
                "validation_metrics": metrics,
                "iid_features_loaded": False,
            }, checkpoint_path)
        else:
            stale += 1
        if stale >= patience:
            break

    checkpoint = torch.load(checkpoint_path, map_location="cpu",
                            weights_only=False)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    validation_scores = predict_scores(model, arrays["validation_features"], batch_size)
    probabilities = probabilities_from_scores(validation_scores)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    write_validation_predictions(
        Path(output_dir) / "validation_predictions.csv",
        arrays["validation_metadata"], probabilities)
    final_metrics = checkpoint_metrics(arrays["validation_labels"], probabilities)
    final_metrics.pop("selection_key")
    summary = {
        "schema_version": 1, "task": "safe_critical_binary",
        "model": "fp_nofc" if stage == "fp_pretrain" else "bnn_nofc",
        "stage": stage, "mode": "fp" if stage == "fp_pretrain" else stage,
        "width": int(model.width), "seed": int(seed), "window_length": 32,
        "best_epoch": int(best_epoch), "epochs_completed": len(history),
        "history": history, "best_validation_metrics": final_metrics,
        "training_config": training_config, "model_config": model_config,
        "input_contract": "thermometer32_sensor_code_only",
        "iid_features_loaded": False,
        "windows_sha256": sha256_file(windows),
        "runtime": {"torch": torch.__version__,
                    "python": platform.python_version(),
                    "cpu_threads": torch.get_num_threads()},
        "training_wall_seconds": time.perf_counter() - started,
    }
    (Path(output_dir) / "training_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def run_training(args):
    """Run all three stages and publish one immutable width/seed directory."""

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError("refusing to overwrite BNN training run")
    model_config = read_json(args.model_config)
    training_config = read_json(args.training_config)
    width = validate_width(args.width)
    if width not in [int(value) for value in model_config["candidate_widths"]]:
        raise ValueError("requested width is absent from model configuration")
    if int(args.seed) not in [int(value) for value in training_config["seeds"]]:
        raise ValueError("requested seed is absent from training configuration")
    if model_config.get("window_length") != 32 or model_config.get("input_channels") != 32:
        raise ValueError("model configuration is not the fixed thermometer L32 contract")
    configure_cpu(args.seed, training_config["cpu_threads_per_process"])
    arrays = load_training_arrays(args.windows)
    output_dir.mkdir(parents=True, exist_ok=False)
    summaries = {}

    fp_model = _stage_model("fp_pretrain", width)
    fp_dir = output_dir / "fp_pretrain"
    fp_dir.mkdir()
    summaries["fp_pretrain"] = train_stage(
        fp_model, "fp_pretrain", arrays, training_config, args.seed,
        fp_dir, model_config, args.windows)

    w1a8_model = _stage_model("w1a8", width)
    w1a8_model.initialize_from_fp(fp_model)
    w1a8_dir = output_dir / "w1a8"
    w1a8_dir.mkdir()
    summaries["w1a8"] = train_stage(
        w1a8_model, "w1a8", arrays, training_config, args.seed,
        w1a8_dir, model_config, args.windows)

    w1a1_model = _stage_model("w1a1", width)
    w1a1_model.initialize_from_binary(w1a8_model)
    w1a1_dir = output_dir / "w1a1"
    w1a1_dir.mkdir()
    summaries["w1a1"] = train_stage(
        w1a1_model, "w1a1", arrays, training_config, args.seed,
        w1a1_dir, model_config, args.windows)
    (output_dir / "run_summary.json").write_text(
        json.dumps({"schema_version": 1, "width": width, "seed": int(args.seed),
                    "stages": summaries, "iid_features_loaded": False},
                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summaries


def parse_args():
    """Parse one explicit immutable width/seed training run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    result = run_training(arguments)
    print(json.dumps({"status": "PASS", "stages": list(result)}, sort_keys=True))
