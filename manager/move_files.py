from pathlib import Path
from glob import glob
import os
import sys
from shutil import move, copy
from datetime import datetime
import re
import yaml
from collections import defaultdict


TIME_TAG_PATTERNS = (
    re.compile(r"\d{8}_\d{6}"),
    re.compile(r"\d{4}-\d{2}-\d{2}[_-]\d{2}-\d{2}-\d{2}"),
)
SWEEP_SPLIT_PATTERN = re.compile(r"_sweep_", re.IGNORECASE)
NUMERIC_TOKEN_PATTERN = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$")
TOKEN_WITH_TRAILING_NUMERIC_PATTERN = re.compile(
    r"^(?P<prefix>[A-Za-z_][A-Za-z0-9_]*?)(?P<value>[+-]?\d.*)$"
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


def get_current_measurement_file(config):
    file_type = config['file_type']
    files = glob('*'+file_type)
    if len(files) == 0:
        print('Could not find any measurement files '
              f'matching the configured file extension {file_type}')
        sys.exit()
    elif len(files) == 1:
        return files[0]
    else:
        file_index = file_selector(files)
        return files[file_index]


def _get_sweep_files(config):
    file_type = config['file_type']
    files = glob('*' + file_type)
    files.sort()
    sweepfiles = []
    for file in files:
        if 'sweep' in file or "_ch-" in file:
            sweepfiles.append(file)
    if sweepfiles == []:
        raise FileNotFoundError("No measurement sweep files found to copy.")
    return sweepfiles


def file_selector(files):
    while True:
        print(
            f"Found multiple files! Please select one of the following {len(files)} files:")
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


def _add_channel_companion_files(files):
    channel_files = [file for file in files if "_ch-" in Path(file).name]
    if not channel_files:
        return

    channel_tags = set()
    for file in channel_files:
        channel_tags.update(_extract_time_tags(file))

    if not channel_tags:
        return

    candidates = glob("*.npy") + glob("*.yaml")
    for candidate in candidates:
        if candidate in files:
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


def _filter_images_by_time_tag(images, measurement_files):
    measurement_tags = set()
    for measurement_file in measurement_files:
        measurement_tags.update(_extract_time_tags(measurement_file))

    if not measurement_tags:
        return []

    matching_images = []
    for image in images:
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


def _extract_sweep_parameter_key(filename):
    stem = Path(filename).stem
    split = SWEEP_SPLIT_PATTERN.split(stem, maxsplit=1)
    if len(split) < 2:
        return None

    sweep_part = split[1]
    for pattern in TIME_TAG_PATTERNS:
        sweep_part = pattern.sub("", sweep_part)
    sweep_part = sweep_part.strip("_-")
    if not sweep_part:
        return None

    tokens = [token for token in sweep_part.split("_") if token]
    if not tokens:
        return None

    last_token = tokens[-1]
    trailing_numeric_match = TOKEN_WITH_TRAILING_NUMERIC_PATTERN.match(last_token)
    if trailing_numeric_match:
        prefix = trailing_numeric_match.group("prefix")
        key_tokens = tokens[:-1] + [prefix]
    elif NUMERIC_TOKEN_PATTERN.match(last_token):
        key_tokens = tokens[:-1]
    else:
        key_tokens = tokens

    key_tokens = [token for token in key_tokens if token]
    if not key_tokens:
        return None
    return "_".join(key_tokens)


def _group_sweep_files_by_parameter(files):
    groups = defaultdict(list)
    for file in files:
        key = _extract_sweep_parameter_key(file)
        if key is None:
            key = "__unknown_parameter__"
        groups[key].append(file)
    for key in groups:
        groups[key].sort()
    return groups


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




def move_data(include_comments=True):
    config = get_manager_config()
    files_to_move = []
    files_to_move.append(get_current_measurement_file(config))
    _add_yaml_if_configured(config, files_to_move)
    image_files = _get_images_if_configured(config)
    image_files = _filter_images_by_time_tag(image_files, files_to_move)
    _add_analysis_file(files_to_move)
    _write_lab_log_if_configured(
        config, image_files, files_to_move, include_comments=include_comments)
    _move_files(files_to_move)
    image_files = move_images(image_files, files_to_move[0], config)


def move_sweep(include_comments=True):
    config = get_manager_config()
    files_to_move = _get_sweep_files(config)
    _add_yaml_if_configured(config, files_to_move)
    _add_channel_companion_files(files_to_move)
    image_files = _get_images_if_configured(config)
    image_files = _filter_images_by_time_tag(image_files, files_to_move)
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
