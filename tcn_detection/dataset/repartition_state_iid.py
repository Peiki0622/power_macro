#!/usr/bin/env python3
"""Repartition existing current-state traces into train/validation/IID.

The module never creates electrical samples.  It treats the existing corpus
and current-state labels as immutable evidence, builds leakage-safe connected
components, and later assigns those components to a new versioned split.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


CLASS_IDS = (0, 1, 2)


def sha256_file(path):
    """Return a bounded-memory digest for input and output provenance."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_digest(payload):
    """Hash one JSON-compatible value with stable ordering and separators."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DisjointSet(object):
    """Minimal union-find used to close every leakage relationship.

    A priority rule such as "hard pair, otherwise base waveform" is unsafe:
    two traces may be connected indirectly through both identifiers.  Union-
    find computes the transitive closure, ensuring the entire connected
    component receives one split assignment.
    """

    def __init__(self, identifiers):
        self.parent = {identifier: identifier for identifier in identifiers}
        self.rank = {identifier: 0 for identifier in identifiers}

    def find(self, identifier):
        """Return the canonical root while compressing the lookup path."""

        parent = self.parent[identifier]
        if parent != identifier:
            self.parent[identifier] = self.find(parent)
        return self.parent[identifier]

    def union(self, left, right):
        """Join two roots deterministically using rank then lexical order."""

        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        left_rank = self.rank[left_root]
        right_rank = self.rank[right_root]
        # Lexical ordering makes equal-rank unions independent of input row
        # order.  This is important because the published component inventory
        # must reproduce byte-for-byte from a semantically identical corpus.
        if left_rank < right_rank or (left_rank == right_rank and left_root > right_root):
            left_root, right_root = right_root, left_root
            left_rank, right_rank = right_rank, left_rank
        self.parent[right_root] = left_root
        if left_rank == right_rank:
            self.rank[left_root] += 1


def load_corpus(path):
    """Load 240 unique trace specifications from the immutable JSONL corpus."""

    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    trace_ids = [row["trace_id"] for row in rows]
    if not rows or len(trace_ids) != len(set(trace_ids)):
        raise ValueError("corpus is empty or contains duplicate trace IDs")
    return rows


def load_state_profiles(label_dir, expected_trace_ids):
    """Count current-state samples per trace without exposing sensor features.

    Aggregated truth counts are legitimate split-stratification attributes;
    the function deliberately reads only trace identity, eligibility, and
    ``current_raw_label``.  Sensor code and voltage never enter the inventory
    or optimization objective.
    """

    profiles = {}
    for path in sorted(Path(label_dir).glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != 500 or {row["trace_id"] for row in rows} != {path.stem}:
            raise ValueError("state label trace is malformed: {}".format(path))
        if any(row.get("state_label_eligible", "").lower() != "true" for row in rows):
            raise ValueError("current-state label layer contains an ineligible row")
        counts = Counter(int(row["current_raw_label"]) for row in rows)
        if set(counts) - set(CLASS_IDS):
            raise ValueError("current-state label is outside 0..2")
        profiles[path.stem] = {str(class_id): counts[class_id] for class_id in CLASS_IDS}
    if set(profiles) != set(expected_trace_ids):
        raise ValueError("label trace IDs differ from corpus trace IDs")
    return profiles


def coarse_family_for(component_rows, coarse_groups):
    """Return the component's coarse distribution category.

    Any hard-pair membership takes precedence because the operational paired
    experiment is the relevant grouping characteristic.  Non-pair components
    must map to exactly one configured family category.
    """

    if any(row.get("hard_pair_id") for row in component_rows):
        return "hard_pair"
    families = {row["waveform_family_id"] for row in component_rows}
    matches = [name for name, members in coarse_groups.items()
               if name != "hard_pair" and families <= set(members)]
    if len(matches) != 1:
        raise ValueError("component families do not map to one coarse category: {}".format(
            sorted(families)))
    return matches[0]


def build_component_inventory(corpus_rows, state_profiles, config):
    """Build stable connected components and their stratification attributes."""

    trace_by_id = {row["trace_id"]: row for row in corpus_rows}
    disjoint = DisjointSet(trace_by_id)
    # Each non-empty value in either link field defines a clique.  Joining the
    # first member to every other member is sufficient to construct that clique
    # while keeping the implementation linear in the number of traces.
    for field in config["component_link_fields"]:
        buckets = defaultdict(list)
        for row in corpus_rows:
            value = row.get(field)
            if value:
                buckets[value].append(row["trace_id"])
        for members in buckets.values():
            first = members[0]
            for member in members[1:]:
                disjoint.union(first, member)

    grouped = defaultdict(list)
    for trace_id in trace_by_id:
        grouped[disjoint.find(trace_id)].append(trace_id)
    inventory = []
    for members in grouped.values():
        members = sorted(members)
        rows = [trace_by_id[trace_id] for trace_id in members]
        class_counts = {str(class_id): sum(
            int(state_profiles[trace_id][str(class_id)]) for trace_id in members)
                        for class_id in CLASS_IDS}
        exact_families = sorted({row["waveform_family_id"] for row in rows})
        component_id = "component_{}".format(stable_digest(members)[:16])
        inventory.append({
            "component_id": component_id,
            "trace_ids": members,
            "trace_count": len(members),
            "base_waveform_ids": sorted({row["base_waveform_id"] for row in rows}),
            "hard_pair_ids": sorted({row["hard_pair_id"] for row in rows if row.get("hard_pair_id")}),
            "waveform_families": exact_families,
            "coarse_family": coarse_family_for(rows, config["coarse_family_groups"]),
            "source_cohorts": sorted({row.get("source_cohort", "") for row in rows}),
            "background_modes": sorted({row.get("background_mode", "") for row in rows}),
            "duty_cycles": sorted({str(row.get("event_duty_cycle")) for row in rows}),
            "state_class_counts": class_counts,
            "maximum_state": max(class_id for class_id in CLASS_IDS if class_counts[str(class_id)] > 0),
            "original_splits": sorted({row["split"] for row in rows}),
        })
    inventory.sort(key=lambda component: component["component_id"])
    trace_ids = [trace_id for component in inventory for trace_id in component["trace_ids"]]
    if len(trace_ids) != len(trace_by_id) or set(trace_ids) != set(trace_by_id):
        raise ValueError("component inventory does not cover the corpus exactly once")
    return inventory


def component_trace_values(inventory, attribute, value):
    """Return per-component trace counts for one categorical attribute value."""

    values = []
    plural_field = {
        "waveform_family": "waveform_families",
        "source_cohort": "source_cohorts",
        "background_mode": "background_modes",
        "duty_cycle": "duty_cycles",
    }[attribute]
    for component in inventory:
        # A connected component can contain multiple attribute values.  Count
        # the entire component only when it represents the value uniformly;
        # mixed components are represented by their individual trace metadata
        # in ``build_stratification_measures`` below.
        values.append(component["trace_count"] if value in component[plural_field] else 0)
    return np.asarray(values, dtype=np.float64)


def build_stratification_measures(inventory, corpus_rows):
    """Build numeric measures whose split proportions should match globally.

    Every measure is a per-component vector.  State measures count samples;
    categorical measures count traces.  Using trace-level membership from the
    corpus avoids over-counting a mixed component under every listed value.
    """

    component_by_trace = {trace_id: index for index, component in enumerate(inventory)
                          for trace_id in component["trace_ids"]}
    measures = []
    for class_id in CLASS_IDS:
        measures.append({
            "name": "state_class:{}".format(class_id),
            "kind": "state_class",
            "values": np.asarray([component["state_class_counts"][str(class_id)]
                                  for component in inventory], dtype=np.float64),
        })

    categorical_fields = (
        ("waveform_family", "waveform_family_id"),
        ("source_cohort", "source_cohort"),
        ("background_mode", "background_mode"),
        ("duty_cycle", "event_duty_cycle"),
    )
    for public_name, corpus_field in categorical_fields:
        values = sorted({str(row.get(corpus_field)) for row in corpus_rows})
        for value in values:
            vector = np.zeros(len(inventory), dtype=np.float64)
            for row in corpus_rows:
                if str(row.get(corpus_field)) == value:
                    vector[component_by_trace[row["trace_id"]]] += 1.0
            measures.append({"name": "{}:{}".format(public_name, value),
                             "kind": public_name, "values": vector})

    for coarse in sorted({component["coarse_family"] for component in inventory}):
        measures.append({
            "name": "coarse_family:{}".format(coarse),
            "kind": "coarse_family",
            "values": np.asarray([component["trace_count"]
                                  if component["coarse_family"] == coarse else 0
                                  for component in inventory], dtype=np.float64),
        })
    for severity in CLASS_IDS:
        measures.append({
            "name": "maximum_state:{}".format(severity),
            "kind": "maximum_state",
            "values": np.asarray([component["trace_count"]
                                  if component["maximum_state"] == severity else 0
                                  for component in inventory], dtype=np.float64),
        })
    return measures


def solve_assignment(inventory, corpus_rows, config):
    """Solve the three-stage deterministic component assignment MILP.

    Variable layout is ``x[group,split]``, one scalar ``z`` for the maximum
    state-proportion deviation, then positive/negative absolute-deviation
    variables for every stratification measure and split.  The three solves
    reuse exactly the same feasible region:

    1. Minimize ``z``.
    2. Freeze the optimal ``z`` and minimize total normalized stratum error.
    3. Freeze both scientific objectives and minimize a SHA256-derived cost.

    The final stage does not improve metrics; it merely selects one stable
    member when several assignments are scientifically equivalent.
    """

    split_names = tuple(config["split_trace_quotas"].keys())
    quotas = np.asarray([config["split_trace_quotas"][name]
                         for name in split_names], dtype=np.float64)
    group_count = len(inventory)
    split_count = len(split_names)
    measures = build_stratification_measures(inventory, corpus_rows)
    x_count = group_count * split_count
    z_index = x_count
    deviation_start = z_index + 1
    variable_count = deviation_start + len(measures) * split_count * 2

    def x_index(group_index, split_index):
        return group_index * split_count + split_index

    def deviation_indices(measure_index, split_index):
        positive = deviation_start + (measure_index * split_count + split_index) * 2
        return positive, positive + 1

    rows = []
    lower = []
    upper = []

    def add_constraint(coefficients, minimum, maximum):
        rows.append(coefficients)
        lower.append(float(minimum))
        upper.append(float(maximum))

    # Assignment and trace quotas are exact hard constraints.  Component size
    # rather than component count is used because connected groups have sizes
    # one, two, or four.
    for group_index in range(group_count):
        add_constraint({x_index(group_index, split_index): 1.0
                        for split_index in range(split_count)}, 1.0, 1.0)
    group_sizes = np.asarray([component["trace_count"] for component in inventory],
                             dtype=np.float64)
    for split_index, quota in enumerate(quotas):
        add_constraint({x_index(group_index, split_index): group_sizes[group_index]
                        for group_index in range(group_count)}, quota, quota)

    # Every exact family must be represented in train.  Families with enough
    # independent components must also cover validation and IID.  This keeps
    # the new holdout within the training family support without pretending a
    # one-component family can be present everywhere.
    all_families = sorted({family for component in inventory
                           for family in component["waveform_families"]})
    for family in all_families:
        component_indices = [index for index, component in enumerate(inventory)
                             if family in component["waveform_families"]]
        add_constraint({x_index(index, 0): 1.0 for index in component_indices},
                       1.0, np.inf)
        if len(component_indices) >= int(config["family_all_split_min_component_count"]):
            for split_index in range(split_count):
                add_constraint({x_index(index, split_index): 1.0
                                for index in component_indices}, 1.0, np.inf)

    # Both source cohorts, hard-pair groups, and all three truth classes must be
    # present in every split.  These are coverage constraints, not balance
    # objectives; the later deviations refine their proportions.
    source_cohorts = sorted({source for component in inventory
                             for source in component["source_cohorts"]})
    for source in source_cohorts:
        indices = [index for index, component in enumerate(inventory)
                   if source in component["source_cohorts"]]
        for split_index in range(split_count):
            add_constraint({x_index(index, split_index): 1.0 for index in indices},
                           1.0, np.inf)
    hard_pair_indices = [index for index, component in enumerate(inventory)
                         if component["coarse_family"] == "hard_pair"]
    for split_index in range(split_count):
        add_constraint({x_index(index, split_index): 1.0 for index in hard_pair_indices},
                       1.0, np.inf)
    for class_id in CLASS_IDS:
        indices = [index for index, component in enumerate(inventory)
                   if component["state_class_counts"][str(class_id)] > 0]
        for split_index in range(split_count):
            add_constraint({x_index(index, split_index): 1.0 for index in indices},
                           1.0, np.inf)

    # Linearize every absolute count deviation around its exact quota-scaled
    # target.  For state samples, each trace supplies 500 rows, so division by
    # ``quota*500`` below converts count error into class-proportion error.
    stage_2_objective = np.zeros(variable_count, dtype=np.float64)
    state_measure_indices = []
    for measure_index, measure in enumerate(measures):
        values = measure["values"]
        total = float(np.sum(values))
        if measure["kind"] == "state_class":
            state_measure_indices.append(measure_index)
        for split_index, quota in enumerate(quotas):
            positive, negative = deviation_indices(measure_index, split_index)
            coefficients = {x_index(group_index, split_index): values[group_index]
                            for group_index in range(group_count) if values[group_index]}
            coefficients[positive] = -1.0
            coefficients[negative] = 1.0
            target = total * quota / float(np.sum(quotas))
            add_constraint(coefficients, target, target)
            denominator = quota * (500.0 if measure["kind"] == "state_class" else 1.0)
            stage_2_objective[positive] = 1.0 / denominator
            stage_2_objective[negative] = 1.0 / denominator

    # ``z`` upper-bounds every state-class proportion error.  Two inequalities
    # per class/split express the absolute value without introducing another
    # integer variable.
    for measure_index in state_measure_indices:
        measure = measures[measure_index]
        values = measure["values"]
        total = float(np.sum(values))
        for split_index, quota in enumerate(quotas):
            target = total * quota / float(np.sum(quotas))
            scale = quota * 500.0
            positive = {x_index(group_index, split_index): values[group_index]
                        for group_index in range(group_count) if values[group_index]}
            positive[z_index] = -scale
            add_constraint(positive, -np.inf, target)
            negative = {x_index(group_index, split_index): -values[group_index]
                        for group_index in range(group_count) if values[group_index]}
            negative[z_index] = -scale
            add_constraint(negative, -np.inf, -target)

    matrix = lil_matrix((len(rows), variable_count), dtype=np.float64)
    for row_index, coefficients in enumerate(rows):
        for variable_index, coefficient in coefficients.items():
            matrix[row_index, variable_index] = coefficient
    base_constraint = LinearConstraint(matrix.tocsr(), np.asarray(lower), np.asarray(upper))
    lower_bounds = np.zeros(variable_count, dtype=np.float64)
    upper_bounds = np.full(variable_count, np.inf, dtype=np.float64)
    upper_bounds[:x_count] = 1.0
    integrality = np.zeros(variable_count, dtype=np.int8)
    integrality[:x_count] = 1
    bounds = Bounds(lower_bounds, upper_bounds)
    options = {"time_limit": 120.0, "mip_rel_gap": 0.0, "presolve": True}

    stage_1_objective = np.zeros(variable_count, dtype=np.float64)
    stage_1_objective[z_index] = 1.0
    stage_1 = milp(stage_1_objective, integrality=integrality, bounds=bounds,
                   constraints=base_constraint, options=options)
    if not stage_1.success:
        raise ValueError("stage-1 split MILP failed: {}".format(stage_1.message))
    z_optimum = float(stage_1.fun)

    # Freeze the maximum class deviation with a small numerical allowance.
    z_row = lil_matrix((1, variable_count), dtype=np.float64)
    z_row[0, z_index] = 1.0
    z_constraint = LinearConstraint(z_row.tocsr(), [-np.inf], [z_optimum + 1.0e-9])
    stage_2 = milp(stage_2_objective, integrality=integrality, bounds=bounds,
                   constraints=(base_constraint, z_constraint), options=options)
    if not stage_2.success:
        raise ValueError("stage-2 split MILP failed: {}".format(stage_2.message))
    deviation_optimum = float(stage_2.fun)

    # The final coefficients are stable pseudo-random ranks in [0,1).  Their
    # sum has no scientific meaning and is used only after both balance
    # objectives have been fixed at their optima.
    tie_objective = np.zeros(variable_count, dtype=np.float64)
    seed = int(config["root_seed"])
    for group_index, component in enumerate(inventory):
        for split_index, split_name in enumerate(split_names):
            digest = hashlib.sha256("{}|{}|{}".format(
                seed, component["component_id"], split_name).encode("ascii")).hexdigest()
            tie_objective[x_index(group_index, split_index)] = int(digest[:15], 16) / float(16 ** 15)
    objective_row = lil_matrix((1, variable_count), dtype=np.float64)
    for variable_index, coefficient in enumerate(stage_2_objective):
        if coefficient:
            objective_row[0, variable_index] = coefficient
    stage_2_constraint = LinearConstraint(objective_row.tocsr(), [-np.inf],
                                          [deviation_optimum + 1.0e-8])
    # Proving the arbitrary tie objective globally optimal can be much harder
    # than proving the two scientific balance objectives.  Bound this final
    # search to 15 seconds and accept an incumbent only if it lies on the
    # already frozen stage-1/stage-2 optimum face.  SciPy's public ``milp`` API
    # does not accept a warm start, so HiGHS occasionally spends the complete
    # tie-break budget rediscovering that narrow feasible face and returns no
    # incumbent.  In that specific case the stage-2 optimum is the only valid
    # fallback: it has already been proven feasible and scientifically optimal.
    # The release command repeats the *complete* solve and requires identical
    # assignment hashes, so a nondeterministic stage-2 fallback cannot silently
    # enter the published split.  The report also records the fallback plainly;
    # it never claims that the arbitrary tie objective was proven optimal.
    stage_3_options = dict(options, time_limit=15.0)
    stage_3 = milp(tie_objective, integrality=integrality, bounds=bounds,
                   constraints=(base_constraint, z_constraint, stage_2_constraint),
                   options=stage_3_options)
    used_stage_2_fallback = stage_3.x is None
    final_solution = stage_2.x if used_stage_2_fallback else stage_3.x
    achieved_stage_2 = float(np.dot(stage_2_objective, final_solution))
    if (float(final_solution[z_index]) > z_optimum + 1.1e-9
            or achieved_stage_2 > deviation_optimum + 1.1e-8):
        raise ValueError("stage-3 incumbent left the frozen scientific optimum face")

    choices = np.asarray(final_solution[:x_count]).reshape(group_count, split_count)
    assignment = {}
    component_splits = {}
    for group_index, component in enumerate(inventory):
        split_index = int(np.argmax(choices[group_index]))
        if choices[group_index, split_index] < 0.5:
            raise ValueError("MILP returned a non-integral component assignment")
        split_name = split_names[split_index]
        component_splits[component["component_id"]] = split_name
        for trace_id in component["trace_ids"]:
            assignment[trace_id] = split_name
    return assignment, component_splits, {
        "solver": "scipy.optimize.milp",
        "stage_1_max_state_proportion_deviation": z_optimum,
        "stage_2_total_normalized_deviation": deviation_optimum,
        "stage_3_achieved_total_normalized_deviation": achieved_stage_2,
        "stage_3_tie_break_objective": (
            None if used_stage_2_fallback else float(stage_3.fun)),
        "stage_status": [int(stage_1.status), int(stage_2.status), int(stage_3.status)],
        "stage_3_tie_break_proven_optimal": bool(stage_3.success),
        "stage_3_used_stage_2_fallback": used_stage_2_fallback,
        "stage_3_message": str(stage_3.message),
    }


def audit_assignment(inventory, corpus_rows, assignment, config):
    """Return distribution evidence and fail on every publication gate."""

    quotas = config["split_trace_quotas"]
    split_names = tuple(quotas)
    trace_by_id = {row["trace_id"]: row for row in corpus_rows}
    if set(assignment) != set(trace_by_id) or set(assignment.values()) - set(split_names):
        raise ValueError("assignment IDs or split names are invalid")
    counts = Counter(assignment.values())
    if dict(counts) != quotas:
        raise ValueError("assignment does not satisfy exact trace quotas")
    for component in inventory:
        if len({assignment[trace_id] for trace_id in component["trace_ids"]}) != 1:
            raise ValueError("connected component crosses split")

    measures = build_stratification_measures(inventory, corpus_rows)
    component_index = {trace_id: index for index, component in enumerate(inventory)
                       for trace_id in component["trace_ids"]}
    component_split = {index: assignment[component["trace_ids"][0]]
                       for index, component in enumerate(inventory)}
    distributions = {}
    max_state_deviation = 0.0
    max_supported_deviation = 0.0
    supported_minimum = int(config["acceptance"]["supported_stratum_min_trace_count"])
    for measure in measures:
        total = float(np.sum(measure["values"]))
        denominator_per_trace = 500.0 if measure["kind"] == "state_class" else 1.0
        global_proportion = total / (240.0 * denominator_per_trace)
        split_values = {}
        split_deviations = {}
        for split_name in split_names:
            value = float(sum(measure["values"][index] for index in range(len(inventory))
                              if component_split[index] == split_name))
            proportion = value / (quotas[split_name] * denominator_per_trace)
            split_values[split_name] = int(round(value))
            split_deviations[split_name] = abs(proportion - global_proportion)
        distributions[measure["name"]] = {
            "kind": measure["kind"], "global_count": int(round(total)),
            "split_counts": split_values, "absolute_proportion_deviation": split_deviations,
        }
        maximum = max(split_deviations.values())
        if measure["kind"] == "state_class":
            max_state_deviation = max(max_state_deviation, maximum)
        elif total >= supported_minimum:
            max_supported_deviation = max(max_supported_deviation, maximum)

    if max_state_deviation > float(config["acceptance"]["max_current_state_proportion_deviation"]) + 1.0e-12:
        raise ValueError("current-state proportion deviation exceeds acceptance")
    if max_supported_deviation > float(config["acceptance"]["max_supported_stratum_proportion_deviation"]) + 1.0e-12:
        raise ValueError("supported-stratum proportion deviation exceeds acceptance")

    family_train_coverage = {}
    for family in sorted({row["waveform_family_id"] for row in corpus_rows}):
        family_train_coverage[family] = any(
            row["waveform_family_id"] == family and assignment[row["trace_id"]] == "train"
            for row in corpus_rows)
    if not all(family_train_coverage.values()):
        raise ValueError("one or more waveform families are absent from train")
    return {
        "trace_counts": {split: counts[split] for split in split_names},
        "component_count": len(inventory),
        "max_current_state_proportion_deviation": max_state_deviation,
        "max_supported_stratum_proportion_deviation": max_supported_deviation,
        "family_train_coverage": family_train_coverage,
        "distributions": distributions,
        "assignment_sha256": stable_digest(dict(sorted(assignment.items()))),
    }


def json_bytes(payload):
    """Serialize published JSON deterministically, including a final newline."""

    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def publish_without_overwrite(temporary_path, target_path):
    """Atomically publish one file while refusing to replace existing evidence.

    ``os.replace`` would be atomic but could overwrite another process's newly
    created target after our preflight check.  A hard link is also atomic and
    fails with ``FileExistsError`` when the target already exists.  Both paths
    reside in the same target directory, so they are necessarily on the same
    filesystem.  Removing the temporary name after linking leaves the target
    inode and bytes unchanged.
    """

    os.link(str(temporary_path), str(target_path))
    temporary_path.unlink()


def render_split_report(config, inventory, audit, solver_runs, source_corpus_sha256,
                        published_corpus_sha256):
    """Render a concise human-readable companion to machine-readable evidence."""

    quotas = audit["trace_counts"]
    lines = [
        "# IID repartition evidence",
        "",
        "- Policy: `{}`".format(config["policy_id"]),
        "- Source corpus SHA256: `{}`".format(source_corpus_sha256),
        "- Published corpus SHA256: `{}`".format(published_corpus_sha256),
        "- Assignment SHA256: `{}`".format(audit["assignment_sha256"]),
        "- Connected components: {}".format(len(inventory)),
        "- OOD split retained: no",
        "- Pristine blind-test claim: no (prior trace-level results were viewed)",
        "",
        "| Split | Traces |",
        "|---|---:|",
    ]
    lines.extend("| {} | {} |".format(split_name, quotas[split_name])
                 for split_name in config["split_trace_quotas"])
    lines.extend([
        "",
        "| Acceptance check | Observed | Limit | Result |",
        "|---|---:|---:|---|",
        "| Current-state proportion deviation | {:.9f} | {:.9f} | PASS |".format(
            audit["max_current_state_proportion_deviation"],
            config["acceptance"]["max_current_state_proportion_deviation"]),
        "| Supported-stratum proportion deviation | {:.9f} | {:.9f} | PASS |".format(
            audit["max_supported_stratum_proportion_deviation"],
            config["acceptance"]["max_supported_stratum_proportion_deviation"]),
        "| Repeated assignment digest | `{}` | identical twice | PASS |".format(
            solver_runs[0]["assignment_sha256"]),
        "",
        "The IID holdout is frozen for one final evaluation after all model and",
        "post-processing choices are selected using training and validation only.",
        "",
    ])
    return "\n".join(lines).encode("utf-8")


def parse_args():
    """Parse explicit paths so publication never depends on the launch directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--source-corpus", required=True, type=Path)
    parser.add_argument("--source-label-dir", required=True, type=Path)
    parser.add_argument("--output-corpus", required=True, type=Path)
    parser.add_argument("--output-split-dir", required=True, type=Path)
    return parser.parse_args()


