"""
tests/driver/test_stubs.py
=============================

Unit tests for obs_monitor.driver.stubs.

Coverage targets
----------------
clone_schema_stub:
  - Clones dims/groups/vars from a real reference file
  - Float variables filled with NaN (not zero, not copied data)
  - Int variables filled with zero
  - String variables (other than validTime) filled with placeholder "NA"
  - validTime is rewritten for the new cycle, not copied verbatim
  - Offset between filename cycle and validTime is preserved from reference
  - Falls back to DEFAULT_VALIDTIME_OFFSET_HOURS when reference validTime
    cannot be parsed
  - Unlimited dimension (analysisCycle) stays unlimited, sized to 1 in output
  - Output passes validate_nc_file against the same figure specs the
    reference file would satisfy

write_generic_stub:
  - Group hierarchy and variable names derived correctly from figure specs
  - Duplicate (group_path, stat) pairs across specs don't raise or duplicate
  - Domain dimension sized from domain_count
  - binsZDim/binsYDim/binsXDim sized from nc_groups.bins when present
  - coords_group gets latitude/longitude variables when bins are present
  - Missing 'figures' key raises ValueError
  - Missing 'domain_count' key raises ValueError
  - Output passes validate_nc_file end-to-end (the critical integration check)
  - validTime uses DEFAULT_VALIDTIME_OFFSET_HOURS
  - Float stat variables are NaN-filled
  - Unprefixed group_path (no byDomains/griddedBins prefix) falls back to
    Domain-shaped dims correctly

NetCDF inspection in this module uses netCDF4 directly rather than the
write_nc_file factory, since these tests are validating what stubs.py itself
produces, not consuming pre-built fixture files.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone, timedelta
from pathlib import Path

import netCDF4 as nc4
import numpy as np
import pytest

from obs_monitor.driver.stubs import (
    DEFAULT_FLOAT_FILL,
    DEFAULT_VALIDTIME_OFFSET_HOURS,
    clone_schema_stub,
    write_generic_stub,
)
from obs_monitor.plotting.reader import (
    validate_nc_file,
    MissingGroupError,
    MissingVariableError,
)

# Reuse the same schema constants as the rest of the plotting test suite
from conftest import N_DOMAINS, BINS_Z, BINS_Y, BINS_X, nc_filename


# ---------------------------------------------------------------------------
# plot_config fixture — modeled on the real prepbufr_adpsfc entry
# ---------------------------------------------------------------------------

@pytest.fixture
def plot_config() -> dict:
    """
    Minimal plot config matching the confirmed prepbufr_adpsfc schema:
    byDomains/{ombg,oman}/stationPressure + griddedBins/{ombg,oman}/stationPressure,
    stat=assimilated_mean, coords=griddedBins.

    Deliberately includes the same group_path/stat pair twice (time_series +
    map_gridded both reference assimilated_mean under different paths, and
    ombg/oman duplicate the stat name) to mirror the real YAML and exercise
    deduplication in write_generic_stub.
    """
    return {
        "variable": "stationPressure",
        "unit": "Pa",
        "domain_count": N_DOMAINS,
        "nc_groups": {
            "coords": "griddedBins",
            "bins": [BINS_Z, BINS_Y, BINS_X],
        },
        "figures": [
            {
                "type": "time_series",
                "group_path": "byDomains/ombg/stationPressure",
                "stat": "assimilated_mean",
            },
            {
                "type": "time_series",
                "group_path": "byDomains/oman/stationPressure",
                "stat": "assimilated_mean",
            },
            {
                "type": "map_gridded",
                "group_path": "griddedBins/ombg/stationPressure",
                "stat": "assimilated_mean",
            },
            {
                "type": "map_gridded",
                "group_path": "griddedBins/oman/stationPressure",
                "stat": "assimilated_mean",
            },
        ],
    }


@pytest.fixture
def plot_config_no_bins(plot_config) -> dict:
    """Variant with no griddedBins group at all (aerosol-style, unprefixed paths)."""
    cfg = copy.deepcopy(plot_config)
    cfg["nc_groups"] = {"coords": ""}
    cfg["figures"] = [
        {
            "type": "time_series",
            "group_path": "oman/aerosolOpticalDepth",
            "stat": "mean",
        },
    ]
    return cfg


# ---------------------------------------------------------------------------
# clone_schema_stub
# ---------------------------------------------------------------------------

class TestCloneSchemaStub:

    def test_clones_dims_and_groups(self, single_nc_file, tmp_path, cycle_times):
        out = tmp_path / "cloned.nc"
        clone_schema_stub(single_nc_file, out, cycle_times[1])

        with nc4.Dataset(out, "r") as ds:
            assert ds.dimensions["Domain"].size == N_DOMAINS
            # write_nc_file's reference fixture creates analysisCycle as a
            # fixed-size dim (size=1), not unlimited — clone_schema_stub
            # faithfully mirrors whatever the reference dimension type is,
            # so the clone should match: fixed-size, sized 1.
            assert not ds.dimensions["analysisCycle"].isunlimited()
            assert ds.dimensions["analysisCycle"].size == 1
            assert "byDomains" in ds.groups
            assert "griddedBins" in ds.groups
            assert "ombg" in ds.groups["byDomains"].groups
            assert "stationPressure" in ds.groups["byDomains"].groups["ombg"].groups

    def test_float_variables_filled_with_nan(self, single_nc_file, tmp_path, cycle_times):
        out = tmp_path / "cloned.nc"
        clone_schema_stub(single_nc_file, out, cycle_times[1])

        with nc4.Dataset(out, "r") as ds:
            mean = ds.groups["byDomains"].groups["ombg"].groups["stationPressure"] \
                     .variables["assimilated_mean"][:]
            assert np.all(np.isnan(np.asarray(mean)))

    def test_int_variables_filled_with_zero(self, single_nc_file, tmp_path, cycle_times):
        out = tmp_path / "cloned.nc"
        clone_schema_stub(single_nc_file, out, cycle_times[1])

        with nc4.Dataset(out, "r") as ds:
            count = ds.groups["byDomains"].groups["ombg"].groups["stationPressure"] \
                      .variables["assimilated_count"][:]
            assert np.all(np.asarray(count) == 0)

    def test_validtime_rewritten_not_copied(self, single_nc_file, tmp_path, cycle_times):
        """
        The reference file's validTime corresponds to cycle_times[0]; cloning
        for cycle_times[1] must produce a validTime reflecting the new cycle,
        not the original.
        """
        out = tmp_path / "cloned.nc"
        clone_schema_stub(single_nc_file, out, cycle_times[1])

        with nc4.Dataset(out, "r") as ds:
            vt_raw = ds.variables["validTime"][0]
            vt_str = vt_raw if isinstance(vt_raw, str) else str(vt_raw)

        with nc4.Dataset(single_nc_file, "r") as ref:
            ref_vt = ref.variables["validTime"][0]
            ref_vt_str = ref_vt if isinstance(ref_vt, str) else str(ref_vt)

        assert vt_str != ref_vt_str
        # Reference cycle_times[0] -> validTime same hour (offset 0, since
        # write_nc_file sets validTime == cycle_dt exactly); new cycle is 6h later
        assert vt_str.startswith(cycle_times[1].strftime("%Y-%m-%dT%H"))

    def test_offset_preserved_from_reference(self, write_nc_file, tmp_path, ob_type):
        """
        If the reference file's validTime is offset from its filename cycle
        (e.g. +3h, common for snow-style products), that offset must be
        reproduced in the cloned stub for the new cycle.
        """
        ref_cycle = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        ref_valid = ref_cycle + timedelta(hours=3)

        ref_path = tmp_path / nc_filename(ob_type, ref_cycle)
        write_nc_file(ref_path, ref_cycle)
        # Overwrite validTime to simulate a +3h offset product
        with nc4.Dataset(ref_path, "a") as ds:
            ds.variables["validTime"][0] = ref_valid.strftime("%Y-%m-%dT%H:%M:%SZ")

        new_cycle = ref_cycle + timedelta(hours=6)
        out = tmp_path / "cloned.nc"
        clone_schema_stub(ref_path, out, new_cycle)

        with nc4.Dataset(out, "r") as ds:
            vt_raw = ds.variables["validTime"][0]
            vt_str = vt_raw if isinstance(vt_raw, str) else str(vt_raw)

        expected = (new_cycle + timedelta(hours=3)).strftime("%Y-%m-%dT%H:00:00Z")
        assert vt_str == expected

    def test_falls_back_to_default_offset_when_unparseable(
        self, write_nc_file, tmp_path, ob_type
    ):
        ref_cycle = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        ref_path = tmp_path / nc_filename(ob_type, ref_cycle)
        write_nc_file(ref_path, ref_cycle)
        with nc4.Dataset(ref_path, "a") as ds:
            ds.variables["validTime"][0] = "not-a-parseable-date"

        new_cycle = ref_cycle + timedelta(hours=6)
        out = tmp_path / "cloned.nc"
        clone_schema_stub(ref_path, out, new_cycle)

        with nc4.Dataset(out, "r") as ds:
            vt_raw = ds.variables["validTime"][0]
            vt_str = vt_raw if isinstance(vt_raw, str) else str(vt_raw)

        expected = (
            new_cycle + timedelta(hours=DEFAULT_VALIDTIME_OFFSET_HOURS)
        ).strftime("%Y-%m-%dT%H:00:00Z")
        assert vt_str == expected

    def test_dimension_sizing_matches_reference(
        self, single_nc_file, tmp_path, cycle_times
    ):
        """
        clone_schema_stub mirrors the reference file's dimension type
        exactly. The shared write_nc_file fixture creates analysisCycle as
        fixed-size (1), so the clone should also be fixed-size, sized 1 —
        this isn't testing 'preserve unlimited' (the reference fixture
        doesn't use one) but rather that clone_schema_stub doesn't
        mistakenly mark a fixed dim as unlimited or vice versa.
        """
        out = tmp_path / "cloned.nc"
        clone_schema_stub(single_nc_file, out, cycle_times[1])

        with nc4.Dataset(out, "r") as ds:
            assert ds.dimensions["analysisCycle"].isunlimited() == (
                nc4.Dataset(single_nc_file, "r").dimensions["analysisCycle"].isunlimited()
            )
            assert ds.dimensions["analysisCycle"].size == 1

    def test_unlimited_reference_dimension_preserved_as_unlimited(
        self, tmp_path, cycle_times
    ):
        """
        Real obs-monitor files declare analysisCycle as UNLIMITED (confirmed
        via ncdump -h on production output). The shared write_nc_file
        fixture simplifies this to a fixed-size dim, so this test builds a
        reference file with a genuine unlimited dimension directly to
        exercise that branch of copy_root_dims.
        """
        ref_path = tmp_path / "ref_unlimited.nc"
        with nc4.Dataset(ref_path, "w", format="NETCDF4") as ds:
            ds.createDimension("analysisCycle", None)  # unlimited
            ds.createDimension("Domain", N_DOMAINS)
            vt = ds.createVariable("validTime", str, ("analysisCycle",))
            vt[0] = cycle_times[0].strftime("%Y-%m-%dT%H:%M:%SZ")
            grp = ds.createGroup("byDomains").createGroup("ombg").createGroup("stationPressure")
            v = grp.createVariable("assimilated_mean", "f4", ("analysisCycle", "Domain"))
            v[:] = np.ones((1, N_DOMAINS), dtype=np.float32)

        out = tmp_path / "cloned.nc"
        clone_schema_stub(ref_path, out, cycle_times[1])

        with nc4.Dataset(out, "r") as ds:
            assert ds.dimensions["analysisCycle"].isunlimited()
            assert ds.dimensions["analysisCycle"].size == 1

    def test_output_passes_validate_nc_file(
        self, single_nc_file, tmp_path, cycle_times
    ):
        out = tmp_path / "cloned.nc"
        clone_schema_stub(single_nc_file, out, cycle_times[1])

        figure_specs = [
            {"group_path": "byDomains/ombg/stationPressure", "stat": "assimilated_mean"},
            {"group_path": "griddedBins/ombg/stationPressure", "stat": "assimilated_mean"},
        ]
        # Must not raise
        validate_nc_file(out, "griddedBins", figure_specs)

    def test_fill_value_attribute_preserved_on_float_vars(
        self, tmp_path, cycle_times
    ):
        """
        The real files set _FillValue on float stat variables (the sentinel
        ~-3.369e38). The shared write_nc_file fixture doesn't set
        _FillValue, so this test builds its own reference file with one
        directly to confirm clone_schema_stub's create_var carries the
        attribute over rather than dropping it.
        """
        ref_path = tmp_path / "ref_fillvalue.nc"
        with nc4.Dataset(ref_path, "w", format="NETCDF4") as ds:
            ds.createDimension("analysisCycle", 1)
            ds.createDimension("Domain", N_DOMAINS)
            vt = ds.createVariable("validTime", str, ("analysisCycle",))
            vt[0] = cycle_times[0].strftime("%Y-%m-%dT%H:%M:%SZ")
            grp = ds.createGroup("byDomains").createGroup("ombg").createGroup("stationPressure")
            v = grp.createVariable(
                "assimilated_mean", "f4", ("analysisCycle", "Domain"),
                fill_value=DEFAULT_FLOAT_FILL,
            )
            v[:] = np.ones((1, N_DOMAINS), dtype=np.float32)

        out = tmp_path / "cloned.nc"
        clone_schema_stub(ref_path, out, cycle_times[1])

        with nc4.Dataset(out, "r") as ds:
            leaf = ds.groups["byDomains"].groups["ombg"].groups["stationPressure"]
            mean_var = leaf.variables["assimilated_mean"]
            assert "_FillValue" in mean_var.ncattrs()


# ---------------------------------------------------------------------------
# write_generic_stub
# ---------------------------------------------------------------------------

class TestWriteGenericStub:

    def test_creates_expected_group_hierarchy(self, plot_config, tmp_path):
        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "prepbufr_adpsfc", plot_config)

        with nc4.Dataset(out, "r") as ds:
            assert "byDomains" in ds.groups
            assert "griddedBins" in ds.groups
            for top in ("byDomains", "griddedBins"):
                for side in ("ombg", "oman"):
                    assert side in ds.groups[top].groups
                    assert "stationPressure" in ds.groups[top].groups[side].groups

    def test_variable_names_derived_from_stat(self, plot_config, tmp_path):
        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "prepbufr_adpsfc", plot_config)

        with nc4.Dataset(out, "r") as ds:
            leaf = ds.groups["byDomains"].groups["ombg"].groups["stationPressure"]
            assert "assimilated_mean" in leaf.variables

    def test_duplicate_group_stat_pairs_do_not_raise_or_duplicate(
        self, plot_config, tmp_path
    ):
        """
        plot_config fixture already has assimilated_mean referenced by both
        a time_series and (separately, under a different group_path) a
        map_gridded spec. Adding an exact duplicate spec must not raise or
        create a second variable.
        """
        cfg = copy.deepcopy(plot_config)
        cfg["figures"].append(dict(cfg["figures"][0]))  # exact duplicate

        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "prepbufr_adpsfc", cfg)  # must not raise

        with nc4.Dataset(out, "r") as ds:
            leaf = ds.groups["byDomains"].groups["ombg"].groups["stationPressure"]
            assert list(leaf.variables.keys()) == ["assimilated_mean"]

    def test_domain_dimension_sized_from_config(self, plot_config, tmp_path):
        cfg = copy.deepcopy(plot_config)
        cfg["domain_count"] = 10  # snow-style size

        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "snocvr", cfg)

        with nc4.Dataset(out, "r") as ds:
            assert ds.dimensions["Domain"].size == 10
            assert ds.variables["statisticDomain"].shape[0] == 10

    def test_bins_dimensions_sized_from_config(self, plot_config, tmp_path):
        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "prepbufr_adpsfc", plot_config)

        with nc4.Dataset(out, "r") as ds:
            assert ds.dimensions["binsZDim"].size == BINS_Z
            assert ds.dimensions["binsYDim"].size == BINS_Y
            assert ds.dimensions["binsXDim"].size == BINS_X

            grid_leaf = ds.groups["griddedBins"].groups["ombg"].groups["stationPressure"]
            mean = grid_leaf.variables["assimilated_mean"]
            assert mean.shape == (1, BINS_Z, BINS_Y, BINS_X)

    def test_coords_group_gets_lat_lon_when_bins_present(self, plot_config, tmp_path):
        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "prepbufr_adpsfc", plot_config)

        with nc4.Dataset(out, "r") as ds:
            coords = ds.groups["griddedBins"]
            assert "latitude" in coords.variables
            assert "longitude" in coords.variables
            assert coords.variables["latitude"].shape == (BINS_Y, BINS_X)

    def test_missing_figures_key_raises(self, plot_config, tmp_path):
        cfg = copy.deepcopy(plot_config)
        del cfg["figures"]

        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="figures"):
            write_generic_stub(out, dt, "prepbufr_adpsfc", cfg)

    def test_missing_domain_count_key_raises(self, plot_config, tmp_path):
        cfg = copy.deepcopy(plot_config)
        del cfg["domain_count"]

        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="domain_count"):
            write_generic_stub(out, dt, "prepbufr_adpsfc", cfg)

    def test_output_passes_validate_nc_file(self, plot_config, tmp_path):
        """
        The critical integration check: a stub generated purely from
        plot_config must satisfy the exact same validate_nc_file call that
        run_monitoring_job makes against real/cloned files.
        """
        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "prepbufr_adpsfc", plot_config)

        coords_group = plot_config["nc_groups"]["coords"]
        # Must not raise
        validate_nc_file(out, coords_group, plot_config["figures"])

    def test_validtime_uses_default_offset(self, plot_config, tmp_path):
        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "prepbufr_adpsfc", plot_config)

        with nc4.Dataset(out, "r") as ds:
            vt_raw = ds.variables["validTime"][0]
            vt_str = vt_raw if isinstance(vt_raw, str) else str(vt_raw)

        expected = (
            dt + timedelta(hours=DEFAULT_VALIDTIME_OFFSET_HOURS)
        ).strftime("%Y-%m-%dT%H:00:00Z")
        assert vt_str == expected

    def test_float_stat_variables_are_nan_filled(self, plot_config, tmp_path):
        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "prepbufr_adpsfc", plot_config)

        with nc4.Dataset(out, "r") as ds:
            leaf = ds.groups["byDomains"].groups["ombg"].groups["stationPressure"]
            mean = np.asarray(leaf.variables["assimilated_mean"][:])
            assert np.all(np.isnan(mean))

    def test_unprefixed_group_path_uses_domain_dims(
        self, plot_config_no_bins, tmp_path
    ):
        """
        Aerosol-style configs reference group paths with no byDomains/
        griddedBins prefix at all (e.g. 'oman/aerosolOpticalDepth'). Since
        nc_groups.bins is absent, the resulting variable must be Domain-
        shaped, not gridded-shaped, and must not require binsZDim etc. to
        exist.
        """
        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "viirs_n20", plot_config_no_bins)

        with nc4.Dataset(out, "r") as ds:
            assert "binsZDim" not in ds.dimensions
            leaf = ds.groups["oman"].groups["aerosolOpticalDepth"]
            mean = leaf.variables["mean"]
            assert mean.shape == (1, N_DOMAINS)

    def test_figure_spec_missing_group_path_or_stat_is_skipped(
        self, plot_config, tmp_path
    ):
        """
        A malformed figure spec (missing group_path or stat) must be
        silently skipped by _collect_group_specs rather than raising or
        creating a malformed group/variable.
        """
        cfg = copy.deepcopy(plot_config)
        cfg["figures"].append({"type": "time_series"})  # no group_path/stat
        cfg["figures"].append({"group_path": "byDomains/ombg/stationPressure"})  # no stat

        out = tmp_path / "stub.nc"
        dt = datetime(2025, 6, 1, 0, tzinfo=timezone.utc)
        write_generic_stub(out, dt, "prepbufr_adpsfc", cfg)  # must not raise

        coords_group = cfg["nc_groups"]["coords"]
        validate_nc_file(out, coords_group, plot_config["figures"])  # original valid specs still satisfied
