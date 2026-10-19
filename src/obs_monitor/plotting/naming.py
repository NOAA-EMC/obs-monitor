"""
obs_monitor.plotting.naming
===========================

Figure file names. **These are the website contract**: the web pages link to
PNGs by name, so any change here breaks the site. ``tests/plotting/test_naming.py``
pins the exact names for every obs space currently on the site.

Conventions
-----------
Time series, one PNG per domain::

    {ob_type}_{variable}_{stat}_{label}_{domain}_timeseries.png
    prepbufr_adpsfc_stationPressure_assimilated_mean_ombg_Global_timeseries.png

Gridded map::

    {ob_type}_{variable}_{stat}_{label}_map.png
    prepbufr_adpsfc_stationPressure_assimilated_mean_ombg_map.png

``ob_type`` is the obs space's ``label`` (its ``web_name`` if set, else its name),
``stat`` is ``<qc_class>_<statistic>`` as in the old stat files, and ``label`` is
the field (``ombg``, ``oman``, ``obs``).
"""

from __future__ import annotations

import re


def _safe_stem(text: str) -> str:
    """Replace characters that are unsafe in filenames with underscores."""
    return re.sub(r"[^\w\-]", "_", text)


def stat_name(qc_class: str, stat: str) -> str:
    """``("assimilated", "mean") -> "assimilated_mean"``, the old stat-file variable name."""
    return f"{qc_class}_{stat}"


def build_timeseries_filename(ob_type: str, variable: str, stat: str, domain: str, label: str | None = None) -> str:
    """``{ob_type}_{variable}_{stat}_{label}_{domain}_timeseries.png`` (``label`` optional)."""
    parts = [ob_type, variable, stat]
    if label:
        parts.append(label)
    parts += [domain, "timeseries"]
    return "_".join(_safe_stem(p) for p in parts) + ".png"


def build_map_filename(ob_type: str, variable: str, stat: str, label: str | None = None) -> str:
    """``{ob_type}_{variable}_{stat}_{label}_map.png`` (``label`` optional)."""
    parts = [ob_type, variable, stat]
    if label:
        parts.append(label)
    parts.append("map")
    return "_".join(_safe_stem(p) for p in parts) + ".png"