def main():
    """Create one non-overwriting, reproducible IID-only split release.

    Publication intentionally performs two complete solver runs.  A single
    deterministic-looking result is insufficient because the final tie-break
    can hit its time limit; matching trace and component assignment digests are
    therefore hard release gates.  All generated objects are prepared under
    temporary names and validated before either public target becomes visible.
    The immutable source corpus is hashed both before and after publication.
    """

    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    expected_source_hash = config["source_hashes"]["corpus_sha256"]
    source_hash_before = sha256_file(args.source_corpus)
    if source_hash_before != expected_source_hash:
        raise ValueError("source corpus hash differs from the frozen split config")

    # Refuse every pre-existing public target before doing the expensive MILP
    # work.  Parent directories may already contain older versions, but the new
    # version's corpus and evidence directory must both be absent.
    for target in (args.output_corpus, args.output_split_dir):
        if target.exists():
            raise FileExistsError("refusing to overwrite published target: {}".format(target))
    args.output_corpus.parent.mkdir(parents=True, exist_ok=True)
    args.output_split_dir.parent.mkdir(parents=True, exist_ok=True)

    corpus_rows = load_corpus(args.source_corpus)
    state_profiles = load_state_profiles(
        args.source_label_dir, [row["trace_id"] for row in corpus_rows])
    inventory = build_component_inventory(corpus_rows, state_profiles, config)
    inventory_hash = stable_digest(inventory)

    solver_runs = []
    accepted = None
    for run_number in (1, 2):
        assignment, component_splits, solver = solve_assignment(inventory, corpus_rows, config)
        audit = audit_assignment(inventory, corpus_rows, assignment, config)
        solver_runs.append({
            "run": run_number,
            "assignment_sha256": audit["assignment_sha256"],
            "component_assignment_sha256": stable_digest(dict(sorted(component_splits.items()))),
            "solver": solver,
        })
        if accepted is None:
            accepted = (assignment, component_splits, audit)
    if len({run["assignment_sha256"] for run in solver_runs}) != 1:
        raise ValueError("two complete solves produced different trace assignments")
    if len({run["component_assignment_sha256"] for run in solver_runs}) != 1:
        raise ValueError("two complete solves produced different component assignments")
    assignment, component_splits, audit = accepted

    # Preserve every source field byte-for-byte at the value level.  Only the
    # active split changes; ``original_split`` retains the historical value and
    # ``split_policy_id`` makes accidental mixing of old/new rows detectable.
    published_rows = []
    for source_row in corpus_rows:
        row = dict(source_row)
        row["original_split"] = source_row["split"]
        row["split"] = assignment[source_row["trace_id"]]
        row["split_policy_id"] = config["policy_id"]
        published_rows.append(row)
    corpus_payload = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in published_rows)
    published_corpus_hash = hashlib.sha256(corpus_payload).hexdigest()

    # Stage every evidence file in a private sibling directory.  The manifest
    # contains hashes of the exact configuration, inputs, inventory, assignment
    # and corpus, allowing later label/window builders to bind to this release.
    temporary_dir = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(args.output_split_dir.name),
        dir=str(args.output_split_dir.parent)))
    corpus_fd, corpus_temp_name = tempfile.mkstemp(
        prefix=".{}.tmp.".format(args.output_corpus.name),
        dir=str(args.output_corpus.parent))
    os.close(corpus_fd)
    temporary_corpus = Path(corpus_temp_name)
    try:
        temporary_corpus.write_bytes(corpus_payload)
        evidence = {
            "component_inventory.json": inventory,
            "trace_assignment.json": dict(sorted(assignment.items())),
            "component_assignment.json": dict(sorted(component_splits.items())),
            "split_audit.json": audit,
            "solver_reproducibility.json": solver_runs,
        }
        provenance = {
            "schema_version": 1,
            "policy_id": config["policy_id"],
            "config_path": str(args.config.resolve()),
            "config_sha256": sha256_file(args.config),
            "source_corpus": str(args.source_corpus.resolve()),
            "source_corpus_sha256": source_hash_before,
            "source_label_dir": str(args.source_label_dir.resolve()),
            "component_inventory_sha256": inventory_hash,
            "assignment_sha256": audit["assignment_sha256"],
            "component_assignment_sha256": solver_runs[0]["component_assignment_sha256"],
            "published_corpus": str(args.output_corpus.resolve()),
            "published_corpus_sha256": published_corpus_hash,
            "trace_counts": audit["trace_counts"],
            "component_count": len(inventory),
            "contains_ood_split": False,
            "pristine_blind_test": False,
            "solver_repeated_runs": 2,
            "solver_assignment_hashes_identical": True,
        }
        evidence["provenance.json"] = provenance
        for filename, payload in evidence.items():
            (temporary_dir / filename).write_bytes(json_bytes(payload))
        (temporary_dir / "README.md").write_bytes(render_split_report(
            config, inventory, audit, solver_runs, source_hash_before,
            published_corpus_hash))

        # Validate staged bytes rather than trusting construction: reload the
        # JSONL, re-run the full audit, and confirm forbidden OOD labels are
        # absent before publication.  This also catches serialization mistakes.
        staged_rows = [json.loads(line) for line in temporary_corpus.read_text(
            encoding="utf-8").splitlines() if line]
        staged_ids = [row["trace_id"] for row in staged_rows]
        if len(staged_rows) != 240 or len(set(staged_ids)) != 240:
            raise ValueError("staged corpus does not contain 240 unique traces")
        if any(row["split"] == "ood_test" for row in staged_rows):
            raise ValueError("staged IID-only corpus unexpectedly contains ood_test")
        audit_assignment(inventory, corpus_rows,
                         {row["trace_id"]: row["split"] for row in staged_rows}, config)
        if sha256_file(temporary_corpus) != published_corpus_hash:
            raise ValueError("staged corpus digest changed during publication")
        if sha256_file(args.source_corpus) != source_hash_before:
            raise ValueError("immutable source corpus changed during publication")

        # Publish the corpus without overwrite, then atomically rename the
        # complete evidence directory.  If a concurrent publisher wins either
        # target, fail visibly.  No old/versioned artifact is ever replaced.
        publish_without_overwrite(temporary_corpus, args.output_corpus)
        os.rename(str(temporary_dir), str(args.output_split_dir))
    finally:
        if temporary_corpus.exists():
            temporary_corpus.unlink()
        if temporary_dir.exists():
            shutil.rmtree(str(temporary_dir))

    print(json.dumps({
        "status": "published",
        "output_corpus": str(args.output_corpus),
        "output_split_dir": str(args.output_split_dir),
        "assignment_sha256": audit["assignment_sha256"],
        "published_corpus_sha256": published_corpus_hash,
        "trace_counts": audit["trace_counts"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
