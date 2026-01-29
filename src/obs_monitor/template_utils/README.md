# Building EVA YAML templates with `template_utils`

This guide explains how obs-monitor builds EVA configuration templates
and how to extend them safely.

---

## End-to-end build flow

For a given `ob_type`, the template builder performs:

1. Lookup in `monitor_types.yaml`
2. Load monitor-type configuration
3. Merge global defaults (`common.yaml.j2`)
4. Build datasets and transforms
5. Expand figure presets
6. Convert authoring tokens to EVA-time Jinja
7. Emit a YAML template

The main entry point is:

```python
build_template_for_ob_type(ob_type, jinja_ctx=None)
```

---

## Monitor-type configs

Location:
```text
template_utils/config/monitor_types/
```

Each file groups multiple observation types and defines:

- Datasets
- Optional transforms
- Figures (via presets)

Example:

```yaml
ob_types:
  prepbufr_adpsfc:
    datasets: [...]
    transforms: [...]
    figures: [...]
```

---

## Datasets

Datasets describe how EVA reads NetCDF input files.

Typical fields:
- `filenames_template.template`
- `groups`
- `variables`

Filename templates use EVA-time Jinja, e.g.:

```yaml
template: "{{ runtime_dir }}/prepbufr_adpsfc_%Y%m%d%H_output_atmos.nc"
```

---

## Transforms

Transforms generate derived variables for plotting.

Example:

```yaml
- transform: reduce
  source: "ObsMonitor::griddedBins::latitude"
  new name: "ObsMonitor::griddedBins::latitude_2d"
  op: mean
  dims: ["analysisCycle"]
```

Transforms are optional and are merged with global defaults when present. Current transforms can be found here: [transforms](https://github.com/JCSDA-internal/eva/tree/develop/src/eva/transforms)

---

## Figures via presets

Figures are defined using presets for reuse and consistency.

Example usage:

```yaml
- use: time_series_multi_line
  params:
    title: "{{ ob_type }} Time Series\n[[start_YMDH]]-[[end_YMDH]]"
    output: "[[runtime_dir]]/plots/{{ ob_type }}/plot.png"
    series:
      - series_label: "OMB"
        series_color: "black"
        series_y: "ObsMonitor::byDomains_ombg_stationPressure::assimilated_mean"
        series_slices: "[:,0]"
```

Figures are created in EVA using [EMCPy](https://noaa-emc.github.io/emcpy/index.html). See examples of how to utilize EMCPy to create different plot types.

---

## Preset hierarchy

### Base preset: `time_series`

Defines:
- Figure layout
- Title and output placeholders
- Empty plot container

### Derived preset: `time_series_multi_line`

Adds:
- Default x-axis variable
- Multi-line expansion via `layer_template`
- Automatic layer construction from `series`

Each entry in `series` expands into one plot layer.

---

## Placeholder rules (critical)

Three placeholder systems are supported:

| Syntax | Resolved by |
|------|-------------|
| `{var}` | Python formatter (template build) |
| `[[token]]` | Converted to EVA Jinja |
| `{{ var }}` | EVA at runtime |

Never rely on EVA to resolve `{}` placeholders.

---

## Adding a new observation type

Checklist:

1. Add entry to `monitor_types.yaml`
2. Add `ob_type` block to correct monitor-type file
3. Define datasets
4. Define figures using presets
5. Generate and inspect template via CLI

---

## Best practices

- Prefer presets over inline graphics
- Reuse existing presets when possible
- Keep transforms plot-focused
- Avoid hardcoding paths; use `[[runtime_dir]]`

This system is designed to scale cleanly as new observation types are added.
