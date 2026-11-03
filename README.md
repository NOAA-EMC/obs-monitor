# obs-monitor
Observation Monitoring Tools and Pages

## Code Managers:
Ed Safford @EdwardSafford-NOAA
Cory Martin @CoryMartin-NOAA
Kevin Dougherty @KevinDougherty-NOAA

## Documentation:
[Wiki](https://github.com/NOAA-EMC/obs-monitor/wiki)

## Experiment runs (quickstart)
Make the obs-monitor figures for your own experiment's IODA diag files:

```bash
module use $HOMEobsmon/modulefiles && module load obs-monitor/<machine>   # or any env with requirements.txt
export PYTHONPATH=$HOMEobsmon/src:$PYTHONPATH

python -m obs_monitor.pipelines.experiment \
    --input  /scratch/$USER/myexpt/diags \
    --start 2026100100 --end 2026100518 \
    --output /scratch/$USER/myexpt/obsmon
```

(`obs-monitor-exp` is the same command when the package is pip-installed.)

* `--input` holds files named `diag_<obs_space>_YYYYMMDDHH.nc`. Use `--pattern` for other names or
  sub-folders, e.g. `--pattern "{cycle:%Y%m%d%H}/diag_{obs_space}_{cycle:%Y%m%d%H}.nc"`.
* Every configured obs space with files in the window is run (`--obs-space` to pick). Obs spaces not in
  `src/obs_monitor/config/yaml/obs_spaces/` are listed in the log and skipped. Add them with
  `--obs-space-config my_obs_spaces.yaml` (same format).
* `--output` gets the figures, `obsmon_status.json` (ok / partial / no_data / failed per obs space) and a
  `summaries/` cache, so re-running or extending the window only reads new cycles. Use one output folder
  per experiment.
* Everything can go in a run YAML instead: `--config my_run.yaml`
  (format in `src/obs_monitor/config/run_config.py`).
* Exit status: 0 figures written, 1 nothing produced, 2 bad arguments or config.
