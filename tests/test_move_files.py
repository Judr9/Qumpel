import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import yaml

from manager.move_files import move_data, move_sweep


class MoveFilesTests(unittest.TestCase):
    def setUp(self):
        original_directory = Path.cwd()
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.addCleanup(os.chdir, original_directory)
        os.chdir(temporary_directory.name)
        self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch('builtins.input', side_effect=AssertionError(
            'Unexpected interactive prompt')))
        config = {
            'file_type': '.npy',
            'track_yaml': True,
            'save_images': True,
            'image_format': '.png',
            'save_obsidian': False,
            'prepend_filename': False,
            'keep_lab_log': False,
        }
        Path('manager_config.yml').write_text(
            yaml.safe_dump(config), encoding='utf-8')

    def create_files(self, *names):
        for name in names:
            Path(name).write_text('test data', encoding='utf-8')

    def assert_moved(self, directory, *names):
        for name in names:
            self.assertFalse(Path(name).exists(), name)
            self.assertTrue((Path(directory) / name).is_file(), name)

    def test_move_data_without_filters_keeps_existing_behavior(self):
        measurement = 'CASR_20261007_120000.npy'
        configuration = 'CASR_20261007_120000.yaml'
        image = 'plot_20261007_120000.png'
        self.create_files(measurement, configuration, image)

        move_data(False)

        self.assert_moved('data/CASR', measurement, configuration, image)

    def test_move_data_filters_prefix_and_moves_related_files(self):
        measurement = 'CASR_sensitivity_20261007_120000.npy'
        configuration = 'CASR_sensitivity_20261007_120000.yaml'
        image = 'plot_20261007_120000.png'
        unrelated = [
            'CASR_readout_20261007_130000.npy',
            'Other_CASR_sensitivity_20261007_130000.npy',
            'plot_20261007_130000.png',
        ]
        self.create_files(measurement, configuration, image, *unrelated)

        move_data(experiment_type='CASR_sensitivity')

        self.assert_moved('data/CASR', measurement, configuration, image)
        for name in unrelated:
            self.assertTrue(Path(name).is_file(), name)

    def test_move_data_selects_only_among_matching_files(self):
        matching = [
            'CASR_sensitivity_20261007_120000.npy',
            'CASR_sensitivity_20261007_130000.npy',
        ]
        unrelated = 'Other_20261007_140000.npy'
        self.create_files(*matching, unrelated)

        with patch('manager.move_files.file_selector', return_value=0) as selector:
            move_data(experiment_type='CASR_sensitivity')

        selector.assert_called_once()
        self.assertCountEqual(selector.call_args.args[0], matching)
        selected = selector.call_args.args[0][0]
        self.assert_moved('data/CASR', selected)
        self.assertTrue(Path(unrelated).is_file())

    def test_move_sweep_without_filters_selects_one_variant_and_its_companions(self):
        first = 'CASR_sweep_freq_1_20261007_120000.npy'
        other = 'Other_sweep_delay_1_20261007_130000.npy'
        channel = 'CASR_ch-1_20261007_140000.npy'
        companion = 'summary_20261007_140000.npy'
        configuration = 'summary_20261007_140000.yaml'
        ordinary_measurement = 'ordinary_20261007_150000.npy'
        self.create_files(
            first, other, channel, companion, configuration, ordinary_measurement)

        with patch('builtins.input', return_value='1') as prompt:
            move_sweep(False)

        directory = 'data/CASR_sweeps/CASR_ch-1_20261007_140000'
        self.assert_moved(directory, channel, companion, configuration)
        prompt.assert_called_once()
        self.assertTrue(Path(first).is_file())
        self.assertTrue(Path(other).is_file())
        self.assertTrue(Path(ordinary_measurement).is_file())

    def test_move_sweep_accepts_timetraces_without_sweep_or_channel_markers(self):
        first = 'CASR_timetrace_2026-10-07-16-00-00.npy'
        second = 'CASR_timetrace_2026-10-07-16-01-00.npy'
        configuration = first.replace('.npy', '.yaml')
        image = 'plot_2026-10-07-16-00-00.png'
        unrelated = [
            'CASR_timetrace_2026-10-07-15-59-59.npy',
            'CASR_readout_2026-10-07-16-00-00.npy',
        ]
        self.create_files(first, second, configuration, image, *unrelated)

        move_sweep(experiment_type='CASR', data_after='2026-10-07-16-00-00')

        directory = Path('data/CASR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, configuration, image)
        for name in unrelated:
            self.assertTrue(Path(name).is_file(), name)

    def test_timetrace_values_share_a_variant_and_move_all_matching_images(self):
        first = 'ESR_AWG_timetrace_mw_duration0.25_ch-1_2026-10-07-16-00-00.npy'
        second = 'ESR_AWG_timetrace_mw_duration1.5_2026-10-07-16-01-00.npy'
        configuration = second.replace('.npy', '.yaml')
        image = second.replace('.npy', '.png')
        other_sweep = first.replace('_timetrace_', '_sweep_')
        other_timetrace = second.replace('mw_duration1.5', 'laser_duration10')
        unrelated = [
            other_sweep, other_sweep.replace('.npy', '.yaml'),
            other_timetrace, other_timetrace.replace('.npy', '.yaml'),
        ]
        images = [image, other_sweep.replace('.npy', '.png'),
                  other_timetrace.replace('.npy', '.png')]
        self.create_files(first, second, configuration, *images, *unrelated)

        with patch('builtins.input', side_effect=['3']) as prompt:
            move_sweep()

        prompt.assert_called_once()
        directory = Path('data/ESR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, configuration, *images)
        for name in unrelated:
            self.assertTrue(Path(name).is_file(), name)

    def test_selecting_channel_sweep_does_not_add_same_timestamp_timetrace(self):
        channel = 'ESR_AWG_sweep_mw_duration0.25_ch-1_2026-10-07-16-00-00.npy'
        timetrace = 'ESR_AWG_timetrace_mw_duration0.25_2026-10-07-16-00-00.npy'
        configuration = timetrace.replace('.npy', '.yaml')
        image = timetrace.replace('.npy', '.png')
        self.create_files(channel, timetrace, configuration, image)

        with patch('builtins.input', side_effect=['1']) as prompt:
            move_sweep()

        prompt.assert_called_once()
        directory = Path('data/ESR_sweeps') / Path(channel).stem
        self.assert_moved(directory, channel, image)
        for name in (timetrace, configuration):
            self.assertTrue(Path(name).is_file(), name)

    def test_move_sweep_combines_prefix_and_final_parameter_key(self):
        first = 'CASR_sensitivity_sweep_AWG_Ch1_freq_1_20261007_120000.npy'
        second = 'CASR_sensitivity_sweep_AWG_Ch1_freq_2_20261007_120000.npy'
        configuration = first.replace('.npy', '.yaml')
        image = 'plot_20261007_120000.png'
        unrelated = [
            'CASR_readout_sweep_AWG_Ch1_freq_1_20261007_130000.npy',
            'CASR_sensitivity_sweep_delay_1_20261007_140000.npy',
            'Other_CASR_sensitivity_sweep_AWG_Ch1_freq_1_20261007_150000.npy',
            'CASR_sensitivity_AWG_Ch1_freq_20261007_160000.npy',
            'plot_20261007_130000.png',
        ]
        self.create_files(first, second, configuration, image, *unrelated)

        move_sweep(
            experiment_type='CASR_sensitivity',
            sweep_param="['pulse_sequence']['AWG_Ch1_freq']")

        directory = Path('data/CASR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, configuration, image)
        for name in unrelated:
            self.assertTrue(Path(name).is_file(), name)

    def test_move_sweep_accepts_parameter_without_experiment_prefix(self):
        for index, sweep_param in enumerate((
                "['pulse_sequence']['AWG_Ch1_freq']",
                '[ "pulse_sequence" ][ "AWG_Ch1_freq" ]',
                'AWG_Ch1_freq')):
            with self.subTest(sweep_param=sweep_param):
                measurement = f'Other_sweep_AWG_Ch1_freq_{index}_20261007_120000.npy'
                self.create_files(measurement)

                move_sweep(sweep_param=sweep_param)

                directory = Path('data/Other_sweeps') / Path(measurement).stem
                self.assert_moved(directory, measurement)

    def test_move_sweep_accepts_experiment_prefix_without_parameter(self):
        first = 'CASR_sensitivity_sweep_freq_1_20261007_120000.npy'
        second = 'CASR_sensitivity_sweep_delay_1_20261007_130000.npy'
        unrelated = 'CASR_readout_sweep_freq_1_20261007_140000.npy'
        self.create_files(first, second, unrelated)

        with patch('builtins.input', return_value='1') as prompt:
            move_sweep(experiment_type='CASR_sensitivity')

        directory = 'data/CASR_sweeps/CASR_sensitivity_sweep_delay_1_20261007_130000'
        self.assert_moved(directory, second)
        prompt.assert_called_once()
        self.assertTrue(Path(first).is_file())
        self.assertTrue(Path(unrelated).is_file())

    def test_channel_companions_respect_filters_even_with_shared_timestamp(self):
        channel = 'CASR_sensitivity_sweep_AWG_Ch1_freq_1_ch-1_20261007_120000.npy'
        companion = 'CASR_sensitivity_AWG_Ch1_freq_summary_20261007_120000.npy'
        configuration = companion.replace('.npy', '.yaml')
        unrelated = [
            'Other_AWG_Ch1_freq_20261007_120000.npy',
            'Other_AWG_Ch1_freq_20261007_120000.yaml',
            'CASR_sensitivity_delay_20261007_120000.npy',
            'CASR_sensitivity_delay_20261007_120000.yaml',
        ]
        self.create_files(channel, companion, configuration, *unrelated)

        move_sweep(
            experiment_type='CASR_sensitivity',
            sweep_param="['pulse_sequence']['AWG_Ch1_freq']")

        directory = Path('data/CASR_sweeps') / Path(channel).stem
        self.assert_moved(directory, channel, companion, configuration)
        for name in unrelated:
            self.assertTrue(Path(name).is_file(), name)

    def test_unmatched_sweep_filters_leave_files_in_place(self):
        measurement = 'CASR_sensitivity_sweep_delay_1_20261007_120000.npy'
        self.create_files(measurement)

        with self.assertRaises(FileNotFoundError):
            move_sweep(
                experiment_type='CASR_sensitivity',
                sweep_param="['pulse_sequence']['AWG_Ch1_freq']")

        self.assertTrue(Path(measurement).is_file())
        self.assertFalse(Path('data').exists())

    def test_move_data_after_includes_boundary_and_excludes_older_files(self):
        measurement = 'CASR_sensitivity_2026-10-07-16-02-32.npy'
        configuration = measurement.replace('.npy', '.yaml')
        image = 'plot_2026-10-07-16-02-32.png'
        older = 'CASR_sensitivity_2026-10-07-16-02-31.npy'
        self.create_files(measurement, configuration, image, older)

        move_data(data_after='2026-10-07-16-02-32')

        self.assert_moved('data/CASR', measurement, configuration, image)
        self.assertTrue(Path(older).is_file())

    def test_move_data_before_includes_boundary_and_excludes_newer_files(self):
        measurement = 'CASR_sensitivity_2026-10-07-16-02-32.npy'
        newer = 'CASR_sensitivity_2026-10-07-16-02-33.npy'
        self.create_files(measurement, newer)

        move_data(data_before='2026-10-07-16-02-32')

        self.assert_moved('data/CASR', measurement)
        self.assertTrue(Path(newer).is_file())

    def test_move_data_combines_time_range_with_prefix(self):
        measurement = 'CASR_sensitivity_2026-10-07-16-02-32.npy'
        unrelated = [
            'CASR_sensitivity_2026-10-07-15-59-59.npy',
            'CASR_sensitivity_2026-10-07-17-00-01.npy',
            'CASR_readout_2026-10-07-16-02-32.npy',
        ]
        self.create_files(measurement, *unrelated)

        move_data(
            experiment_type='CASR_sensitivity',
            data_after='2026-10-07-16-00-00',
            data_before='2026-10-07-17-00-00')

        self.assert_moved('data/CASR', measurement)
        for name in unrelated:
            self.assertTrue(Path(name).is_file(), name)

    def test_move_sweep_combines_inclusive_time_range_with_filename_filters(self):
        first = 'CASR_sensitivity_sweep_AWG_Ch1_freq_1_ch-1_2026-10-07-16-00-00.npy'
        middle = 'CASR_sensitivity_sweep_AWG_Ch1_freq_2_2026-10-07-16-02-32.npy'
        last = 'CASR_sensitivity_sweep_AWG_Ch1_freq_3_2026-10-07-17-00-00.npy'
        companion = 'CASR_sensitivity_AWG_Ch1_freq_summary_2026-10-07-16-00-00.npy'
        configuration = companion.replace('.npy', '.yaml')
        image = 'plot_2026-10-07-16-00-00.png'
        unrelated = [
            'CASR_sensitivity_sweep_AWG_Ch1_freq_0_ch-1_2026-10-07-15-59-59.npy',
            'CASR_sensitivity_sweep_AWG_Ch1_freq_4_2026-10-07-17-00-01.npy',
            'CASR_readout_sweep_AWG_Ch1_freq_1_2026-10-07-16-02-32.npy',
            'CASR_sensitivity_sweep_delay_1_2026-10-07-16-02-32.npy',
            'CASR_sensitivity_AWG_Ch1_freq_summary_2026-10-07-15-59-59.npy',
            'plot_2026-10-07-15-59-59.png',
        ]
        self.create_files(first, middle, last, companion, configuration, image, *unrelated)

        with patch('builtins.input', return_value='0') as prompt:
            move_sweep(
                experiment_type='CASR_sensitivity',
                sweep_param="['pulse_sequence']['AWG_Ch1_freq']",
                data_after='2026-10-07-16-00-00',
                data_before='2026-10-07-17-00-00')
        prompt.assert_called_once()

        directory = Path('data/CASR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, middle, last, companion, configuration, image)
        for name in unrelated:
            self.assertTrue(Path(name).is_file(), name)

    def test_move_sweep_accepts_each_open_ended_time_range(self):
        for index, bound in enumerate(('data_before', 'data_after')):
            with self.subTest(bound=bound):
                before = f'CASR_sweep_freq_{index}_2026-10-07-16-02-31.npy'
                exact = f'CASR_sweep_freq_{index}_2026-10-07-16-02-32.npy'
                after = f'CASR_sweep_freq_{index}_2026-10-07-16-02-33.npy'
                self.create_files(before, exact, after)

                move_sweep(**{bound: '2026-10-07-16-02-32'})

                first = before if bound == 'data_before' else exact
                directory = Path('data/CASR_sweeps') / Path(first).stem
                included = before if bound == 'data_before' else after
                excluded = after if bound == 'data_before' else before
                self.assert_moved(directory, exact, included)
                self.assertTrue(Path(excluded).is_file())
                Path(excluded).unlink()

    def test_time_filters_exclude_missing_or_invalid_filename_timestamps(self):
        for function in (move_data, move_sweep):
            with self.subTest(function=function.__name__):
                measurement = 'CASR_sweep_freq_1_2026-10-07-16-02-32.npy'
                unrelated = [
                    'CASR_sweep_freq_2_without_timestamp.npy',
                    'CASR_sweep_freq_3_2026-02-30-16-02-32.npy',
                ]
                self.create_files(measurement, *unrelated)

                function(data_after='2026-10-07-16-00-00')

                for name in unrelated:
                    self.assertTrue(Path(name).is_file(), name)
                self.assertFalse(Path(measurement).exists())

    def test_invalid_time_bounds_fail_before_moving_files(self):
        measurement = 'CASR_sweep_freq_1_2026-10-07-16-02-32.npy'
        self.create_files(measurement)
        invalid_bounds = (
            {'data_before': 'not-a-date'},
            {'data_after': '2026-02-30-16-02-32'},
            {'data_after': '2026-10-07-17-00-00',
             'data_before': '2026-10-07-16-00-00'},
        )
        for function in (move_data, move_sweep):
            for bounds in invalid_bounds:
                with self.subTest(function=function.__name__, bounds=bounds):
                    with self.assertRaises(ValueError):
                        function(**bounds)

                    self.assertTrue(Path(measurement).is_file())
                    self.assertFalse(Path('data').exists())

    def test_time_filters_accept_legacy_timestamp_formats(self):
        for time_tag in ('20261007_160232', '2026-10-07_16-02-32'):
            with self.subTest(time_tag=time_tag):
                measurement = f'CASR_sweep_freq_1_{time_tag}.npy'
                self.create_files(measurement)

                move_sweep(
                    data_after='2026-10-07-16-02-32',
                    data_before='2026-10-07-16-02-32')

                directory = Path('data/CASR_sweeps') / Path(measurement).stem
                self.assert_moved(directory, measurement)

    def test_omitting_time_bounds_allows_untagged_filenames(self):
        measurement = 'CASR_sensitivity_without_timestamp.npy'
        self.create_files(measurement)

        move_data()

        self.assert_moved('data/CASR', measurement)

    def test_decimal_sweep_values_are_one_variant_and_keep_their_figures(self):
        first = 'ESR_AWG_sweep_mw_duration0.25_2026-10-07-15-59-59.npy'
        second = 'ESR_AWG_sweep_mw_duration1.5_2026-10-07-16-12-45.npy'
        other = 'ESR_AWG_sweep_laser_duration10_2026-10-07-16-12-45.npy'
        configuration = second.replace('.npy', '.yaml')
        image = second.replace('.npy', '.png')
        other_configuration = other.replace('.npy', '.yaml')
        other_image = other.replace('.npy', '.png')
        self.create_files(
            first, second, other, configuration, image, other_configuration, other_image)

        with patch('builtins.input', return_value='2') as prompt:
            move_sweep()

        prompt.assert_called_once()
        directory = Path('data/ESR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, configuration, image, other_image)
        for name in (other, other_configuration):
            self.assertTrue(Path(name).is_file(), name)

    def test_sweep_moves_images_regardless_of_variant_or_experiment_name(self):
        first = 'CASR_sensitivity_sweep_N8_ch-0_2026-10-19-21-19-12.npy'
        channel = first.replace('ch-0', 'ch-2')
        second = 'CASR_sensitivity_sweep_N16_ch-0_2026-10-19-21-20-12.npy'
        configuration = first.replace('.npy', '.yaml')
        image = 'CASR_sensitivity_sweep_sweep_N_2026-10-19-21-19-12_combined.png'
        regular_image = 'CASR_sensitivity_sweep_N_2026-10-19-21-20-12_combined.png'
        images = [image, regular_image,
            'CASR_sensitivity_sweep_sweep_delay_2026-10-19-21-19-12_combined.png',
            'Other_sweep_sweep_N_2026-10-19-21-19-12_combined.png',
        ]
        unrelated = [
            'CASR_sensitivity_sweep_sweep_N_2026-10-19-21-21-12_combined.png',
        ]
        self.create_files(
            first, channel, second, configuration, *images, *unrelated)

        move_sweep(experiment_type='CASR_sensitivity', sweep_param='N')

        directory = Path('data/CASR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, channel, second, configuration, *images)
        for name in unrelated:
            self.assertTrue(Path(name).is_file(), name)

    def test_combined_sweep_image_still_matches_literal_sweep_parameter_name(self):
        measurement = 'CASR_sensitivity_sweep_sweep_N8_2026-10-19-21-19-12.npy'
        image = 'CASR_sensitivity_sweep_sweep_N_2026-10-19-21-19-12_combined.png'
        self.create_files(measurement, image)

        move_sweep()

        directory = Path('data/CASR_sweeps') / Path(measurement).stem
        self.assert_moved(directory, measurement, image)

    def test_grid_sweep_moves_images_using_only_selected_measurement_timestamps(self):
        first = 'CASR_sensitivity_sweep_pi0.028_pi_half0.014_2026-10-20-09-30-07.npy'
        second = 'CASR_sensitivity_sweep_pi0.0285_pi_half0.0143_2026-10-20-09-31-07.npy'
        configuration = first.replace('.npy', '.yaml')
        images = [
            'CASR_sensitivity_sweep_pi_2026-10-20-09-30-07_combined.png',
            'Other_sweep_delay_2026-10-20-09-30-07.png',
            'anything_2026-10-20-09-30-07_summary.png',
            'Other_timetrace_freq_2026-10-20-09-31-07.png',
        ]
        unrelated = [
            'CASR_sensitivity_sweep_pi_2026-10-20-09-29-59_combined.png',
            'anything_2026-10-20-09-31-08.png',
            'plot_without_timestamp.png',
            'notes_2026-10-20-09-30-07.txt',
        ]
        self.create_files(first, second, configuration, *images, *unrelated)

        move_sweep(
            experiment_type='CASR_sensitivity', sweep_param='pi_half',
            data_after='2026-10-20-09-30-07', data_before='2026-10-20-09-31-07')

        directory = Path('data/CASR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, configuration, *images)
        for name in unrelated:
            self.assertTrue(Path(name).is_file(), name)

    def test_grid_sweep_moves_all_parameter_values_channels_and_related_files(self):
        stems = [
            'CASR_sensitivity_sweep_pi0.028_pi_half0.014_2026-10-19-19-54-05',
            'CASR_sensitivity_sweep_pi0.0285_pi_half0.0143_2026-10-19-19-54-49',
        ]
        measurements = [
            f'{stem}_ch-{channel}.npy' for stem in stems for channel in (0, 1, 2)
        ]
        configurations = [name.replace('.npy', '.yaml') for name in measurements]
        images = [f'{stem}.png' for stem in stems]
        images.append(
            'CASR_sensitivity_sweep_sweep_pi_pi_half_2026-10-19-19-54-05_combined.png')
        self.create_files(*measurements, *configurations, *images)

        move_sweep(experiment_type='CASR_sensitivity', sweep_param='pi_half')

        directory = Path('data/CASR_sweeps') / Path(measurements[0]).stem
        self.assert_moved(directory, *measurements, *configurations, *images)

    def test_grid_sweep_keeps_other_parameter_combinations_separate(self):
        first = 'CASR_sweep_pi0.028_pi_half0.014_ch-0_2026-10-19-19-54-05.npy'
        second = 'CASR_sweep_pi0.0285_pi_half0.0143_ch-2_2026-10-19-19-54-49.npy'
        configuration = second.replace('.npy', '.yaml')
        image = second.replace('.npy', '.png')
        other = first.replace('pi_half0.014', 'laser_duration10')
        single_parameter = first.replace('_pi_half0.014', '')
        unrelated = [
            other, other.replace('.npy', '.yaml'),
            single_parameter, single_parameter.replace('.npy', '.yaml'),
        ]
        images = [image, other.replace('.npy', '.png'),
                  single_parameter.replace('.npy', '.png')]
        self.create_files(first, second, configuration, *images, *unrelated)
        output = io.StringIO()

        with redirect_stdout(output), patch('builtins.input', side_effect=['3']) as prompt:
            move_sweep()

        prompt.assert_called_once()
        self.assertIn('CASR_sweep_pi_pi_half (2 measurement files)', output.getvalue())
        directory = Path('data/CASR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, configuration, *images)
        for name in unrelated:
            self.assertTrue(Path(name).is_file(), name)

    def test_grid_sweep_accepts_integer_signed_and_scientific_values(self):
        cases = (
            ('sweep', 'pi1_pi_half2', 'pi3_pi_half4'),
            ('sweep', 'pi_1_pi_half_2', 'pi_3_pi_half_4'),
            ('sweep', 'pi-0.0285_pi_half+1.43e-2', 'pi+2.8e-2_pi_half.014'),
            ('timetrace', 'pi0.028_pi_half0.014', 'pi0.0285_pi_half0.0143'),
        )
        for marker, first_values, second_values in cases:
            with self.subTest(marker=marker, values=first_values):
                first = f'CASR_{marker}_{first_values}_2026-10-19-19-54-05.npy'
                second = f'CASR_{marker}_{second_values}_2026-10-19-19-54-49.npy'
                self.create_files(first, second)

                move_sweep()

                directory = Path('data/CASR_sweeps') / Path(first).stem
                self.assert_moved(directory, first, second)

    def test_indexed_phase_grids_with_two_or_three_variables_stay_together(self):
        for dimensions in (2, 3):
            with self.subTest(dimensions=dimensions):
                stems = []
                for index, value in enumerate(('0.07', '-0.07', '+0.14', '-1e-2')):
                    parameters = f'readout_phase{value}_readout_phase_2{value}'
                    if dimensions == 3:
                        parameters += f'_readout_phase_3{value}'
                    stems.append(
                        f'CASR_sensitivity_sweep_{parameters}_2026-10-20-10-{38 + index:02}-39')
                measurements = [f'{stem}_ch-{channel}.npy'
                                for stem in stems for channel in (0, 2)]
                configurations = [name.replace('.npy', '.yaml') for name in measurements]
                images = [f'{stem}_combined.png' for stem in stems]
                self.create_files(*measurements, *configurations, *images)

                existing = set(Path('data/CASR_sweeps').glob('*'))
                move_sweep(experiment_type='CASR_sensitivity', sweep_param='readout_phase')

                directory, = set(Path('data/CASR_sweeps').glob('*')) - existing
                names = {name: name for name in measurements + configurations + images}
                if (directory / 'filename_map.json').exists():
                    mapping = json.loads((directory / 'filename_map.json').read_text('utf-8'))
                    names.update(mapping['files'])
                    names.update(mapping['images'])
                for name in measurements + configurations + images:
                    self.assertFalse(Path(name).exists(), name)
                    self.assertTrue((directory / names[name]).is_file(), name)

    def test_grid_sweep_preserves_numbered_hardware_channel_identifiers(self):
        first = 'CASR_sweep_AWG_Ch1_freq1_pi0.028_2026-10-19-19-54-05.npy'
        second = 'CASR_sweep_AWG_Ch1_freq2_pi0.0285_2026-10-19-19-54-49.npy'
        other = first.replace('Ch1', 'Ch2')
        self.create_files(first, second, other)
        output = io.StringIO()

        with redirect_stdout(output), patch('builtins.input', side_effect=['1']) as prompt:
            move_sweep()

        prompt.assert_called_once()
        self.assertIn('CASR_sweep_AWG_Ch1_freq_pi (2 measurement files)', output.getvalue())
        directory = Path('data/CASR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second)
        self.assertTrue(Path(other).is_file())

    def test_grid_sweep_still_separates_sessions_by_timestamp_gaps(self):
        first = 'CASR_sweep_pi0.028_pi_half0.014_ch-0_2026-10-19-19-54-05.npy'
        second = 'CASR_sweep_pi0.0285_pi_half0.0143_ch-2_2026-10-19-19-54-49.npy'
        later = 'CASR_sweep_pi0.029_pi_half0.0145_ch-0_2026-10-19-21-00-00.npy'
        configuration = later.replace('.npy', '.yaml')
        image = later.replace('.npy', '.png')
        self.create_files(first, second, later, configuration, image)
        output = io.StringIO()

        with redirect_stdout(output), patch('builtins.input', side_effect=['2']) as prompt:
            move_sweep()

        prompt.assert_called_once()
        self.assertIn('Found potentially separate sweeps', output.getvalue())
        directory = Path('data/CASR_sweeps') / Path(later).stem
        self.assert_moved(directory, later, configuration, image)
        self.assertTrue(Path(first).is_file())
        self.assertTrue(Path(second).is_file())

    def test_sweep_folder_and_log_use_earliest_dataset_in_selected_time_range(self):
        first = 'CASR_sweep_pi0.028_pi_half0.014_ch-0_2026-10-19-19-54-05.npy'
        second = 'CASR_sweep_pi0.0285_pi_half0.0143_ch-0_2026-10-19-19-54-49.npy'
        later = 'CASR_sweep_pi0.029_pi_half0.0145_ch-0_2026-10-19-21-00-00.npy'
        configuration = first.replace('.npy', '.yaml')
        image = 'CASR_sweep_sweep_pi_pi_half_2026-10-19-19-54-05_combined.png'
        self.create_files(first, second, later, configuration, image)
        config = yaml.safe_load(Path('manager_config.yml').read_text(encoding='utf-8'))
        config['keep_lab_log'] = True
        Path('manager_config.yml').write_text(yaml.safe_dump(config), encoding='utf-8')
        Path('data/LabLog').mkdir(parents=True)

        with patch('builtins.input', side_effect=['1']) as prompt:
            move_sweep(include_comments=False)

        prompt.assert_called_once()
        directory = Path('data/CASR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, configuration, image)
        self.assertTrue(Path(later).is_file())
        log_path, = Path('data/LabLog').glob('log_*.md')
        log = log_path.read_text(encoding='utf-8')
        self.assertIn(f'![](../CASR_sweeps/{Path(first).stem}/{image})', log)
        self.assertIn(f'[config](../CASR_sweeps/{Path(first).stem}/{configuration})', log)

    def test_sweep_folder_prefers_dated_measurement_when_combining_undated_files(self):
        undated = 'CASR_sweep_freq0.npy'
        dated = 'CASR_sweep_freq1_2026-10-19-19-54-05.npy'
        image = 'plot_2026-10-19-19-54-05.png'
        self.create_files(undated, dated, image)

        with patch('builtins.input', side_effect=['0']) as prompt:
            move_sweep()

        prompt.assert_called_once()
        directory = Path('data/CASR_sweeps') / Path(dated).stem
        self.assert_moved(directory, undated, dated, image)

    def test_sweep_folder_orders_legacy_and_current_timestamps_chronologically(self):
        later = 'CASR_sweep_freq1_20261019_195449.npy'
        first = 'CASR_sweep_freq2_2026-10-19-19-54-05.npy'
        image = 'plot_2026-10-19-19-54-05.png'
        self.create_files(later, first, image)

        move_sweep()

        directory = Path('data/CASR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, later, image)

    def test_selecting_variant_does_not_readd_other_channel_sweeps(self):
        channel = 'ESR_AWG_sweep_mw_duration0.25_ch-1_2026-10-07-16-12-45.npy'
        second_channel = 'ESR_AWG_sweep_mw_duration0.25_ch-2_2026-10-07-16-12-45.npy'
        other = 'ESR_AWG_sweep_laser_duration10_ch-1_2026-10-07-16-12-45.npy'
        other_configuration = other.replace('.npy', '.yaml')
        self.create_files(channel, second_channel, other, other_configuration)

        with patch('builtins.input', return_value='2') as prompt:
            move_sweep()

        prompt.assert_called_once()
        directory = Path('data/ESR_sweeps') / Path(channel).stem
        self.assert_moved(directory, channel, second_channel)
        self.assertTrue(Path(other).is_file())
        self.assertTrue(Path(other_configuration).is_file())

    def test_numbered_time_range_uses_chronology_and_leaves_other_session_in_place(self):
        first = 'ESR_AWG_sweep_mw_duration10_2026-10-07-15-59-59.npy'
        second = 'ESR_AWG_sweep_mw_duration2_2026-10-07-16-12-45.npy'
        later = 'ESR_AWG_sweep_mw_duration0.25_2026-10-07-18-12-45.npy'
        later_second = 'ESR_AWG_sweep_mw_duration1.5_2026-10-07-18-25-00.npy'
        configuration = first.replace('.npy', '.yaml')
        image = 'plot_2026-10-07-15-59-59.png'
        later_image = 'plot_2026-10-07-18-12-45.png'
        self.create_files(first, second, later, later_second, configuration, image, later_image)
        output = io.StringIO()

        with redirect_stdout(output), patch('builtins.input', return_value='1') as prompt:
            move_sweep()

        prompt.assert_called_once()
        self.assertIn('2026-10-07-15-59-59 - 2026-10-07-16-12-45', output.getvalue())
        self.assertIn('2026-10-07-18-12-45 - 2026-10-07-18-25-00', output.getvalue())
        directory = Path('data/ESR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, configuration, image)
        for name in (later, later_second, later_image):
            self.assertTrue(Path(name).is_file(), name)

    def test_zero_combines_time_ranges_for_selected_variant_only(self):
        first = 'ESR_AWG_sweep_mw_duration0.25_2026-10-07-16-12-45.npy'
        second = 'ESR_AWG_sweep_mw_duration0.5_2026-10-07-16-17-45.npy'
        later = 'ESR_AWG_sweep_mw_duration1.5_2026-10-07-18-12-45.npy'
        other = 'ESR_AWG_sweep_laser_duration10_2026-10-07-16-12-45.npy'
        image = 'plot_2026-10-07-18-12-45.png'
        self.create_files(first, second, later, other, image)

        with patch('builtins.input', side_effect=['2', '0']) as prompt:
            move_sweep()

        self.assertEqual(prompt.call_count, 2)
        directory = Path('data/ESR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, later, image)
        self.assertTrue(Path(other).is_file())

    def test_manual_time_range_filters_selected_variant_and_companions(self):
        first = 'ESR_AWG_sweep_mw_duration0.25_ch-1_2026-10-07-16-12-45.npy'
        second = 'ESR_AWG_sweep_mw_duration0.5_ch-1_2026-10-07-16-17-45.npy'
        later = 'ESR_AWG_sweep_mw_duration1.5_ch-1_2026-10-07-18-12-45.npy'
        companion = 'ESR_AWG_mw_duration_summary_2026-10-07-18-12-45.npy'
        configuration = companion.replace('.npy', '.yaml')
        earlier_image = 'plot_2026-10-07-16-12-45.png'
        image = 'plot_2026-10-07-18-12-45.png'
        self.create_files(first, second, later, companion, configuration, earlier_image, image)

        with patch('builtins.input', return_value=(
                '2026-10-07-18-00-00 - 2026-10-07-18-30-00')) as prompt:
            move_sweep()

        prompt.assert_called_once()
        directory = Path('data/ESR_sweeps') / Path(later).stem
        self.assert_moved(directory, later, companion, configuration, image)
        self.assertTrue(Path(first).is_file())
        self.assertTrue(Path(second).is_file())
        self.assertTrue(Path(earlier_image).is_file())

    def test_invalid_and_empty_manual_ranges_retry_without_moving_files(self):
        first = 'ESR_AWG_sweep_mw_duration0.25_2026-10-07-16-12-45.npy'
        second = 'ESR_AWG_sweep_mw_duration0.5_2026-10-07-16-17-45.npy'
        later = 'ESR_AWG_sweep_mw_duration1.5_2026-10-07-18-12-45.npy'
        self.create_files(first, second, later)
        choices = iter((
            '99', 'not a range',
            '2026-02-30-16-00-00 - 2026-10-07-18-30-00',
            '2026-10-07-19-00-00 - 2026-10-07-18-00-00',
            '2026-10-08-16-00-00 - 2026-10-08-18-00-00',
            '2',
        ))

        def choose(_prompt):
            self.assertTrue(Path(first).is_file())
            self.assertTrue(Path(second).is_file())
            self.assertTrue(Path(later).is_file())
            self.assertFalse(Path('data').exists())
            return next(choices)

        with patch('builtins.input', side_effect=choose) as prompt:
            move_sweep()

        self.assertEqual(prompt.call_count, 6)
        directory = Path('data/ESR_sweeps') / Path(later).stem
        self.assert_moved(directory, later)
        self.assertTrue(Path(first).is_file())

    def test_explicit_time_bounds_avoid_prompt_when_only_one_session_remains(self):
        first = 'ESR_AWG_sweep_mw_duration0.25_2026-10-07-16-12-45.npy'
        later = 'ESR_AWG_sweep_mw_duration1.5_2026-10-07-18-12-45.npy'
        self.create_files(first, later)

        move_sweep(data_after='2026-10-07-18-00-00')

        directory = Path('data/ESR_sweeps') / Path(later).stem
        self.assert_moved(directory, later)
        self.assertTrue(Path(first).is_file())

    def test_gap_exactly_five_times_previous_gap_keeps_files_together(self):
        first = 'ESR_AWG_sweep_mw_duration0.25_2026-10-07-16-00-00.npy'
        second = 'ESR_AWG_sweep_mw_duration0.5_2026-10-07-16-01-00.npy'
        last = 'ESR_AWG_sweep_mw_duration1.5_2026-10-07-16-06-00.npy'
        self.create_files(first, second, last)

        move_sweep()

        directory = Path('data/ESR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, last)

    def test_timing_check_still_applies_when_sweep_param_is_a_variable(self):
        sweep_param = "['pulse_sequence']['mw_duration']"
        first = 'ESR_AWG_sweep_mw_duration0.25_2026-10-07-16-00-00.npy'
        second = 'ESR_AWG_sweep_mw_duration0.5_2026-10-07-16-01-00.npy'
        last = 'ESR_AWG_sweep_mw_duration1.5_2026-10-07-16-03-01.npy'
        configuration = last.replace('.npy', '.yaml')
        image = last.replace('.npy', '.png')
        other_image = 'ESR_AWG_sweep_laser_duration20_2026-10-07-16-03-01.png'
        unrelated = [
            'ESR_AWG_sweep_laser_duration10_2026-10-07-16-02-00.npy',
            'ESR_AWG_sweep_laser_duration20_2026-10-07-16-03-01.npy',
        ]
        self.create_files(first, second, last, configuration, image, other_image, *unrelated)
        output = io.StringIO()

        with redirect_stdout(output), patch('builtins.input', return_value='2') as prompt:
            move_sweep(experiment_type='ESR_AWG', sweep_param=sweep_param, sweep_gap_factor=2)

        prompt.assert_called_once()
        self.assertIn('1 -> 2026-10-07-16-00-00 - 2026-10-07-16-01-00', output.getvalue())
        self.assertIn('2 -> 2026-10-07-16-03-01 - 2026-10-07-16-03-01', output.getvalue())
        directory = Path('data/ESR_sweeps') / Path(last).stem
        self.assert_moved(directory, last, configuration, image, other_image)
        for name in (first, second, *unrelated):
            self.assertTrue(Path(name).is_file(), name)

    def test_sudden_short_gap_increase_prompts_and_ignores_duplicate_timestamps(self):
        first = 'ESR_AWG_sweep_mw_duration0.25_ch-1_2026-10-07-16-00-00.npy'
        first_channel = first.replace('ch-1', 'ch-2')
        second = 'ESR_AWG_sweep_mw_duration0.5_ch-1_2026-10-07-16-01-00.npy'
        second_channel = second.replace('ch-1', 'ch-2')
        last = 'ESR_AWG_sweep_mw_duration1.5_ch-1_2026-10-07-16-06-01.npy'
        image = 'plot_2026-10-07-16-06-01.png'
        configuration = last.replace('.npy', '.yaml')
        self.create_files(first, first_channel, second, second_channel, last, image, configuration)

        with patch('builtins.input', return_value='2') as prompt:
            move_sweep()

        prompt.assert_called_once()
        directory = Path('data/ESR_sweeps') / Path(last).stem
        self.assert_moved(directory, last, image, configuration)
        for name in (first, first_channel, second, second_channel):
            self.assertTrue(Path(name).is_file(), name)

    def test_gap_three_times_previous_gap_stays_together_by_default(self):
        measurements = [
            f'CASR_sweep_freq{index}_2026-10-20-10-{minute}-00.npy'
            for index, minute in enumerate(('00', '01', '04'))
        ]
        self.create_files(*measurements)

        move_sweep()

        self.assert_moved(Path('data/CASR_sweeps') / Path(measurements[0]).stem, *measurements)

    def test_regular_channel_timestamps_do_not_cause_false_splits(self):
        measurements = [
            f'ESR_AWG_sweep_mw_duration{value}_ch-{channel}_2026-10-07-16-{minute}-00.npy'
            for value, minute in (('0.25', '00'), ('0.5', '01'), ('1.5', '02'))
            for channel in (1, 2)
        ]
        self.create_files(*measurements)

        move_sweep()

        directory = Path('data/ESR_sweeps') / Path(measurements[0]).stem
        self.assert_moved(directory, *measurements)

    def test_gap_comparison_uses_immediately_preceding_gap(self):
        measurements = [
            f'ESR_AWG_sweep_mw_duration{index}_2026-10-07-16-{minute}-00.npy'
            for index, minute in enumerate(('00', '01', '03', '06'))
        ]
        self.create_files(*measurements)

        move_sweep()

        directory = Path('data/ESR_sweeps') / Path(measurements[0]).stem
        self.assert_moved(directory, *measurements)

    def test_two_distinct_timestamps_have_no_previous_gap_to_compare(self):
        first = 'ESR_AWG_sweep_mw_duration0.25_2026-10-07-16-12-45.npy'
        later = 'ESR_AWG_sweep_mw_duration1.5_2026-10-07-18-12-45.npy'
        self.create_files(first, later)

        move_sweep()

        directory = Path('data/ESR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, later)

    def test_gap_factor_can_be_adjusted(self):
        first = 'ESR_AWG_sweep_mw_duration0.25_2026-10-07-16-00-00.npy'
        second = 'ESR_AWG_sweep_mw_duration0.5_2026-10-07-16-01-00.npy'
        last = 'ESR_AWG_sweep_mw_duration1.5_2026-10-07-16-03-01.npy'
        self.create_files(first, second, last)

        move_sweep(sweep_gap_factor=3)

        directory = Path('data/ESR_sweeps') / Path(first).stem
        self.assert_moved(directory, first, second, last)

    def test_consecutive_gap_increases_suggest_multiple_ranges(self):
        measurements = [
            f'ESR_AWG_sweep_mw_duration{index}_2026-10-07-16-{minute}-{second}.npy'
            for index, (minute, second) in enumerate((
                ('00', '00'), ('01', '00'), ('06', '01'), ('31', '07')))
        ]
        self.create_files(*measurements)
        output = io.StringIO()

        with redirect_stdout(output), patch('builtins.input', return_value='3') as prompt:
            move_sweep()

        prompt.assert_called_once()
        self.assertIn('3 -> 2026-10-07-16-31-07 - 2026-10-07-16-31-07', output.getvalue())
        directory = Path('data/ESR_sweeps') / Path(measurements[-1]).stem
        self.assert_moved(directory, measurements[-1])
        for name in measurements[:-1]:
            self.assertTrue(Path(name).is_file(), name)

    def test_invalid_gap_threshold_fails_before_any_prompt_or_file_move(self):
        first = 'ESR_AWG_sweep_mw_duration0.25_2026-10-07-16-12-45.npy'
        other = 'ESR_AWG_sweep_laser_duration10_2026-10-07-16-12-45.npy'
        self.create_files(first, other)
        for gap in (0, 1, -1, float('inf'), float('nan')):
            with self.subTest(gap=gap), self.assertRaises(ValueError):
                move_sweep(sweep_gap_factor=gap)
        self.assertTrue(Path(first).is_file())
        self.assertTrue(Path(other).is_file())
        self.assertFalse(Path('data').exists())

    def test_cli_passes_filters_to_move_functions(self):
        cli = import_module('manager.main')
        with patch.object(cli, 'move_data') as move:
            cli.main([
                'move', '--experiment-type', 'CASR_sensitivity', '--no-comments',
                '--data-after', '2026-10-07-16-00-00'])
        move.assert_called_once_with(
            include_comments=False, experiment_type='CASR_sensitivity',
            data_after='2026-10-07-16-00-00', data_before=None)

        sweep_param = "['pulse_sequence']['AWG_Ch1_freq']"
        with patch.object(cli, 'move_sweep') as move:
            cli.main([
                'movesweep', '--experiment-type', 'CASR_sensitivity',
                '--sweep-param', sweep_param,
                '--data-after', '2026-10-07-16-00-00',
                '--data-before', '2026-10-07-17-00-00'])
        move.assert_called_once_with(
            include_comments=True, experiment_type='CASR_sensitivity',
            sweep_param=sweep_param, data_after='2026-10-07-16-00-00',
            data_before='2026-10-07-17-00-00', sweep_gap_factor=5)

        with patch.object(cli, 'move_sweep') as move:
            cli.main(['movesweep', '--sweep-gap-factor', '3'])
        move.assert_called_once_with(
            include_comments=True, experiment_type=None, sweep_param=None,
            data_before=None, data_after=None, sweep_gap_factor=3)


if __name__ == '__main__':
    unittest.main()
