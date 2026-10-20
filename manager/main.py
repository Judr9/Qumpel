import argparse
from manager.new_folder_setup import new
from manager.move_files import move_data, move_sweep
from manager.meta_data import new_metadata_package, update_metadata


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Handle measurement folder and live lab logs'
    )
    parser.add_argument(
        'action',
        help='choose wether to init a new folder, or to move data',
        choices=['new', 'move', 'movesweep', 'new_meta', 'update_meta'],
    )
    parser.add_argument(
        '--no-comments',
        action='store_true',
        help='skip interactive comment prompt when writing lab logs',
    )
    parser.add_argument(
        '--experiment-type',
        help='only move measurement filenames starting with this prefix',
    )
    parser.add_argument(
        '--sweep-param',
        help='only move sweep filenames containing this parameter or the final '
             'key of a bracket expression (movesweep only)',
    )
    parser.add_argument(
        '--data-before',
        help='only move files with timestamps at or before YYYY-MM-DD-HH-MM-SS',
    )
    parser.add_argument(
        '--data-after',
        help='only move files with timestamps at or after YYYY-MM-DD-HH-MM-SS',
    )
    parser.add_argument(
        '--sweep-gap-factor',
        type=float,
        help='suggest separate sweep time ranges when a timestamp gap exceeds '
             'this factor times the preceding gap (default: 5; movesweep only)',
    )
    return parser


def main(argv=None):
    """Match through argparse arguments to determine course of action"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.experiment_type is not None and args.action not in ('move', 'movesweep'):
        parser.error('--experiment-type is only supported for move and movesweep')
    if args.sweep_param is not None and args.action != 'movesweep':
        parser.error('--sweep-param is only supported for movesweep')
    if args.sweep_gap_factor is not None and args.action != 'movesweep':
        parser.error('--sweep-gap-factor is only supported for movesweep')
    if ((args.data_before is not None or args.data_after is not None)
            and args.action not in ('move', 'movesweep')):
        parser.error('--data-before and --data-after are only supported for move and movesweep')

    match args.action:
        case 'new':
            new()
        case 'move':
            move_data(
                include_comments=not args.no_comments,
                experiment_type=args.experiment_type,
                data_before=args.data_before,
                data_after=args.data_after)
        case 'movesweep':
            move_sweep(
                include_comments=not args.no_comments,
                experiment_type=args.experiment_type,
                sweep_param=args.sweep_param,
                data_before=args.data_before,
                data_after=args.data_after,
                sweep_gap_factor=(args.sweep_gap_factor
                                  if args.sweep_gap_factor is not None else 5))
        case 'new_meta':
            new_metadata_package()
        case 'update_meta':
            update_metadata()
        case _:
            print('invalid option')


if __name__ == '__main__':
    main()


def entry():
    from manager.main import main
    main()
