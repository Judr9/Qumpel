# pylab_manager

Move measurements and sweeps from the current measurement folder using its
`manager_config.yml` configuration.

From Python, use optional keyword arguments to filter the measurement filenames:

```python
from manager.move_files import move_data, move_sweep

experiment_type = "CASR_sensitivity"
sweep_param = "['pulse_sequence']['laser_duration']"

move_data(experiment_type=experiment_type)
move_sweep(experiment_type=experiment_type, sweep_param=sweep_param)
```

`experiment_type` requires the filename to start with the supplied text.
`sweep_param` requires the final key (`laser_duration` in this example) to appear
anywhere in the filename stem. A plain parameter name such as `"laser_duration"`
also works. Both filters are case-sensitive and can be used independently.
Channel companion measurements must also match any supplied filters; matching
YAML files and timestamp-linked images are included as before.

Use `data_after` and `data_before` to filter by the timestamp in the filename,
for example `2026-10-07-16-02-32`. Supply strings in `YYYY-MM-DD-HH-MM-SS` format:

```python
# Measurements at or after this time:
move_data(data_after="2026-10-07-16-00-00")

# Sweeps at or before this time:
move_sweep(data_before="2026-10-07-17-00-00")

# Combine both bounds with the filename filters for a time range:
move_sweep(
    experiment_type=experiment_type,
    sweep_param=sweep_param,
    data_after="2026-10-07-16-00-00",
    data_before="2026-10-07-17-00-00",
)
```

Both time bounds are inclusive and available in `move_data` and `move_sweep`.
Either can be omitted to leave that end of the range open. Filtering uses the
filename timestamp, not filesystem creation or modification times. Files with
missing or invalid timestamps are excluded when a time bound is supplied.
Invalid bounds or a `data_after` later than `data_before` raise `ValueError`
before any files are moved. Existing compact (`20261007_160232`) and underscore
(`2026-10-07_16-02-32`) timestamps remain supported.

`move_sweep` accepts measurement filenames containing `sweep`, `_ch-`, or
`timetrace` (including `_timetrace_`). Timetraces use the same filters,
selection prompts, related-file handling, and sweep destination folders.
`_sweep_` and `_timetrace_` identify separate variants, even when the experiment
prefix and parameter match.

`move_sweep` first applies the supplied filters, then groups files by their
experiment prefix and sweep parameter. Values such as `mw_duration0.25` and
`mw_duration1.5` belong to the same variant, including their channel files.

Grid sweeps are grouped by all parameter names in filename order, ignoring
every numeric sweep value. For example, these measurements belong to one
variant, `CASR_sensitivity_sweep_pi_pi_half`:

```text
CASR_sensitivity_sweep_pi0.0285_pi_half0.0143_2026-10-19-19-54-49
CASR_sensitivity_sweep_pi0.028_pi_half0.014_2026-10-19-19-54-05
```

All their channel measurements (such as `ch-0` and `ch-2`), matching YAML
files, and figures move into the same folder. Measurement filenames keep their
original parameter values.
Integer, decimal, signed, and scientific notation values are supported, either
attached to parameter names or separated by underscores. Hardware channel
identifiers such as `Ch1` in `AWG_Ch1_freq` are preserved. Different parameter
combinations remain separate variants, and the timestamp-gap check below still
applies to separate measurement sessions. This also works for `_timetrace_` files.

Grids can contain two, three, or more parameters. Indexed parameter/value fragments
are normalized too: `readout_phase0.07_readout_phase_20.07` and
`readout_phase-0.07_readout_phase_2-0.07` belong to the same grid variant,
`readout_phase_readout_phase`. The numeric-only index/value fragments are omitted
from the grouping key, including signs and scientific notation. Parameter names
and their order still define the grid; hardware channel identifiers such as
`Ch1` remain distinct. Original parameter values remain in the measurement files.

The destination folder is named after the earliest selected measurement, using
its filename timestamp. Images and lab-log links use that same destination.
Files sharing a timestamp are ordered by filename. Files without valid timestamps
follow dated measurements; if all selected files are undated, filename order is used.

If there are multiple variants, you choose one by entering its number:

```text
1 -> ESR_AWG_sweep_laser_duration (3 measurement files)
2 -> ESR_AWG_sweep_mw_duration (12 measurement files)
```

For that variant, distinct timestamps are compared in chronological order.
If a gap is more than five times the preceding gap, it suggests a potentially new
sweep. For example, gaps of 60 seconds, 75 seconds, then 400 seconds split before
the last dataset because 400 is greater than 5 times 75. A gap exactly five times
the previous gap stays in the same range. Files sharing a timestamp, such as
channels of the same dataset, stay together and do not reset the comparison.
At least three distinct timestamps are needed to compare two gaps; with fewer,
the files remain together. There is no fixed minimum gap in minutes.
When such gaps occur, you can select a suggested time range, enter `0` to move
all files of the selected variant into one folder, or enter a manual range:

