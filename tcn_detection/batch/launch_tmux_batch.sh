#!/usr/bin/env bash
# Start a bounded HSPICE worker pool in detached tmux. Every window owns one
# task-private directory, so HSPICE extension-based files cannot collide.
set -eu

run_dir=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir) run_dir=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$run_dir" ]] || { echo "--run-dir is required" >&2; exit 2; }
run_dir=$(cd "$run_dir" && pwd -P)
root=$(cd "$(dirname "$0")/../../.." && pwd -P)
dataset_id=$(basename "$run_dir")
session="tcn_hspice_${dataset_id}"
if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 2
fi
python3 "$root/power_macro/tcn_detection/batch/preflight.py" --run-dir "$run_dir" > "$run_dir/state/preflight.json"
# Read the single scalar with a POSIX text filter instead of an embedded
# Python expression.  This launcher is itself invoked through tmux/shell
# layers; keeping the configuration extraction quote-simple prevents a shell
# quoting regression from silently starting the wrong worker count.
worker_count=$(sed -n '/worker_count/s/[^0-9]//gp' "$root/power_macro/tcn_detection/config/execution_v1.json")
[[ "$worker_count" =~ ^[1-9][0-9]*$ ]] || { echo "invalid worker_count in execution_v1.json" >&2; exit 2; }
tmux new-session -d -s "$session" -n supervisor "python3 '$root/power_macro/tcn_detection/batch/status.py' --run-dir '$run_dir'; exec bash"
for ((index=0; index<worker_count; index++)); do
  name=$(printf 'w%02d' "$index")
  tmux new-window -t "$session" -n "$name" "python3 '$root/power_macro/tcn_detection/batch/worker.py' --run-dir '$run_dir' --worker '$name'; exec bash"
done
printf 'session=%s\nworker_count=%s\nstarted=1\n' "$session" "$worker_count" > "$run_dir/state/tmux_start.rpt"
echo "started $session with $worker_count workers"
