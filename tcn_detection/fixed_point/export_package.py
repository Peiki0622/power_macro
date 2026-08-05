#!/usr/bin/env python3
"""Export the selected bit-true CNN as a versioned, round-tripped RTL package."""

from __future__ import print_function

import argparse
import copy
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sklearn
import torch

from power_macro.tcn_detection.fixed_point import bittrue
from power_macro.tcn_detection.fixed_point.float_reference import (
    checkpoint_inputs, decode_sensor_codes, float_metrics,
    load_development_windows, numpy_float_forward, select_golden_windows,
    torch_float_inference)
from power_macro.tcn_detection.fixed_point.provenance import (
    build_validated_model, sha256_file, source_commit)


METRIC_NAMES = (
    "accuracy", "balanced_accuracy", "macro_f1", "critical_pr_auc",
    "critical_recall", "safe_window_false_alarm_rate",
)


def utc_now():
    """Return an ISO-8601 UTC timestamp with an explicit timezone."""

    return datetime.now(timezone.utc).isoformat()


def write_json(path, payload):
    """Write canonical, human-readable JSON with stable key ordering."""

    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")


def _signed_word(value, bits):
    """Encode one signed integer as a fixed-width two's-complement word."""

    lower, upper = bittrue.signed_limits(bits)
    value = int(value)
    if value < lower or value > upper:
        raise OverflowError("value {} does not fit signed {} bits".format(
            value, bits))
    return value & ((1 << int(bits)) - 1)


def write_mem(path, values, bits, tensor_name, flatten_order):
    """Write one integer tensor as documented hexadecimal words.

    Comments use ``//`` so common Verilog memory readers ignore them.  Data is
    one fixed-width word per line and always flattens in C order.  Conv weights
    therefore follow [out][in][kernel], matching both NumPy and the future RTL
    address generator; the L32 first-layer bias follows [out][position].
    """

    path = Path(path)
    array = np.asarray(values, dtype=np.int64)
    digits = int(math.ceil(int(bits) / 4.0))
    lines = [
        "// tensor: {}".format(tensor_name),
        "// shape: {}".format("x".join(str(value) for value in array.shape)),
        "// signed_bits: {}".format(int(bits)),
        "// flatten_order: {}".format(flatten_order),
    ]
    lines.extend("{:0{}x}".format(_signed_word(value, bits), digits)
                 for value in array.reshape(-1, order="C"))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return {
        "path": str(path.name), "tensor_name": tensor_name,
        "shape": list(array.shape), "signed_bits": int(bits),
        "flatten_order": flatten_order, "entry_count": int(array.size),
        "sha256": sha256_file(path),
    }


def read_mem(path, shape, bits):
    """Read a fixed-width memory file and sign-extend every word."""

    words = []
    with Path(path).open(encoding="ascii") as stream:
        for line in stream:
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            unsigned = int(stripped, 16)
            if unsigned >= (1 << (int(bits) - 1)):
                unsigned -= 1 << int(bits)
            words.append(unsigned)
    expected = int(np.prod(shape))
    if len(words) != expected:
        raise ValueError("memory entry count differs from declared shape")
    return np.asarray(words, dtype=np.int64).reshape(tuple(shape), order="C")


def _write_weight_package(directory, package):
    """Write selected coefficients and return records used for round-trip."""

    directory.mkdir(parents=True, exist_ok=False)
    records = []
    for layer in package["layers"]:
        accumulator_bits = int(package["accumulator_widths"][layer["name"]])
        records.append((layer, "weights", write_mem(
            directory / "{}_weights.mem".format(layer["name"]),
            layer["weights"], package["weight_bits"],
            "{}.weights".format(layer["name"]),
            "out_channel,in_channel,kernel")))
        records.append((layer, "bias", write_mem(
            directory / "{}_bias.mem".format(layer["name"]),
            layer["bias"], accumulator_bits,
            "{}.bias".format(layer["name"]),
            ("out_channel,output_position" if layer["bias"].ndim == 2
             else "out_channel"))))
    classifier = package["classifier"]
    classifier_bits = int(package["accumulator_widths"]["classifier"])
    records.append((classifier, "weights", write_mem(
        directory / "classifier_weights.mem", classifier["weights"],
        package["weight_bits"], "classifier.weights",
        "output_class,summary_feature")))
    records.append((classifier, "bias", write_mem(
        directory / "classifier_bias.mem", classifier["bias"],
        classifier_bits, "classifier.bias", "output_class")))
    return records


