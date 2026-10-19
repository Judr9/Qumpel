from pathlib import Path
from glob import glob
import os
import sys
from shutil import move, copy
from datetime import datetime
from math import isfinite
import re
import yaml
from collections import defaultdict


TIME_TAG_PATTERNS = (
    re.compile(r"\d{8}_\d{6}"),
    re.compile(r"\d{4}-\d{2}-\d{2}[_-]\d{2}-\d{2}-\d{2}"),
)
TIME_FILTER_FORMAT = '%Y-%m-%d-%H-%M-%S'
SWEEP_SPLIT_PATTERN = re.compile(r"_(?:sweep|timetrace)_", re.IGNORECASE)
NUMERIC_VALUE_PATTERN = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
NUMERIC_TOKEN_PATTERN = re.compile(rf"^{NUMERIC_VALUE_PATTERN}$")
TOKEN_WITH_TRAILING_NUMERIC_PATTERN = re.compile(
    rf"^(?P<prefix>[A-Za-z_][A-Za-z0-9_]*?)(?P<value>{NUMERIC_VALUE_PATTERN})$"
)
CHANNEL_IDENTIFIER_PATTERN = re.compile(r"(?:ch|channel)\d+", re.IGNORECASE)
MANUAL_TIME_RANGE_PATTERN = re.compile(
    r"^\s*(\d{4}(?:-\d{2}){5})\s+-\s+(\d{4}(?:-\d{2}){5})\s*$"
)


def get_manager_config():
    try:
        with open('manager_config.yml', 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
    except FileNotFoundError as exeception:
        print('\nCould not fined manager config.'
              '\nPlase make sure that:'
              '\n\n1) You are in the root of your measurement folder'
              '\n2) The manager_config.yml file exists '
              '(e.g. by running "manager new")')
        raise FileNotFoundError from exeception
    return config


def _parse_time_bound(value, name):
    if value is None:
        return None
    try:
        return datetime.strptime(value, TIME_FILTER_FORMAT)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f'{name} must be a valid timestamp in YYYY-MM-DD-HH-MM-SS format') from error


def _extract_file_timestamps(filename):
    timestamps = []
    for tag in _extract_time_tags(filename):
        if len(tag) == 15:
            time_format = '%Y%m%d_%H%M%S'
        else:
            time_format = TIME_FILTER_FORMAT
            tag = tag.replace('_', '-')
        try:
            timestamps.append(datetime.strptime(tag, time_format))
        except ValueError:
            continue
    return sorted(timestamps)


def _matches_time_range(filename, data_before, data_after):
    if data_before is None and data_after is None:
        return True
    return any(
        (data_before is None or timestamp <= data_before)
        and (data_after is None or timestamp >= data_after)
        for timestamp in _extract_file_timestamps(filename)
    )


def _filter_measurement_files(
        files, experiment_type=None, sweep_param=None,
        data_before=None, data_after=None):
    data_before = _parse_time_bound(data_before, 'data_before')
    data_after = _parse_time_bound(data_after, 'data_after')
    if (data_before is not None and data_after is not None
            and data_after > data_before):
        raise ValueError('data_after must be earlier than or equal to data_before')

    parameter_name = sweep_param
    if sweep_param is not None:
        keys = re.findall(r"\[\s*['\"]([^'\"]+)['\"]\s*\]", sweep_param)
        if keys:
            parameter_name = keys[-1]

    return [
        file for file in files
        if (experiment_type is None
            or Path(file).name.startswith(experiment_type))
        and (parameter_name is None or parameter_name in Path(file).stem)
        and _matches_time_range(file, data_before, data_after)
    ]


def get_current_measurement_file(
        config, experiment_type=None, data_before=None, data_after=None):
    file_type = config['file_type']
    files = _filter_measurement_files(
        glob('*'+file_type), experiment_type=experiment_type,
        data_before=data_before, data_after=data_after)
    if len(files) == 0:
        print('Could not find any measurement files '
              f'matching the configured file extension {file_type}')
        sys.exit()
    elif len(files) == 1:
        return files[0]
    else:
        file_index = file_selector(files)
        return files[file_index]


