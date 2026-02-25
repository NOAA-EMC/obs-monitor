#!/bin/bash

# -------------------------------------------------------
#  copy_ioda_stats.sh
#
#  Copy these files: 
#
#     - gdas.t[HH]z.atmos_analysis.ioda_stats.tar.gz 
#     - gdas.t[HH]z.atmos_stats.txt
#
#  from SOURCE to TARGET preserving the source directory 
#  structure.  
#
#  Only copy files that are non-zero sized and older 
#  than 10 minutes to avoid copying partial files.
# -------------------------------------------------------

usage() {
    echo "Usage: $0 [ -s | --src SOURCE_DIR ] [ -t | --target TARGET_DIR ]"
    exit 1
}

ioda_file="atmos_analysis.ioda_hofx_stats.tar.gz"
atmos_file="atmos_stats.txt"

SOURCE=""
TARGET=""

# ------------------------
# Handle input parameters
# ------------------------
while [[ $# -gt 0 ]]; do
    # --------------------------------------------------------------------
    # If an arg contains '=', split it into two separate args ($1 and $2)
    # --------------------------------------------------------------------
    if [[ "$1" == "--"*=* ]]; then
        arg="${1%%=*}"
        val="${1#*=}"
        shift
        set -- "$arg" "$val" "$@"
    fi

    case $1 in
        -s|--src)
	    if [[ -z "$2" || "$2" == -* ]]; then
                echo "Error: -s|--src requires a value."
                exit 1
            fi
            SOURCE="$2"; shift 2 ;;
	-t|--target)
            if [[ -z "$2" || "$2" == -* ]]; then
                echo "Error: -t|--target requires a value."
                exit 1
            fi
            TARGET="$2"; shift 2 ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown: $1"; 
            usage
	    exit 1
	    ;;
    esac
done


# ------------------------------------------------------
# Confirm both parameters have been provided and parsed
# ------------------------------------------------------
if [[ -z "$SOURCE" ]] || [[ -z "$TARGET" ]]; then
    echo "Error: Both --src and --target are required."
    usage
fi

# ------------------------------------------------
# Perform sanity check for both source and target
# ------------------------------------------------
if [[ ! -d "$SOURCE" ]]; then
   echo "Source $SOURCE is not a valid directory"
   exit 2
fi
if [[ ! -d "$TARGET" ]]; then
   echo "Source $TARGET is not a valid directory"
   exit 2
fi

echo; echo "using:"
echo "  SOURCE = $SOURCE"
echo "  TARGET = $TARGET"; echo


# ------------------------------------------------------------
# Determine the latest cycle time in target directory
#
# 1. Find files matching $ioda_file
# 2. Use sed to extract YYYYMMDD and HH from the path
# 3. Sort and Unique to ensure each cycle is only listed once
# ------------------------------------------------------------
mapfile -t cycles < <(find "$TARGET" -type f \
	\( -name "gdas.t[0-9][0-9]z.${ioda_file}" \) \
    | sed -n 's/.*gdas\.\([0-9]\{8\}\)\/\([0-9]\{2\}\).*/\1\2/p' \
    | sort -u)

if [[ ${#cycles[@]} -eq 0 ]]; then
    echo "WARNING:  No cycle times found in TARGET directory. Assuming TARGET directory is new/empty"
    LAST_TARGET_CYCLE=0
else
    CYCLE_TIME=$(echo "$PATH_VAR" | sed -n 's/.*gdas\.\([0-9]\{8\}\)\/\([0-9]\{2\}\).*/\1\2/p')
    LAST_TARGET_CYCLE="${cycles[-1]}"
fi

echo; echo "latest cycle in TARGET: $LAST_TARGET_CYCLE"; echo

# -----------------------------------------------------
# In source directory get an array of available cycles 
# -----------------------------------------------------
mapfile -t cycles < <(find "$SOURCE" -type f \
    \( -name "gdas.t[0-9][0-9]z.${ioda_file}" \
    -o -name "gdas.t[0-9][0-9]z.${atmos_file}" \) \
    | sed -n 's/.*gdas\.\([0-9]\{8\}\)\/\([0-9]\{2\}\).*/\1\2/p' \
    | sort -u)

if [[ ${#cycles[@]} -eq 0 ]]; then
    echo "No matching files found. Check your SOURCE or file patterns."

else
    SOURCE_CYCLE_TIME=$(echo "$PATH_VAR" | sed -n 's/.*gdas\.\([0-9]\{8\}\)\/\([0-9]\{2\}\).*/\1\2/p')
    echo "$SOURCE_CYCLE_TIME"

fi

# -------------------------------------------------------------------
# Determine which available cycles are newer than $LAST_TARGET_CYCLE
# -------------------------------------------------------------------
for cycle in "${cycles[@]}"; do

    if [[ ${cycle} -gt ${LAST_TARGET_CYCLE} ]]; then
        ymd="${cycle:0:8}"
        hh="${cycle:8:2}"
        
        # Define the base directory for this cycle
        cycle_base="gdas.${ymd}/${hh}"

	#-------------------------------------------------------------
        # Find the specific files we want within this cycle's folder.
	#
        # Using 'find' inside the loop to get the FULL relative path
	# with included checks to avoid copying zero-sized files and 
	# those less than 10 min old.
	#-------------------------------------------------------------
	
	find "${SOURCE}/${cycle_base}" -type f \( \
            -name "gdas.t${hh}z.${ioda_file}" -o \
            -name "gdas.t${hh}z.${atmos_file}" \
        \) -mmin +10 -size +0c | while read -r full_src_path; do

            # -------------------------------------
            # Get the path relative to $SOURCE
            # -------------------------------------
            rel_file_path="${full_src_path#$SOURCE/}"
           
	    # ----------------------------------------------- 
            # Get the directory portion of the relative path
            # e.g., gdas.20260224/06/products/atmos/anlmon
	    # ----------------------------------------------- 
            rel_dir_path=$(dirname "${rel_file_path}")

	    # --------------------------------------
            # Create the target directory structure
	    # --------------------------------------
            mkdir -p "${TARGET}/${rel_dir_path}"

	    # --------------
            # Copy the file
	    # --------------
	    echo; echo "copying files for cycle ${cycle}"
            cp -v "${full_src_path}" "${TARGET}/${rel_file_path}"
        done

    fi

done

exit
