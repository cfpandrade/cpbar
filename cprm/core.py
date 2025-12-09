"""
Core functionality and CLI for cprm.
Handles command-line argument parsing and dispatches to appropriate operations.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import sys
import argparse

from .operations import do_copy, do_remove
from .benchmark import run_benchmark
from .utils import get_optimal_workers
from .ui import Colors


def main():
    """Main entry point for cprm CLI."""
    parser = argparse.ArgumentParser(
        description="Enhanced cp/rm with unified progress bar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cprm cp file.txt /destination/
  cprm cp -r folder/ /destination/
  cprm cp *.jpg /photos/
  cprm cp -P large_file.iso /backup/        # Parallel copy with 4 workers
  cprm cp --parallel=8 large_file.iso /backup/  # Parallel with 8 workers
  cprm rm file.txt
  cprm rm -r folder/
  cprm rm -rf folder/  # No confirmation

Author:
  Carlos Andrade <carlos@perezandrade.com>
  https://github.com/cfpandrade/cpbar
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Copy subcommand
    cp_parser = subparsers.add_parser('cp', help='Copy files with progress bar',
                                     description='Copy files and directories with a unified progress bar, speed tracking, and optional parallel mode for large files.',
                                     epilog="""
Examples:
  cp file.txt /destination/              # Copy single file
  cp -r folder/ /destination/            # Copy directory recursively
  cp -n large_folder/ /backup/           # Dry-run: preview before copying
  cp --parallel=4 large.iso /backup/     # Fast parallel copy (4 workers)
  cp --parallel=8 *.mkv /backup/         # Parallel copy multiple large files (8 workers)

Performance tips:
  • Use --parallel for files > 64MB on SSDs (2-4x faster)
  • Optimal workers: 4-8 for most systems
  • Shows real-time speed (MB/s) during transfer
  • 16MB buffer for efficient operations

Author:
  Carlos Andrade <carlos@perezandrade.com>
  https://github.com/cfpandrade/cpbar
                                     """,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    cp_parser.add_argument('-r', '-R', '--recursive', action='store_true',
                          help='copy directories recursively')
    cp_parser.add_argument('-n', '--dry-run', action='store_true',
                          help='preview what would be copied without actually copying (shows file count, size, and estimated time)')

    # Get optimal workers from config for help text
    optimal = get_optimal_workers()
    cp_parser.add_argument('-P', '--parallel', type=int, nargs='?', const=optimal, default=0, metavar='WORKERS',
                          help=f'use parallel mode for large files (default: {optimal} workers from benchmark). Optimal: 4-8 for SSDs. Activates automatically for files > 64MB. Run "cprm benchmark" to detect optimal value.')
    cp_parser.add_argument('sources', nargs='+', help='source files or directories to copy')
    cp_parser.add_argument('destination', help='destination path')

    # Benchmark subcommand
    benchmark_parser = subparsers.add_parser('benchmark', help='Run benchmark to detect optimal parallel workers',
                                            description='Tests different worker counts to determine the optimal configuration for your system.',
                                            epilog="""
Examples:
  cprm benchmark              # Run full benchmark with detailed output
  cprm benchmark --quiet      # Run benchmark with minimal output

The benchmark will:
  • Create a temporary 100MB test file
  • Test with 1, 2, 4, 6, and 8 workers
  • Run 3 trials for each configuration
  • Save the optimal setting to ~/.config/cprm/config.json
  • This setting becomes the default when using -P flag

Author:
  Carlos Andrade <carlos@perezandrade.com>
  https://github.com/cfpandrade/cpbar
                                            """,
                                            formatter_class=argparse.RawDescriptionHelpFormatter)
    benchmark_parser.add_argument('-q', '--quiet', action='store_true',
                                 help='minimal output, only show final result')

    # Remove subcommand
    rm_parser = subparsers.add_parser('rm', help='Remove files with progress bar',
                                     description='Remove files and directories with a unified progress bar, speed tracking, and safety confirmations.',
                                     epilog="""
Examples:
  rm file.txt                    # Remove file (asks for confirmation with 3s countdown)
  rm -r folder/                  # Remove directory recursively
  rm -rf temp/                   # Force remove without confirmation
  rm -n old_files/               # Dry-run: preview what would be deleted

Safety features:
  • 3-second countdown before confirmation prompt
  • Shows total files and size before deletion
  • Dry-run mode to preview operations
  • Force mode (-f) to skip confirmation

Author:
  Carlos Andrade <carlos@perezandrade.com>
  https://github.com/cfpandrade/cpbar
                                     """,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    rm_parser.add_argument('-r', '-R', '--recursive', action='store_true',
                          help='remove directories and their contents recursively')
    rm_parser.add_argument('-f', '--force', action='store_true',
                          help='force removal without confirmation (skips 3s countdown)')
    rm_parser.add_argument('-n', '--dry-run', action='store_true',
                          help='preview what would be deleted without actually deleting (shows file count, size, and estimated time)')
    rm_parser.add_argument('targets', nargs='+', help='files or directories to remove')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == 'cp':
        # Last argument is destination, rest are sources
        if len(args.sources) < 1:
            print(f"{Colors.RED}Error: At least one source file and a destination required{Colors.RESET}", file=sys.stderr)
            sys.exit(1)
        do_copy(args.sources, args.destination, args.recursive, args.dry_run, args.parallel)

    elif args.command == 'rm':
        do_remove(args.targets, args.recursive, args.force, args.dry_run)

    elif args.command == 'benchmark':
        run_benchmark(quiet=args.quiet)


if __name__ == '__main__':
    main()