def _get_sweep_files(
        config, experiment_type=None, sweep_param=None,
        data_before=None, data_after=None):
    file_type = config['file_type']
    files = _filter_measurement_files(
        glob('*' + file_type), experiment_type, sweep_param,
        data_before=data_before, data_after=data_after)
    files.sort()
    sweepfiles = []
    for file in files:
        if 'sweep' in file or "_ch-" in file or 'timetrace' in file:
            sweepfiles.append(file)
    if sweepfiles == []:
        raise FileNotFoundError("No measurement sweep files found to copy.")
    return sweepfiles


def file_selector(files, description='files'):
    while True:
        print(
            f"Found multiple {description}! Please select one of the following {len(files)} {description}:")
        for i, file in enumerate(files, 1):
            print(f"{i} -> {file}")
        choice = input('\nYour Choice: ')
        if choice.isdigit() and 1 <= int(choice) <= len(files):
            return int(choice)-1
        print("\nYour choice was invalid, please try again!")


def _add_yaml_if_configured(config, files):
    if config['track_yaml']:
        original_files = files.copy()
        for file in original_files:
            yaml_file = file.replace(config['file_type'], '.yaml')
            if Path(yaml_file).exists():
                files.append(yaml_file)


def _add_channel_companion_files(
        files, experiment_type=None, sweep_param=None,
        data_before=None, data_after=None, sweep_variant=None):
    channel_files = [file for file in files if "_ch-" in Path(file).name]
    if not channel_files:
        return

    channel_tags = set()
    for file in channel_files:
        channel_tags.update(_extract_time_tags(file))

    if not channel_tags:
        return

    candidates = _filter_measurement_files(
        glob("*.npy") + glob("*.yaml"), experiment_type, sweep_param,
        data_before=data_before, data_after=data_after)
    for candidate in candidates:
        if candidate in files:
            continue
        if (sweep_variant is not None
                and ('sweep' in candidate or '_ch-' in candidate
                     or 'timetrace' in candidate)
                and _extract_sweep_variant_key(candidate) != sweep_variant):
            continue
        candidate_tags = _extract_time_tags(candidate)
        if channel_tags.intersection(candidate_tags):
            files.append(candidate)


def _get_images_if_configured(config):
    if config['save_images']:
        images = glob('*'+config['image_format'])
    else:
        images = []
    return images


def _extract_time_tags(filename):
    stem = Path(filename).stem
    tags = set()
    for pattern in TIME_TAG_PATTERNS:
        tags.update(pattern.findall(stem))
    return tags


def _filter_images_by_time_tag(images, measurement_files, sweep_variant=None):
    measurement_tags = set()
    for measurement_file in measurement_files:
        measurement_tags.update(_extract_time_tags(measurement_file))

    if not measurement_tags:
        return []

    matching_images = []
    for image in images:
        if (sweep_variant is not None
                and SWEEP_SPLIT_PATTERN.search(Path(image).stem)
                and _extract_sweep_variant_key(image) != sweep_variant):
            continue
        image_tags = _extract_time_tags(image)
        if measurement_tags.intersection(image_tags):
            matching_images.append(image)
    return matching_images


def _select_files_with_same_time_tag(files):
    if not files:
        return []
    if len(files) == 1:
        return files

    selected_file = files[file_selector(files)]
    selected_tags = _extract_time_tags(selected_file)
    if not selected_tags:
        return [selected_file]

    matching_files = []
    for file in files:
        if selected_tags.intersection(_extract_time_tags(file)):
            matching_files.append(file)
    return matching_files


