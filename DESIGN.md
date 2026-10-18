# Hollowpipe design direction

Committed for this build; every screen (every command's output) consumes it.

## Archetype and family

- **Archetype**: cli - the terminal is the only surface. There is no web UI and
  none is planned.
- **Style family**: calm-precise. The output states what happened and then gets
  out of the way: no box chatter, no ASCII art, no spinner.
- **Density**: compact - one blank line between sections, two spaces between
  columns, no padding rows.
- **Type personality**: mono / mono. Everything is set in the terminal's own
  system monospace font; the tool ships no fonts and loads none (offline-safe).
- **Surface / mode**: terminal dark, the honest default of a CLI. The tool emits
  no colour at all, so it reads correctly on a dark or a light terminal and
  through a pipe into a file.

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| `accent` | `oklch(0.58 0.12 265)` = `#5777c1` | the one accent: docs headings, terminal profile/shell theme. Terminal output stays colourless so no status depends on hue. |
| `surface` | terminal default background (`#12151b` reference in docs) | no background is painted by the tool |
| `ink` | terminal default foreground | all body text |
| `rule` | `-` (ASCII) | section rules and header underlines |
| `rule-title` | `=` (ASCII) | the title rule of the log masthead |
| `gutter` | 2 spaces | column separation, uniform in every table |
| `indent` | 0 | no indentation, no nesting |
| `ramp` | one size only | terminal font size; hierarchy comes from CASE and rules, not size |

The `#5777c1` hex is the same accent as the OKLCH value above, for any context
that cannot parse `oklch()` (a terminal profile, a docs site, a screenshot
frame). No copy of it is ever passed to a charting API - there are no charts.

## Signature

Aligned columns under an ASCII rule, with one accent reserved for the product's
status voice - carried here by words, never by colour:

- `logged gate operation: ...` for a successful append
- `none yet - log one with: ...` for an empty section
- `error: ...` on stderr for a refused input
- exit codes `0` / `2` / `3` for machine consumers

Nothing is signalled by colour alone: `closed` / `open`, `42 deg`, `12.5 cm` are
words and numbers, so the log survives `| tee`, screen readers and monochrome
terminals.

## Layout skeleton

```
Hollowpipe shift log - N entries          <- masthead, one line
================================           <- '=' title rule
log: ./hollowpipe_log.json                <- where the data lives

GATE OPERATIONS (n)                        <- section, fixed order
-------------------
TIMESTAMP (UTC)  GATE  ACTION  OPERATOR  NOTE    <- header
---------------------------------------------    <- '-' rule
...aligned rows, newest first within the section

SLUICE ANGLE NOTES (n)
...
MUD DEPTH READINGS (n)
...
```

Fixed section order (gate, sluice, mud) is the navigation skeleton: a keeper
reading the log always knows where to look. `--type` collapses it to one
section; `--json` bypasses the skeleton for scripts. Help is the first thing a
bare invocation prints, then a one-line read on the current log.

## Shape language

Monospace, no chrome. Rules are ASCII (`=` for the masthead, `-` under section
headings and table headers) and every table uses the same gutter, rule style and
header casing. No borders, no elevation, no padding boxes - the same system on
every command's output.

## What this rejects

- No colours, no ANSI escapes, no emoji: the plan requires plain ASCII list
  output, and colour-only signals are out.
- No spinners, progress bars, splash, or timed animations: a one-shot command.
- No Inter-on-slate default, no dark-slate card table, no web dashboard: this
  product is a terminal tool.
