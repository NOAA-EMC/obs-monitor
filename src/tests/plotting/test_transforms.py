"""
tests/plotting/test_transforms.py
===================================

Unit tests for ``obs_monitor.plotting.transforms``.

Coverage targets
----------------
cycle_mean:
  - Reduces analysisCycle dimension correctly
  - NaN values are ignored (nanmean behaviour)
  - All-NaN cells produce NaN (not zero)
  - n_cycles coordinate recorded correctly
  - Raises ValueError when analysisCycle dim is absent
  - Subset of variables respected

squeeze_gridded:
  - Drops degenerate binsZDim=1 axis
  - Leaves variables without the target dim unchanged
  - Warns and skips squeeze when dim size != 1

attach_coords:
  - latitude and longitude appear in Dataset coordinates
  - Shapes match the spatial dims
  - Existing coordinates are preserved

prepare_gridded (full pipeline):
  - Output shape is (binsYDim, binsXDim) after full pipeline
  - latitude/longitude coordinates present
  - n_cycles coordinate present

prepare_time_series:
  - analysisCycle dimension preserved (no averaging)
  - Variable subsetting works
  - Raises ValueError when analysisCycle is absent
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from obs_monitor.plotting.reader import read_group, read_coords, read_dim_labels
from obs_monitor.plotting.transforms import (
    cycle_mean,
    squeeze_gridded,
    attach_coords,
    prepare_time_series,
    prepare_gridded,
)

from conftest import DOMAINS, N_DOMAINS, BINS_Y, BINS_X


# ---------------------------------------------------------------------------
# Helpers — build minimal synthetic Datasets without touching files
# ---------------------------------------------------------------------------

def _make_domain_ds(n_cycles: int = 4, n_domains: int = N_DOMAINS) -> xr.Dataset:
    """
    Synthetic byDomains Dataset: shape (analysisCycle=n_cycles, dim_0=n_domains).
    Values are sequential floats so means are easy to verify analytically.
    """
    times = np.array(
        [np.datetime64(f"2025-11-13T{h:02d}:00:00", "ns") for h in range(n_cycles)]
    )
    data = np.arange(n_cycles * n_domains, dtype=float).reshape(n_cycles, n_domains)
    return xr.Dataset(
        {"assimilated_mean": xr.Variable(("analysisCycle", "dim_0"), data)},
        coords={"analysisCycle": times},
    )


def _make_gridded_ds(n_cycles: int = 4) -> xr.Dataset:
    """
    Synthetic griddedBins Dataset:
    shape (analysisCycle=n_cycles, dim_1=1, dim_2=BINS_Y, dim_3=BINS_X).
    Values are 1.0 throughout for easy mean verification.
    """
    times = np.array(
        [np.datetime64(f"2025-11-13T{h:02d}:00:00", "ns") for h in range(n_cycles)]
    )
    data = np.ones((n_cycles, 1, BINS_Y, BINS_X), dtype=float)
    return xr.Dataset(
        {
            "assimilated_mean": xr.Variable(
                ("analysisCycle", "dim_1", "dim_2", "dim_3"), data
            )
        },
        coords={"analysisCycle": times},
    )


def _make_lat_lon() -> tuple[np.ndarray, np.ndarray]:
    lat_1d = np.linspace(-88.75, 88.75,  BINS_Y)
    lon_1d = np.linspace(-178.75, 178.75, BINS_X)
    lon2d, lat2d = np.meshgrid(lon_1d, lat_1d)
    return lat2d.astype(float), lon2d.astype(float)


# ---------------------------------------------------------------------------
# cycle_mean
# ---------------------------------------------------------------------------

class TestCycleMean:

    def test_removes_analysisCycle_dim(self):
        ds = _make_domain_ds(n_cycles=4)
        result = cycle_mean(ds)
        assert "analysisCycle" not in result.dims

    def test_output_shape(self):
        ds = _make_domain_ds(n_cycles=4)
        result = cycle_mean(ds)
        assert result["assimilated_mean"].shape == (N_DOMAINS,)

    def test_mean_value_correct(self):
        """
        Data is sequential integers reshaped to (4, 7).
        Row means: mean of rows 0-3 for each column.
        """
        ds = _make_domain_ds(n_cycles=4)
        result = cycle_mean(ds)
        data = ds["assimilated_mean"].values  # (4, 7)
        expected = np.mean(data, axis=0)      # (7,)
        np.testing.assert_allclose(result["assimilated_mean"].values, expected)

    def test_nan_ignored_in_mean(self):
        """A single NaN cycle should not poison the mean for other cycles."""
        ds = _make_domain_ds(n_cycles=4)
        data = ds["assimilated_mean"].values.copy()
        data[0, :] = np.nan  # poison first cycle
        ds["assimilated_mean"].values[:] = data

        result = cycle_mean(ds)
        # Mean of cycles 1-3 for domain 0: values 7, 14, 21 → mean 14.0
        assert np.isfinite(result["assimilated_mean"].values[0])

    def test_all_nan_produces_nan(self):
        """All-NaN over analysisCycle should produce NaN, not zero."""
        ds = _make_domain_ds(n_cycles=4)
        ds["assimilated_mean"].values[:] = np.nan

        result = cycle_mean(ds)
        assert np.all(np.isnan(result["assimilated_mean"].values))

    def test_n_cycles_coordinate(self):
        ds = _make_domain_ds(n_cycles=4)
        result = cycle_mean(ds)
        assert "n_cycles" in result.coords
        assert int(result.coords["n_cycles"]) == 4

    def test_variable_attrs_preserved(self):
        ds = _make_domain_ds()
        ds["assimilated_mean"].attrs["units"] = "Pa"
        result = cycle_mean(ds)
        assert result["assimilated_mean"].attrs.get("units") == "Pa"

    def test_raises_without_analysisCycle_dim(self):
        ds = xr.Dataset({"x": xr.Variable(("lat", "lon"), np.ones((3, 4)))})
        with pytest.raises(ValueError, match="analysisCycle"):
            cycle_mean(ds)

    def test_subset_variables(self):
        ds = _make_domain_ds()
        ds["extra_var"] = xr.Variable(
            ("analysisCycle", "dim_0"), np.zeros_like(ds["assimilated_mean"].values)
        )
        result = cycle_mean(ds, variables=["assimilated_mean"])
        assert "assimilated_mean" in result.data_vars
        assert "extra_var" not in result.data_vars

    def test_raises_on_unknown_variable(self):
        ds = _make_domain_ds()
        with pytest.raises(ValueError, match="not found"):
            cycle_mean(ds, variables=["nonexistent"])

    def test_gridded_output_shape(self):
        ds = _make_gridded_ds(n_cycles=4)
        result = cycle_mean(ds)
        # analysisCycle collapsed; remaining dims: (dim_1=1, dim_2=72, dim_3=144)
        assert result["assimilated_mean"].shape == (1, BINS_Y, BINS_X)


# ---------------------------------------------------------------------------
# squeeze_gridded
# ---------------------------------------------------------------------------

class TestSqueezeGridded:

    def test_removes_zdim(self):
        ds = cycle_mean(_make_gridded_ds())
        # Before squeeze: (1, 72, 144) with dims (dim_1, dim_2, dim_3)
        assert "dim_1" in ds["assimilated_mean"].dims
        result = squeeze_gridded(ds, zdim="dim_1")
        assert "dim_1" not in result["assimilated_mean"].dims

    def test_output_shape_after_squeeze(self):
        ds = cycle_mean(_make_gridded_ds())
        result = squeeze_gridded(ds, zdim="dim_1")
        assert result["assimilated_mean"].shape == (BINS_Y, BINS_X)

    def test_variables_without_zdim_unchanged(self):
        """Variables that don't have the target dim should pass through."""
        ds = cycle_mean(_make_gridded_ds())
        # Add a scalar variable with no zdim
        ds["scalar"] = xr.DataArray(42.0)
        result = squeeze_gridded(ds, zdim="dim_1")
        assert "scalar" in result.data_vars
        assert result["scalar"].values == 42.0

    def test_warns_and_skips_non_unit_dim(self, caplog):
        """If dim size != 1, squeeze should warn and leave the variable alone."""
        import logging
        times = np.array([np.datetime64("2025-11-13T00:00:00", "ns")])
        data = np.ones((2, BINS_Y, BINS_X))  # zdim=2, not 1
        ds = xr.Dataset(
            {"field": xr.Variable(("zdim", "y", "x"), data)}
        )
        with caplog.at_level(logging.WARNING, logger="obs_monitor.plotting.transforms"):
            result = squeeze_gridded(ds, zdim="zdim")
        assert result["field"].shape == (2, BINS_Y, BINS_X)
        assert "size 2" in caplog.text


