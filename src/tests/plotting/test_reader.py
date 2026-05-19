"""
tests/plotting/test_reader.py
==============================

Unit tests for ``obs_monitor.plotting.reader``.

Coverage targets
----------------
read_group:
  - Returns correct Dataset shape and dimension names
  - Stacks multiple cycles along analysisCycle with correct timestamps
  - Handles missing files gracefully (warning, not exception)
  - Handles missing group gracefully (warning, skips cycle)
  - Replaces sentinel fill value with NaN
  - Attaches dim_labels as named coordinates when provided
  - Returns empty Dataset when no files yield data
  - Raises ValueError on empty nc_files or variables

read_coords:
  - Returns lat/lon arrays of correct shape from first readable file
  - lat/lon are 2-D meshgrids matching (binsYDim, binsXDim)
  - Skips missing files and tries next
  - Raises RuntimeError when no file yields coords

read_dim_labels:
  - Returns the correct domain label list
  - Returns empty list (not exception) when variable is absent
  - Decodes bytes/str robustly
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from obs_monitor.plotting.reader import read_group, read_coords, read_dim_labels

from conftest import (
    DOMAINS,
    N_DOMAINS,
    BINS_Y,
    BINS_X,
    SENTINEL,
    nc_filename,
    DOMAIN_VARS,
)

# ---------------------------------------------------------------------------
# read_group — shape and dimension tests
# ---------------------------------------------------------------------------

class TestReadGroupShape:

    def test_single_file_returns_dataset(self, single_nc_file, stat_group):
        ds = read_group(
            [single_nc_file],
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        assert isinstance(ds, xr.Dataset)
        assert "assimilated_mean" in ds.data_vars

    def test_single_file_analysisCycle_dim_size_1(self, single_nc_file, stat_group):
        ds = read_group(
            [single_nc_file],
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        assert ds.sizes["analysisCycle"] == 1

    def test_multi_file_stack_size(self, multi_nc_files, stat_group):
        ds = read_group(
            multi_nc_files,
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        assert ds.sizes["analysisCycle"] == len(multi_nc_files)

    def test_domain_dim_size(self, multi_nc_files, stat_group):
        """byDomains variables should have a second dim of size 7 (Domain)."""
        ds = read_group(
            multi_nc_files,
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        # dim_0 corresponds to the in-file Domain dimension
        assert ds["assimilated_mean"].shape == (len(multi_nc_files), N_DOMAINS)

    def test_gridded_variable_shape(self, multi_nc_files, stat_group):
        """griddedBins variables should stack to (N, binsZDim, binsYDim, binsXDim)."""
        ds = read_group(
            multi_nc_files,
            group_path=f"griddedBins/{stat_group}",
            variables=["assimilated_mean"],
        )
        n = len(multi_nc_files)
        assert ds["assimilated_mean"].shape == (n, 1, BINS_Y, BINS_X)

    def test_multiple_variables_all_present(self, single_nc_file, stat_group):
        vars_ = ["assimilated_mean", "assimilated_count", "assimilated_RMS"]
        ds = read_group(
            [single_nc_file],
            group_path=f"byDomains/{stat_group}",
            variables=vars_,
        )
        for v in vars_:
            assert v in ds.data_vars


# ---------------------------------------------------------------------------
# read_group — analysisCycle coordinate values
# ---------------------------------------------------------------------------

class TestReadGroupTimestamps:

    def test_analysisCycle_coord_is_datetime64(self, single_nc_file, stat_group):
        ds = read_group(
            [single_nc_file],
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        assert ds.coords["analysisCycle"].dtype == np.dtype("datetime64[ns]")

    def test_analysisCycle_values_match_filenames(
        self, multi_nc_files, stat_group, cycle_times
    ):
        """Timestamps parsed from filenames should match the cycle_times fixture."""
        ds = read_group(
            multi_nc_files,
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        for i, dt in enumerate(cycle_times):
            expected = np.datetime64(dt.replace(tzinfo=None), "ns")
            assert ds.coords["analysisCycle"].values[i] == expected

    def test_cycles_in_chronological_order(self, multi_nc_files, stat_group):
        ds = read_group(
            multi_nc_files,
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        times = ds.coords["analysisCycle"].values
        assert list(times) == sorted(times)


# ---------------------------------------------------------------------------
# read_group — fault tolerance
# ---------------------------------------------------------------------------

class TestReadGroupFaultTolerance:

    def test_missing_file_skipped_not_raised(
        self, tmp_path, single_nc_file, stat_group
    ):
        """A path that doesn't exist should be skipped with a warning."""
        ghost = tmp_path / "prepbufr_adpsfc_2025111306_output_atmos.nc"
        ds = read_group(
            [single_nc_file, ghost],
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        # Only one file was readable → one cycle
        assert ds.sizes["analysisCycle"] == 1

    def test_missing_group_skipped_not_raised(
        self, single_nc_file
    ):
        """A group that doesn't exist in a file should skip that cycle."""
        ds = read_group(
            [single_nc_file],
            group_path="byDomains/nonexistent/group",
            variables=["assimilated_mean"],
        )
        assert ds == xr.Dataset() or ds.sizes.get("analysisCycle", 0) == 0

    def test_all_files_missing_returns_empty_dataset(
        self, tmp_path, stat_group
    ):
        ghost1 = tmp_path / "prepbufr_adpsfc_2025111300_output_atmos.nc"
        ghost2 = tmp_path / "prepbufr_adpsfc_2025111306_output_atmos.nc"
        ds = read_group(
            [ghost1, ghost2],
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        assert isinstance(ds, xr.Dataset)
        assert len(ds.data_vars) == 0

    def test_gap_in_cycles_correct_count(
        self, multi_nc_files_with_gap, stat_group
    ):
        """Three files (one missing cycle) → analysisCycle dim = 3."""
        ds = read_group(
            multi_nc_files_with_gap,
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        assert ds.sizes["analysisCycle"] == 3

    def test_raises_on_empty_nc_files(self, stat_group):
        with pytest.raises(ValueError, match="nc_files must not be empty"):
            read_group([], f"byDomains/{stat_group}", ["assimilated_mean"])

    def test_raises_on_empty_variables(self, single_nc_file, stat_group):
        with pytest.raises(ValueError, match="variables must not be empty"):
            read_group([single_nc_file], f"byDomains/{stat_group}", [])


# ---------------------------------------------------------------------------
# read_group — sentinel fill value scrubbing
# ---------------------------------------------------------------------------

class TestReadGroupSentinel:

    def test_sentinel_replaced_with_nan(self, single_nc_file, stat_group):
        """monitored_mean is written as SENTINEL; reader must convert to NaN."""
        ds = read_group(
            [single_nc_file],
            group_path=f"byDomains/{stat_group}",
            variables=["monitored_mean"],
        )
        data = ds["monitored_mean"].values
        # No value should be <= the sentinel threshold
        assert not np.any(data < -1e36), (
            f"Sentinel value not scrubbed; min value = {np.nanmin(data)}"
        )
        # All values should be NaN (sentinel was the only content)
        assert np.all(np.isnan(data))

    def test_valid_values_not_affected(self, single_nc_file, stat_group):
        """assimilated_mean has real data; values should be finite floats."""
        ds = read_group(
            [single_nc_file],
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
        )
        data = ds["assimilated_mean"].values
        assert np.any(np.isfinite(data)), "Expected some finite values in assimilated_mean"


# ---------------------------------------------------------------------------
# read_group — dim_labels coordinate attachment
# ---------------------------------------------------------------------------

class TestReadGroupDimLabels:

    def test_dim_labels_attached_as_coordinate(self, single_nc_file, stat_group):
        ds = read_group(
            [single_nc_file],
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
            dim_labels={"statisticDomain": DOMAINS},
        )
        assert "statisticDomain" in ds.coords

    def test_dim_labels_correct_values(self, single_nc_file, stat_group):
        ds = read_group(
            [single_nc_file],
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
            dim_labels={"statisticDomain": DOMAINS},
        )
        actual = list(ds.coords["statisticDomain"].values.astype(str))
        assert actual == DOMAINS

    def test_dim_labels_none_no_coordinate(self, single_nc_file, stat_group):
        ds = read_group(
            [single_nc_file],
            group_path=f"byDomains/{stat_group}",
            variables=["assimilated_mean"],
            dim_labels=None,
        )
        assert "statisticDomain" not in ds.coords


# ---------------------------------------------------------------------------
# read_coords
# ---------------------------------------------------------------------------

class TestReadCoords:

    def test_returns_two_arrays(self, single_nc_file):
        lat, lon = read_coords([single_nc_file], coords_group_path="griddedBins")
        assert isinstance(lat, np.ndarray)
        assert isinstance(lon, np.ndarray)

    def test_lat_lon_shape(self, single_nc_file):
        lat, lon = read_coords([single_nc_file], coords_group_path="griddedBins")
        assert lat.shape == (BINS_Y, BINS_X)
        assert lon.shape == (BINS_Y, BINS_X)

    def test_lat_range(self, single_nc_file):
        lat, _ = read_coords([single_nc_file], coords_group_path="griddedBins")
        assert lat.min() >= -90.0
        assert lat.max() <= 90.0

    def test_lon_range(self, single_nc_file):
        _, lon = read_coords([single_nc_file], coords_group_path="griddedBins")
        assert lon.min() >= -180.0
        assert lon.max() <= 180.0

    def test_skips_missing_file_uses_next(
        self, tmp_path, single_nc_file
    ):
        ghost = tmp_path / "prepbufr_adpsfc_2025010100_output_atmos.nc"
        # ghost doesn't exist; single_nc_file does — should still succeed
        lat, lon = read_coords(
            [ghost, single_nc_file], coords_group_path="griddedBins"
        )
        assert lat.shape == (BINS_Y, BINS_X)

    def test_raises_when_no_file_has_coords(self, tmp_path):
        ghost = tmp_path / "prepbufr_adpsfc_2025010100_output_atmos.nc"
        with pytest.raises(RuntimeError, match="Could not read coordinate arrays"):
            read_coords([ghost], coords_group_path="griddedBins")

    def test_coords_identical_across_cycles(self, multi_nc_files):
        """Lat/lon should be the same regardless of which cycle file is read."""
        lat0, lon0 = read_coords([multi_nc_files[0]], coords_group_path="griddedBins")
        lat3, lon3 = read_coords([multi_nc_files[-1]], coords_group_path="griddedBins")
        np.testing.assert_array_equal(lat0, lat3)
        np.testing.assert_array_equal(lon0, lon3)


# ---------------------------------------------------------------------------
# read_dim_labels
# ---------------------------------------------------------------------------

class TestReadDimLabels:

    def test_returns_correct_domain_list(self, single_nc_file):
        labels = read_dim_labels([single_nc_file], var_name="statisticDomain")
        assert labels == DOMAINS

    def test_returns_list_of_strings(self, single_nc_file):
        labels = read_dim_labels([single_nc_file], var_name="statisticDomain")
        assert all(isinstance(l, str) for l in labels)

    def test_correct_length(self, single_nc_file):
        labels = read_dim_labels([single_nc_file], var_name="statisticDomain")
        assert len(labels) == N_DOMAINS

    def test_missing_variable_returns_empty_list(self, single_nc_file):
        """Absent variable should return [] with a warning, not raise."""
        labels = read_dim_labels([single_nc_file], var_name="nonexistent_var")
        assert labels == []

    def test_missing_file_skipped_tries_next(
        self, tmp_path, single_nc_file
    ):
        ghost = tmp_path / "prepbufr_adpsfc_2025010100_output_atmos.nc"
        labels = read_dim_labels([ghost, single_nc_file], var_name="statisticDomain")
        assert labels == DOMAINS

    def test_all_files_missing_returns_empty_list(self, tmp_path):
        ghost = tmp_path / "prepbufr_adpsfc_2025010100_output_atmos.nc"
        labels = read_dim_labels([ghost], var_name="statisticDomain")
        assert labels == []

    def test_consistent_across_cycles(self, multi_nc_files):
        """Domain labels should be the same whichever file is read first."""
        labels = read_dim_labels(multi_nc_files, var_name="statisticDomain")
        assert labels == DOMAINS
