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
    return parser


def main(argv=None):
    """Match through argparse arguments to determine course of action"""
    parser = _build_parser()
    args = parser.parse_args(argv)

    match args.action:
        case 'new':
            new()
        case 'move':
            move_data(include_comments=not args.no_comments)
        case 'movesweep':
            move_sweep(include_comments=not args.no_comments)
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
