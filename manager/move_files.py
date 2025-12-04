from pathlib import Path
from glob import glob
import os
import sys
from shutil import move, copy
from datetime import datetime
import yaml


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
        if 'sweep' in file:
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
            files.append(file.replace(config['file_type'], '.yaml'))


def _get_images_if_configured(config):
    if config['save_images']:
        images = glob('*'+config['image_format'])
    else:
        images = []
    return images


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


def _write_lab_log_if_configured(config, imagefiles, files, sweep=False):
    if config['keep_lab_log']:
        data_message = input('Please enter a comment about this measurement: ')
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
            file.write(data_message + '\n')

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
            file.write(data_message + '\n')




def move_data():
    config = get_manager_config()
    files_to_move = []
    files_to_move.append(get_current_measurement_file(config))
    _add_yaml_if_configured(config, files_to_move)
    image_files = _get_images_if_configured(config)
    _add_analysis_file(files_to_move)
    _move_files(files_to_move)
    image_files = move_images(image_files, files_to_move[0], config)
    _write_lab_log_if_configured(config, image_files, files_to_move)


def move_sweep():
    config = get_manager_config()
    files_to_move = []
    files_to_move.extend(_get_sweep_files(config))
    _add_yaml_if_configured(config, files_to_move)
    image_files = _get_images_if_configured(config)
    #_add_analysis_file(files_to_move)
    _move_files(files_to_move, sweep=True)
    image_files = move_images(
        image_files, files_to_move[0], config, sweep=True)
    _write_lab_log_if_configured(
        config, image_files, files_to_move, sweep=True)