# ---------------------------------------------------------------------------
# attach_coords
# ---------------------------------------------------------------------------

class TestAttachCoords:

    def test_latitude_coordinate_present(self):
        ds = squeeze_gridded(cycle_mean(_make_gridded_ds()), zdim="dim_1")
        lat, lon = _make_lat_lon()
        result = attach_coords(ds, lat, lon, lat_dim="dim_2", lon_dim="dim_3")
        assert "latitude" in result.coords

    def test_longitude_coordinate_present(self):
        ds = squeeze_gridded(cycle_mean(_make_gridded_ds()), zdim="dim_1")
        lat, lon = _make_lat_lon()
        result = attach_coords(ds, lat, lon, lat_dim="dim_2", lon_dim="dim_3")
        assert "longitude" in result.coords

    def test_coord_shapes(self):
        ds = squeeze_gridded(cycle_mean(_make_gridded_ds()), zdim="dim_1")
        lat, lon = _make_lat_lon()
        result = attach_coords(ds, lat, lon, lat_dim="dim_2", lon_dim="dim_3")
        assert result.coords["latitude"].shape  == (BINS_Y, BINS_X)
        assert result.coords["longitude"].shape == (BINS_Y, BINS_X)

    def test_existing_coords_preserved(self):
        ds = squeeze_gridded(cycle_mean(_make_gridded_ds()), zdim="dim_1")
        lat, lon = _make_lat_lon()
        result = attach_coords(ds, lat, lon, lat_dim="dim_2", lon_dim="dim_3")
        # n_cycles from cycle_mean should still be present
        assert "n_cycles" in result.coords


