#!/usr/bin/env bash
# Execute the three already-frozen RF6 HSPICE decks on the mandated EDA host.
#
# The script accepts no voltage selection or period override: RF6 requires all
# three scenarios to be pre-frozen together and forbids per-voltage retuning.
# ``--infrastructure-retry`` is the sole exception mode.  It uses separately
# frozen child decks that differ only in verified unavailable host library
# paths; it never rewrites or replaces the original failed decks/logs.
# Raw simulator products stay beside their corresponding deck below
# ``controller/refrequency/hspice``.  Historical Phase-1 directories are never
# read-write targets of this command.

set -euo pipefail

# Resolve from this script so an arbitrary caller working directory cannot
# redirect mixed-signal artifacts into the workspace root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HSPICE_ROOT="${CONTROLLER_ROOT}/refrequency/hspice"
REMOTE_ROOT="/home/zhupl/rocky8/container-home/zhupl25/chiplet_side_channel/chiplet_gds_data/power_macro/delay_chain/ftc/controller/refrequency/hspice"
REMOTE_HSPICE="/home/soft/synopsys/hspice/P-2019.06-SP2/hspice/linux64/hspice"
EMPTY_SUBCKT="${CONTROLLER_ROOT}/../spice/empty_subckt.sp_cal"

# Select exactly one immutable RF6 evidence set.  Reject all other arguments
# so a shell typo cannot silently become a single-voltage or retimed run.
retry_mode=0
if [[ $# -eq 1 && "$1" == "--infrastructure-retry" ]]; then
    retry_mode=1
elif [[ $# -ne 0 ]]; then
    echo "usage: $0 [--infrastructure-retry]" >&2
    exit 2
fi

# Rendering/freeze validation runs locally and performs no simulation.  It is
# repeated immediately before remote execution to catch accidental deck drift.
# The retry freeze additionally proves that child decks contain only the three
# recorded path substitutions.
if [[ ${retry_mode} -eq 1 ]]; then
    python3 "${SCRIPT_DIR}/run_refrequency_hspice.py" verify-retry-freeze
else
    python3 "${SCRIPT_DIR}/run_refrequency_hspice.py" verify-freeze
fi

for voltage in 0p80 0p95 1p10; do
    local_dir="${HSPICE_ROOT}/cycle_path_refreq_${voltage}"
    remote_dir="${REMOTE_ROOT}/cycle_path_refreq_${voltage}"
    if [[ ${retry_mode} -eq 1 ]]; then
        local_dir="${local_dir}/infrastructure_retry"
        remote_dir="${remote_dir}/infrastructure_retry"
    fi
    test -f "${local_dir}/cycle_bridge_v2.sp"
    test -f "${EMPTY_SUBCKT}"
    # The container path is a host bind mount.  Copying this one required
    # collateral is confined to the task-owned scenario directory and is
    # necessary because the frozen LVT CDL references it by relative path.
    cp "${EMPTY_SUBCKT}" "${local_dir}/empty_subckt.sp_cal"
    # Do not stop after a failed supply: RF6 requires one frozen three-voltage
    # data set.  Each return code is retained and the later Python audit turns
    # any electrical or infrastructure failure into the gate decision.
    ssh -p 40022 -o BatchMode=yes zhupl@166.111.78.45 "set -u; cd '${remote_dir}'; '${REMOTE_HSPICE}' cycle_bridge_v2.sp -o cycle_bridge_v2 > hspice_command.log 2>&1; status=\$?; printf '%s\\n' \"\$status\" > hspice_returncode.txt; exit 0"
done
