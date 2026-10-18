# Installing Hollowpipe

Hollowpipe is a single-file Python command-line tool. It needs no database, no
server, no environment file and no network at runtime.

## Prerequisites (system level - not installed by `install.sh`)

1. **Python 3.9 or newer** (built and tested on Python 3.11). Check it:

   ```bash
   python3 --version
   ```

No compiler, no system libraries, no service to start: the tool is standard
library only.

## Package manager

**pip**, driven by `requirements.txt` at the project root. The only declared
dependency is the test runner (`pytest==8.4.2`); the tool itself imports
nothing outside the standard library. There is no other package manager and no
lockfile alternative in this project.

## Steps

1. **Install dependencies (one command, it exits when done).**

   ```bash
   bash install.sh
   ```

   It upgrades `pip`/`setuptools`/`wheel`, installs `requirements.txt`, installs
   the `hollowpipe` console script in editable mode
   (`pip install --no-build-isolation -e .`), then runs an import self-check.
   Re-running it is safe.

   Optional: skip this step entirely and call the file directly -
   `python3 hollowpipe.py ...` needs no installation at all.

2. **Seed (optional; the log starts empty by design).**

   An empty log is a real state: `python3 hollowpipe.py list` prints
   `No entries yet — log one with: hollowpipe.py gate add ...`. To get real
   content in one step, pick either:

   ```bash
   bash demo.sh                                            # builds ./.demo-run/hollowpipe_log.json
   cp examples/sample_log.json hollowpipe_log.json         # a realistic shift log to browse
   ```

   Nothing else seeds data; the tool never writes a log file until you log an
   entry.

3. **Run it.**

   ```bash
   python3 hollowpipe.py --help
   python3 hollowpipe.py list
   ```

   (or `hollowpipe --help` if step 1 installed the console script).

   There is no server and no port. The log is always
   `./hollowpipe_log.json` in the current working directory, so `cd` to the
   directory that should hold your shift log before logging entries.

4. **Run the tests.**

   ```bash
   python3 -m pytest
   ```

## Uninstall

Remove the console script and the package:

```bash
python3 -m pip uninstall hollowpipe
```

Your data stays in `./hollowpipe_log.json` - copy it somewhere first if you want
to keep the shift history.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `error: cannot read log file ./hollowpipe_log.json: invalid JSON at line N column M` | The log was hand-edited into invalid JSON. The file is left untouched - fix or move it aside, then `hollowpipe.py list` again. |
| `No entries yet — log one with: hollowpipe.py gate add ...` | You are in a directory with no log yet. Log an entry, or `cd` to the directory holding your log. |
| `error: gate name is required` | `--gate` is missing or blank. `hollowpipe.py gate add --gate North --action open`. |
| `error: angle must be a whole number between 0 and 90` | Angles are whole degrees only - `--angle 42`, not `42.5` or `130`. |
| `error: depth must be a positive number of centimetres` | Depths must be greater than zero: `--depth 12.5`, not `-3` or `nan`. |
| `hollowpipe: command not found` | `install.sh` step 1 was skipped. Use `python3 hollowpipe.py` or run `bash install.sh`. |
