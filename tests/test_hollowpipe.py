"""Behavioural tests for Hollowpipe.

The CLI contract (streams, exit codes, persisted log) is exercised through
real subprocess runs in a throwaway working directory; the crash-safety and
store paths are exercised against the module directly.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

APP = Path(__file__).resolve().parents[1] / "hollowpipe.py"
LOG_NAME = "hollowpipe_log.json"
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
EMPTY_HINT = "No entries yet \u2014 log one with: hollowpipe.py gate add ..."


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Run every command in its own directory so ./hollowpipe_log.json is fresh."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def hollowpipe() -> ModuleType:
    # Registering the module in sys.modules is required: the tool uses
    # `from __future__ import annotations`, and dataclasses resolves those
    # string annotations through sys.modules[cls.__module__].
    name = "hollowpipe_under_test"
    spec = importlib.util.spec_from_file_location(name, APP)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        [sys.executable, str(APP), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == expect, (
        "exit " + str(completed.returncode) + " for " + " ".join(args) + "\n"
        "stdout:\n" + completed.stdout + "\nstderr:\n" + completed.stderr
    )
    return completed


def read_log(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# T1 - skeleton, help, empty state
# --------------------------------------------------------------------------


def test_help_lists_every_subcommand(workdir):
    completed = run("--help")
    for name in ("gate", "sluice", "mud", "list"):
        assert name in completed.stdout
    assert "hollowpipe.py list --type mud" in completed.stdout  # usage examples


def test_version_flag(workdir):
    completed = run("--version")
    assert "Hollowpipe" in completed.stdout
    assert "1.0.0" in completed.stdout


def test_empty_log_prints_guidance_and_exits_zero(workdir):
    completed = run("list")
    assert EMPTY_HINT in completed.stdout
    assert completed.stderr == ""
    assert not (workdir / LOG_NAME).exists()


def test_empty_log_json_is_an_empty_array(workdir):
    completed = run("list", "--json")
    assert json.loads(completed.stdout) == []


def test_bare_invocation_prints_help_and_never_writes(workdir):
    completed = run()
    assert "usage: hollowpipe.py" in completed.stdout
    assert "Log:" in completed.stdout
    assert not (workdir / LOG_NAME).exists()


def test_group_without_subcommand_is_a_usage_error(workdir):
    completed = run("gate", expect=2)
    assert "'gate' needs a subcommand" in completed.stderr
    assert not (workdir / LOG_NAME).exists()


def test_module_imports_with_no_side_effects(workdir, hollowpipe):
    assert hollowpipe.__version__ == "1.0.0"
    assert hollowpipe.EMPTY_HINT == EMPTY_HINT
    assert not (workdir / LOG_NAME).exists()


# --------------------------------------------------------------------------
# T2 - gate operations
# --------------------------------------------------------------------------


def test_gate_add_echoes_fields_and_persists(workdir):
    completed = run(
        "gate",
        "add",
        "--gate",
        "North",
        "--action",
        "closed",
        "--operator",
        "AB",
        "--note",
        "driftwood cleared",
    )
    confirmation = completed.stdout.strip()
    for fragment in ("North", "closed", "AB", "driftwood cleared"):
        assert fragment in confirmation
    assert len(confirmation.splitlines()) == 1

    entries = read_log(workdir / LOG_NAME)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["type"] == "gate"
    assert entry["gate"] == "North"
    assert entry["action"] == "closed"
    assert entry["operator"] == "AB"
    assert entry["note"] == "driftwood cleared"
    assert ISO_UTC.match(entry["timestamp"])


def test_gate_add_without_gate_name_is_rejected(workdir):
    completed = run("gate", "add", "--action", "open", expect=2)
    assert "gate name is required" in completed.stderr
    assert completed.stdout == ""
    assert not (workdir / LOG_NAME).exists()


def test_gate_add_with_blank_gate_name_is_rejected(workdir):
    completed = run("gate", "add", "--gate", "   ", "--action", "open", expect=2)
    assert "gate name is required" in completed.stderr
    assert not (workdir / LOG_NAME).exists()


def test_gate_add_rejects_unknown_action(workdir):
    completed = run("gate", "add", "--gate", "North", "--action", "ajar", expect=2)
    assert "action must be 'open' or 'closed'" in completed.stderr
    assert not (workdir / LOG_NAME).exists()


def test_gate_action_is_case_insensitive(workdir):
    run("gate", "add", "--gate", "South", "--action", "OPEN")
    assert read_log(workdir / LOG_NAME)[0]["action"] == "open"


def test_list_prints_newer_gate_above_older_gate(workdir):
    run("gate", "add", "--gate", "North", "--action", "closed", "--note", "first shift")
    run("gate", "add", "--gate", "South", "--action", "open", "--note", "second shift")
    output = run("list").stdout
    assert output.index("second shift") < output.index("first shift")


def test_gate_row_uses_dash_when_operator_and_note_are_omitted(workdir):
    run("gate", "add", "--gate", "East", "--action", "open")
    row = [line for line in run("list").stdout.splitlines() if "East" in line][0]
    assert row.count("-") >= 2


# --------------------------------------------------------------------------
# T3 - sluice angles
# --------------------------------------------------------------------------


def test_sluice_add_confirms_angle_and_note(workdir):
    completed = run("sluice", "add", "--angle", "42", "--note", "half gate")
    confirmation = completed.stdout.strip()
    assert "42 deg" in confirmation
    assert "half gate" in confirmation
    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", confirmation)

    entry = read_log(workdir / LOG_NAME)[0]
    assert entry["type"] == "sluice"
    assert entry["angle_deg"] == 42
    assert "42 deg" in run("list").stdout


@pytest.mark.parametrize("angle", ["130", "abc", "-1", "90.5", ""])
def test_sluice_add_rejects_bad_angles(workdir, angle):
    completed = run("sluice", "add", "--angle", angle, expect=2)
    assert "angle must be a whole number between 0 and 90" in completed.stderr
    assert completed.stdout == ""
    assert not (workdir / LOG_NAME).exists()


@pytest.mark.parametrize("angle", ["0", "90"])
def test_sluice_add_accepts_range_edges(workdir, angle):
    run("sluice", "add", "--angle", angle)
    assert read_log(workdir / LOG_NAME)[0]["angle_deg"] == int(angle)


def test_rejected_sluice_angle_does_not_touch_existing_log(workdir):
    run("sluice", "add", "--angle", "30", "--note", "kept")
    before = (workdir / LOG_NAME).read_text(encoding="utf-8")
    run("sluice", "add", "--angle", "300", expect=2)
    assert (workdir / LOG_NAME).read_text(encoding="utf-8") == before


# --------------------------------------------------------------------------
# T4 - mud depth readings
# --------------------------------------------------------------------------


def test_mud_add_confirms_depth_and_note(workdir):
    completed = run("mud", "add", "--depth", "12.5", "--note", "upstream sill")
    confirmation = completed.stdout.strip()
    assert "12.5 cm" in confirmation
    assert "upstream sill" in confirmation
    assert ISO_UTC.match(read_log(workdir / LOG_NAME)[0]["timestamp"])

    entry = read_log(workdir / LOG_NAME)[0]
    assert entry["type"] == "mud"
    assert entry["depth_cm"] == 12.5
    assert "12.5 cm" in run("list").stdout


def test_mud_whole_depth_renders_without_decimals(workdir):
    run("mud", "add", "--depth", "34.0")
    assert "34 cm" in run("list").stdout


@pytest.mark.parametrize("depth", ["-3", "deep", "0", "nan", "inf", ""])
def test_mud_add_rejects_bad_depths(workdir, depth):
    completed = run("mud", "add", "--depth", depth, expect=2)
    assert "depth must be a positive number of centimetres" in completed.stderr
    assert completed.stdout == ""
    assert not (workdir / LOG_NAME).exists()


# --------------------------------------------------------------------------
# T5 - list rendering, grouping, filtering
# --------------------------------------------------------------------------


def seed_mixed_log(workdir: Path) -> None:
    run(
        "gate",
        "add",
        "--gate",
        "North",
        "--action",
        "closed",
        "--operator",
        "AB",
        "--note",
        "driftwood cleared from the sill",
    )
    run("sluice", "add", "--angle", "42", "--note", "half gate, ebb running")
    run("mud", "add", "--depth", "12.5", "--note", "upstream sill, 40 cm rod")
    run(
        "gate",
        "add",
        "--gate",
        "South",
        "--action",
        "open",
        "--operator",
        "RK",
        "--note",
        "spring tide, 3.1 m on the gauge",
    )


def test_list_groups_by_type_in_aligned_columns(workdir):
    seed_mixed_log(workdir)
    lines = run("list").stdout.splitlines()

    gate_heading = next(i for i, line in enumerate(lines) if line.startswith("GATE OPERATIONS"))
    sluice_heading = next(
        i for i, line in enumerate(lines) if line.startswith("SLUICE ANGLE NOTES")
    )
    mud_heading = next(i for i, line in enumerate(lines) if line.startswith("MUD DEPTH READINGS"))
    assert gate_heading < sluice_heading < mud_heading
    assert lines[gate_heading + 1].startswith("---")
    assert lines[gate_heading + 2].startswith("TIMESTAMP (UTC)")
    assert lines[gate_heading + 3].startswith("---")

    north_row = next(line for line in lines if "North" in line)
    south_row = next(line for line in lines if "South" in line)
    # every row of a group starts its columns at the same offset
    assert north_row.index("North") == south_row.index("South")
    assert north_row.index("closed") == south_row.index("open")


def test_list_type_filter_shows_only_that_section(workdir):
    seed_mixed_log(workdir)
    output = run("list", "--type", "mud").stdout
    assert "MUD DEPTH READINGS (1)" in output
    assert "upstream sill" in output
    assert "GATE OPERATIONS" not in output
    assert "SLUICE ANGLE NOTES" not in output


def test_list_type_filter_with_no_matching_entries(workdir):
    run("gate", "add", "--gate", "North", "--action", "open")
    completed = run("list", "--type", "mud")
    assert "No mud depth readings in the log yet" in completed.stdout
    assert "GATE OPERATIONS" not in completed.stdout


def test_list_json_output_round_trips(workdir):
    seed_mixed_log(workdir)
    entries = json.loads(run("list", "--json").stdout)
    assert [entry["type"] for entry in entries] == ["gate", "sluice", "mud", "gate"]
    assert all({"id", "type", "timestamp", "note"} <= set(entry) for entry in entries)


def test_list_invalid_type_is_a_usage_error(workdir):
    completed = run("list", "--type", "tide", expect=2)
    assert "invalid choice" in completed.stderr


# --------------------------------------------------------------------------
# Crash-safe store
# --------------------------------------------------------------------------


def test_corrupt_log_is_reported_and_left_alone(workdir):
    path = workdir / LOG_NAME
    path.write_text('[{"id": ', encoding="utf-8")
    before = path.read_bytes()

    completed = run("list", expect=3)
    assert "hollowpipe_log.json" in completed.stderr
    assert "invalid JSON" in completed.stderr
    assert completed.stderr.count("\n") == 1
    assert path.read_bytes() == before


def test_append_refuses_to_overwrite_a_corrupt_log(workdir):
    path = workdir / LOG_NAME
    path.write_text("not json at all", encoding="utf-8")
    before = path.read_bytes()

    completed = run("gate", "add", "--gate", "North", "--action", "open", expect=3)
    assert "hollowpipe_log.json" in completed.stderr
    assert path.read_bytes() == before


def test_non_array_and_malformed_entries_are_reported(workdir):
    path = workdir / LOG_NAME
    path.write_text('{"entries": []}', encoding="utf-8")
    assert "expected a JSON array" in run("list", expect=3).stderr

    path.write_text('[{"id": "a", "type": "gate", "timestamp": "t"}]', encoding="utf-8")
    assert "has no gate name" in run("list", expect=3).stderr

    path.write_text(
        '[{"id": "a", "type": "sluice", "timestamp": "t", "angle_deg": 120}]',
        encoding="utf-8",
    )
    assert "angle outside 0-90" in run("list", expect=3).stderr


def test_failed_write_leaves_previous_history_intact(workdir, hollowpipe, monkeypatch):
    path = workdir / LOG_NAME
    hollowpipe.write_records(
        path,
        [hollowpipe.GateOperation("id-1", "2025-07-12T09:00:00Z", "North", "open", "AB", "kept")],
    )
    original = path.read_text(encoding="utf-8")

    def failing_replace(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(hollowpipe.os, "replace", failing_replace)
    with pytest.raises(hollowpipe.StoreError) as excinfo:
        hollowpipe.append_record(
            path,
            hollowpipe.GateOperation(
                "id-2", "2025-07-12T10:00:00Z", "South", "closed", "AB", "lost"
            ),
        )
    assert "cannot write log file" in str(excinfo.value)
    assert path.read_text(encoding="utf-8") == original
    assert list(workdir.glob("*.tmp")) == []


def test_successful_append_leaves_no_temp_files(workdir):
    run("gate", "add", "--gate", "North", "--action", "open")
    run("mud", "add", "--depth", "18")
    assert sorted(path.name for path in workdir.iterdir()) == [LOG_NAME]


def test_alignment_and_unicode_notes_survive_a_round_trip(workdir):
    note = 'gauge 3,1 m \u00b0 \u2014 "bruecke" frei'
    run("gate", "add", "--gate", "Nord", "--action", "open", "--operator", "AB", "--note", note)
    assert read_log(workdir / LOG_NAME)[0]["note"] == note
    assert note in run("list").stdout


# --------------------------------------------------------------------------
# Non-functional: 10k entries still list fast
# --------------------------------------------------------------------------


def test_ten_thousand_entries_list_under_two_seconds(workdir):
    entries = []
    for index in range(10000):
        kind = ("gate", "sluice", "mud")[index % 3]
        stamp = "2025-07-%02dT%02d:%02d:00Z" % (1 + index % 28, index % 24, index % 60)
        if kind == "gate":
            entry = {
                "id": str(index),
                "type": "gate",
                "timestamp": stamp,
                "gate": "North",
                "action": "open",
                "operator": "AB",
                "note": "shift note " + str(index),
            }
        elif kind == "sluice":
            entry = {
                "id": str(index),
                "type": "sluice",
                "timestamp": stamp,
                "angle_deg": index % 91,
                "note": "angle note " + str(index),
            }
        else:
            entry = {
                "id": str(index),
                "type": "mud",
                "timestamp": stamp,
                "depth_cm": 1.5 + index % 50,
                "note": "sounding " + str(index),
            }
        entries.append(entry)
    (workdir / LOG_NAME).write_text(json.dumps(entries), encoding="utf-8")

    started = time.monotonic()
    completed = run("list")
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, "listing 10k entries took %.3fs" % elapsed
    assert completed.stdout.count("shift note") == 3334
    assert "Hollowpipe shift log - 10000 entries" in completed.stdout
