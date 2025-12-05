#!/usr/bin/env python3
"""
cprm - Enhanced cp/rm with unified progress bar
Usage:
    cprm cp <source>... <destination>
    cprm rm <files>...
    cprm cp -r <source>... <destination>
    cprm rm -r <directories>...
"""

import os
import sys
import shutil
import argparse
import time
import select
from pathlib import Path
from typing import List, Tuple
import signal

# ANSI escape codes for styling
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    DIM = "\033[2m"

# ANSI escape codes for cursor/screen control
class Cursor:
    SAVE = "\033[s"
    RESTORE = "\033[u"
    HIDE = "\033[?25l"
    SHOW = "\033[?25h"
    
    @staticmethod
    def move_to(row: int, col: int = 1) -> str:
        return f"\033[{row};{col}H"
    
    @staticmethod
    def move_to_bottom() -> str:
        """Move cursor to last line of terminal."""
        rows = shutil.get_terminal_size().lines
        return f"\033[{rows};1H"


class ProgressBar:
    """A single progress bar that tracks total progress across all files.
    Always displays at the bottom of the terminal and adapts to terminal width.
    """

    def __init__(self, total_items: int, total_bytes: int, operation: str):
        self.total_items = total_items
        self.total_bytes = total_bytes
        self.completed_items = 0
        self.completed_bytes = 0
        self.operation = operation
        self.current_file = ""
        self.interrupted = False
        self.started = False
        self.overwrite_all = False  # Track if user chose "overwrite all"
        self.skipped_items = 0

        # Time estimation
        self.start_time = time.time()
        self.last_update_time = self.start_time

        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGWINCH, self._resize_handler)
    
    def _signal_handler(self, signum, frame):
        self.interrupted = True
        self._cleanup()
        print(f"\n{Colors.YELLOW}⚠ Operation cancelled by user{Colors.RESET}")
        sys.exit(130)
    
    def _resize_handler(self, signum, frame):
        """Handle terminal resize."""
        self.update(self.current_file, 0)
    
    def _get_terminal_size(self) -> Tuple[int, int]:
        """Get terminal dimensions (columns, lines)."""
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    
    def _setup(self):
        """Setup the progress bar display area."""
        if self.started:
            return
        self.started = True
        # Hide cursor and save position
        sys.stdout.write(Cursor.HIDE)
        # Add a blank line at the bottom for the progress bar
        sys.stdout.write("\n")
        sys.stdout.flush()
    
    def _cleanup(self):
        """Restore terminal state."""
        # Show cursor
        sys.stdout.write(Cursor.SHOW)
        sys.stdout.flush()

    def ask_overwrite(self, filepath: str) -> bool:
        """Ask user if they want to overwrite a file.
        Returns True if file should be overwritten, False to skip.
        Can also set self.overwrite_all if user chooses 'all'.
        """
        if self.overwrite_all:
            return True

        _, rows = self._get_terminal_size()

        # Move to the line just above the progress bar and clear it
        sys.stdout.write(Cursor.move_to(rows - 1, 1))
        sys.stdout.write("\033[2K")  # Clear entire line
        sys.stdout.flush()

        # Show cursor for input
        sys.stdout.write(Cursor.SHOW)

        while True:
            # Move to the same line each time
            sys.stdout.write(Cursor.move_to(rows - 1, 1))
            sys.stdout.write("\033[2K")  # Clear line
            sys.stdout.flush()

            # Use sys.stdout.write + input to control positioning
            sys.stdout.write(f"{Colors.YELLOW}Overwrite '{filepath}'? [y/n/a/q]: {Colors.RESET}")
            sys.stdout.flush()
            response = input().strip().lower()

            if response in ['y', 'yes']:
                # Clear the prompt line
                sys.stdout.write(Cursor.move_to(rows - 1, 1))
                sys.stdout.write("\033[2K")
                sys.stdout.flush()
                # Hide cursor again
                sys.stdout.write(Cursor.HIDE)
                return True
            elif response in ['n', 'no']:
                self.skipped_items += 1
                # Clear the prompt line
                sys.stdout.write(Cursor.move_to(rows - 1, 1))
                sys.stdout.write("\033[2K")
                sys.stdout.flush()
                # Hide cursor again
                sys.stdout.write(Cursor.HIDE)
                return False
            elif response in ['a', 'all']:
                self.overwrite_all = True
                # Clear the prompt line
                sys.stdout.write(Cursor.move_to(rows - 1, 1))
                sys.stdout.write("\033[2K")
                sys.stdout.flush()
                # Hide cursor again
                sys.stdout.write(Cursor.HIDE)
                return True
            elif response in ['q', 'quit']:
                self._cleanup()
                print(f"\n{Colors.YELLOW}⚠ Operation cancelled by user{Colors.RESET}")
                sys.exit(0)
            else:
                # Show error on the same line
                sys.stdout.write(Cursor.move_to(rows - 1, 1))
                sys.stdout.write("\033[2K")
                sys.stdout.write(f"{Colors.RED}Invalid option. Use: y (yes), n (no), a (all), q (quit){Colors.RESET}")
                sys.stdout.flush()
                time.sleep(1.5)  # Show error briefly before re-prompting
    
    def _clear_line(self):
        """Clear the current line."""
        cols, _ = self._get_terminal_size()
        sys.stdout.write("\r" + " " * cols + "\r")
        sys.stdout.flush()
    
    def _format_size(self, size: int) -> str:
        """Format bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}PB"

    def _format_time(self, seconds: float) -> str:
        """Format seconds to human-readable time."""
        if seconds < 0:
            return "calculating..."
        elif seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}h {mins}m"

    def _get_elapsed_time(self) -> str:
        """Get elapsed time since operation started."""
        elapsed = time.time() - self.start_time
        return self._format_time(elapsed)
    
    def _calculate_bar_width(self, other_content_len: int) -> int:
        """Calculate available width for the progress bar.
        Uses all remaining terminal width after other content.
        """
        cols, _ = self._get_terminal_size()
        # Calculate remaining space for bar (subtract other content + brackets + padding)
        available = cols - other_content_len - 5
        # Minimum bar width of 10, no maximum - use all available space
        return max(10, available)
    
    def update(self, current_file: str, bytes_delta: int = 0):
        """Update progress bar with current state."""
        self._setup()

        self.current_file = current_file
        self.completed_bytes += bytes_delta
        self.last_update_time = time.time()

        cols, rows = self._get_terminal_size()

        # Calculate progress
        if self.total_bytes > 0:
            progress = min(self.completed_bytes / self.total_bytes, 1.0)
        else:
            progress = self.completed_items / self.total_items if self.total_items > 0 else 1.0

        # Build components
        op_icon = "📋" if self.operation == "cp" else "🗑️ "
        pct = f"{progress * 100:5.1f}%"
        items_str = f"{self.completed_items}/{self.total_items}"
        size_str = f"{self._format_size(self.completed_bytes)}/{self._format_size(self.total_bytes)}"

        # Show elapsed time
        elapsed_str = self._get_elapsed_time()
        time_display = f"{elapsed_str}"

        # Truncate filename to reasonable length and pad to fixed width
        max_filename_len = 20  # Reduced to make room for time
        display_name = current_file
        if len(display_name) > max_filename_len:
            display_name = "..." + display_name[-(max_filename_len-3):]
        else:
            # Pad with spaces to maintain constant width
            display_name = display_name.ljust(max_filename_len)

        # Calculate fixed content length (icon + pct + items + size + filename + time + separators)
        # Format: "📋 100.0% [BAR] 999/999 | 999.9GB/999.9GB | 5m 23s | filename"
        fixed_len = 2 + 1 + 6 + 1 + 2 + 1 + len(items_str) + 3 + len(size_str) + 3 + len(time_display) + 3 + max_filename_len

        # Calculate bar width to fill remaining space
        bar_width = self._calculate_bar_width(fixed_len)

        filled = int(bar_width * progress)
        empty = bar_width - filled
        bar = f"{Colors.GREEN}{'█' * filled}{Colors.DIM}{'░' * empty}{Colors.RESET}"

        # Build the line
        line = f"{op_icon} {Colors.BOLD}{pct}{Colors.RESET} [{bar}] {items_str} | {size_str} | {Colors.DIM}{time_display}{Colors.RESET} | {Colors.CYAN}{display_name}{Colors.RESET}"

        # Move to bottom, clear line, print
        sys.stdout.write(Cursor.move_to_bottom())
        sys.stdout.write("\033[2K")  # Clear entire line
        sys.stdout.write(line)
        sys.stdout.write(Cursor.move_to(rows - 1, 1))  # Move back up one line
        sys.stdout.flush()
    
    def complete_item(self):
        """Mark one item as complete."""
        self.completed_items += 1
    
    def finish(self):
        """Finish progress bar and print summary."""
        cols, rows = self._get_terminal_size()

        # Clear the progress bar line
        sys.stdout.write(Cursor.move_to_bottom())
        sys.stdout.write("\033[2K")

        # Print summary
        op_name = "Copied" if self.operation == "cp" else "Deleted"
        icon = "✅" if self.operation == "cp" else "🗑️ "
        summary = f"{icon} {Colors.GREEN}{op_name}: {self.completed_items} files ({self._format_size(self.completed_bytes)}){Colors.RESET}"

        if self.skipped_items > 0:
            summary += f" {Colors.YELLOW}(Skipped: {self.skipped_items}){Colors.RESET}"

        sys.stdout.write(summary)
        # Don't add extra newline - the shell prompt will handle spacing

        self._cleanup()


def get_all_files(paths: List[str], recursive: bool) -> List[Tuple[str, int]]:
    """
    Get all files from given paths with their sizes.
    Returns list of tuples (filepath, size).
    """
    files = []
    
    for path in paths:
        p = Path(path)
        if not p.exists():
            print(f"{Colors.RED}Error: '{path}' does not exist{Colors.RESET}", file=sys.stderr)
            continue
            
        if p.is_file():
            try:
                files.append((str(p), p.stat().st_size))
            except (PermissionError, OSError) as e:
                print(f"{Colors.YELLOW}Warning: Cannot access '{path}': {e}{Colors.RESET}", file=sys.stderr)
        elif p.is_dir():
            if recursive:
                for root, dirs, filenames in os.walk(str(p)):
                    for filename in filenames:
                        filepath = os.path.join(root, filename)
                        try:
                            files.append((filepath, os.path.getsize(filepath)))
                        except (PermissionError, OSError):
                            files.append((filepath, 0))
            else:
                print(f"{Colors.RED}Error: '{path}' is a directory. Use -r for recursive{Colors.RESET}", file=sys.stderr)
    
    return files


def copy_file_with_progress(src: str, dst: str, progress: ProgressBar, buffer_size: int = 1024*1024):
    """Copy a single file with progress updates."""
    src_path = Path(src)
    dst_path = Path(dst)

    # Handle destination being a directory
    if dst_path.is_dir():
        dst_path = dst_path / src_path.name

    # Check if destination file already exists
    if dst_path.exists():
        if not progress.ask_overwrite(str(dst_path)):
            # User chose not to overwrite, skip this file
            return False

    # Create parent directories if needed
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    file_size = src_path.stat().st_size

    if file_size == 0:
        # Empty file, just touch it
        dst_path.touch()
        progress.update(src_path.name, 0)
        return True

    with open(src, 'rb') as fsrc:
        with open(dst_path, 'wb') as fdst:
            copied = 0
            while True:
                buf = fsrc.read(buffer_size)
                if not buf:
                    break
                fdst.write(buf)
                copied += len(buf)
                progress.update(src_path.name, len(buf))

    # Preserve metadata
    shutil.copystat(src, dst_path)
    return True


def copy_directory_with_progress(src: str, dst: str, progress: ProgressBar):
    """Recursively copy a directory with progress updates."""
    src_path = Path(src)
    dst_path = Path(dst)
    
    # If dst is an existing directory, copy into it
    if dst_path.exists() and dst_path.is_dir():
        dst_path = dst_path / src_path.name
    
    dst_path.mkdir(parents=True, exist_ok=True)
    
    for root, dirs, files in os.walk(src):
        # Create directories
        rel_root = os.path.relpath(root, src)
        if rel_root != '.':
            (dst_path / rel_root).mkdir(parents=True, exist_ok=True)
        
        # Copy files
        for filename in files:
            src_file = os.path.join(root, filename)
            if rel_root == '.':
                dst_file = dst_path / filename
            else:
                dst_file = dst_path / rel_root / filename
            
            try:
                if copy_file_with_progress(src_file, str(dst_file), progress):
                    progress.complete_item()
            except (PermissionError, OSError) as e:
                print(f"\n{Colors.YELLOW}Warning: Could not copy '{src_file}': {e}{Colors.RESET}", file=sys.stderr)


def estimate_copy_time(total_bytes: int) -> str:
    """Estimate time to copy based on average disk speed.
    Assumes ~100 MB/s for typical SSD operations.
    """
    if total_bytes == 0:
        return "< 1s"

    # Conservative estimate: 80 MB/s (to account for overhead)
    MB_PER_SECOND = 80
    bytes_per_second = MB_PER_SECOND * 1024 * 1024
    estimated_seconds = total_bytes / bytes_per_second

    # Use the same formatter
    pb = ProgressBar(0, 0, 'cp')
    return pb._format_time(estimated_seconds)


def do_copy(sources: List[str], destination: str, recursive: bool, dry_run: bool = False):
    """Execute copy operation with progress bar."""
    # Validate inputs
    if not sources:
        print(f"{Colors.RED}Error: No source files specified{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    dst_path = Path(destination)

    # If multiple sources, destination must be a directory
    if len(sources) > 1 and not dst_path.is_dir():
        if not dst_path.exists():
            if not dry_run:
                dst_path.mkdir(parents=True)
        else:
            print(f"{Colors.RED}Error: Destination must be a directory for multiple sources{Colors.RESET}", file=sys.stderr)
            sys.exit(1)

    # Collect all files to copy
    all_files = []
    dirs_to_copy = []

    for src in sources:
        src_path = Path(src)
        if not src_path.exists():
            print(f"{Colors.RED}Error: '{src}' does not exist{Colors.RESET}", file=sys.stderr)
            continue

        if src_path.is_file():
            all_files.append((str(src_path), src_path.stat().st_size))
        elif src_path.is_dir():
            if recursive:
                dirs_to_copy.append(str(src_path))
                # Count all files in directory
                for root, _, files in os.walk(str(src_path)):
                    for filename in files:
                        filepath = os.path.join(root, filename)
                        try:
                            all_files.append((filepath, os.path.getsize(filepath)))
                        except (PermissionError, OSError):
                            all_files.append((filepath, 0))
            else:
                print(f"{Colors.RED}Error: '{src}' is a directory. Use -r to copy recursively{Colors.RESET}", file=sys.stderr)

    if not all_files and not dirs_to_copy:
        print(f"{Colors.RED}Error: No files to copy{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    total_bytes = sum(size for _, size in all_files)
    total_items = len(all_files)

    # Dry-run mode: just show what would be copied
    if dry_run:
        pb = ProgressBar(0, 0, 'cp')
        size_str = pb._format_size(total_bytes)
        estimated_time = estimate_copy_time(total_bytes)

        print(f"{Colors.CYAN}🔍 Dry-run mode - No files will be copied{Colors.RESET}\n")
        print(f"{Colors.BOLD}Summary:{Colors.RESET}")
        print(f"  Files to copy: {Colors.GREEN}{total_items}{Colors.RESET}")
        print(f"  Total size: {Colors.GREEN}{size_str}{Colors.RESET}")
        print(f"  Estimated time: {Colors.YELLOW}~{estimated_time}{Colors.RESET}")
        print(f"  Destination: {Colors.BLUE}{destination}{Colors.RESET}\n")

        # Show first 10 files as preview
        print(f"{Colors.BOLD}Files (showing first 10):{Colors.RESET}")
        for filepath, size in all_files[:10]:
            rel_path = os.path.relpath(filepath)
            print(f"  {Colors.DIM}→{Colors.RESET} {rel_path} {Colors.DIM}({pb._format_size(size)}){Colors.RESET}")

        if len(all_files) > 10:
            print(f"  {Colors.DIM}... and {len(all_files) - 10} more files{Colors.RESET}")

        return

    print(f"{Colors.BLUE}Copying {total_items} files ({ProgressBar(0, 0, 'cp')._format_size(total_bytes)})...{Colors.RESET}")

    progress = ProgressBar(total_items, total_bytes, "cp")

    # Copy directories
    for src_dir in dirs_to_copy:
        copy_directory_with_progress(src_dir, destination, progress)

    # Copy individual files
    for src_file, _ in all_files:
        if not any(src_file.startswith(d) for d in dirs_to_copy):
            try:
                if copy_file_with_progress(src_file, destination, progress):
                    progress.complete_item()
            except (PermissionError, OSError) as e:
                print(f"\n{Colors.YELLOW}Warning: Could not copy '{src_file}': {e}{Colors.RESET}", file=sys.stderr)

    progress.finish()


def estimate_delete_time(total_bytes: int) -> str:
    """Estimate time to delete files based on filesystem operations.
    Deletion is typically faster than copying, but depends on filesystem.
    """
    if total_bytes == 0:
        return "< 1s"

    # Conservative estimate: ~200 MB/s for deletions on SSD
    MB_PER_SECOND = 200
    bytes_per_second = MB_PER_SECOND * 1024 * 1024
    estimated_seconds = total_bytes / bytes_per_second

    # Use the same formatter
    pb = ProgressBar(0, 0, 'rm')
    return pb._format_time(estimated_seconds)


def do_remove(targets: List[str], recursive: bool, force: bool, dry_run: bool = False):
    """Execute remove operation with progress bar."""
    if not targets:
        print(f"{Colors.RED}Error: No files specified for deletion{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    # Collect all files to remove
    all_files = get_all_files(targets, recursive)
    dirs_to_remove = []

    # Also collect directories if recursive
    if recursive:
        for target in targets:
            p = Path(target)
            if p.is_dir():
                dirs_to_remove.append(str(p))

    if not all_files and not dirs_to_remove:
        print(f"{Colors.RED}Error: No files to delete{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    total_bytes = sum(size for _, size in all_files)
    total_items = len(all_files)

    # Dry-run mode: just show what would be deleted
    if dry_run:
        pb = ProgressBar(0, 0, 'rm')
        size_str = pb._format_size(total_bytes)
        estimated_time = estimate_delete_time(total_bytes)

        print(f"{Colors.CYAN}🔍 Dry-run mode - No files will be deleted{Colors.RESET}\n")
        print(f"{Colors.BOLD}Summary:{Colors.RESET}")
        print(f"  Files to delete: {Colors.RED}{total_items}{Colors.RESET}")
        print(f"  Total size: {Colors.RED}{size_str}{Colors.RESET}")
        print(f"  Estimated time: {Colors.YELLOW}~{estimated_time}{Colors.RESET}\n")

        # Show first 10 files as preview
        print(f"{Colors.BOLD}Files (showing first 10):{Colors.RESET}")
        for filepath, size in all_files[:10]:
            rel_path = os.path.relpath(filepath)
            print(f"  {Colors.DIM}→{Colors.RESET} {rel_path} {Colors.DIM}({pb._format_size(size)}){Colors.RESET}")

        if len(all_files) > 10:
            print(f"  {Colors.DIM}... and {len(all_files) - 10} more files{Colors.RESET}")

        if dirs_to_remove:
            print(f"\n{Colors.BOLD}Directories:{Colors.RESET}")
            for dir_path in dirs_to_remove:
                rel_path = os.path.relpath(dir_path)
                print(f"  {Colors.DIM}→{Colors.RESET} {rel_path}/")

        return

    # Confirmation prompt with countdown (unless force)
    if not force:
        print(f"{Colors.YELLOW}Will delete {total_items} files ({ProgressBar(0, 0, 'rm')._format_size(total_bytes)}){Colors.RESET}")

        # 3-second countdown before allowing confirmation
        for i in range(3, 0, -1):
            sys.stdout.write(f"\r{Colors.DIM}Wait {i}s before confirming...{Colors.RESET}  ")
            sys.stdout.flush()
            time.sleep(1)

        sys.stdout.write("\r" + " " * 40 + "\r")  # Clear countdown line
        sys.stdout.flush()

        confirm = input(f"{Colors.BOLD}Continue? [y/N]: {Colors.RESET}").strip().lower()
        if confirm not in ['y', 'yes']:
            print(f"{Colors.DIM}Operation cancelled{Colors.RESET}")
            sys.exit(0)

    print(f"{Colors.BLUE}Deleting {total_items} files...{Colors.RESET}")

    progress = ProgressBar(total_items, total_bytes, "rm")

    # Remove files first
    for filepath, size in all_files:
        try:
            progress.update(os.path.basename(filepath), size)
            os.remove(filepath)
            progress.complete_item()
        except (PermissionError, OSError) as e:
            print(f"\n{Colors.YELLOW}Warning: Could not delete '{filepath}': {e}{Colors.RESET}", file=sys.stderr)

    # Remove directories (in reverse order to handle nested dirs)
    if recursive:
        for target in targets:
            p = Path(target)
            if p.is_dir():
                try:
                    shutil.rmtree(target)
                except (PermissionError, OSError) as e:
                    print(f"\n{Colors.YELLOW}Warning: Could not delete directory '{target}': {e}{Colors.RESET}", file=sys.stderr)

    progress.finish()


def main():
    parser = argparse.ArgumentParser(
        description="Enhanced cp/rm with unified progress bar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cprm cp file.txt /destination/
  cprm cp -r folder/ /destination/
  cprm cp *.jpg /photos/
  cprm rm file.txt
  cprm rm -r folder/
  cprm rm -rf folder/  # No confirmation
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Copy subcommand
    cp_parser = subparsers.add_parser('cp', help='Copy files')
    cp_parser.add_argument('-r', '-R', '--recursive', action='store_true',
                          help='Copy directories recursively')
    cp_parser.add_argument('-n', '--dry-run', action='store_true',
                          help='Show what would be copied without actually copying')
    cp_parser.add_argument('sources', nargs='+', help='Source files/directories')
    cp_parser.add_argument('destination', help='Destination')
    
    # Remove subcommand
    rm_parser = subparsers.add_parser('rm', help='Remove files')
    rm_parser.add_argument('-r', '-R', '--recursive', action='store_true',
                          help='Remove directories recursively')
    rm_parser.add_argument('-f', '--force', action='store_true',
                          help='Do not ask for confirmation')
    rm_parser.add_argument('-n', '--dry-run', action='store_true',
                          help='Show what would be deleted without actually deleting')
    rm_parser.add_argument('targets', nargs='+', help='Files/directories to remove')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'cp':
        # Last argument is destination, rest are sources
        if len(args.sources) < 1:
            print(f"{Colors.RED}Error: At least one source file and a destination required{Colors.RESET}", file=sys.stderr)
            sys.exit(1)
        do_copy(args.sources, args.destination, args.recursive, args.dry_run)

    elif args.command == 'rm':
        do_remove(args.targets, args.recursive, args.force, args.dry_run)


if __name__ == '__main__':
    main()
