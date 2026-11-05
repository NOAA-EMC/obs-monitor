# obs-monitor
Observation Monitoring Tools and Pages

## Code Managers:
Ed Safford @EdwardSafford-NOAA
Cory Martin @CoryMartin-NOAA
Kevin Dougherty @KevinDougherty-NOAA

## Documentation:
[Wiki](https://github.com/NOAA-EMC/obs-monitor/wiki)

## Running obs-monitor on your own experiment
`obs-monitor-exp` makes the obs-monitor figures (O-F and O-A time series by region, and gridded maps) from
your experiment's IODA diag files. It uses the same code as the operational run, so the numbers and figures
match what's on the website.

### 1. Set up (once per shell)
On ursa:
```bash
cd /path/to/obs-monitor                      # your clone
module purge
module use $PWD/modulefiles
module load obs-monitor/ursa                 # hera / orion / hercules / wcoss2 also have modulefiles
export PYTHONPATH=$PWD/src:$PYTHONPATH
```
Anywhere else: `pip install -r requirements.txt` in a Python 3.10+ environment, then the same `PYTHONPATH`.
(If obs-monitor is pip-installed, `obs-monitor-exp` is the same as `python -m obs_monitor.pipelines.experiment`.)

### 2. Point it at your diag files
The files must be IODA diag files (`ombg`, `oman`, `EffectiveQC*` groups), one per obs space per cycle,
named with the obs space and cycle. The default name is the one GDAS writes:

```
/scratch/$USER/myexpt/diags/
    diag_prepbufr_adpsfc_2026100100.nc
    diag_prepbufr_adpsfc_2026100106.nc
    diag_prepbufr_adpupa_2026100100.nc
    ...
```

If yours are inside the global-workflow tarballs, extract them first, e.g.
`tar -xzf gdas.t00z.atmos_analysis.ioda_hofx.tar.gz -C /scratch/$USER/myexpt/diags`.

### 3. Run
```bash
python -m obs_monitor.pipelines.experiment \
    --input  /scratch/$USER/myexpt/diags \
    --start  2026100100 \
    --end    2026100518 \
    --output /scratch/$USER/myexpt/obsmon
```
It finds every configured obs space with files between `--start` and `--end` and makes its figures.
At the end the log lists each obs space with its status, cycles found and figures written.

### 4. Look at the output
```
/scratch/$USER/myexpt/obsmon/
    prepbufr_adpsfc_stationPressure_assimilated_mean_ombg_Global_timeseries.png
    prepbufr_adpsfc_stationPressure_assimilated_mean_ombg_map.png
    ...
    obsmon_status.json        ok / partial / no_data / failed for each obs space, with any missing cycles
    summaries/                per-cycle statistics cache (plus obsmon_run.json, which input made it)
```
Missing cycles show as gaps in the time series. Re-running, or extending `--end`, only reads the new
cycles. Use a new `--output` folder for each experiment: a folder made from one input is refused for another.

### Options
| Option | What it does |
|---|---|
| `--input DIR` | Folder with the diag files (required) |
| `--start`, `--end YYYYMMDDHH` | First and last cycle (required) |
| `--output DIR` | Where figures, status and cache go (required) |
| `--interval HOURS` | Hours between cycles (default 6) |
| `--pattern NAME` | File name under `--input`, with `{obs_space}` and `{cycle:<strftime>}`. Default `diag_{obs_space}_{cycle:%Y%m%d%H}.nc`. Sub-folders work: `"{cycle:%Y%m%d%H}/diag_{obs_space}_{cycle:%Y%m%d%H}.nc"` |
| `--obs-space NAME ...` | Only these obs spaces, separated by spaces or commas: `--obs-space prepbufr_adpsfc prepbufr_adpupa` or `--obs-space prepbufr_adpsfc,prepbufr_adpupa` |
| `--obs-space-config YAML` | Your own obs-space definitions, for obs spaces not in `src/obs_monitor/config/yaml/obs_spaces/` (same format) |
| `--config YAML` | Everything above from a run YAML instead (format in `src/obs_monitor/config/run_config.py`). Can't be combined with other options |

Example run YAML:
```yaml
cycles: {start: 2026100100, end: 2026100518, interval_hours: 6}
source: {type: glob, template: /scratch/me/myexpt/diags/diag_{obs_space}_{cycle:%Y%m%d%H}.nc}
obs_spaces: [prepbufr_adpsfc, prepbufr_adpupa]      # or: all
output_dir: /scratch/me/myexpt/obsmon
work_dir: /scratch/me/myexpt/obsmon/work
```

`source` says where the diag files are. There are two types:
- **`type: glob`**: the files are already on disk. `template` is the full path to one file, with
  `{obs_space}` and `{cycle:<strftime>}` filled in for each obs space and cycle. This is the same as
  `--input` + `--pattern` on the command line. (A "glob" is a wildcard file match: obs-monitor swaps
  `{obs_space}` for `*` to find every obs space with a file for each cycle.) Your files are only read.
- **`type: com`**: the files are still in the global-workflow tarballs. Give `comroot` (and `run` if
  it isn't `gdas`). obs-monitor finds
  `<comroot>/gdas.YYYYMMDD/HH/analysis/<component>/gdas.tHHz.<component>_analysis.ioda_hofx.tar.gz`
  for each cycle, extracts only the diag files it needs into `work_dir`, and removes them at the end
  (`keep_work: true` keeps them). No need to untar anything yourself. Only available with `--config`.

  ```yaml
  source: {type: com, comroot: /scratch/me/COMROOT/myexpt}
  ```

### If something goes wrong
| Exit status / message | Meaning |
|---|---|
| 0 | Figures were written. Check `obsmon_status.json` for anything `partial` or `failed` |
| 1, "No files for any configured obs space matched ..." | Nothing matched `--input` + `--pattern` in the window. Check the folder, the file names and the dates |
| 1, "No figures were produced" | Files were found but none could be read or plotted. The log names each obs space's error |
| 2 | Bad option or config, explained on the last log line (unknown obs space, bad `--pattern`, `--output` already used for another input, ...) |
| "Found files for obs spaces with no configuration, skipped: ..." | Those obs spaces need an entry in `--obs-space-config` |

Your diag files are never modified or deleted.
