"""Contract tests for the shipped sample log and the --json output mode.

These guard the artefact the README points at (`examples/sample_log.json`) and
the machine-readable shape scripts depend on.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "hollowpipe.py"
SAMPLE = ROOT / "examples" / "sample_log.json"
LOG_NAME = "hollowpipe_log.json"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        [sys.executable, str(APP), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == expect, (
        "exit "
        + str(completed.returncode)
        + "\nstdout:\n"
        + completed.stdout
        + "\nstderr:\n"
        + completed.stderr
    )
    return completed


def test_sample_log_ships_and_renders(workdir):
    assert SAMPLE.is_file()
    shutil.copy(SAMPLE, workdir / LOG_NAME)
    completed = run("list")
    assert "Hollowpipe shift log - 10 entries" in completed.stdout
    assert "GATE OPERATIONS (4)" in completed.stdout
    assert "SLUICE ANGLE NOTES (3)" in completed.stdout
    assert "MUD DEPTH READINGS (3)" in completed.stdout
    for gate in ("North", "South", "East"):
        assert gate in completed.stdout


def test_sample_log_entries_are_all_valid(workdir):
    shutil.copy(SAMPLE, workdir / LOG_NAME)
    entries = json.loads(run("list", "--json").stdout)
    assert len(entries) == 10
    assert {entry["type"] for entry in entries} == {"gate", "sluice", "mud"}
    for entry in entries:
        assert entry["id"] and entry["timestamp"] and isinstance(entry["note"], str)
        if entry["type"] == "gate":
            assert entry["gate"] and entry["action"] in ("open", "closed")
        if entry["type"] == "sluice":
            assert 0 <= entry["angle_deg"] <= 90
        if entry["type"] == "mud":
            assert entry["depth_cm"] > 0


def test_every_add_command_can_print_the_saved_entry_as_json(workdir):
    gate = json.loads(
        run(
            "gate",
            "add",
            "--gate",
            "North",
            "--action",
            "open",
            "--operator",
            "AB",
            "--note",
            "kept",
            "--json",
        ).stdout
    )
    assert gate["type"] == "gate"
    assert gate["action"] == "open"
    assert gate["operator"] == "AB"

    sluice = json.loads(run("sluice", "add", "--angle", "42", "--json").stdout)
    assert sluice["type"] == "sluice"
    assert sluice["angle_deg"] == 42

    mud = json.loads(run("mud", "add", "--depth", "8.25", "--note", "outer face", "--json").stdout)
    assert mud["type"] == "mud"
    assert mud["depth_cm"] == 8.25

    assert [entry["type"] for entry in json.loads(run("list", "--json").stdout)] == [
        "gate",
        "sluice",
        "mud",
    ]


def test_add_json_does_not_mix_diagnostics_into_stdout(workdir):
    completed = run("sluice", "add", "--angle", "100", expect=2)
    assert completed.stdout == ""
    assert completed.stderr.startswith("error: ")


@pytest.mark.parametrize(
    "filename", ["README.md", "INSTALL.md", "USAGE.md", "DESIGN.md", "demo.sh"]
)
def test_documented_files_exist(workdir, filename):
    assert (ROOT / filename).is_file()
