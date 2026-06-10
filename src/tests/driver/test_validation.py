"""
tests/driver/test_validation.py
================================

Unit tests for NetCDF pre-flight validation in obs_monitor.

validate_nc_file (obs_monitor.plotting.reader):
  - Clean file passing all checks
  - Corrupt / unopenable file         → CorruptFileError
  - Missing coords group              → MissingGroupError naming coords group
  - Missing figure group_path         → MissingGroupError naming figure group
  - Missing stat variable             → MissingVariableError naming variable + group
  - Duplicate specs deduplicated      (same group checked only once)
  - Second spec caught when first passes
  - All error messages include the filename

validate_and_quarantine_nc_files (obs_monitor.driver):
  - All valid files pass through unchanged
  - Corrupt file quarantined; valid sibling retained
  - Missing-group file quarantined
  - Missing-variable file quarantined
  - All files quarantined → empty return
  - Quarantined cycle times absent from valid_times (stub-path contract)
  - Each error type produces a distinctly labelled log entry
  - valid_files[i] stays in sync with valid_times[i] after quarantine
  - Empty input returns empty output

NetCDF files are built using the shared ``write_nc_file`` factory from
``tests/conftest.py`` for structurally correct files, and written manually
with netCDF4 for controlled failure cases — no production data required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import netCDF4 as nc4
import numpy as np
import pytest
from unittest.mock import MagicMock

from obs_monitor.plotting.reader import (
    validate_nc_file,
    CorruptFileError,
    MissingGroupError,
    MissingVariableError,
)
from obs_monitor.driver import validate_and_quarantine_nc_files

# Import shared schema constants from the root conftest
from conftest import nc_filename, N_DOMAINS, BINS_Y, BINS_X


# ---------------------------------------------------------------------------
# Figure specs matching the prepbufr_adpsfc conventional.yaml config
# ---------------------------------------------------------------------------

COORDS_GROUP = "griddedBins"

FIGURE_SPECS = [
    {
        "type": "time_series",
        "group_path": "byDomains/ombg/stationPressure",
        "stat": "assimilated_mean",
    },
    {
        "type": "map_gridded",
        "group_path": "griddedBins/ombg/stationPressure",
        "stat": "assimilated_mean",
    },
]


# ---------------------------------------------------------------------------
# Failure-case NetCDF fixtures
#
# These are local to this module rather than in conftest.py because they
# represent deliberately broken files — not useful to other test modules.
# Valid files are built via the shared write_nc_file fixture.
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_nc(tmp_path, ob_type, cycle_times, write_nc_file):
    """Single valid file with all expected groups and variables present."""
    path = tmp_path / nc_filename(ob_type, cycle_times[0])
    return write_nc_file(path, cycle_times[0], stat_group="ombg/stationPressure")


@pytest.fixture
def corrupt_nc(tmp_path, ob_type, cycle_times):
    """Raw garbage bytes — netCDF4 cannot open this file."""
    path = tmp_path / nc_filename(ob_type, cycle_times[1])
    path.write_bytes(b"\x00\x01\x02\x03 not a netcdf file")
    return path


@pytest.fixture
def nc_missing_coords_group(tmp_path, ob_type, cycle_times):
    """
    Valid NetCDF structure but griddedBins group is entirely absent.
    Written manually to guarantee griddedBins is never created.
    """
    path = tmp_path / nc_filename(ob_type, cycle_times[2])
    with nc4.Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("analysisCycle", 1)
        ds.createDimension("Domain", N_DOMAINS)
        g1 = ds.createGroup("byDomains")
        g2 = g1.createGroup("ombg")
        g3 = g2.createGroup("stationPressure")
        g3.createDimension("analysisCycle", 1)
        g3.createDimension("Domain", N_DOMAINS)
        v = g3.createVariable("assimilated_mean", "f4", ("analysisCycle", "Domain"))
        v[:] = np.ones((1, N_DOMAINS), dtype=np.float32)
        # griddedBins intentionally absent
    return path


@pytest.fixture
def nc_missing_figure_group(tmp_path, ob_type, cycle_times, write_nc_file):
    """
    File with griddedBins (coords check passes) but byDomains/ombg/stationPressure
    absent. Achieved by writing with a different stat_group leaf so the wrong
    group exists under byDomains.
    """
    path = tmp_path / nc_filename(ob_type, cycle_times[3])
    return write_nc_file(path, cycle_times[3], stat_group="ombg/windSpeed")


@pytest.fixture
def nc_missing_variable(tmp_path, ob_type, cycle_times):
    """
    All group paths present but assimilated_mean variable absent — replaced
    with wrong_variable so the group structure passes but variable check fails.
    """
    path = tmp_path / nc_filename(ob_type, cycle_times[0])
    with nc4.Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("analysisCycle", 1)
        ds.createDimension("Domain", N_DOMAINS)
        ds.createDimension("binsYDim", BINS_Y)
        ds.createDimension("binsXDim", BINS_X)

        # griddedBins present with lat/lon (coords check passes)
        grp_grid = ds.createGroup("griddedBins")
        lat_1d = np.linspace(-88.75,  88.75,  BINS_Y, dtype=np.float32)
        lon_1d = np.linspace(-178.75, 178.75, BINS_X, dtype=np.float32)
        lon2d, lat2d = np.meshgrid(lon_1d, lat_1d)
        grp_grid.createVariable("latitude",  "f4", ("binsYDim", "binsXDim"))[:] = lat2d
        grp_grid.createVariable("longitude", "f4", ("binsYDim", "binsXDim"))[:] = lon2d

        # byDomains/ombg/stationPressure present but wrong variable name inside
        g1 = ds.createGroup("byDomains")
        g2 = g1.createGroup("ombg")
        g3 = g2.createGroup("stationPressure")
        g3.createDimension("analysisCycle", 1)
        g3.createDimension("Domain", N_DOMAINS)
        g3.createVariable(
            "wrong_variable", "f4", ("analysisCycle", "Domain")
        )[:] = np.ones((1, N_DOMAINS), dtype=np.float32)
    return path


# ---------------------------------------------------------------------------
# validate_nc_file
# ---------------------------------------------------------------------------

class TestValidateNcFile:

    def test_valid_file_passes_all_checks(self, valid_nc):
        validate_nc_file(valid_nc, COORDS_GROUP, FIGURE_SPECS)

    def test_corrupt_file_raises_corrupt_error(self, corrupt_nc):
        with pytest.raises(CorruptFileError, match="could not be opened"):
            validate_nc_file(corrupt_nc, COORDS_GROUP, FIGURE_SPECS)

    def test_nonexistent_file_raises_corrupt_error(self, tmp_path):
        ghost = tmp_path / "prepbufr_adpsfc_2025010100_output_atmos.nc"
        with pytest.raises(CorruptFileError):
            validate_nc_file(ghost, COORDS_GROUP, FIGURE_SPECS)

    def test_missing_coords_group_raises_missing_group(self, nc_missing_coords_group):
        with pytest.raises(MissingGroupError) as exc_info:
            validate_nc_file(nc_missing_coords_group, COORDS_GROUP, FIGURE_SPECS)
        assert exc_info.value.group_path == COORDS_GROUP

    def test_missing_figure_group_raises_missing_group(self, nc_missing_figure_group):
        with pytest.raises(MissingGroupError) as exc_info:
            validate_nc_file(nc_missing_figure_group, COORDS_GROUP, FIGURE_SPECS)
        assert exc_info.value.group_path == FIGURE_SPECS[0]["group_path"]

    def test_missing_stat_variable_raises_missing_variable(self, nc_missing_variable):
        with pytest.raises(MissingVariableError) as exc_info:
            validate_nc_file(nc_missing_variable, COORDS_GROUP, FIGURE_SPECS)
        assert exc_info.value.variable == "assimilated_mean"
        assert exc_info.value.group_path == FIGURE_SPECS[0]["group_path"]

    def test_duplicate_specs_do_not_cause_false_failure(self, valid_nc):
        """Identical specs must be deduplicated — not double-checked."""
        validate_nc_file(valid_nc, COORDS_GROUP, FIGURE_SPECS + FIGURE_SPECS)

    def test_second_spec_group_caught_when_first_passes(
        self, tmp_path, ob_type, cycle_times
    ):
        """
        A file satisfying spec[0] but not spec[1] must raise MissingGroupError
        naming spec[1]'s group_path, not spec[0]'s.
        """
        path = tmp_path / nc_filename(ob_type, cycle_times[0])
        with nc4.Dataset(path, "w", format="NETCDF4") as ds:
            ds.createDimension("analysisCycle", 1)
            ds.createDimension("Domain", N_DOMAINS)

            # griddedBins present at root (coords check passes) but no sub-groups
            grp_grid = ds.createGroup("griddedBins")
            grp_grid.createVariable("latitude",  "f4", ())
            grp_grid.createVariable("longitude", "f4", ())

            # byDomains/ombg/stationPressure present with assimilated_mean
            g1 = ds.createGroup("byDomains")
            g2 = g1.createGroup("ombg")
            g3 = g2.createGroup("stationPressure")
            g3.createDimension("analysisCycle", 1)
            g3.createDimension("Domain", N_DOMAINS)
            g3.createVariable(
                "assimilated_mean", "f4", ("analysisCycle", "Domain")
            )[:] = np.ones((1, N_DOMAINS), dtype=np.float32)

        # spec[0] (byDomains/...) passes, spec[1] (griddedBins/ombg/...) fails
        with pytest.raises(MissingGroupError) as exc_info:
            validate_nc_file(path, COORDS_GROUP, FIGURE_SPECS)
        assert exc_info.value.group_path == FIGURE_SPECS[1]["group_path"]

    def test_error_messages_include_filename(
        self, corrupt_nc, nc_missing_coords_group, nc_missing_variable
    ):
        with pytest.raises(CorruptFileError) as exc_info:
            validate_nc_file(corrupt_nc, COORDS_GROUP, FIGURE_SPECS)
        assert corrupt_nc.name in str(exc_info.value)

        with pytest.raises(MissingGroupError) as exc_info:
            validate_nc_file(nc_missing_coords_group, COORDS_GROUP, FIGURE_SPECS)
        assert nc_missing_coords_group.name in str(exc_info.value)

        with pytest.raises(MissingVariableError) as exc_info:
            validate_nc_file(nc_missing_variable, COORDS_GROUP, FIGURE_SPECS)
        assert nc_missing_variable.name in str(exc_info.value)


# ---------------------------------------------------------------------------
# validate_and_quarantine_nc_files
# ---------------------------------------------------------------------------

class TestValidateAndQuarantineNcFiles:

    def _logger(self):
        return MagicMock()

    def _quarantine(self, nc_files, found_times, logger=None):
        return validate_and_quarantine_nc_files(
            nc_files=nc_files,
            found_times=found_times,
            coords_group=COORDS_GROUP,
            figure_specs=FIGURE_SPECS,
            ob_type="prepbufr_adpsfc",
            logger=logger or self._logger(),
        )

    def test_all_valid_files_pass_through(
        self, valid_nc, tmp_path, ob_type, cycle_times, write_nc_file
    ):
        second = tmp_path / nc_filename(ob_type, cycle_times[1])
        write_nc_file(second, cycle_times[1], stat_group="ombg/stationPressure")
        files = [valid_nc, second]
        times = [cycle_times[0], cycle_times[1]]

        valid_files, valid_times = self._quarantine(files, times)
        assert valid_files == files
        assert valid_times == times

    def test_corrupt_file_quarantined_sibling_retained(
        self, valid_nc, corrupt_nc, cycle_times
    ):
        valid_files, valid_times = self._quarantine(
            [valid_nc, corrupt_nc],
            [cycle_times[0], cycle_times[1]],
        )
        assert valid_files == [valid_nc]
        assert valid_times == [cycle_times[0]]

    def test_missing_group_file_quarantined(
        self, valid_nc, nc_missing_figure_group, cycle_times
    ):
        valid_files, valid_times = self._quarantine(
            [valid_nc, nc_missing_figure_group],
            [cycle_times[0], cycle_times[3]],
        )
        assert valid_files == [valid_nc]
        assert valid_times == [cycle_times[0]]

    def test_missing_variable_file_quarantined(
        self, valid_nc, nc_missing_variable, cycle_times
    ):
        valid_files, valid_times = self._quarantine(
            [nc_missing_variable, valid_nc],
            [cycle_times[0], cycle_times[1]],
        )
        assert valid_nc in valid_files
        assert nc_missing_variable not in valid_files

    def test_all_quarantined_returns_empty(
        self, corrupt_nc, nc_missing_figure_group, cycle_times
    ):
        valid_files, valid_times = self._quarantine(
            [corrupt_nc, nc_missing_figure_group],
            [cycle_times[1], cycle_times[3]],
        )
        assert valid_files == []
        assert valid_times == []

    def test_quarantined_cycle_absent_from_valid_times(
        self, valid_nc, corrupt_nc, cycle_times
    ):
        """
        Core stub-path contract: a quarantined cycle's datetime must not
        appear in valid_times so run_monitoring_job treats it as missing
        and creates a stub for it.
        """
        _, valid_times = self._quarantine(
            [valid_nc, corrupt_nc],
            [cycle_times[0], cycle_times[1]],
        )
        assert cycle_times[0] in valid_times
        assert cycle_times[1] not in valid_times

    def test_each_error_type_produces_labelled_log_entry(
        self, corrupt_nc, nc_missing_coords_group, nc_missing_variable, cycle_times
    ):
        logger = self._logger()
        self._quarantine(
            [corrupt_nc, nc_missing_coords_group, nc_missing_variable],
            [cycle_times[1], cycle_times[2], cycle_times[0]],
            logger=logger,
        )
        all_errors = " ".join(str(c) for c in logger.error.call_args_list)
        assert "CORRUPT FILE"     in all_errors
        assert "MISSING GROUP"    in all_errors
        assert "MISSING VARIABLE" in all_errors

    def test_files_and_times_stay_in_sync_after_quarantine(
        self, valid_nc, corrupt_nc, nc_missing_figure_group, cycle_times
    ):
        """
        valid_files[i] must correspond to valid_times[i] after quarantine.
        A misalignment would cause stubs to be created for the wrong cycles.
        """
        valid_files, valid_times = self._quarantine(
            [valid_nc, corrupt_nc, nc_missing_figure_group],
            [cycle_times[0], cycle_times[1], cycle_times[3]],
        )
        assert len(valid_files) == len(valid_times)
        assert valid_files == [valid_nc]
        assert valid_times == [cycle_times[0]]

    def test_empty_input_returns_empty(self):
        valid_files, valid_times = self._quarantine([], [])
        assert valid_files == []
        assert valid_times == []
