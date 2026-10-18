#!/usr/bin/env python3
"""Hollowpipe - the tide gate crew's shift log.

A single-file, standard-library command-line tool that records tide gate
operations, sluice angle notes and mud depth readings into one local JSON log
and prints the log back newest-first in aligned plain text.

Design tokens (calm-precise / mono / compact):
    accent      #5777c1  (oklch(0.58 0.12 265)) - the one product accent, used
                by the docs and any shell theme; terminal output itself is
                plain ASCII with no colour, so no status is carried by hue.
    type        system monospace, a single ramp, compact 2-space column gutter
    separators  ASCII '=' title rule and '-' section rules (box-drawing role)
    status      carried by words ("closed", "12.5 cm", "none yet"), never hue

Exit codes:
    0  success (including the empty log)
    2  rejected input: missing/invalid argument or out-of-range value
    3  the log file could not be read or written
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Sequence, Tuple, Union

__version__ = "1.0.0"

PROG = "hollowpipe.py"
LOG_FILENAME = "hollowpipe_log.json"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_STORE = 3

MSG_GATE_REQUIRED = "gate name is required"
MSG_ACTION_INVALID = "action must be 'open' or 'closed'"
MSG_ANGLE_INVALID = "angle must be a whole number between 0 and 90"
MSG_DEPTH_INVALID = "depth must be a positive number of centimetres"
EMPTY_HINT = "No entries yet \u2014 log one with: hollowpipe.py gate add ..."

# Closed vocabulary for --action; membership is checked by hand so a rejected
# value prints exactly one line instead of an argparse usage dump.
ACTIONS = ("open", "closed")

SECTIONS: Tuple[Tuple[str, str], ...] = (
    ("gate", "GATE OPERATIONS"),
    ("sluice", "SLUICE ANGLE NOTES"),
    ("mud", "MUD DEPTH READINGS"),
)
SECTION_HEADERS: Dict[str, Tuple[str, ...]] = {
    "gate": ("TIMESTAMP (UTC)", "GATE", "ACTION", "OPERATOR", "NOTE"),
    "sluice": ("TIMESTAMP (UTC)", "ANGLE", "NOTE"),
    "mud": ("TIMESTAMP (UTC)", "DEPTH", "NOTE"),
}
SECTION_PLURAL: Dict[str, str] = {
    "gate": "gate operations",
    "sluice": "sluice angle notes",
    "mud": "mud depth readings",
}
SECTION_HINT: Dict[str, str] = {
    "gate": 'hollowpipe.py gate add --gate North --action open --operator AB --note "..."',
    "sluice": 'hollowpipe.py sluice add --angle 42 --note "..."',
    "mud": 'hollowpipe.py mud add --depth 12.5 --note "..."',
}


class UsageError(Exception):
    """Input the tool refuses; reported as one line on stderr, exit code 2."""


class StoreError(Exception):
    """The log file could not be read or written; exit code 3."""


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


def utc_now() -> str:
    """ISO 8601 timestamp in UTC, second precision, e.g. 2025-07-12T09:20:00Z."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class GateOperation:
    """One tide gate operation: which gate, what it did, who logged it."""

    id: str
    timestamp: str
    gate: str
    action: str
    operator: str
    note: str
    kind: ClassVar[str] = "gate"

    def to_record(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.kind,
            "timestamp": self.timestamp,
            "gate": self.gate,
            "action": self.action,
            "operator": self.operator,
            "note": self.note,
        }


@dataclass(frozen=True)
class SluiceNote:
    """The sluice angle in whole degrees, 0-90, at the moment it was set."""

    id: str
    timestamp: str
    angle_deg: int
    note: str
    kind: ClassVar[str] = "sluice"

    def to_record(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.kind,
            "timestamp": self.timestamp,
            "angle_deg": self.angle_deg,
            "note": self.note,
        }


@dataclass(frozen=True)
class MudReading:
    """One mud depth sounding, in centimetres above the sill."""

    id: str
    timestamp: str
    depth_cm: float
    note: str
    kind: ClassVar[str] = "mud"

    def to_record(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.kind,
            "timestamp": self.timestamp,
            "depth_cm": self.depth_cm,
            "note": self.note,
        }