# ---------------------------------------------------------------------------
# prepare_gridded (full pipeline)
# ---------------------------------------------------------------------------

class TestPrepareGridded:

    def test_output_shape(self):
        ds = _make_gridded_ds(n_cycles=4)
        lat, lon = _make_lat_lon()
        result = prepare_gridded(ds, lat, lon)
        assert result["assimilated_mean"].shape == (BINS_Y, BINS_X)

    def test_lat_lon_coords_present(self):
        ds = _make_gridded_ds(n_cycles=4)
        lat, lon = _make_lat_lon()
        result = prepare_gridded(ds, lat, lon)
        assert "latitude"  in result.coords
        assert "longitude" in result.coords

    def test_n_cycles_present(self):
        ds = _make_gridded_ds(n_cycles=4)
        lat, lon = _make_lat_lon()
        result = prepare_gridded(ds, lat, lon)
        assert "n_cycles" in result.coords
        assert int(result.coords["n_cycles"]) == 4

    def test_mean_value_is_1_for_constant_input(self):
        """All input values are 1.0 → mean should be 1.0 everywhere."""
        ds = _make_gridded_ds(n_cycles=4)
        lat, lon = _make_lat_lon()
        result = prepare_gridded(ds, lat, lon)
        np.testing.assert_allclose(result["assimilated_mean"].values, 1.0)

    def test_variable_subset(self):
        ds = _make_gridded_ds(n_cycles=4)
        ds["extra"] = xr.Variable(
            ("analysisCycle", "dim_1", "dim_2", "dim_3"),
            np.zeros_like(ds["assimilated_mean"].values),
        )
        lat, lon = _make_lat_lon()
        result = prepare_gridded(ds, lat, lon, variables=["assimilated_mean"])
        assert "assimilated_mean" in result.data_vars
        assert "extra" not in result.data_vars


# ---------------------------------------------------------------------------
# prepare_time_series
# ---------------------------------------------------------------------------

class TestPrepareTimeSeries:

    def test_analysisCycle_preserved(self):
        ds = _make_domain_ds(n_cycles=4)
        result = prepare_time_series(ds)
        assert "analysisCycle" in result.dims
        assert result.sizes["analysisCycle"] == 4

    def test_values_unchanged(self):
        ds = _make_domain_ds(n_cycles=4)
        result = prepare_time_series(ds, variables=["assimilated_mean"])
        np.testing.assert_array_equal(
            result["assimilated_mean"].values,
            ds["assimilated_mean"].values,
        )

    def test_variable_subset(self):
        ds = _make_domain_ds(n_cycles=4)
        ds["extra"] = xr.Variable(
            ("analysisCycle", "dim_0"),
            np.zeros_like(ds["assimilated_mean"].values),
        )
        result = prepare_time_series(ds, variables=["assimilated_mean"])
        assert "assimilated_mean" in result.data_vars
        assert "extra" not in result.data_vars

    def test_raises_without_analysisCycle_dim(self):
        ds = xr.Dataset({"x": xr.Variable(("lat",), np.ones(5))})
        with pytest.raises(ValueError, match="analysisCycle"):
            prepare_time_series(ds)

    def test_raises_on_unknown_variable(self):
        ds = _make_domain_ds()
        with pytest.raises(ValueError, match="not found"):
            prepare_time_series(ds, variables=["nonexistent"])

    def test_dim_labels_coordinate_preserved(self):
        """statisticDomain coord added by read_group should survive the transform."""
        ds = _make_domain_ds(n_cycles=4)
        ds = ds.assign_coords(
            statisticDomain=xr.Variable("dim_0", np.array(DOMAINS, dtype=object))
        )
        result = prepare_time_series(ds)
        assert "statisticDomain" in result.coords


# ---------------------------------------------------------------------------
# Integration: reader → transforms using synthetic files
# ---------------------------------------------------------------------------

class TestReaderTransformsIntegration:

    def test_full_domain_pipeline(self, multi_nc_files, stat_group):
        """read_group → prepare_time_series should produce correct shape."""
        ds = read_group(
            multi_nc_files,
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
            dim_labels={"statisticDomain": DOMAINS},
        )
        result = prepare_time_series(ds, variables=["assimilated_mean"])
        assert result.sizes["analysisCycle"] == len(multi_nc_files)
        assert result["assimilated_mean"].shape[1] == N_DOMAINS

    def test_full_gridded_pipeline(self, multi_nc_files, stat_group):
        """read_group → prepare_gridded should produce (72, 144) output."""
        ds = read_group(
            multi_nc_files,
            group_path=f"griddedBins/{stat_group}",
            variables=["assimilated_mean"],
        )
        lat, lon = read_coords(multi_nc_files, coords_group_path="griddedBins")
        result = prepare_gridded(ds, lat, lon, variables=["assimilated_mean"])
        assert result["assimilated_mean"].shape == (BINS_Y, BINS_X)
        assert "latitude"  in result.coords
        assert "longitude" in result.coords