def _strip_sweep_metadata(filename):
    stem = Path(filename).stem
    for pattern in TIME_TAG_PATTERNS:
        match = pattern.search(stem)
        if match:
            stem = stem[:match.start()]
    return re.sub(r'_ch-[^_]+', '', stem).strip('_-')


def _extract_sweep_parameter_key(filename):
    """Group by parameter names, removing every numeric value in a grid sweep."""
    stem = _strip_sweep_metadata(filename)
    split = SWEEP_SPLIT_PATTERN.split(stem, maxsplit=1)
    if len(split) < 2:
        return None

    sweep_part = split[1]
    sweep_part = sweep_part.strip("_-")
    if not sweep_part:
        return None

    tokens = [token for token in sweep_part.split("_") if token]
    if not tokens:
        return None

    key_tokens = []
    for token in tokens:
        if NUMERIC_TOKEN_PATTERN.fullmatch(token):
            continue
        # Ch1 in AWG_Ch1_freq names hardware rather than a swept value.
        if CHANNEL_IDENTIFIER_PATTERN.fullmatch(token):
            key_tokens.append(token)
            continue
        trailing_numeric_match = TOKEN_WITH_TRAILING_NUMERIC_PATTERN.fullmatch(token)
        key_tokens.append(
            trailing_numeric_match.group('prefix') if trailing_numeric_match else token)

    if not key_tokens:
        return None
    return "_".join(key_tokens)


def _extract_sweep_variant_key(filename):
    stem = _strip_sweep_metadata(filename)
    parameter = _extract_sweep_parameter_key(filename)
    if parameter is None:
        return stem
    marker = SWEEP_SPLIT_PATTERN.search(stem)
    return stem[:marker.start()] + marker.group().lower() + parameter


def _group_sweep_files_by_parameter(files):
    groups = defaultdict(list)
    for file in files:
        key = _extract_sweep_variant_key(file)
        groups[key].append(file)
    for key in groups:
        groups[key].sort()
    return groups


def _select_sweep_variant(files):
    groups = _group_sweep_files_by_parameter(files)
    variants = sorted(groups)
    if len(variants) == 1:
        return files, variants[0]
    options = [
        f'{variant} ({len(groups[variant])} measurement files)'
        for variant in variants
    ]
    variant = variants[file_selector(options, description='sweep variants')]
    return groups[variant], variant


def _group_sweep_files_by_time(files, sweep_gap_factor):
    timed_files = []
    untimed_files = []
    for file in files:
        timestamps = _extract_file_timestamps(file)
        if timestamps:
            timed_files.append((timestamps[0], file))
        else:
            untimed_files.append(file)
    timed_files.sort()

    groups = []
    previous_timestamp = None
    previous_gap = None
    for timestamp, file in timed_files:
        gap = (timestamp - previous_timestamp
               if previous_timestamp is not None else None)
        if (not groups or (previous_gap is not None
                           and gap > previous_gap * sweep_gap_factor)):
            groups.append([])
        groups[-1].append((timestamp, file))
        # Channel files sharing a timestamp must not reset the previous gap to zero.
        if gap is not None and gap.total_seconds() > 0:
            previous_gap = gap
        previous_timestamp = timestamp
    ranges = [
        (sorted(file for _, file in group), group[0][0], group[-1][0])
        for group in groups
    ]
    if untimed_files:
        ranges.append((sorted(untimed_files), None, None))
    return ranges