def _format_document(records, package):
    """Describe the neutral memory representation without implementation lore."""

    classifier_width = int(package["classifier"]["weights"].shape[1])
    if classifier_width % 3 != 0:
        raise ValueError("classifier summary width must contain three branches")
    branch_width = classifier_width // 3
    first_bias_shape = list(package["layers"][0]["bias"].shape)

    lines = [
        "# Fixed-Point Weight Memory Format", "",
        "Each `.mem` file contains one fixed-width hexadecimal two's-complement "
        "word per data line. Lines beginning with `//` are metadata comments.",
        "", "All tensors flatten in C order. Convolution weights use "
        "`[out_channel][in_channel][kernel]`; classifier weights use "
        "`[output_class][summary_feature]`. The summary order is average "
        "features 0-{0}, maximum features {1}-{2}, and endpoint features "
        "{3}-{4}.".format(branch_width - 1, branch_width,
                            2 * branch_width - 1, 2 * branch_width,
                            3 * branch_width - 1),
        "", "The first convolution bias is `{}` and retains position-specific "
        "edge columns after the train-only input standardizer is folded into "
        "raw sensor-code arithmetic.".format(first_bias_shape), "",
        "| File | Tensor | Shape | Signed bits | Entries | SHA256 |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for _, _, record in records:
        lines.append("| `{}` | `{}` | `{}` | {} | {} | `{}` |".format(
            record["path"], record["tensor_name"], record["shape"],
            record["signed_bits"], record["entry_count"], record["sha256"]))
    return "\n".join(lines) + "\n"


def _round_trip_weights(directory, package, records):
    """Replace every coefficient from disk and assert exact numeric identity."""

    restored = copy.deepcopy(package)
    # Locate copied destination dictionaries by the stable layer/classifier
    # names rather than relying on object identity from the original package.
    destinations = {layer["name"]: layer for layer in restored["layers"]}
    destinations["classifier"] = restored["classifier"]
    for original_owner, field, record in records:
        owner = destinations[original_owner["name"]]
        recovered = read_mem(directory / record["path"], record["shape"],
                             record["signed_bits"])
        if not np.array_equal(recovered, original_owner[field]):
            raise ValueError("memory round-trip changed {}".format(
                record["tensor_name"]))
        owner[field] = recovered
    return restored


def _package_metadata(package, records):
    """Convert selected numeric formats to JSON without embedding large arrays."""

    files = {record["tensor_name"]: record for _, _, record in records}
    layers = []
    for layer in package["layers"]:
        layers.append({
            "name": layer["name"],
            "weight_file": files["{}.weights".format(layer["name"])],
            "bias_file": files["{}.bias".format(layer["name"])],
            "weight_exponents": layer["weight_exponents"].tolist(),
            "input_exponent": int(layer["input_exponent"]),
            "accumulator_exponents": layer["accumulator_exponents"].tolist(),
            "output_exponent": int(layer["output_exponent"]),
            "accumulator_bounds": layer["accumulator_bounds"].tolist(),
            "accumulator_width": int(package["accumulator_widths"][layer["name"]]),
        })
    classifier = package["classifier"]
    return {
        "architecture_id": package["architecture_id"],
        "candidate_id": package["candidate_id"],
        "weight_bits": int(package["weight_bits"]),
        "activation_bits": int(package["activation_bits"]),
        "classifier_output_bits": int(classifier["output_bits"]),
        "classifier_output_exponent": int(classifier["output_exponent"]),
        "activation_exponents": dict(package["activation_exponents"]),
        "normalization_fold": dict(package["normalization_fold"]),
        "layers": layers,
        "classifier": {
            "weight_file": files["classifier.weights"],
            "bias_file": files["classifier.bias"],
            "weight_exponents": classifier["weight_exponents"].tolist(),
            "input_exponent": int(classifier["input_exponent"]),
            "accumulator_exponents": classifier[
                "accumulator_exponents"].tolist(),
            "accumulator_bounds": classifier["accumulator_bounds"].tolist(),
            "accumulator_width": int(package["accumulator_widths"]["classifier"]),
        },
    }


def _write_golden(directory, table, codes, checkpoint_input_values,
                  float_inference, selection, model, package):
    """Write source windows, float trace, integer trace, and expected logits."""

    directory.mkdir(parents=True, exist_ok=False)
    indices = np.asarray([item["row_index"] for item in selection], dtype=np.int64)
    selected_codes = codes[indices]
    integer = bittrue.run_bittrue(
        selected_codes, package, batch_size=len(indices),
        capture_intermediates=True)
    float_trace = numpy_float_forward(checkpoint_input_values[indices], model)

    with (directory / "windows.jsonl").open("w", encoding="utf-8") as stream:
        for item, index in zip(selection, indices):
            payload = dict(item)
            payload["sensor_codes"] = codes[index, 0].astype(int).tolist()
            payload["normalized_sensor_code"] = table.features[
                index, 0].astype(float).tolist()
            stream.write(json.dumps(payload, sort_keys=True) + "\n")

    tensors = {}
    for name, values in float_trace.items():
        tensors["float_{}".format(name)] = values
    for name, values in integer["trace"].items():
        tensors["integer_{}".format(name)] = values
    np.savez_compressed(directory / "expected_layer_outputs.npz", **tensors)

    with (directory / "expected_logits.csv").open(
            "w", newline="", encoding="utf-8") as stream:
        fields = [
            "category", "window_id", "trace_id", "end_index", "target_label",
            "float_logit_safe", "float_logit_critical",
            "integer_logit_safe", "integer_logit_critical",
            "dequantized_logit_safe", "dequantized_logit_critical",
            "integer_logit_difference", "decision",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row_number, item in enumerate(selection):
            writer.writerow({
                "category": item["category"], "window_id": item["window_id"],
                "trace_id": item["trace_id"], "end_index": item["end_index"],
                "target_label": item["target_label"],
                "float_logit_safe": "{:.9g}".format(
                    float_inference.logits[indices[row_number], 0]),
                "float_logit_critical": "{:.9g}".format(
                    float_inference.logits[indices[row_number], 1]),
                "integer_logit_safe": int(integer["integer_logits"][row_number, 0]),
                "integer_logit_critical": int(integer["integer_logits"][row_number, 1]),
                "dequantized_logit_safe": "{:.12g}".format(
                    integer["dequantized_logits"][row_number, 0]),
                "dequantized_logit_critical": "{:.12g}".format(
                    integer["dequantized_logits"][row_number, 1]),
                "integer_logit_difference": int(
                    integer["integer_logits"][row_number, 1]
                    - integer["integer_logits"][row_number, 0]),
                "decision": int(integer["predictions"][row_number]),
            })
    return integer, tensors


def _report_markdown(search_report, package_metadata, fold_report,
                     golden_round_trip_passed):
    """Render the phase-one numeric acceptance report."""

    lines = [
        "# Fixed-Point `{}` Report".format(
            package_metadata["architecture_id"]), "",
        "Status: **PASS**. This is a validation-selected bit-true reference "
        "candidate, not a deployment-ready model and not a new IID result.", "",
        "## Selected Numeric Contract", "",
        "- Candidate: `{}` (signed W{}, signed A{}, signed INT32 logits).".format(
            package_metadata["candidate_id"], package_metadata["weight_bits"],
            package_metadata["activation_bits"]),
        "- Weight scales: symmetric per-output-channel powers of two; "
        "activation scales: symmetric per-layer powers of two.",
        "- Rounding: round-to-nearest, ties-to-even; saturation occurs after "
        "each requantization; validation saturation count is zero.",
        "- Pooling: sum 32 relu3 integers, ties-to-even divide by 32; maximum "
        "and endpoint retain the relu3 scale.",
        "- Decision: compare two common-scale INT32 logits; exact ties select "
        "Safe, matching two-class argmax.",
        "- Input folding: alpha `{:.15g}`, beta `{:.15g}`, first bias shape "
            "`{}` to preserve standardized zero padding.".format(
            package_metadata["normalization_fold"]["alpha"],
            package_metadata["normalization_fold"]["beta"],
            package_metadata["normalization_fold"]["bias_shape"]), "",
        "## Validation Metrics", "",
        "| Candidate | Accuracy | Balanced acc. | Macro-F1 | Critical PR-AUC | "
        "Critical recall | Safe FAR | Gates |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    float_metrics_report = search_report["float_validation_metrics"]
    lines.append("| Float | {:.6f} | {:.6f} | {:.6f} | {:.6f} | {:.6f} | "
                 "{:.6f} | reference |".format(
                     float_metrics_report["accuracy"],
                     float_metrics_report["balanced_accuracy"],
                     float_metrics_report["macro_f1"],
                     float_metrics_report["critical_pr_auc"],
                     float_metrics_report["critical_recall"],
                     float_metrics_report["safe_window_false_alarm_rate"]))
    for candidate in search_report["candidate_reports"]:
        metrics = candidate["validation_metrics"]
        lines.append("| {} | {:.6f} | {:.6f} | {:.6f} | {:.6f} | {:.6f} | "
                     "{:.6f} | {} |".format(
                         candidate["candidate_id"], metrics["accuracy"],
                         metrics["balanced_accuracy"], metrics["macro_f1"],
                         metrics["critical_pr_auc"], metrics["critical_recall"],
                         metrics["safe_window_false_alarm_rate"],
                         "PASS" if candidate["quality_gates"]["passed"] else "FAIL"))
    selected_report = next(item for item in search_report["candidate_reports"]
                           if item["candidate_id"] == package_metadata["candidate_id"])
    lines.extend([
        "", "## Overflow and Determinism", "",
        "- Derived accumulator widths: `{}`.".format(
            selected_report["accumulator_widths"]),
        "- Observed validation accumulator ranges stayed within every "
        "per-channel analytical bound.",
        "- Validation upper-saturation counts: `{}`.".format(
            selected_report["saturation_counts"]),
        "- Exhaustive normalization fold error over sensor codes 0..32: "
        "`{:.9g}` maximum absolute float error.".format(
            fold_report["max_abs_error"]),
        "- Exported `.mem` files were reloaded and golden tensors/logits were "
        "bit-exact: `{}`.".format(str(bool(golden_round_trip_passed)).lower()),
        "", "## Scientific Boundary and Remaining Risks", "",
        "- Calibration used train only; quantization selection and acceptance "
        "used validation only. IID/OOD features and predictions were not read.",
        "- Power-of-two scaling prioritizes a shift-only RTL path; synthesis, "
        "cycle accuracy, area, timing, and power remain tasks for the RTL phase.",
        "- Validation evidence does not establish deployment readiness or "
        "side-channel masking effectiveness.", "",
    ])
    return "\n".join(lines)


def _file_manifest(root):
    """Hash every package file except the manifest that contains those hashes."""

    files = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files[str(path.relative_to(root))] = {
                "sha256": sha256_file(path), "bytes": int(path.stat().st_size)}
    return files


def export_package(args):
    """Build, verify, and atomically publish one complete hardware package."""

    started = utc_now()
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        raise FileExistsError("refusing to overwrite fixed-point package")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(output_dir.name), dir=str(output_dir.parent)))
    try:
        model, checkpoint, provenance = build_validated_model(
            args.model_config, args.checkpoint, args.fixed_point_config)
        config = json.loads(Path(args.fixed_point_config).read_text(encoding="utf-8"))
        train = load_development_windows(args.windows, "train")
        validation = load_development_windows(args.windows, "validation")
        train_inputs = checkpoint_inputs(train, checkpoint["normalizer"])
        validation_inputs = checkpoint_inputs(
            validation, checkpoint["normalizer"])
        validation_codes = decode_sensor_codes(validation.features)
        float_inference = torch_float_inference(validation_inputs, model)
        all_float_metrics = float_metrics(validation.labels, float_inference)
        float_metric_report = {name: all_float_metrics[name]
                               for name in METRIC_NAMES}
        packages, search_report = bittrue.search_candidates(
            model, checkpoint, train_inputs, validation_codes,
            validation.labels, float_metric_report, config, batch_size=512)
        if search_report["status"] != "PASS":
            raise ValueError("no quantization candidate passed frozen gates")
        selected_package = packages[search_report["selected_candidate"]]

        records = _write_weight_package(temporary / "weights", selected_package)
        (temporary / "weights" / "FORMAT.md").write_text(
            _format_document(records, selected_package), encoding="utf-8")
        restored_package = _round_trip_weights(
            temporary / "weights", selected_package, records)
        package_metadata = _package_metadata(selected_package, records)
        selected_windows = select_golden_windows(
            validation, validation_codes, float_inference, model)
        original_golden, original_tensors = _write_golden(
            temporary / "golden", validation, validation_codes,
            validation_inputs, float_inference, selected_windows, model,
            selected_package)
        restored_golden = bittrue.run_bittrue(
            validation_codes[np.asarray([item["row_index"]
                                         for item in selected_windows])],
            restored_package, batch_size=len(selected_windows),
            capture_intermediates=True)
        if (not np.array_equal(original_golden["integer_logits"],
                               restored_golden["integer_logits"])
                or any(not np.array_equal(
                    original_tensors["integer_{}".format(name)], value)
                    for name, value in restored_golden["trace"].items())):
            raise ValueError("reloaded memory package changed golden outputs")

        fold_report = __import__(
            "power_macro.tcn_detection.fixed_point.normalization",
            fromlist=["exhaustive_fold_error"]).exhaustive_fold_error(
                model, checkpoint["normalizer"])
        quantization_config = {
            "schema_version": 1,
            "source_contract": config,
            "source_contract_sha256": sha256_file(args.fixed_point_config),
            "selected_numeric_package": package_metadata,
        }
        write_json(temporary / "quantization_config.json", quantization_config)
        write_json(temporary / "quantization_search.json", search_report)

        finished = utc_now()
        provenance.update({
            "source_commit_sha": source_commit(args.repository_root),
            "source_worktree_dirty": bool(subprocess.check_output(
                ["git", "-C", str(args.repository_root), "status", "--porcelain"],
                text=True).strip()),
            "model_config_path": str(Path(args.model_config).resolve()),
            "checkpoint_path": str(Path(args.checkpoint).resolve()),
            "fixed_point_config_path": str(Path(args.fixed_point_config).resolve()),
            "windows_path": str(Path(args.windows).resolve()),
            "windows_sha256": sha256_file(args.windows),
            "training_config_path": str(Path(args.training_config).resolve()),
            "training_config_sha256": sha256_file(args.training_config),
            "fixed_point_config_sha256": sha256_file(args.fixed_point_config),
            "random_seed": int(config["data_policy"]["random_seed"]),
            "tool_versions": {
                "python": sys.version.replace("\n", " "),
                "numpy": np.__version__, "torch": torch.__version__,
                "scikit_learn": sklearn.__version__,
            },
            "command_line": list(sys.argv),
            "start_time_utc": started, "end_time_utc": finished,
            "exit_status": 0,
            "iid_features_loaded": False, "iid_metrics_computed": False,
        })
        write_json(temporary / "model_provenance.json", provenance)
        (temporary / "FIXED_POINT_REPORT.md").write_text(
            _report_markdown(search_report, package_metadata, fold_report, True),
            encoding="utf-8")
        write_json(temporary / "manifest.json", {
            "schema_version": 1, "status": "PASS",
            "architecture_id": selected_package["architecture_id"],
            "selected_candidate": search_report["selected_candidate"],
            "checkpoint_sha256": provenance["checkpoint_sha256"],
            "quantization_config_sha256": sha256_file(
                temporary / "quantization_config.json"),
            "input_window_set_sha256": sha256_file(args.windows),
            "files": _file_manifest(temporary),
        })
        os.rename(str(temporary), str(output_dir))
        return output_dir
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def parse_args():
    """Parse explicit versioned inputs; no path is inferred from a run name."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--fixed-point-config", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main():
    """CLI entry point."""

    output = export_package(parse_args())
    print(str(output.resolve()))


if __name__ == "__main__":
    main()
