# obs-monitor Documentation

**obs-monitor** is an operational observation monitoring pipeline that runs on NOAA HPC infrastructure to generate diagnostic plots for data assimilation (DA) system health monitoring. The system processes meteorological observation types from IODA HofX statistics NetCDF files and produces time-series and gridded map plots published to the newly revamped obs monitoring website.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Repository Layout](#2-repository-layout)
3. [Environment Setup](#3-environment-setup)
4. [Workflow XML Generation](#4-workflow-xml-generation)
5. [Running with Rocoto](#5-running-with-rocoto)
6. [Plot Configuration Reference](#6-plot-configuration-reference)
7. [Adding a New Observation Type](#7-adding-a-new-observation-type)
8. [Driver Architecture](#8-driver-architecture)
9. [Plotting Subpackage Architecture](#9-plotting-subpackage-architecture)
10. [Stub Generation](#10-stub-generation)
11. [Pre-flight Validation and Quarantine](#11-pre-flight-validation-and-quarantine)
12. [Troubleshooting and Common Failure Modes](#12-troubleshooting-and-common-failure-modes)
13. [Development Notes](#13-development-notes)

---

## 1. System Overview

obs-monitor runs on a six-hour GDAS cycle schedule managed by [Rocoto](https://github.com/christopherwharrop/rocoto). Each cycle invocation:

1. Reads the current cycle endpoint from `PDY` (YYYYMMDD) and `CYC` (HH) environment variables set by Rocoto.
2. Builds a rolling window of `CYCLES` timestamps ending at that endpoint, spaced by `INTERVAL_HOURS`.
3. For each observation type in the job list (run in parallel via Python multiprocessing):
   - Searches `DATAROOT` for tarball archives containing IODA HofX stats NetCDF files.
   - Stages tarballs into a per-window runtime directory and extracts them.
   - Runs pre-flight structural validation on each NetCDF file; quarantines corrupt or structurally invalid files.
   - Optionally creates stub `.nc` files for any missing or quarantined cycles.
   - Dispatches the internal `obs_monitor.plotting` pipeline to render figures.
   - Copies output plots to `COMROOT` (and optionally to a public directory).
   - Cleans up the runtime directory unless `KEEP_DATA` is set.

### Supported observation types

| ob_type | Monitor type | Status |
|---|---|---|
| `prepbufr_adpsfc` | conventional | Confirmed working |
| `prepbufr_adpupa` | conventional | Confirmed working |
| `prepbufr_sfcshp` | conventional | Confirmed working |

### Supported plot types

| Type key | Description |
|---|---|
| `time_series` | Multi-line cycle-over-cycle statistic plot, one line per domain |
| `map_gridded` | Global gridded map of a cycle-averaged field |

---

## 2. Repository Layout

```
obs-monitor/
├── dev/
│   └── workflow/
│       ├── generate_workflow_xml.py   # Rocoto XML generator
│       └── example_input.yaml        # Example workflow input
├── modulefiles/
│   └── obs-monitor/
│       └── ursa                      # Module file for ursa HPC
├── src/
│   └── obs_monitor/
│       ├── driver.py                 # Main pipeline driver
│       ├── stubs.py                  # Stub NetCDF generation
│       └── plotting/
│           ├── __init__.py           # Exports dispatch_plots
│           ├── dispatcher.py         # Orchestrates read → transform → render
│           ├── reader.py             # NetCDF reading, validation, typed exceptions
│           ├── transforms.py         # Dataset reductions (cycle_mean, squeeze, coords)
│           ├── figures.py            # EMCPy-backed figure classes
│           └── config/
│               ├── monitor_types.yaml          # ob_type index (PLOT_CONFIG_YAML)
│               └── monitor_types/
│                   ├── conventional.yaml
│                   ├── aerosol.yaml
│                   └── snow.yaml
└── src/
    └── tests/
        ├── conftest.py
        ├── driver/
        │   ├── test_driver.py
        │   ├── test_validation.py
        │   └── test_stubs.py
        └── plotting/
            ├── test_dispatcher.py
            ├── test_figures.py
            ├── test_reader.py
            └── test_transforms.py
```

The key split to understand: `driver.py` handles the operational pipeline (file discovery, staging, coverage tracking, COM copy, cleanup) while `obs_monitor/plotting/` handles all plot rendering. `driver.py` calls `dispatch_plots()` as a single function call.

---

## 3. Environment Setup

Clone the repository and load the module environment:

```bash
git clone https://github.com/NOAA-EMC/obs-monitor.git
cd obs-monitor
module use modulefiles
module load obs-monitor/ursa
```

The module file sets up the Python environment with all required dependencies: `netCDF4`, `xarray`, `numpy`, `matplotlib`, `emcpy`, `wxflow`, and `pyyaml`.

> **Note:** EMCPy is a hard runtime requirement for plot rendering. If it cannot be imported, `obs_monitor.plotting.figures` will raise an `ImportError` at load time rather than silently failing at first use.

---

## 4. Workflow XML Generation

The Rocoto workflow XML is generated once per experiment before the first run. The generator is `dev/workflow/generate_workflow_xml.py` and takes a single YAML input file.

### Input YAML reference

Create an input YAML based on the template below. All `paths` fields are required. All `hpc` and `resources` fields have defaults shown.

```yaml
# Experiment identifier — used in XML filenames and PSLOT naming
pslot: "obsmon_gdas"

# Observation component(s) to monitor.
# Accepts a string or comma-separated string: "atmos", "snow", "atmos,aod"
component: "atmos"

# Rolling window definition
start_date: "202511140000"    # YYYYMMDDHHMM — start of the experiment window
end_date:   "202511151800"    # YYYYMMDDHHMM — end of the experiment window
interval_hours: 6             # Hours between cycles (default: 6)
cycles: 8                     # Number of cycles per rolling window

paths:
  obsmondir: "/path/to/obs-monitor"
  expdir:    "/path/to/expdir"   # EXPDIR
  rundir:    "/path/to/runtime_dir"  # RUNTIME_DIR
  comroot:   "/path/to/COMROOT"  # COMROOT
  dataroot:  "/path/to/DATAROOT"    # DATAROOT

run: "gdas"    # Run type (default: gdas)

hpc:
  account:   "da-cpu"    # HPC account
  queue:     "batch"     # Scheduler queue
  scheduler: "slurm"     # Scheduler type

resources:
  walltime:    "00:15:00"
  task_nodes:  "1:ppn=1:tpp=1"
  task_mem:    "4G"

flags:
  copy_data:    false   # Copy data to /local
  keep_data:    true    # Keep runtime dir after run (useful for debugging)
  create_stubs: true    # Create stub .nc files for missing cycles
```

### Input field descriptions

| Field | Required | Default | Description |
|---|---|---|---|
| `pslot` | Yes | — | Experiment slot name; used in XML/DB filenames |
| `component` | Yes | — | Component(s): `atmos`, `snow`, `aod`, or comma-separated |
| `start_date` | Yes | — | Window start in `YYYYMMDDHHMM` |
| `end_date` | Yes | — | Window end in `YYYYMMDDHHMM` |
| `interval_hours` | No | `6` | Hours between cycle timestamps |
| `cycles` | No | — | Number of cycles per rolling window |
| `paths.obsmondir` | Yes | — | Path to the obs-monitor repository root |
| `paths.expdir` | Yes | — | Experiment directory (`EXPDIR`) |
| `paths.rundir` | Yes | — | Runtime/scratch directory (`RUNTIME_DIR`) |
| `paths.comroot` | Yes | — | COM output root (`COMROOT`) |
| `paths.dataroot` | Yes | — | Root of the GDAS experiment output (`DATAROOT`) |
| `run` | No | `gdas` | Run identifier |
| `hpc.account` | No | `da-cpu` | HPC account |
| `hpc.queue` | No | `batch` | Scheduler queue |
| `hpc.scheduler` | No | `slurm` | Scheduler |
| `resources.walltime` | No | `00:15:00` | Per-task wall time |
| `resources.task_nodes` | No | `batch` | Node/thread spec |
| `resources.task_mem` | No | `4G` | Memory per task |
| `flags.copy_data` | No | `false` | Copy staging data to `/local` |
| `flags.keep_data` | No | `false` | Preserve runtime directory after job |
| `flags.create_stubs` | No | `false` | Generate stub `.nc` files for missing cycles |

### Running the generator

```bash
cd dev/workflow
python generate_workflow_xml.py --input your_input.yaml
```

This creates `$EXPDIR/$PSLOT/$PSLOT_gdas_obsmon_rocoto.xml`. Inspect the XML to confirm your inputs are reflected correctly before proceeding.

---

## 5. Running with Rocoto

From your `$EXPDIR/$PSLOT` directory:

```bash
rocotorun -w ${PSLOT}_gdas_obsmon_rocoto.xml -d ${PSLOT}_gdas_obsmon_rocoto.db
```

The `.db` file is the Rocoto state database. Using the same basename as the XML is conventional but not required.

### Checking job status

```bash
rocotostat -w ${PSLOT}_gdas_obsmon_rocoto.xml -d ${PSLOT}_gdas_obsmon_rocoto.db
```

### Where outputs go

| Output | Location |
|---|---|
| Log files | `$COMROOT` |
| Plot PNGs (per run) | `$RUNTIME_DIR/<ob_type>/plots/` |
| Plot PNGs (archived) | `$COMROOT/$RUN.$PDY/$CYC/$COMPONENT/` |
| Coverage report | `$RUNTIME_DIR/<window_dir>/coverage.csv` |

### Parallel execution

The driver uses Python `multiprocessing.Pool` and will spawn up to `cpu_count()` worker processes, one per ob_type job in the config. Jobs for different ob_types run concurrently and do not depend on each other. A failure in one ob_type (e.g. missing snow data) does not abort the others — the driver catches per-job exceptions and logs a structured summary at the end.

### Data availability caveats

- Currently, only surface pressure ob types work (`prepbufr_adpsfc`, `prepbufr_adpupa`, `prepbufr_sfcshp`). We are awaiting more input data types to test.
- In production all jobs are dispatched simultaneously; data should be co-located in `DATAROOT` at the same path depth.

---

## 6. Plot Configuration Reference

The plotting system uses a two-level YAML configuration structure. The environment variable `PLOT_CONFIG_YAML` points to the index file.

### Level 1: `monitor_types.yaml` (index)

```yaml
# src/obs_monitor/plotting/config/monitor_types.yaml
ob_type_index:

  prepbufr_adpsfc:
    monitor_type: conventional
    path: monitor_types/conventional.yaml

  viirs_npp:
    monitor_type: aerosol
    path: monitor_types/aerosol.yaml

  snocvr:
    monitor_type: snow
    path: monitor_types/snow.yaml
```

Paths under `path` are relative to the directory containing `monitor_types.yaml` (i.e. relative to `config/`, not to the repository root).

### Level 2: Per-monitor-type YAML

Each monitor-type file defines an `ob_types` block. Here is a fully annotated example for a conventional ob_type:

```yaml
# src/obs_monitor/plotting/config/monitor_types/conventional.yaml
ob_types:

  prepbufr_adpsfc:
    # Physical variable name — used in plot titles and output filenames
    variable: stationPressure
    unit: Pa

    # Number of Domain dimension entries in real NC files.
    # Required by stubs.py to size the Domain dimension in generic stubs.
    domain_count: 7

    # NetCDF group structure metadata
    nc_groups:
      # Top-level group containing lat/lon coordinate arrays.
      # Used by reader.read_coords() and validate_nc_file().
      coords: griddedBins

      # [binsZDim, binsYDim, binsXDim] — required when the ob_type has
      # a griddedBins group. Omit or set to null if not applicable.
      bins: [1, 72, 144]

    figures:

      # --- Time Series ---
      - type: time_series
        # Slash-separated path from the NC file root to the group
        # containing the stat variable.
        group_path: byDomains/ombg/stationPressure
        # Variable name within that group
        stat: assimilated_mean
        # Short label used in output filenames
        label: ombg
        title: "prepbufr_adpsfc Time Series — Assimilated Mean O-F"
        y_label: "stationPressure (Pa)"
        # Domain names to plot. Must match statisticDomain values in the NC file.
        domains: [Global, NH, SH, CONUS]

      # --- Gridded Map ---
      - type: map_gridded
        group_path: griddedBins/ombg/stationPressure
        stat: assimilated_mean
        label: ombg
        title: "prepbufr_adpsfc O-F — Assimilated Mean Cycle Avg"
        colorbar_label: "stationPressure (Pa)"
        projection: plcarr      # EMCPy projection name
        domain: global          # EMCPy domain name
        cmap: coolwarm          # matplotlib colormap
        # Optional: fix colorbar range. Omit to use full data range.
        # vmin: -5.0
        # vmax:  5.0
```

### Figure spec key reference

**Common keys (all figure types)**

| Key | Required | Description |
|---|---|---|
| `type` | Yes | `time_series` or `map_gridded` |
| `group_path` | Yes | Slash-separated NC group path from file root |
| `stat` | Yes | Variable name within the group |
| `label` | No | Short string appended to output filename to disambiguate specs |
| `title` | No | Plot title. Supports `{ob_type}`, `{variable}`, `{stat}`, `{domain}` placeholders |

**`time_series` keys**

| Key | Required | Description |
|---|---|---|
| `y_label` | No | Y-axis label |
| `domains` | No | List of domain names to plot. Must match `statisticDomain` values in the NC file. Omit to plot all domains. |

**`map_gridded` keys**

| Key | Required | Description |
|---|---|---|
| `colorbar_label` | No | Colorbar axis label |
| `projection` | No | EMCPy projection name (default: `plcarr`) |
| `domain` | No | EMCPy domain name (default: `global`) |
| `cmap` | No | matplotlib colormap name (default: `coolwarm`) |
| `vmin` | No | Colorbar lower bound. Omit to use full data range. |
| `vmax` | No | Colorbar upper bound. Omit to use full data range. |

### Output filename conventions

Time series: `{ob_type}_{variable}_{stat}_{label}_{domain}_timeseries.png`

Gridded map: `{ob_type}_{variable}_{stat}_{label}_map.png`

These filenames are used directly by the frontend toggle system, so changing the convention requires a coordinated frontend update.

---

## 7. Adding a New Observation Type

No Python changes are required to add a new ob_type. All configuration lives in YAML.

**Step 1.** Determine the actual NC file group structure using `ncdump`:

```bash
ncdump -h /path/to/your_ob_type_2025010106.nc
```

Record the group hierarchy, variable names under each group, and the shape of key dimensions (`Domain`, `binsYDim`, `binsXDim`, etc.).

**Step 2.** Add the ob_type to `monitor_types.yaml`:

```yaml
ob_type_index:
  your_new_ob_type:
    monitor_type: conventional   # or aerosol, snow, or a new type
    path: monitor_types/conventional.yaml
```

**Step 3.** Add the ob_type block to the appropriate monitor-type YAML (or create a new one if it is a new monitor type):

```yaml
ob_types:
  your_new_ob_type:
    variable: yourVariable
    unit: your_unit
    domain_count: domain count from .nc file
    nc_groups:
      coords: griddedBins
      bins: gridded bins from .nc file  # (i.e [1, 72, 144])
    figures:
      - type: time_series
        group_path: byDomains/ombg/yourVariable
        stat: assimilated_mean
        label: ombg
        title: "your_new_ob_type Time Series — O-F"
        y_label: "yourVariable (your_unit)"
        domains: [Global, NH, SH, CONUS]
```

**Step 4.** Add the ob_type to `CONFIG_YAML` (the driver job list) with the appropriate `monitor_type`, `variable` (or `sensor`/`satellite` for radiance), `component`, and `filename_template` fields.

**Step 5.** Validate against a real production file on HPC before merging:

```bash
ncdump -h /path/to/real_file.nc   # confirm group paths match figure specs
```

Then run the plotting pipeline against a small window with `keep_data: true` to inspect output before production.

> **Note:** The aerosol and snow YAML configs currently have known schema mismatches against their production NC files (wrong `stat` variable names, incorrect `group_path` prefixes). These will be resolved in Phase 2. For now only conventional types are confirmed working.

---

## 8. Driver Architecture

`src/obs_monitor/driver.py` orchestrates the full operational pipeline. Understanding its structure is important for diagnosing failures.

### `MonitoringConfig`

All configuration for a single ob_type job is encapsulated in `MonitoringConfig`. The `__init__` method reads environment variables and computes paths but does not touch the filesystem. The runtime directory is only created when `setup_runtime_dir()` is called explicitly. This keeps the class testable without HPC filesystem access.

Key attributes derived from environment variables:

| Attribute | Env var | Description |
|---|---|---|
| `end_time` | `PDY` + `CYC` | Cycle endpoint (UTC) |
| `start_time` | derived | `end_time - (CYCLES-1) * INTERVAL_HOURS` |
| `interval_hours` | `INTERVAL_HOURS` | Hours between cycle timestamps |
| `cycles` | `CYCLES` | Rolling window length |
| `runtime_dir` | `RUNTIME_DIR` | Per-job runtime scratch path (UUID-suffixed) |
| `dataroot` | `DATAROOT` | Root of GDAS experiment output |
| `comroot` | `COMROOT` | Archive destination |
| `create_stubs` | `CREATE_STUBS` | Whether to create stubs for missing cycles |
| `keep_data` | `KEEP_DATA` | Whether to preserve runtime dir |

### `run_monitoring_job` — pipeline stages

Each stage is individually exception-wrapped. A failure in any stage produces a structured result dict rather than an unhandled exception that would silently drop the job.

| Stage | Description | On failure |
|---|---|---|
| 0 | Config construction + runtime dir setup | Fatal — job returns `status: failed` |
| 1 | Tarball discovery in DATAROOT | Fatal |
| 2 | Tarball extraction + NC file scan | Fatal |
| 2b | Pre-flight NC file validation + quarantine | Non-fatal — proceeds with reduced file set |
| 3 | Coverage report CSV | Non-fatal |
| 4 | Stub creation for missing/quarantined cycles | Non-fatal per-stub |
| 5 | Guard: skip if no `.nc` files present | Returns `status: skipped_no_input` |
| 6 | Plot config resolution | Returns `status: skipped_no_plot_config` |
| 7 | `dispatch_plots()` | Fatal |
| 8 | COM copy | Non-fatal |
| 9 | Public copy (if `COPY_DATA=true`) | Non-fatal |

The `finally` block in `run_monitoring_job` always runs cleanup (deletes the runtime dir) unless `KEEP_DATA` is set, even if the job failed partway through.

### Tarball path convention

The driver expects GDAS tarballs at:

```
$DATAROOT/$RUN.$PDY/$CYC/products/$COMPONENT/anlmon/
  gdas.t${CYC}z.${COMPONENT}_analysis.ioda_hofx_stats.tar.gz
```

After copying the tarball to the runtime directory, it is extracted and any `.nc` files not belonging to the current ob_type are deleted. The ob_type prefix (`{ob_type}_`) is used as the filter criterion.

### Coverage reporting

For each window, `driver.py` writes a `coverage.csv` alongside the NC files:

```
time_utc,present
2025-11-14 00:00,1
2025-11-14 06:00,1
2025-11-14 12:00,0
...
coverage,7/8
coverage_pct,88%
```

This file is written before stub creation, so it reflects actual data availability rather than the padded set.

---

## 9. Plotting Subpackage Architecture

The `obs_monitor.plotting` subpackage is entirely internal and replaced the former version that relied on EVA. The entry point is `dispatch_plots()`.

```
driver.py
  └── dispatch_plots(ob_type, runtime_dir, plot_config, output_dir)
        ├── _discover_nc_files()         # glob {ob_type}_*.nc, sort by name
        ├── reader.read_dim_labels()     # read statisticDomain labels once
        ├── reader.read_coords()         # read lat/lon once (lazy, on first map spec)
        └── for each figure spec:
              ├── reader.read_group()    # open + stack NC files → xr.Dataset
              ├── transforms.prepare_*() # reduce / attach coords
              └── figures.build_figure() # EMCPy figure class → .save() → PNG
```

### `reader.py`

Handles all NetCDF I/O. Key design decisions:

- **`read_group(nc_files, group_path, variables)`** opens each file, navigates to the group via `_navigate_to_group()`, reads the requested variables, squeezes the in-file `analysisCycle=1` leading dimension, and stacks everything into a single `xr.Dataset` with an `analysisCycle` dimension. Files where the group is missing are skipped with a warning.
- **Sentinel fill value scrubbing:** obs-monitor NC files use a large-negative fill value (~-3.369e+38) that is not always exposed as a proper masked array by netCDF4-python. The reader explicitly replaces values below `-1e36` with `NaN`.
- **`read_coords()`** reads lat/lon from the `coords` group (e.g. `griddedBins`) from the first readable file — the coordinate grid is identical across all cycles.
- **`read_dim_labels()`** reads root-level string arrays (e.g. `statisticDomain`) from the first file. These describe the data structure rather than data values, so one file is sufficient.

### `transforms.py`

Pure functions — all return new Datasets, never mutate inputs.

| Function | Input shape | Output shape | Purpose |
|---|---|---|---|
| `prepare_time_series(ds)` | `(analysisCycle, Domain)` | same | Validates and optionally subsets; no averaging |
| `prepare_gridded(ds, lat, lon)` | `(analysisCycle, Z, Y, X)` | `(Y, X)` | `cycle_mean` → `squeeze_gridded` → `attach_coords` |
| `cycle_mean(ds)` | `(analysisCycle, ...)` | `(...)` | `nanmean` across cycles |
| `squeeze_gridded(ds)` | `(Z=1, Y, X)` | `(Y, X)` | Drops degenerate `binsZDim=1` axis |
| `attach_coords(ds, lat, lon)` | `(Y, X)` | `(Y, X)` + coords | Attaches lat/lon as named coordinates |

### `figures.py`

Object-oriented figure classes backed by EMCPy. Both inherit from `FigureBase`.

**`TimeSeriesFigure`** produces one PNG per requested domain (e.g. four PNGs for `domains: [Global, NH, SH, CONUS]`). It uses `emcpy.plots.plots.LinePlot` and draws a zero-reference `HorizontalLine` as a proper plot layer. Domain colors are drawn from a preset colorblind-safe palette.

**`MapGriddedFigure`** produces one PNG per figure spec. It uses `emcpy.plots.map_plots.MapGridded`. The `vmin`/`vmax` spec keys flow directly to EMCPy's `MapGridded` attributes; when omitted, EMCPy uses the full data range.

New figure types can be registered without modifying the dispatcher. Add a class that inherits `FigureBase`, implements `_render()`, and add it to `FIGURE_REGISTRY` in `figures.py`:

```python
FIGURE_REGISTRY["my_new_type"] = MyNewFigureClass
```

Then use `type: my_new_type` in any figure spec.

### `dispatcher.py`

Ties the subpackage together. Key behaviors:

- Loads the per-ob-type config via the two-level YAML index at startup (`_load_ob_type_config()`).
- Validates config structure before any I/O (`_validate_config()`).
- Uses `_DatasetCache` to avoid re-reading the same group more than once when multiple figure specs share a `(group_path, variables)` combination.
- Returns a summary dict with `status`, `figures_requested`, `figures_written`, `paths`, and `errors` — the driver logs this and maps it to an operational job status.

---

## 10. Stub Generation

When `CREATE_STUBS=true`, the driver creates placeholder `.nc` files for cycles that have no real data. This ensures the plotting pipeline always receives a complete window of inputs and the frontend always has figures (showing data gaps) rather than missing files.

### Strategy

The driver uses two stub strategies, tried in order:

**Strategy 1: Clone from a real reference file (`clone_schema_stub`)**

Used when at least one real file exists in the window. The stub exactly mirrors the group hierarchy, dimension sizes, and variable types of a real file — all data values are filled with NaN (float) or zero (int). The `validTime` string is recalculated for the target cycle, preserving the offset between cycle time and valid time that was observed in the reference file.

**Strategy 2: Derive schema from plot config (`write_generic_stub`)**

Used as a last resort when the entire window has no real files. The group hierarchy, variable names, and dimension sizes are all derived from the per-ob-type plot config YAML — specifically from the `figures[*].group_path` + `figures[*].stat` pairs and the `domain_count` / `nc_groups.bins` metadata keys. The stub schema is guaranteed to satisfy `validate_nc_file` for the same config.

> The generic stub strategy requires `domain_count` and (for gridded ob_types) `nc_groups.bins` to be present in the plot config YAML. These were added as part of the `feature/fix_stubs` work. If these keys are absent for a new ob_type, generic stub creation will fail with a `ValueError` — the solution is to add them to the YAML.

### Stub filename convention

If the ob_type config provides a `filename_template` (a `strftime`-formatted string), that is used. Otherwise the driver replaces the 10-digit timestamp in a reference file's name with the target cycle's timestamp. If no reference file exists, it falls back to `{ob_type}_{YYYYMMDDHH}.nc`.

---

## 11. Pre-flight Validation and Quarantine

Before the plotting pipeline runs, the driver validates every discovered `.nc` file using `reader.validate_nc_file()`. This catches structurally broken files early and routes them into the stub path rather than letting them cause silent partial output.

### Checks performed (in order)

1. File opens without error → `CorruptFileError`
2. The `coords` group (from `nc_groups.coords`) exists → `MissingGroupError`
3. Each unique `group_path` from figure specs exists → `MissingGroupError`
4. Each `stat` variable exists within its group → `MissingVariableError`


### What happens to quarantined files

- Logged at `ERROR` level with the specific failure type and cycle timestamp.
- Deleted from disk so `dispatch_plots()` cannot rediscover them via glob.
- Their cycle timestamps are excluded from `found_times`, so they fall into the stub creation path on the next stage.

### Typed exceptions

The three exception types (`CorruptFileError`, `MissingGroupError`, `MissingVariableError`) all inherit from `ValueError`. Callers that do not need to distinguish between failure modes can catch `ValueError`; callers that do (e.g. to route to different log levels) can catch the specific subclass.

---

## 12. Troubleshooting and Common Failure Modes

### Job log location

Logs are written to `$COMROOT`. The log prefix per job is `Obs Monitor - {ob_type}`. The main process logs under `Obs Monitor - main`.

### Common failure modes

**`setup: PDY and CYC must be set`**

Rocoto did not set the expected environment variables. Check that the XML task correctly exports `PDY` and `CYC`.

**`Expected directory does not exist: $DATAROOT/$RUN.$PDY/...`**

The GDAS run did not produce output for this cycle, or `DATAROOT` is pointing to the wrong experiment. Verify with:

```bash
ls $DATAROOT/gdas.${PDY}/${CYC}/products/${COMPONENT}/anlmon/
```

**`CORRUPT FILE — quarantining {filename}`**

The NC file exists on disk but could not be opened by netCDF4. This typically means the GDAS run terminated before the file was fully written. The file will be quarantined and a stub created if `CREATE_STUBS=true`.

**`MISSING GROUP — quarantining {filename}`**

The file opened successfully but a required group path from the plot config is absent. Common causes: the YAML `group_path` does not match the actual NC file structure (verify with `ncdump -h`), or the NC file was produced by a different version of the IODA hofx stats writer. Check the aerosol and snow YAMLs particularly — these are known to have schema mismatches as of Phase 1.

**`ob_type 'X' not found in PLOT_CONFIG_YAML`**

The ob_type listed in `CONFIG_YAML` (the driver job list) has no entry in `monitor_types.yaml`. Add it following the steps in [Section 7](#7-adding-a-new-observation-type).

**`No NetCDF files matching '{ob_type}_*.nc' in {runtime_dir}`**

No files were found after tarball extraction. Possible causes: the ob_type name in the driver job config does not match the filename prefix in the tarball, or the tarball for this cycle was missing from DATAROOT. If `create_stubs: false`, the job will return `status: skipped_no_input` and produce no plots for this window.

**`dispatch_plots: figures_written: 0`**

The pipeline ran but no PNGs were produced. Check the per-spec errors in the job log. The most common cause is a `stat` variable name mismatch between the YAML and the actual NC file (`MISSING VARIABLE` in validation) or a transform failure. Run with `keep_data: true` and inspect the staged NC files with `ncdump -h`.


### Debugging with `keep_data`

Setting `keep_data: true` in the input YAML (which sets `KEEP_DATA=True` in the job environment) prevents the driver from deleting the runtime directory after the job completes. You can then inspect:

```bash
# Staged and extracted NC files
ls $RUNDIR/runtime_{ob_type}_*/

# Coverage report
cat $RUNDIR/runtime_{ob_type}_*/coverage.csv

# Generated plots
ls $RUNDIR/runtime_{ob_type}_*/plots/
```

### Verifying NC file structure

Before editing or validating YAML configs against a production NC file:

```bash
ncdump -h /path/to/prepbufr_adpsfc_2025011400.nc
```

This prints all groups, dimensions, variables, and attributes without reading any data. Compare the group paths with what is in the relevant plot config YAML.

---

## 13. Development Notes

### Running the test suite

```bash
cd src
pytest tests/ -v --cov=obs_monitor
```

EMCPy is mocked in the test suite for CI compatibility. Tests that exercise stub generation, driver logic, and NC validation do not require an HPC environment. Tests are organized as:

| File | Covers |
|---|---|
| `tests/driver/test_driver.py` | `MonitoringConfig`, job stage logic, helpers |
| `tests/driver/test_validation.py` | `validate_nc_file`, typed exceptions, quarantine |
| `tests/driver/test_stubs.py` | `clone_schema_stub`, `write_generic_stub`, schema derivation |
| `tests/plotting/test_dispatcher.py` | `dispatch_plots`, config loading, file discovery, dataset cache |
| `tests/plotting/test_figures.py` | `TimeSeriesFigure`, `MapGriddedFigure`, filename conventions |
| `tests/plotting/test_reader.py` | `read_group`, `read_coords`, `read_dim_labels`, sentinel scrubbing |
| `tests/plotting/test_transforms.py` | `cycle_mean`, `squeeze_gridded`, `attach_coords`, `prepare_*` |
| `tests/conftest.py` | Shared fixtures (temp dirs, mock NC files, mock plot configs) |
