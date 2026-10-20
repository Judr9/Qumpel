import errno
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import yaml

from manager import move_files as mover


class TransferPathTests(unittest.TestCase):
    def setUp(self):
        original_directory = Path.cwd()
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.addCleanup(os.chdir, original_directory)
        os.chdir(temporary_directory.name)
        self.output = io.StringIO()
        self.enterContext(redirect_stdout(self.output))
        self.enterContext(patch('builtins.input', side_effect=AssertionError('Unexpected prompt')))
        self.config = {
            'file_type': '.npy', 'track_yaml': True, 'save_images': True,
            'image_format': '.png', 'save_obsidian': False,
            'prepend_filename': False, 'keep_lab_log': False,
        }

    def write_config(self):
        Path('manager_config.yml').write_text(yaml.safe_dump(self.config), encoding='utf-8')

    def create_grid(self):
        parameter = 'readout_very_long_phase_parameter_name'
        stems = [
            f'CASR_sensitivity_sweep_{parameter}0.07_{parameter}_2{value}'
            f'_ch-2_2026-10-20-10-38-{39 + index}'
            for index, value in enumerate(('0.07', '-0.07'))
        ]
        files = [f'{stem}{extension}' for stem in stems for extension in ('.npy', '.yaml')]
        images = ['CASR_sensitivity_sweep_readout_phase_2026-10-20-10-38-39_combined.png']
        for name in files + images:
            Path(name).write_text(name, encoding='utf-8')
        return files, images

    def read_mapping(self):
        mappings = list(Path('data').rglob(mover.FILENAME_MAP))
        self.assertEqual(len(mappings), 1)
        path = mappings[0]
        self.assertNotRegex(path.parent.name, r'_h[0-9a-f]{12}$')
        return path.parent, json.loads(path.read_text(encoding='utf-8'))

    def assert_transferred(self, directory, mapping, originals):
        for original in originals:
            target = directory / mapping[original]
            self.assertFalse(Path(original).exists(), original)
            self.assertEqual(target.read_text(encoding='utf-8'), original)
            self.assertLessEqual(mover._windows_length(target.absolute()), mover.WINDOWS_PATH_LIMIT)
            for tag in mover._extract_time_tags(original):
                self.assertIn(tag, target.name)
            self.assertNotRegex(target.name, r'_h[0-9a-f]{12}(?=\.|$)')
            self.assertEqual(target.suffix, Path(original).suffix)

    def test_initials_fallback_keeps_pairs_images_and_log_links_consistent(self):
        files, images = self.create_grid()
        self.config.update(keep_lab_log=True, prepend_filename=True)
        self.write_config()
        Path('data/LabLog').mkdir(parents=True)

        mover.move_sweep(include_comments=False)

        directory, mapping = self.read_mapping()
        self.assertEqual(mapping['shortening'], 'parameter initials')
        self.assert_transferred(directory, mapping['files'], files)
        self.assert_transferred(directory, mapping['images'], images)
        for measurement in files[::2]:
            self.assertEqual(Path(mapping['files'][measurement]).stem,
                             Path(mapping['files'][measurement.replace('.npy', '.yaml')]).stem)
            self.assertIn('rvlppn0.07_rvlppn_2', mapping['files'][measurement])
            self.assertIn('_ch-2_', mapping['files'][measurement])
        log_path, = Path('data/LabLog').glob('log_*.md')
        log = log_path.read_text(encoding='utf-8')
        relative = directory.relative_to('data').as_posix()
        for name in mapping['images'].values():
            self.assertIn(f'![](../{relative}/{name})', log)
        first = files[0]
        self.assertIn(f'[config](../{relative}/{mapping["files"][first.replace(".npy", ".yaml")]})', log)
        self.assertEqual(self.output.getvalue().count('Shortened this batch'), 1)
        self.assertIn('parameter names -> initials', self.output.getvalue())

    def test_move_data_shortens_overlong_prefixed_images_and_updates_flat_folder_links(self):
        files, images = self.create_grid()
        for name in files[2:]:
            Path(name).unlink()
        files = files[:2]
        long_image = ('unrelated_' + 'very_long_description_' * 6
                      + '2026-10-20-10-38-39_combined.png')
        Path(long_image).write_text(long_image, encoding='utf-8')
        images.append(long_image)
        self.config.update(keep_lab_log=True, prepend_filename=True)
        self.write_config()
        Path('data/LabLog').mkdir(parents=True)

        mover.move_data(include_comments=False)

        directory, mapping = self.read_mapping()
        self.assertEqual(directory, Path('data/CASR'))
        self.assertEqual(mapping['shortening'], 'parameter initials')
        self.assert_transferred(directory, mapping['files'], files)
        self.assert_transferred(directory, mapping['images'], images)
        log_path, = Path('data/LabLog').glob('log_*.md')
        log = log_path.read_text(encoding='utf-8')
        for name in mapping['images'].values():
            self.assertIn(f'![](../CASR/{name})', log)
            self.assertLessEqual(mover._windows_length(name), 255)
        self.assertEqual(self.output.getvalue().count('Shortened this batch'), 1)

    def test_first_parameter_fallback_retains_distinct_grid_points(self):
        files, images = self.create_grid()
        self.write_config()
        ordered = files[::2] + files[1::2]
        initial_plan = mover._prepare_transfer(ordered, images, self.config, sweep=True)
        self.assertEqual(initial_plan.shortening, 1)
        limit = max(mover._windows_length(path.absolute())
                    for path in mover._transfer_targets(initial_plan, self.config)) - 1

        with patch.object(mover, 'WINDOWS_PATH_LIMIT', limit):
            mover.move_sweep()
            directory, mapping = self.read_mapping()
            self.assertEqual(mapping['shortening'], 'first parameter only')
            self.assert_transferred(directory, mapping['files'], files)
            self.assert_transferred(directory, mapping['images'], images)
        names = [mapping['files'][name] for name in files[::2]]
        self.assertEqual(len(set(names)), 2)
        for name in names:
            self.assertIn('_rvlppn0.07_', name)
            self.assertNotIn('_rvlppn_2', name)
            self.assertIn('_ch-2_', name)
        self.assertEqual(self.output.getvalue().count('Shortened this batch'), 1)
        self.assertIn('only the first sweep parameter retained', self.output.getvalue())

    def test_existing_overlong_source_paths_keep_their_yaml_companions(self):
        parameter = 'readout_' + 'x' * 175 + '_phase'
        measurement = (f'CASR_sensitivity_sweep_{parameter}0.07'
                       '_ch-2_2026-10-20-10-38-39.npy')
        files = [measurement, measurement.replace('.npy', '.yaml')]
        images = ['plot_2026-10-20-10-38-39.png']
        self.assertGreater(mover._windows_length(Path(measurement).absolute()), 259)
        for name in files + images:
            Path(mover._io_path(name)).write_text(name, encoding='utf-8')
        self.write_config()

        mover.move_sweep()

        directory, mapping = self.read_mapping()
        self.assert_transferred(directory, mapping['files'], files)
        self.assert_transferred(directory, mapping['images'], images)

    def test_unusable_parent_path_fails_before_any_files_are_moved(self):
        files, images = self.create_grid()
        self.write_config()

        with patch.object(mover, 'WINDOWS_PATH_LIMIT', 50), self.assertRaises(OSError) as error:
            mover.move_sweep()

        self.assertEqual(error.exception.errno, errno.ENAMETOOLONG)
        for name in files + images:
            self.assertEqual(Path(name).read_text(encoding='utf-8'), name)
        self.assertFalse(Path('data').exists())

    def test_existing_shortened_destination_is_never_overwritten(self):
        files, images = self.create_grid()
        self.write_config()
        plan = mover._prepare_transfer(files[::2] + files[1::2],
                                       images, self.config, sweep=True)
        plan.data_path.mkdir(parents=True)
        existing = plan.data_path / plan.file_names[files[0]]
        existing.write_text('existing data', encoding='utf-8')

        with self.assertRaises(FileExistsError):
            mover.move_sweep()

        self.assertEqual(existing.read_text(encoding='utf-8'), 'existing data')
        for name in files + images:
            self.assertTrue(Path(name).is_file(), name)
        self.assertFalse((plan.data_path / mover.FILENAME_MAP).exists())

    def test_shortened_obsidian_copies_and_embeds_use_the_planned_names(self):
        files, images = self.create_grid()
        today = datetime.today()
        log_directory = Path('obsidian/log') / today.strftime('%Y') / today.strftime('%m-%B')
        log_directory.mkdir(parents=True)
        self.config.update(save_obsidian=True, path_obsidian_files='obsidian/images',
                           path_obsidian_lablog='obsidian/log', prepend_filename=True)
        self.write_config()

        mover.move_sweep(include_comments=False)

        directory, mapping = self.read_mapping()
        self.assert_transferred(directory, mapping['images'], images)
        for image, name in mapping['obsidian_images'].items():
            self.assertEqual((Path('obsidian/images') / name).read_text(encoding='utf-8'), image)
        log_path, = log_directory.glob('*.md')
        log = log_path.read_text(encoding='utf-8')
        for name in mapping['obsidian_images'].values():
            self.assertIn(f'![[{name}]]', log)


if __name__ == '__main__':
    unittest.main()