```text
0 -> Move all 12 measurement files into one folder
1 -> 2026-10-07-15-59-59 - 2026-10-07-16-12-45 (6 measurement files)
2 -> 2026-10-07-18-00-00 - 2026-10-07-18-15-00 (6 measurement files)
```

The manual format is `YYYY-MM-DD-HH-MM-SS - YYYY-MM-DD-HH-MM-SS`, for example
`2026-10-07-16-12-45 - 2026-10-07-18-10-31`. These are inclusive `data_after`
and `data_before` bounds applied to the already filtered variant. Invalid or
empty ranges prompt you to try again before any files are moved.
YAML files, channel companions, and lab-log entries follow the selected variant
and timestamps. Images are matched only by filename timestamp: every image in
the configured `image_format` sharing any timestamp with a selected measurement
is moved when `save_images` is enabled. The rest of the image filename, including
experiment prefixes, parameter names, sweep/timetrace labels, and suffixes such
as `_combined`, does not restrict matching.
For example, `CASR_sensitivity_sweep_pi_2026-10-20-09-30-07_combined.png` follows
`CASR_sensitivity_sweep_pi0.028_pi_half0.014_2026-10-20-09-30-07.npy` because
their timestamps match. Images without a matching timestamp remain in place.
This applies to both `move_data` and `move_sweep`, and checks every selected
measurement's timestamp, including the oldest dataset, independently of the
folder name.

To adjust how large an increase suggests a new sweep, set `sweep_gap_factor`
(a finite number greater than 1, default 5):

```python
move_sweep(sweep_gap_factor=3)
```

No selection prompt is needed when only one variant and one time range remain.
Supplying `experiment_type`, `sweep_param`, `data_after`, or `data_before` can
narrow the candidates before these prompts.

The timing check still applies when `sweep_param` is supplied, including as a
Python variable. It compares the timestamps of the matching files and prompts
for a time range if their gaps suggest separate sweeps:

```python
sweep_param = "['pulse_sequence']['mw_duration']"
move_sweep(experiment_type="ESR_AWG", sweep_param=sweep_param)
```

The same filters are available from the command line:

```sh
manager move --experiment-type CASR_sensitivity
manager movesweep --experiment-type CASR_sensitivity --sweep-param "['pulse_sequence']['laser_duration']"
manager move --data-after 2026-10-07-16-00-00
manager movesweep --data-after 2026-10-07-16-00-00 --data-before 2026-10-07-17-00-00
manager movesweep --sweep-gap-factor 3
```

Omitting the filters considers all candidate measurement files. `move_data`
keeps its existing file selector; `move_sweep` uses the variant and time-range
selectors described above. The `include_comments=False` keyword argument (or
the `--no-comments` CLI option) skips the comment prompt while retaining any
necessary file selection prompts.

## Long filenames and Windows paths

`move_data` and `move_sweep` check the entire batch's destination paths before
moving measurements. This includes the sweep folder, measurement/YAML filenames,
images with any configured filename prefix, and Obsidian image copies. Normal
names are retained when they fit. The check uses conservative Windows limits:
259 UTF-16 units for complete file paths, 247 for directories, and 255 for each
path component. These accommodate the classic
[Windows path-length limits](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation).

If the original paths are too long, one naming style is applied to the whole batch:

1. Abbreviate every sweep parameter to its initials while retaining its value.
   For example, `readout_phase0.07_readout_phase_20.07` becomes
   `rp0.07_rp_20.07`.
2. If those paths still do not fit, retain only the first abbreviated sweep
   parameter and its value, for example `rp0.07`. Later parameters are omitted
   from destination filenames.

Both stages preserve filename timestamps, channel tags such as `ch-2`, and file
extensions. Individual timestamps identify grid points; no hashes are appended.
NPY and YAML companions retain the same shortened stem. The sweep folder is shortened using
the earliest selected measurement, and image destinations and lab-log links use
the planned names. Generic image labels are abbreviated too when the batch needs
shortening; image selection still uses only timestamps. Image labels following
timestamps are retained as initials to distinguish plots sharing a timestamp.

The destination folder contains `filename_map.json`, recording every original
filename and its destination name, including images and Obsidian copies. Only
destination names change; measurement and YAML contents are not rewritten.
There are no additional prompts. One batch summary reports the naming style and
mapping location, for example:

```text
Shortened this batch for Windows path limits (24 files, 2 images): parameter names -> initials (readout_phase -> rp); values retained.
Timestamps, channels, and extensions retained.
Original names and destinations: data/CASR_sweeps/.../filename_map.json
```

Existing destination files are never overwritten. If even the first-parameter
style cannot fit, or destination names collide, the operation stops before
moving any measurements. For a parent path that is still too long, move the
measurement folder or configured Obsidian destination closer to the drive root.
