"""
obs_monitor.io
==============

Input layer: everything that knows about files on disk.

``ioda``
    Read JEDI IODA diag files into the canonical per-variable Dataset.
"""

from .ioda import (
    FIELDS,
    QC_MISSING,
    ChannelNotFoundError,
    IodaFormatError,
    VariableNotSimulatedError,
    list_simulated_variables,
    read_ioda,
    resolve_group_map,
)

__all__ = [
    "FIELDS",
    "QC_MISSING",
    "ChannelNotFoundError",
    "IodaFormatError",
    "VariableNotSimulatedError",
    "list_simulated_variables",
    "read_ioda",
    "resolve_group_map",
]