Record = Union[GateOperation, SluiceNote, MudReading]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def parse_gate_name(raw: Optional[str]) -> str:
    gate = (raw or "").strip()
    if not gate:
        raise UsageError(
            MSG_GATE_REQUIRED + " (try: hollowpipe.py gate add --gate North --action open)"
        )
    return gate


def parse_action(raw: Optional[str]) -> str:
    action = (raw or "").strip().lower()
    if action not in ACTIONS:
        raise UsageError(MSG_ACTION_INVALID + " (got " + repr(raw) + "; try --action closed)")
    return action


def parse_angle(raw: Optional[str]) -> int:
    text = (raw or "").strip()
    try:
        value = int(text, 10)
    except ValueError as exc:
        raise UsageError(MSG_ANGLE_INVALID + " (got " + repr(raw) + ")") from exc
    if not 0 <= value <= 90:
        raise UsageError(MSG_ANGLE_INVALID + " (got " + str(value) + ")")
    return value


def parse_depth(raw: Optional[str]) -> float:
    text = (raw or "").strip()
    try:
        value = float(text)
    except ValueError as exc:
        raise UsageError(MSG_DEPTH_INVALID + " (got " + repr(raw) + ")") from exc
    if not math.isfinite(value) or value <= 0:
        raise UsageError(MSG_DEPTH_INVALID + " (got " + repr(raw) + ")")
    return value


def format_depth(value: float) -> str:
    """Render 12.5 as '12.5' and 12.0 as '12' so the log reads like a gauge."""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return repr(number)


def clean_note(raw: Optional[str]) -> str:
    return (raw or "").strip()


# --------------------------------------------------------------------------
# Store: one JSON array at ./hollowpipe_log.json, written atomically
# --------------------------------------------------------------------------


def log_path() -> Path:
    return Path(LOG_FILENAME)


def display_path(path: Path) -> str:
    """The path as the keeper typed it: relative paths keep a './' prefix."""
    text = str(path)
    if not path.is_absolute() and not text.startswith("./"):
        return "./" + text
    return text


def _record_from_dict(data: Any, position: int) -> Record:
    if not isinstance(data, dict):
        raise StoreError("entry " + str(position) + " is not a JSON object")
    entry_id = data.get("id")
    timestamp = data.get("timestamp")
    note = data.get("note", "")
    if not isinstance(entry_id, str) or not entry_id:
        raise StoreError("entry " + str(position) + " has no id")
    if not isinstance(timestamp, str) or not timestamp:
        raise StoreError("entry " + str(position) + " has no timestamp")
    if not isinstance(note, str):
        raise StoreError("entry " + str(position) + " has a non-text note")

    kind = data.get("type")
    if kind == "gate":
        gate = data.get("gate")
        action = data.get("action")
        operator = data.get("operator", "")
        if not isinstance(gate, str) or not gate:
            raise StoreError("entry " + str(position) + " has no gate name")
        if action not in ACTIONS:
            raise StoreError("entry " + str(position) + " has an unknown action")
        if not isinstance(operator, str):
            raise StoreError("entry " + str(position) + " has a non-text operator")
        return GateOperation(entry_id, timestamp, gate, action, operator, note)
    if kind == "sluice":
        angle = data.get("angle_deg")
        if not isinstance(angle, int) or isinstance(angle, bool) or not 0 <= angle <= 90:
            raise StoreError("entry " + str(position) + " has an angle outside 0-90")
        return SluiceNote(entry_id, timestamp, angle, note)
    if kind == "mud":
        depth = data.get("depth_cm")
        if not isinstance(depth, (int, float)) or isinstance(depth, bool) or depth <= 0:
            raise StoreError("entry " + str(position) + " has a depth that is not positive")
        return MudReading(entry_id, timestamp, float(depth), note)
    raise StoreError("entry " + str(position) + " has an unknown type " + repr(kind))


def load_records(path: Path) -> List[Record]:
    """Read the log. A missing file is an empty log; a broken file is an error."""
    shown = display_path(path)
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StoreError(
            "cannot read log file " + shown + ": " + (exc.strerror or str(exc))
        ) from exc
    if not raw.strip():
        raise StoreError("cannot read log file " + shown + ": the file is empty")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StoreError(
            "cannot read log file "
            + shown
            + ": invalid JSON at line "
            + str(exc.lineno)
            + " column "
            + str(exc.colno)
        ) from exc
    if not isinstance(data, list):
        raise StoreError("cannot read log file " + shown + ": expected a JSON array of entries")
    try:
        return [_record_from_dict(item, index) for index, item in enumerate(data, start=1)]
    except StoreError as exc:
        raise StoreError("cannot read log file " + shown + ": " + str(exc)) from exc


