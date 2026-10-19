"""
obs_monitor.config
==================

Configuration: obs-space definitions (YAML under ``config/yaml/obs_spaces/``),
figure specs (``config/yaml/figures.yaml``) and the run configuration. Nothing here
reads environment variables.
"""

from obs_monitor.config.errors import ConfigError
from obs_monitor.config.figures import DEFAULT_FIGURES_FILE, FigureSpec, load_default_figures
from obs_monitor.config.obs_spaces import DEFAULT_OBS_SPACE_DIR, ObsSpaceConfig, load_obs_spaces
from obs_monitor.config.run_config import RunConfig, load_run_config

__all__ = [
    "DEFAULT_FIGURES_FILE",
    "DEFAULT_OBS_SPACE_DIR",
    "ConfigError",
    "FigureSpec",
    "ObsSpaceConfig",
    "RunConfig",
    "load_default_figures",
    "load_obs_spaces",
    "load_run_config",
]
