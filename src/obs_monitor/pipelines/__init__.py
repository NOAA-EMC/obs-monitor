"""
obs_monitor.pipelines
=====================

Entry points that tie io -> stats -> plotting together.

``run``
    :func:`run_window`: the shared engine (one RunConfig in, figures + status out).
``operational``
    The Rocoto job: environment variables -> RunConfig per component -> run_window.
``stage``
    The copy step: extract the monitored diag files from global-workflow
    tarballs into DATAROOT.
"""

from .run import STATUS_FILE, ObsSpaceStatus, RunResult, run_window

__all__ = ["STATUS_FILE", "ObsSpaceStatus", "RunResult", "run_window"]
