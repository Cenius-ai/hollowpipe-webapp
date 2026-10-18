# Using Hollowpipe

Every command below runs from the directory that holds your shift log, because
the log always lives at `./hollowpipe_log.json`.

## 1. Log a tide gate operation

```bash
python3 hollowpipe.py gate add --gate North --action closed --operator AB \
                     --note "driftwood cleared from the sill"
```

```
logged gate operation: North closed by AB at 2025-07-12T05:40:12Z - note: "driftwood cleared from the sill"
```

`--gate` and `--action` are required. `--operator` and `--note` are optional; a
missing operator or note prints as `-` in the log. The timestamp is recorded
automatically as ISO 8601 UTC - you never type a time.

Rejected input prints exactly one line on stderr and changes nothing:

```bash
python3 hollowpipe.py gate add --action open
# error: gate name is required (try: hollowpipe.py gate add --gate North --action open)
# exit code 2

python3 hollowpipe.py gate add --gate North --action ajar
# error: action must be 'open' or 'closed' (got 'ajar'; try --action closed)
```

## 2. Record a sluice angle note

```bash
python3 hollowpipe.py sluice add --angle 42 --note "half gate, ebb running"
# logged sluice angle note: 42 deg at 2025-07-12T07:41:55Z - note: "half gate, ebb running"
```

Angles are whole degrees, 0-90 inclusive (`--angle 0` and `--angle 90` are both
valid). Anything else is refused:

```bash
python3 hollowpipe.py sluice add --angle 130
# error: angle must be a whole number between 0 and 90 (got 130)

python3 hollowpipe.py sluice add --angle abc
# error: angle must be a whole number between 0 and 90 (got 'abc')
```

## 3. Record a mud depth reading

```bash
python3 hollowpipe.py mud add --depth 12.5 --note "upstream sill, 40 cm rod"
# logged mud depth reading: 12.5 cm at 2025-07-12T06:48:37Z - note: "upstream sill, 40 cm rod"
```

Depth is positive centimetres; decimals are fine, zero and negatives are not:

```bash
python3 hollowpipe.py mud add --depth -3
# error: depth must be a positive number of centimetres (got '-3')

python3 hollowpipe.py mud add --depth deep
# error: depth must be a positive number of centimetres (got 'deep')
```

Whole depths render without a decimal point: `--depth 34.0` is printed as
`34 cm`, `--depth 8.25` as `8.25 cm`.

## 4. Read the log

```bash
python3 hollowpipe.py list
```

Groups are printed in a fixed order - gate operations, sluice angle notes, mud
depth readings - and inside each group the newest entry is on top. Columns are
aligned, output is plain ASCII with no colour, and the timestamp column is ISO
8601 UTC.

### One record type only

```bash
cp examples/sample_log.json hollowpipe_log.json      # the shift used below
python3 hollowpipe.py list --type mud
```

```
Hollowpipe shift log - 3 mud depth readings (--type mud)
========================================================
log: ./hollowpipe_log.json

MUD DEPTH READINGS (3)
----------------------
TIMESTAMP (UTC)       DEPTH    NOTE
--------------------------------------------------------------------------------
2025-07-12T09:35:06Z  8.25 cm  sounding rod on the outer face, 8 cm and dropping
2025-07-12T08:10:18Z  34 cm    after the neap, silt settled over the gate cill
2025-07-12T06:48:37Z  12.5 cm  upstream sill, 40 cm rod, soft silt
```

If the log has no entries of that type yet:

```
No mud depth readings in the log yet - log one with: hollowpipe.py mud add --depth 12.5 --note "..."
```

### Machine-readable output

```bash
python3 hollowpipe.py list --json | python3 -m json.tool
python3 hollowpipe.py list --type gate --json
```

`--json` also works on the three `add` commands and prints the entry that was
saved. Results go to stdout; only diagnostics go to stderr, so pipes stay clean.

## 5. Empty log

```bash
python3 hollowpipe.py list
# No entries yet — log one with: hollowpipe.py gate add ...
# exit code 0
```

## 6. A damaged log

If `hollowpipe_log.json` is not a JSON array of valid entries, the tool refuses
to read or overwrite it and names the file:

```bash
python3 hollowpipe.py list
# error: cannot read log file ./hollowpipe_log.json: invalid JSON at line 1 column 8
# exit code 3
```

Fix the file (or move it aside) and run again - entries already in it are never
deleted or rewritten by a failed read.

## 7. Exit codes at a glance

| Code | Meaning |
| --- | --- |
| `0` | success, including an empty log |
| `2` | rejected input (argument or range) |
| `3` | the log file could not be read or written |

## 8. Try it without touching your own log

```bash
bash demo.sh                              # seeded shift in ./.demo-run
python3 hollowpipe.py --help              # full usage with examples
python3 hollowpipe.py gate add --help     # one command in detail
```