def _select_sweep_time_range(files, sweep_gap_factor):
    ranges = _group_sweep_files_by_time(files, sweep_gap_factor)
    if len(ranges) == 1:
        return files, None, None

    while True:
        print('Found potentially separate sweeps: a timestamp gap exceeded '
              f'{sweep_gap_factor:g} times the preceding gap, or files lack valid timestamps.')
        print(f'0 -> Move all {len(files)} measurement files into one folder')
        for index, (group, start, end) in enumerate(ranges, 1):
            label = (f'{start.strftime(TIME_FILTER_FORMAT)} - {end.strftime(TIME_FILTER_FORMAT)}'
                     if start is not None else 'Files without valid timestamps')
            print(f'{index} -> {label} ({len(group)} measurement files)')
        print('Enter a number or an inclusive time range in this format:')
        print('YYYY-MM-DD-HH-MM-SS - YYYY-MM-DD-HH-MM-SS')
        print('Example: 2026-10-07-16-12-45 - 2026-10-07-18-10-31')
        choice = input('\nYour Choice: ').strip()
        if choice.isdigit():
            index = int(choice)
            if index == 0:
                return files, None, None
            if 1 <= index <= len(ranges):
                group, start, end = ranges[index - 1]
                return (group, end.strftime(TIME_FILTER_FORMAT) if end else None,
                        start.strftime(TIME_FILTER_FORMAT) if start else None)
        else:
            match = MANUAL_TIME_RANGE_PATTERN.fullmatch(choice)
            if match:
                data_after, data_before = match.groups()
                try:
                    selected = _filter_measurement_files(
                        files, data_after=data_after, data_before=data_before)
                except ValueError as error:
                    print(error)
                    continue
                if selected:
                    return selected, data_before, data_after
                print('No measurement files match that time range. Please try again.')
                continue
        print('Your choice was invalid, please try again!')


def move_images(images, basefile, config, sweep=False):
    if config['save_obsidian']:
        data_path = Path(config['path_obsidian_files'])
        _ensure_target_path_exists(data_path)
        for image in images:
            copy(image, data_path / image)

    data_path = _get_data_path([basefile], sweep)
    _ensure_target_path_exists(data_path)
    if config['prepend_filename']:
        basename = basefile.rstrip(config['file_type'])
        new_images = []
        for image in images:
            target_filename = basename + '_' + image
            move(image, data_path / target_filename)
            new_images.append(target_filename)
        return new_images
    for image in images:
        move(image, data_path / image)


    return images


def _add_analysis_file(files):
    measurement_type = files[0].split('_')[0]
    basename = Path(files[0]).stem
    notebooks = glob('*.ipynb')
    pyfiles = glob('*.py')
    candidate_files = notebooks + pyfiles
    matching_files = []
    for file in candidate_files:
        if measurement_type == file[:len(measurement_type)]:
            matching_files.append(file)
    if len(matching_files) == 0:
        print("\nCould not find any matching analysis files")
        return
    if len(matching_files) == 1:
        file = matching_files[0]
    else:
        index = file_selector(matching_files)
        file = matching_files[index]
    file_type = file.split('.')[-1]
    if file_type == 'py':
        copy(file, basename + '_' + file)
        files.append(basename + '_' + file)
    if file_type == 'ipynb':
        os.system(f'jupyter nbconvert {file} --to script')
        newfile = file.replace('.ipynb', '.py')
        move(newfile, basename + '_' + newfile)
        files.append(basename + '_' + newfile)


def _get_data_path(files, sweep=False):
    if sweep:
        measurement_type = files[0].split('_')[0] + '_sweeps'
        folder_name = files[0].rstrip('.npy')
        data_path = Path('data') / measurement_type / folder_name
        return data_path
    measurement_type = files[0].split('_')[0]
    data_path = Path('data') / measurement_type
    return data_path


def _ensure_target_path_exists(path):
    if not os.path.exists(path):
        path.mkdir(parents=True)


def _move_files(files, sweep=False):
    data_path = _get_data_path(files, sweep)
    _ensure_target_path_exists(data_path)
    for file in files:
        move(file, data_path / file)


