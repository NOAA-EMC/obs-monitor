"""
obs_monitor.stats.regions
=========================

Statistics domains (lat/lon boxes) and the map grid, loaded from
``config/yaml/regions.yaml``. Both are plain data; the reduction code only
asks them for boolean masks and bin indices.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from obs_monitor.config import ConfigError

#: Regions file shipped with obs-monitor.
DEFAULT_REGIONS_FILE = Path(__file__).resolve().parents[1] / "config" / "yaml" / "regions.yaml"


@dataclass(frozen=True)
class Domain:
    """A lat/lon box. ``lon_min > lon_max`` means the box wraps across the dateline."""
    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def mask(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """True where (lat, lon) is inside the box. Low edges inclusive, high edges exclusive except at 90/180."""
        in_lat = (lat >= self.lat_min) & ((lat < self.lat_max) | ((self.lat_max == 90) & (lat == 90)))
        if self.lon_min <= self.lon_max:
            in_lon = (lon >= self.lon_min) & ((lon < self.lon_max) | ((self.lon_max == 180) & (lon == 180)))
        else:
            in_lon = (lon >= self.lon_min) | (lon < self.lon_max)
        return in_lat & in_lon


@dataclass(frozen=True)
class Grid:
    """Regular lat/lon grid. Points outside it (or NaN) get bin index -1."""
    lat_edges: np.ndarray
    lon_edges: np.ndarray

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.lat_edges) - 1, len(self.lon_edges) - 1

    @property
    def lat_centers(self) -> np.ndarray:
        return 0.5 * (self.lat_edges[:-1] + self.lat_edges[1:])

    @property
    def lon_centers(self) -> np.ndarray:
        return 0.5 * (self.lon_edges[:-1] + self.lon_edges[1:])

    def flat_index(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Flattened (lat_bin * nlon + lon_bin) index per point, -1 if outside the grid."""
        nlat, nlon = self.shape
        i = np.searchsorted(self.lat_edges, lat, side="right") - 1
        j = np.searchsorted(self.lon_edges, lon, side="right") - 1
        i = np.where(lat == self.lat_edges[-1], nlat - 1, i)     # include the top edge (lat 90)
        j = np.where(lon == self.lon_edges[-1], nlon - 1, j)     # include lon 180
        ok = (i >= 0) & (i < nlat) & (j >= 0) & (j < nlon) & np.isfinite(lat) & np.isfinite(lon)
        return np.where(ok, i * nlon + j, -1)


def _pair(value: Any, where: str, lo: float, hi: float) -> tuple[float, float]:
    if (not isinstance(value, list) or len(value) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        raise ConfigError(f"{where} must be [min, max].")
    a, b = float(value[0]), float(value[1])
    if not (lo <= a <= hi and lo <= b <= hi):
        raise ConfigError(f"{where} must be within [{lo}, {hi}], got {value}.")
    return a, b


def _edges(value: Any, where: str, lo: float, hi: float) -> np.ndarray:
    if (not isinstance(value, list) or len(value) != 3
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        raise ConfigError(f"{where} must be [start, stop, step].")
    start, stop, step = map(float, value)
    if not (lo <= start < stop <= hi) or step <= 0:
        raise ConfigError(f"{where} needs {lo} <= start < stop <= {hi} and step > 0, got {value}.")
    n = (stop - start) / step
    if abs(n - round(n)) > 1e-9:
        raise ConfigError(f"{where}: (stop - start) must be a whole number of steps, got {value}.")
    return np.linspace(start, stop, int(round(n)) + 1)


def load_regions(path: str | Path = DEFAULT_REGIONS_FILE) -> tuple[tuple[Domain, ...], Grid]:
    """Load domains (in file order) and the map grid. Raises :class:`ConfigError` on bad input."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Regions file not found: {path}")
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(doc, dict) or set(doc) != {"domains", "grid"}:
        raise ConfigError(f"{path}: must contain exactly the keys 'domains' and 'grid'.")

    if not isinstance(doc["domains"], dict) or not doc["domains"]:
        raise ConfigError(f"{path}: 'domains' must be a non-empty mapping.")
    domains = []
    for name, spec in doc["domains"].items():
        where = f"{path.name}: domain '{name}'"
        if not isinstance(spec, dict) or set(spec) != {"lat", "lon"}:
            raise ConfigError(f"{where} must have exactly 'lat' and 'lon'.")
        lat = _pair(spec["lat"], f"{where} lat", -90, 90)
        lon = _pair(spec["lon"], f"{where} lon", -180, 180)
        if lat[0] >= lat[1]:
            raise ConfigError(f"{where} lat must be [south, north] with south < north.")
        domains.append(Domain(str(name), lat[0], lat[1], lon[0], lon[1]))

    g = doc["grid"]
    if not isinstance(g, dict) or set(g) != {"lat", "lon"}:
        raise ConfigError(f"{path.name}: 'grid' must have exactly 'lat' and 'lon'.")
    grid = Grid(_edges(g["lat"], f"{path.name}: grid lat", -90, 90),
                _edges(g["lon"], f"{path.name}: grid lon", -180, 180))
    return tuple(domains), grid
