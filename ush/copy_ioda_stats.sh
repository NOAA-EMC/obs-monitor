#!/bin/bash

# --------------------------------------------------------------------------
#  copy_ioda_stats.sh
#
#  Stage the monitored JEDI diag files for obs-monitor (run from cron).
#
#  For every cycle in SOURCE not yet staged in TARGET, extract only the
#  diag_<obs_space>_YYYYMMDDHH.nc files that obs-monitor monitors (the obs
#  spaces in src/obs_monitor/config/yaml/obs_spaces/ for COMPONENT) from
#
#     SOURCE/${RUN}.YYYYMMDD/HH/analysis/${COMPONENT}/${RUN}.tHHz.${COMPONENT}_analysis.ioda_hofx.tar.gz
#
#  into
#
#     TARGET/${RUN}.YYYYMMDD/HH/analysis/${COMPONENT}/
#
#  and write obsmon_staged.json there when the cycle is complete (the Rocoto
#  driver task waits on it). Tarballs modified in the last 10 minutes are left
#  for the next run. Already-staged cycles are skipped, so it is safe to run
#  as often as you like.
#
#  (Name kept from when this copied the stat-file tarballs, so existing cron
#  entries keep working. Same options as before.)
# --------------------------------------------------------------------------

usage() {
    echo ""
    echo "Usage: $0 [ -s | --src SOURCE_DIR ] [ -t | --target TARGET_DIR ]"
    echo ""
    echo "  optional parameters:   -r | --run RUN (default is gdas)"
    echo "                         -c | --component COMPONENT (default is atmos)"
    exit 1
}

SOURCE=""
TARGET=""
RUN="gdas"
COMPONENT="atmos"

while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--"*=* ]]; then          # --opt=value -> --opt value
        arg="${1%%=*}"; val="${1#*=}"; shift
        set -- "$arg" "$val" "$@"
    fi
    case $1 in
        -s|--src)       [[ -z "${2:-}" || "$2" == -* ]] && { echo "Error: $1 requires a value."; exit 1; }
                        SOURCE="$2"; shift 2 ;;
        -t|--target)    [[ -z "${2:-}" || "$2" == -* ]] && { echo "Error: $1 requires a value."; exit 1; }
                        TARGET="$2"; shift 2 ;;
        -r|--run)       [[ -z "${2:-}" || "$2" == -* ]] && { echo "Error: $1 requires a value."; exit 1; }
                        RUN="$2"; shift 2 ;;
        -c|--component) [[ -z "${2:-}" || "$2" == -* ]] && { echo "Error: $1 requires a value."; exit 1; }
                        COMPONENT="$2"; shift 2 ;;
        -h|--help)      usage ;;
        *)              echo "Unknown: $1"; usage ;;
    esac
done

if [[ -z "$SOURCE" ]] || [[ -z "$TARGET" ]]; then
    echo "Error: Both --src and --target are required."
    usage
fi
[[ -d "$SOURCE" ]] || { echo "Source $SOURCE is not a valid directory"; exit 2; }
[[ -d "$TARGET" ]] || { echo "Target $TARGET is not a valid directory"; exit 2; }

# ---------------------------------------------------------------
# Python environment: same modules as the Rocoto jobs when the
# module command is available (cron shells often lack it).
# ---------------------------------------------------------------
HOMEobsmon="${HOMEobsmon:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
if command -v module >/dev/null 2>&1; then
    MACHINE="UNKNOWN"
    source "${HOMEobsmon}/ush/detect_machine.sh"
    module use "${HOMEobsmon}/modulefiles"
    module load "obs-monitor/${MACHINE_ID}"
fi
export PYTHONPATH="${HOMEobsmon}/src:${PYTHONPATH:-}"

echo; echo "using:"
echo "  SOURCE    = $SOURCE"
echo "  TARGET    = $TARGET"
echo "  RUN       = $RUN"
echo "  COMPONENT = $COMPONENT"; echo

"${PYTHON:-python}" -m obs_monitor.pipelines.stage \
    --src "$SOURCE" --target "$TARGET" --run "$RUN" --component "$COMPONENT"
exit $?
