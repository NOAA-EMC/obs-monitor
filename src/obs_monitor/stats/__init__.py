"""
obs_monitor.stats
=================

Statistics from IODA diag data: one cycle of one variable in, a small
CycleSummary out (see :mod:`obs_monitor.stats.summary` for the contract).

``regions``
    Statistics domains and the map grid (``config/yaml/regions.yaml``).
``summary``
    :func:`reduce_cycle` and :func:`stack_cycles`.
``cache``
    Per-cycle summaries on disk.
"""

from obs_monitor.stats.cache import read_summary, summary_path, write_summary
from obs_monitor.stats.regions import DEFAULT_REGIONS_FILE, Domain, Grid, load_regions
from obs_monitor.stats.summary import FIELD_QC, QC_CLASSES, STATS, reduce_cycle, stack_cycles

__all__ = [
    "DEFAULT_REGIONS_FILE",
    "FIELD_QC",
    "QC_CLASSES",
    "STATS",
    "Domain",
    "Grid",
    "load_regions",
    "read_summary",
    "reduce_cycle",
    "stack_cycles",
    "summary_path",
    "write_summary",
]