def write_records(path: Path, records: Sequence[Record]) -> None:
    """Write the whole log through a temp file plus rename, so a crash mid-write
    leaves the previous history intact."""
    shown = display_path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StoreError(
            "cannot create log directory " + str(path.parent) + ": " + (exc.strerror or str(exc))
        ) from exc

    payload = json.dumps([record.to_record() for record in records], indent=2) + "\n"
    handle = None
    tmp_name = ""
    try:
        descriptor, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
        )
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(tmp_name, str(path))
        tmp_name = ""
    except OSError as exc:
        raise StoreError(
            "cannot write log file " + shown + ": " + (exc.strerror or str(exc))
        ) from exc
    finally:
        if handle is not None:
            with contextlib.suppress(OSError):
                handle.close()
        if tmp_name:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)


def append_record(path: Path, record: Record) -> None:
    # Reading first means a truncated/corrupt log stops the write instead of
    # being overwritten with a one-entry history.
    records = load_records(path)
    records.append(record)
    write_records(path, records)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def align_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> List[str]:
    """Column-align a block with a '-' rule under the header, trailing space trimmed."""
    widths = [len(cell) for cell in header]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row)]
    rule = "-" * (sum(widths) + 2 * (len(widths) - 1))
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(header, widths)).rstrip()]
    lines.append(rule)
    for row in rows:
        lines.append("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())
    return lines


def entry_row(record: Record) -> Tuple[str, ...]:
    note = record.note or "-"
    if isinstance(record, GateOperation):
        return (record.timestamp, record.gate, record.action, record.operator or "-", note)
    if isinstance(record, SluiceNote):
        return (record.timestamp, str(record.angle_deg) + " deg", note)
    return (record.timestamp, format_depth(record.depth_cm) + " cm", note)


def newest_first(records: Sequence[Record]) -> List[Record]:
    # Reversing first makes the stable sort break equal timestamps by newest
    # insertion, which is what a keeper reading the top of the log expects.
    return sorted(reversed(records), key=lambda record: record.timestamp, reverse=True)


def render_log(records: Sequence[Record], path: Path, only_type: Optional[str]) -> str:
    if only_type:
        shown = sum(1 for record in records if record.kind == only_type)
        headline = (
            "Hollowpipe shift log - "
            + str(shown)
            + " "
            + SECTION_PLURAL[only_type]
            + " (--type "
            + only_type
            + ")"
        )
    else:
        noun = "entry" if len(records) == 1 else "entries"
        headline = "Hollowpipe shift log - " + str(len(records)) + " " + noun

    lines = [headline, "=" * len(headline), "log: " + display_path(path), ""]

    for kind, title in SECTIONS:
        if only_type and kind != only_type:
            continue
        group = newest_first([record for record in records if record.kind == kind])
        heading = title + " (" + str(len(group)) + ")"
        lines.append(heading)
        lines.append("-" * len(heading))
        if group:
            lines.extend(
                align_table(SECTION_HEADERS[kind], [entry_row(record) for record in group])
            )
        else:
            lines.append("none yet - log one with: " + SECTION_HINT[kind])
        lines.append("")

    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def command_gate_add(args: argparse.Namespace) -> int:
    gate = parse_gate_name(args.gate)
    action = parse_action(args.action)
    operator = (args.operator or "").strip()
    note = clean_note(args.note)
    record = GateOperation(uuid.uuid4().hex, utc_now(), gate, action, operator, note)
    append_record(log_path(), record)
    if args.json:
        print(json.dumps(record.to_record(), indent=2))
        return EXIT_OK
    line = "logged gate operation: " + gate + " " + action
    if operator:
        line += " by " + operator
    line += " at " + record.timestamp
    if note:
        line += ' - note: "' + note + '"'
    print(line)
    return EXIT_OK


def command_sluice_add(args: argparse.Namespace) -> int:
    angle = parse_angle(args.angle)
    note = clean_note(args.note)
    record = SluiceNote(uuid.uuid4().hex, utc_now(), angle, note)
    append_record(log_path(), record)
    if args.json:
        print(json.dumps(record.to_record(), indent=2))
        return EXIT_OK
    line = "logged sluice angle note: " + str(angle) + " deg at " + record.timestamp
    if note:
        line += ' - note: "' + note + '"'
    print(line)
    return EXIT_OK


def command_mud_add(args: argparse.Namespace) -> int:
    depth = parse_depth(args.depth)
    note = clean_note(args.note)
    record = MudReading(uuid.uuid4().hex, utc_now(), depth, note)
    append_record(log_path(), record)
    if args.json:
        print(json.dumps(record.to_record(), indent=2))
        return EXIT_OK
    line = "logged mud depth reading: " + format_depth(depth) + " cm at " + record.timestamp
    if note:
        line += ' - note: "' + note + '"'
    print(line)
    return EXIT_OK


def command_list(args: argparse.Namespace) -> int:
    path = log_path()
    records = load_records(path)
    only_type = args.type

    if args.json:
        selected = [record for record in records if not only_type or record.kind == only_type]
        print(json.dumps([record.to_record() for record in selected], indent=2))
        return EXIT_OK

    if not records:
        print(EMPTY_HINT)
        return EXIT_OK

    if only_type and not any(record.kind == only_type for record in records):
        print(
            "No "
            + SECTION_PLURAL[only_type]
            + " in the log yet - log one with: "
            + SECTION_HINT[only_type]
        )
        return EXIT_OK

    print(render_log(records, path, only_type))
    return EXIT_OK


def print_overview(path: Path) -> None:
    """Bare invocation: help first, then a one-line read on the log."""
    shown = display_path(path)
    if not path.exists():
        print()
        print("Log: " + shown + " (not created yet)")
        print("Start with: " + SECTION_HINT["gate"])
        print("Or run: bash demo.sh (a seeded walk-through in ./.demo-run)")
        return
    try:
        records = load_records(path)
    except StoreError:
        print()
        print("Log: " + shown + " (unreadable - run 'hollowpipe.py list' for details)")
        return
    counts = {
        "gate": sum(1 for record in records if record.kind == "gate"),
        "sluice": sum(1 for record in records if record.kind == "sluice"),
        "mud": sum(1 for record in records if record.kind == "mud"),
    }
    noun = "entry" if len(records) == 1 else "entries"
    print()
    print(
        "Log: "
        + shown
        + " - "
        + str(len(records))
        + " "
        + noun
        + " ("
        + str(counts["gate"])
        + " gate, "
        + str(counts["sluice"])
        + " sluice, "
        + str(counts["mud"])
        + " mud)"
    )
    if records:
        print("Next: hollowpipe.py list")


# --------------------------------------------------------------------------
# Argument parser
# --------------------------------------------------------------------------

EXAMPLES = """\
examples:
  hollowpipe.py gate add --gate North --action closed --operator AB \\
                --note "driftwood cleared from the sill"
  hollowpipe.py sluice add --angle 42 --note "half gate, ebb running"
  hollowpipe.py mud add --depth 12.5 --note "upstream sill, 40 cm rod"
  hollowpipe.py list
  hollowpipe.py list --type mud
  hollowpipe.py list --json

the log lives at ./hollowpipe_log.json and is append-only: entries are never
edited or deleted, and every write goes through a temp file plus rename.

exit codes: 0 success, 2 rejected input, 3 the log could not be read or written
docs: README.md (quickstart), USAGE.md (walkthroughs), DESIGN.md (output style)
tests: python3 -m pytest
"""

GATE_EXAMPLES = """\
examples:
  hollowpipe.py gate add --gate North --action closed --operator AB \\
                --note "driftwood cleared from the sill"
  hollowpipe.py gate add --gate South --action open --operator RK --note "spring tide"
  hollowpipe.py list --type gate
"""

SLUICE_EXAMPLES = """\
examples:
  hollowpipe.py sluice add --angle 42 --note "half gate, ebb running"
  hollowpipe.py sluice add --angle 0 --note "sluice shut for the flood"
  hollowpipe.py list --type sluice
"""

MUD_EXAMPLES = """\
examples:
  hollowpipe.py mud add --depth 12.5 --note "upstream sill, 40 cm rod"
  hollowpipe.py mud add --depth 34 --note "after the neap, settled"
  hollowpipe.py list --type mud
"""

LIST_EXAMPLES = """\
examples:
  hollowpipe.py list
  hollowpipe.py list --type gate
  hollowpipe.py list --json

groups are printed gate, sluice, mud, each newest first, in aligned plain text.
"""


def build_parser() -> Tuple[argparse.ArgumentParser, Dict[str, argparse.ArgumentParser]]:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Hollowpipe - tide gate operation log, sluice angle notes and mud depth "
            "readings in one local JSON log."
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="Hollowpipe " + __version__)
    commands = parser.add_subparsers(dest="command", metavar="{gate,sluice,mud,list}")
    groups: Dict[str, argparse.ArgumentParser] = {}

    gate_parser = commands.add_parser(
        "gate",
        help="log a tide gate operation",
        description="Log a tide gate operation: gate name, open/closed action, operator, note.",
        epilog=GATE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gate_commands = gate_parser.add_subparsers(dest="subcommand", metavar="{add}")
    gate_add = gate_commands.add_parser(
        "add",
        help="append one gate operation to the log",
        description="Append one tide gate operation and echo what was saved.",
        epilog=GATE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gate_add.add_argument(
        "--gate", metavar="NAME", default="", help="gate name, e.g. North (required)"
    )
    gate_add.add_argument(
        "--action", metavar="{open,closed}", default="", help="what the gate did (required)"
    )
    gate_add.add_argument(
        "--operator", metavar="INITIALS", default="", help="keeper initials, e.g. AB"
    )
    gate_add.add_argument("--note", metavar="TEXT", default="", help="free-text note")
    gate_add.add_argument("--json", action="store_true", help="print the saved entry as JSON")
    gate_add.set_defaults(handler=command_gate_add)
    groups["gate"] = gate_parser

    sluice_parser = commands.add_parser(
        "sluice",
        help="log a sluice angle note",
        description="Record the sluice angle in whole degrees, 0-90, with an optional note.",
        epilog=SLUICE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sluice_commands = sluice_parser.add_subparsers(dest="subcommand", metavar="{add}")
    sluice_add = sluice_commands.add_parser(
        "add",
        help="append one sluice angle note",
        description="Append one sluice angle note and echo what was saved.",
        epilog=SLUICE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sluice_add.add_argument(
        "--angle", metavar="DEG", default="", help="whole degrees, 0-90 (required)"
    )
    sluice_add.add_argument("--note", metavar="TEXT", default="", help="free-text note")
    sluice_add.add_argument("--json", action="store_true", help="print the saved entry as JSON")
    sluice_add.set_defaults(handler=command_sluice_add)
    groups["sluice"] = sluice_parser

    mud_parser = commands.add_parser(
        "mud",
        help="log a mud depth reading",
        description="Record a mud depth sounding in centimetres, with an optional note.",
        epilog=MUD_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mud_commands = mud_parser.add_subparsers(dest="subcommand", metavar="{add}")
    mud_add = mud_commands.add_parser(
        "add",
        help="append one mud depth reading",
        description="Append one mud depth reading and echo what was saved.",
        epilog=MUD_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mud_add.add_argument(
        "--depth", metavar="CM", default="", help="depth in centimetres, > 0 (required)"
    )
    mud_add.add_argument("--note", metavar="TEXT", default="", help="free-text note")
    mud_add.add_argument("--json", action="store_true", help="print the saved entry as JSON")
    mud_add.set_defaults(handler=command_mud_add)
    groups["mud"] = mud_parser

    list_parser = commands.add_parser(
        "list",
        help="print the shift log, newest first",
        description="Print the whole shift log newest first, grouped by record type.",
        epilog=LIST_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser.add_argument(
        "--type", choices=("gate", "sluice", "mud"), help="only print one record type"
    )
    list_parser.add_argument("--json", action="store_true", help="print the entries as JSON")
    list_parser.set_defaults(handler=command_list)

    return parser, groups


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser, groups = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)

    if handler is None:
        if args.command is None:
            parser.print_help()
            print_overview(log_path())
            return EXIT_OK
        # A command group without a subcommand: help on stderr, usage exit code.
        groups[args.command].print_help(file=sys.stderr)
        print(
            "error: '" + args.command + "' needs a subcommand, e.g. '" + args.command + " add'",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        return int(handler(args))
    except UsageError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return EXIT_USAGE
    except StoreError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return EXIT_STORE


if __name__ == "__main__":
    sys.exit(main())
