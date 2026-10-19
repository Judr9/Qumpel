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

If there are multiple variants, you choose one by entering its number:

```text
1 -> ESR_AWG_sweep_laser_duration (3 measurement files)
2 -> ESR_AWG_sweep_mw_duration (12 measurement files)
```

For that variant, distinct timestamps are compared in chronological order.
If a gap is more than twice the preceding gap, it suggests a potentially new
sweep. For example, gaps of 60 seconds, 75 seconds, then 180 seconds split before
the last dataset because 180 is greater than 2 times 75. A gap exactly twice
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
YAML files, channel companions, figures, and lab-log entries follow the selected
variant and timestamps. Figures explicitly named for another sweep variant are
excluded even if they share a timestamp; generic figures follow timestamp
matching as before.

To adjust how large an increase suggests a new sweep, set `sweep_gap_factor`
(a finite number greater than 1, default 2):

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
