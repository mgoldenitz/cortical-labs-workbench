"""`workbench verify` on hand-built run folders (no simulator needed).

A complete run that passes is covered in test_sdk_integration.py, because verifying
one recomputes digests from a real recording.
"""

import json

import pytest

from workbench import cli, manifest as mf
from workbench.verify import EXIT_INCONSISTENT, EXIT_NOT_COMPLETE, EXIT_OK, STATUSES, verify_run


def _folder(tmp_path, manifest_extra=None, files=("config.json", "worker.log"), list_files=True):
    """A run folder whose listed files match their manifest entries."""
    d = tmp_path / "run"
    d.mkdir()
    for name in files:
        (d / name).write_text(f"contents of {name}\n")
    m = {"schema": mf.MANIFEST_SCHEMA, "run_id": "r1", "status": "running"}
    if list_files:
        m["files"] = {name: mf.file_entry(d / name) for name in files}
    m.update(manifest_extra or {})
    (d / "manifest.json").write_text(json.dumps(m))
    return d


def _code(d):
    return verify_run(d)[0]


def test_exit_code_values_are_documented():
    import workbench.verify as v
    assert (EXIT_OK, EXIT_INCONSISTENT, EXIT_NOT_COMPLETE) == (0, 1, 2)
    for name in ("EXIT_OK", "EXIT_INCONSISTENT", "EXIT_NOT_COMPLETE"):
        assert name in v.__doc__


def test_no_manifest(tmp_path):
    assert _code(tmp_path) == EXIT_INCONSISTENT


@pytest.mark.parametrize("text", ["", "{not json", "[1, 2]", '"running"'])
def test_malformed_manifest(tmp_path, text):
    (tmp_path / "manifest.json").write_text(text)
    assert _code(tmp_path) == EXIT_INCONSISTENT


def test_minimal_running_manifest_is_not_ok(tmp_path):
    # What a killed run can leave behind: no file inventory at all.
    (tmp_path / "manifest.json").write_text('{"status": "running"}')
    code, lines = verify_run(tmp_path)
    assert code == EXIT_INCONSISTENT
    assert not any("verify OK" in line for line in lines)
    assert cli.main(["verify", str(tmp_path)]) == EXIT_INCONSISTENT


def test_missing_file_inventory(tmp_path):
    assert _code(_folder(tmp_path, list_files=False)) == EXIT_INCONSISTENT


def test_empty_file_inventory(tmp_path):
    assert _code(_folder(tmp_path, {"files": {}})) == EXIT_INCONSISTENT


@pytest.mark.parametrize("field", ["status", "run_id", "schema"])
def test_missing_required_field(tmp_path, field):
    d = _folder(tmp_path)
    m = json.loads((d / "manifest.json").read_text())
    del m[field]
    (d / "manifest.json").write_text(json.dumps(m))
    assert _code(d) == EXIT_INCONSISTENT


@pytest.mark.parametrize("status", ["interrupted", "ok", "", None, 3])
def test_unknown_status(tmp_path, status):
    assert _code(_folder(tmp_path, {"status": status})) == EXIT_INCONSISTENT


@pytest.mark.parametrize("entry", [{}, {"sha256": "abc", "bytes": 1}, {"sha256": "0" * 64}, "x"])
def test_malformed_inventory_entry(tmp_path, entry):
    d = _folder(tmp_path)
    m = json.loads((d / "manifest.json").read_text())
    m["files"]["config.json"] = entry
    (d / "manifest.json").write_text(json.dumps(m))
    assert _code(d) == EXIT_INCONSISTENT


@pytest.mark.parametrize("name", ["../outside", "sub/file", "..", "."])
def test_inventory_name_outside_run_folder(tmp_path, name):
    d = _folder(tmp_path)
    m = json.loads((d / "manifest.json").read_text())
    m["files"][name] = {"sha256": "0" * 64, "bytes": 0}
    (d / "manifest.json").write_text(json.dumps(m))
    assert _code(d) == EXIT_INCONSISTENT


@pytest.mark.parametrize("status", [s for s in STATUSES if s != "complete"])
def test_consistent_but_not_complete(tmp_path, status):
    code, lines = verify_run(_folder(tmp_path, {"status": status}))
    assert code == EXIT_NOT_COMPLETE
    assert any("NOT VERIFIED AS COMPLETE" in line for line in lines)
    assert not any("verify OK" in line for line in lines)


def test_interrupted_run_as_recorded_by_the_pipeline(tmp_path):
    # Ctrl-C during acquisition is recorded as status "failed" with this error.
    d = _folder(tmp_path, {"status": "failed", "error": "interrupted by user"})
    assert _code(d) == EXIT_NOT_COMPLETE


@pytest.mark.parametrize("status", [s for s in STATUSES if s != "complete"])
def test_missing_always_required_output(tmp_path, status):
    assert _code(_folder(tmp_path, {"status": status}, files=("config.json",))) == EXIT_INCONSISTENT


def _complete_extra():
    return {"status": "complete",
            "canonical": {"window_frames": 10, "n_spikes": 0, "samples_sha256": "0" * 64,
                          "spikes_sha256": "0" * 64},
            "metrics_sha256": "0" * 64,
            "integrity": {"checks": [], "errors": [], "warnings": []}}


def test_complete_with_required_outputs_missing(tmp_path):
    code, lines = verify_run(_folder(tmp_path, _complete_extra()))
    assert code == EXIT_INCONSISTENT
    text = "\n".join(lines)
    for name in ("recording.h5", "metrics.json", "report.html", "worker_result.json", "channel_metrics.csv"):
        assert f"required output {name} is not in the file inventory" in text


@pytest.mark.parametrize("drop", ["canonical", "metrics_sha256", "integrity"])
def test_complete_without_recorded_digests_or_checks(tmp_path, drop):
    extra = _complete_extra()
    del extra[drop]
    assert _code(_folder(tmp_path, extra)) == EXIT_INCONSISTENT


def test_complete_with_failed_integrity_checks(tmp_path):
    extra = _complete_extra()
    extra["integrity"]["errors"] = ["window_covered"]
    assert _code(_folder(tmp_path, extra)) == EXIT_INCONSISTENT


def test_listed_file_missing_or_changed(tmp_path):
    d = _folder(tmp_path)
    (d / "worker.log").write_text("edited, same length?\n")
    assert _code(d) == EXIT_INCONSISTENT
    (d / "worker.log").unlink()
    assert _code(d) == EXIT_INCONSISTENT


def test_same_size_edit_is_a_checksum_mismatch(tmp_path):
    d = _folder(tmp_path)
    original = (d / "config.json").read_text()
    (d / "config.json").write_text(original.replace("c", "C", 1))
    code, lines = verify_run(d)
    assert code == EXIT_INCONSISTENT
    assert any("checksum mismatch: config.json" in line for line in lines)


def test_unlisted_files_are_reported_not_checked(tmp_path):
    d = _folder(tmp_path)
    (d / "extra.txt").write_text("not in the manifest")
    code, lines = verify_run(d)
    assert code == EXIT_NOT_COMPLETE
    assert any("extra.txt" in line and "not checked" in line for line in lines)
