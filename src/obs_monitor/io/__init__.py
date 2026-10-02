"""
obs_monitor.io
==============

Input layer: everything that knows about files on disk.

``ioda``
    Read JEDI IODA diag files into the canonical per-variable Dataset.
"""

from .ioda import (
    DEFAULT_GROUP_MAP,
    QC_MISSING,
    ChannelNotFoundError,
    IodaFormatError,
    VariableNotSimulatedError,
    list_simulated_variables,
    read_ioda,
)

__all__ = [
    "DEFAULT_GROUP_MAP",
    "QC_MISSING",
    "ChannelNotFoundError",
    "IodaFormatError",
    "VariableNotSimulatedError",
    "list_simulated_variables",
    "read_ioda",
]