def _write_lab_log_if_configured(
        config, imagefiles, files, sweep=False, include_comments=True,
        data_message=None):
    comment_text = data_message if data_message is not None else ''
    if config['keep_lab_log']:
        if include_comments and data_message is None:
            comment_text = input('Please enter a comment about this measurement: ')
        date = datetime.today().strftime('%Y-%m-%d')
        measurement_type = files[0].split('_')[0]
        if sweep:
            measurement_type = files[0].split('_')[0] + '_sweeps'
        folder_name = files[0].rstrip('.npy')
        with open(Path('data')/'LabLog'/ f'log_{date}.md', 'a',
                  encoding='utf-8') as file:
            file.write(
                '## ' + files[0].rstrip(config['file_type'] + '\n\n'))
            # file.write(data_message + '\n')
            for image in imagefiles:
                file.write(f'![](../{measurement_type}/{folder_name}/{image})\n')
            file.write(
                f'[config](../{measurement_type}/{folder_name}/{files[0].replace(config["file_type"], ".yaml")})\n')
            if comment_text:
                file.write(comment_text + '\n')

    if config['save_obsidian']:
        date = datetime.today().strftime('%Y-%m-%d')
        base = Path(config['path_obsidian_lablog'])
        today = datetime.today()
        year = today.strftime("%Y")
        month_folder = today.strftime("%m-%B")  # e.g. "07-July"
        date_file = today.strftime("%Y-%m-%d-%A")  # e.g. "2025-07-07-Monday"

        path_to_file = base / year / month_folder
        print(path_to_file)

        with open(path_to_file / f'{date_file}.md', 'a', encoding='utf-8') as file:
            file.write('\n#### ' + files[0].rstrip(config['file_type'] + '\n'))
            for image in imagefiles:
                file.write(f'![[{image}]]\n')
            if comment_text:
                file.write(comment_text + '\n')




def move_data(
        include_comments=True, experiment_type=None,
        data_before=None, data_after=None):
    """Move a measurement matching an optional prefix and inclusive time bounds."""
    config = get_manager_config()
    files_to_move = []
    files_to_move.append(get_current_measurement_file(
        config, experiment_type, data_before=data_before, data_after=data_after))
    _add_yaml_if_configured(config, files_to_move)
    image_files = _get_images_if_configured(config)
    image_files = _filter_images_by_time_tag(image_files, files_to_move)
    _add_analysis_file(files_to_move)
    _write_lab_log_if_configured(
        config, image_files, files_to_move, include_comments=include_comments)
    _move_files(files_to_move)
    image_files = move_images(image_files, files_to_move[0], config)


def move_sweep(
        include_comments=True, experiment_type=None, sweep_param=None,
        data_before=None, data_after=None, sweep_gap_factor=2):
    """Select a sweep or timetrace variant and time range, then move related files."""
    config = get_manager_config()
    files_to_move = _get_sweep_files(
        config, experiment_type, sweep_param,
        data_before=data_before, data_after=data_after)
    # Validate the gap before asking the user to select a variant.
    if not isfinite(sweep_gap_factor) or sweep_gap_factor <= 1:
        raise ValueError('sweep_gap_factor must be finite and greater than 1')
    files_to_move, sweep_variant = _select_sweep_variant(files_to_move)
    files_to_move, selected_before, selected_after = _select_sweep_time_range(
        files_to_move, sweep_gap_factor)
    if selected_before is not None:
        data_before = selected_before
    if selected_after is not None:
        data_after = selected_after
    _add_yaml_if_configured(config, files_to_move)
    _add_channel_companion_files(
        files_to_move, experiment_type, sweep_param,
        data_before=data_before, data_after=data_after, sweep_variant=sweep_variant)
    image_files = _get_images_if_configured(config)
    image_files = _filter_images_by_time_tag(
        image_files, files_to_move, sweep_variant=sweep_variant)
    shared_comment = None
    if config['keep_lab_log'] and include_comments:
        shared_comment = input('Please enter a comment about this measurement: ')
    #_add_analysis_file(files_to_move)
    _write_lab_log_if_configured(
        config, image_files, files_to_move, sweep=True,
        include_comments=False, data_message=shared_comment)
    _move_files(files_to_move, sweep=True)
    image_files = move_images(
        image_files, files_to_move[0], config, sweep=True)
