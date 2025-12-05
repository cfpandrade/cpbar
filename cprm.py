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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import json
import tempfile

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


# Configuration file management
CONFIG_FILE = Path.home() / ".config" / "cprm" / "config.json"

def load_config() -> dict:
    """Load configuration from config file."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_config(config: dict):
    """Save configuration to config file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def get_optimal_workers() -> int:
    """Get optimal number of workers from config, or return default."""
    config = load_config()
    return config.get('optimal_parallel_workers', 4)


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

        # Speed tracking
        self.last_bytes = 0
        self.current_speed = 0.0  # bytes per second

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

    def _format_speed(self, bytes_per_second: float) -> str:
        """Format speed to human-readable format."""
        if bytes_per_second < 1024:
            return f"{bytes_per_second:.0f}B/s"
        elif bytes_per_second < 1024 * 1024:
            return f"{bytes_per_second / 1024:.1f}KB/s"
        elif bytes_per_second < 1024 * 1024 * 1024:
            return f"{bytes_per_second / (1024 * 1024):.1f}MB/s"
        else:
            return f"{bytes_per_second / (1024 * 1024 * 1024):.1f}GB/s"

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
        return int(max(10, available))
    
    def update(self, current_file: str, bytes_delta: int = 0):
        """Update progress bar with current state."""
        self._setup()

        self.current_file = current_file
        self.completed_bytes += bytes_delta

        # Calculate speed (with smoothing)
        current_time = time.time()
        time_delta = current_time - self.last_update_time
        if time_delta > 0.1:  # Update speed every 100ms
            bytes_since_last = self.completed_bytes - self.last_bytes
            instant_speed = bytes_since_last / time_delta
            # Smooth the speed using exponential moving average
            self.current_speed = 0.7 * self.current_speed + 0.3 * instant_speed
            self.last_bytes = self.completed_bytes
            self.last_update_time = current_time
        else:
            self.last_update_time = current_time

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

        # Show elapsed time and speed
        elapsed_str = self._get_elapsed_time()
        speed_str = self._format_speed(self.current_speed) if self.current_speed > 0 else "---"
        time_display = f"{elapsed_str} @ {speed_str}"

        # Truncate filename to reasonable length and pad to fixed width
        max_filename_len = 20  # Reduced to make room for time and speed
        display_name = current_file
        if len(display_name) > max_filename_len:
            display_name = "..." + display_name[-(max_filename_len-3):]
        else:
            # Pad with spaces to maintain constant width
            display_name = display_name.ljust(max_filename_len)

        # Calculate fixed content length (icon + pct + items + size + filename + time + speed + separators)
        # Format: "📋 100.0% [BAR] 999/999 | 999.9GB/999.9GB | 5m 23s @ 999.9MB/s | filename"
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
        # Save observed speed for adaptive learning
        if self.total_bytes > 0 and self.completed_bytes > 0:
            elapsed = time.time() - self.start_time
            # Only record if operation took more than 0.1 second for accuracy
            if elapsed > 0.1:
                speed_mbps = (self.completed_bytes / (1024 * 1024)) / elapsed

                # Save to config for future estimates
                config = load_config()
                key = 'copy_speeds_mbps' if self.operation == 'cp' else 'delete_speeds_mbps'
                speeds = config.get(key, [])
                speeds.append(speed_mbps)
                # Keep only last 10 observations to prevent unbounded growth
                speeds = speeds[-10:]
                config[key] = speeds
                save_config(config)

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


def copy_file_with_progress(src: str, dst: str, progress: ProgressBar, buffer_size: int = 16*1024*1024):
    """Copy a single file with progress updates. Default buffer: 16MB for optimal performance."""
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


def copy_block(src: str, dst: str, offset: int, size: int, block_num: int, progress: ProgressBar, lock: threading.Lock):
    """Copy a specific block of a file."""
    with open(src, 'rb') as fsrc:
        fsrc.seek(offset)
        data = fsrc.read(size)

        with lock:
            with open(dst, 'r+b') as fdst:
                fdst.seek(offset)
                fdst.write(data)

        # Update progress
        progress.update(os.path.basename(src), len(data))

    return block_num


def copy_file_parallel(src: str, dst: str, progress: ProgressBar, num_workers: int = 4, block_size: int = 32*1024*1024):
    """Copy a large file using parallel block copying.

    Args:
        src: Source file path
        dst: Destination file path
        progress: ProgressBar instance for tracking
        num_workers: Number of parallel workers (default: 4)
        block_size: Size of each block in bytes (default: 32MB)
    """
    src_path = Path(src)
    dst_path = Path(dst)

    # Handle destination being a directory
    if dst_path.is_dir():
        dst_path = dst_path / src_path.name

    # Check if destination file already exists
    if dst_path.exists():
        if not progress.ask_overwrite(str(dst_path)):
            return False

    # Create parent directories if needed
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    file_size = src_path.stat().st_size

    if file_size == 0:
        # Empty file, just touch it
        dst_path.touch()
        progress.update(src_path.name, 0)
        return True

    # For small files, use regular copy
    if file_size < block_size * 2:
        return copy_file_with_progress(src, str(dst_path), progress)

    # Create destination file with correct size
    with open(dst_path, 'wb') as fdst:
        fdst.seek(file_size - 1)
        fdst.write(b'\0')

    # Calculate blocks
    blocks = []
    offset = 0
    block_num = 0
    while offset < file_size:
        current_block_size = min(block_size, file_size - offset)
        blocks.append((offset, current_block_size, block_num))
        offset += current_block_size
        block_num += 1

    # Show parallel mode info
    pb = ProgressBar(0, 0, 'cp')
    block_size_str = pb._format_size(block_size)
    print(f"{Colors.CYAN}⚡ Parallel mode: {num_workers} workers, {len(blocks)} blocks of {block_size_str}{Colors.RESET}")

    # Copy blocks in parallel
    write_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for offset, size, num in blocks:
            future = executor.submit(copy_block, src, str(dst_path), offset, size, num, progress, write_lock)
            futures.append(future)

        # Wait for all blocks to complete
        for future in as_completed(futures):
            future.result()  # This will raise any exceptions that occurred

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
    """Estimate time to copy based on learned speeds from past operations.
    Falls back to conservative defaults if no history exists.
    """
    if total_bytes == 0:
        return "< 1s"

    # Try to use learned speed from past operations
    config = load_config()
    learned_speeds = config.get('copy_speeds_mbps', [])

    if learned_speeds:
        # Use average of last observed speeds
        avg_speed_mbps = sum(learned_speeds) / len(learned_speeds)
    else:
        # Conservative default for first-time use (works for HDDs too)
        avg_speed_mbps = 100

    bytes_per_second = avg_speed_mbps * 1024 * 1024
    estimated_seconds = total_bytes / bytes_per_second

    # Use the same formatter
    pb = ProgressBar(0, 0, 'cp')
    return pb._format_time(estimated_seconds)


def do_copy(sources: List[str], destination: str, recursive: bool, dry_run: bool = False, parallel: int = 0):
    """Execute copy operation with progress bar.

    Args:
        sources: List of source file/directory paths
        destination: Destination path
        recursive: Whether to copy directories recursively
        dry_run: Preview mode without copying
        parallel: Number of parallel workers for large files (0 = disabled)
    """
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
    for src_file, file_size in all_files:
        if not any(src_file.startswith(d) for d in dirs_to_copy):
            try:
                # Use parallel mode for large files (> 64MB) if enabled
                if parallel > 0 and file_size > 64 * 1024 * 1024:
                    if copy_file_parallel(src_file, destination, progress, num_workers=parallel):
                        progress.complete_item()
                else:
                    if copy_file_with_progress(src_file, destination, progress):
                        progress.complete_item()
            except (PermissionError, OSError) as e:
                print(f"\n{Colors.YELLOW}Warning: Could not copy '{src_file}': {e}{Colors.RESET}", file=sys.stderr)

    progress.finish()


def estimate_delete_time(total_bytes: int) -> str:
    """Estimate time to delete based on learned speeds from past operations.
    Falls back to conservative defaults if no history exists.
    """
    if total_bytes == 0:
        return "< 1s"

    # Try to use learned speed from past operations
    config = load_config()
    learned_speeds = config.get('delete_speeds_mbps', [])

    if learned_speeds:
        # Use average of last observed speeds
        avg_speed_mbps = sum(learned_speeds) / len(learned_speeds)
    else:
        # Conservative default for first-time use
        # Deletions are faster than copies (200 MB/s is safe for most systems)
        avg_speed_mbps = 200

    bytes_per_second = avg_speed_mbps * 1024 * 1024
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


def run_benchmark(quiet: bool = False):
    """Run benchmark to determine optimal number of parallel workers.

    Args:
        quiet: If True, minimal output. If False, detailed output.
    """
    if not quiet:
        print(f"{Colors.BOLD}🔬 Running benchmark to determine optimal parallel workers...{Colors.RESET}\n")

    # Create a temporary test file (100MB)
    test_size = 100 * 1024 * 1024  # 100MB

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        test_file = tmpdir_path / "benchmark_test.bin"

        if not quiet:
            print(f"{Colors.CYAN}Creating 100MB test file...{Colors.RESET}")

        # Create test file with random data
        with open(test_file, 'wb') as f:
            # Write in 16MB chunks
            chunk_size = 16 * 1024 * 1024
            remaining = test_size
            while remaining > 0:
                size = min(chunk_size, remaining)
                f.write(os.urandom(size))
                remaining -= size

        # Test different worker counts
        worker_counts = [1, 2, 4, 6, 8]
        results = {}

        if not quiet:
            print(f"\n{Colors.BOLD}Testing different worker counts:{Colors.RESET}")

        for workers in worker_counts:
            dest_file = tmpdir_path / f"test_copy_{workers}.bin"

            # Run 3 trials and take the average
            times = []
            for _ in range(3):
                if dest_file.exists():
                    dest_file.unlink()

                start = time.time()

                # Suppress output during benchmark
                if workers == 1:
                    # Use normal copy for baseline
                    shutil.copy2(test_file, dest_file)
                else:
                    # Use parallel copy (we need to bypass the progress bar for accurate timing)
                    src_stat = test_file.stat()
                    with open(dest_file, 'wb') as fdst:
                        fdst.seek(src_stat.st_size - 1)
                        fdst.write(b'\0')

                    block_size = 32 * 1024 * 1024  # 32MB blocks
                    blocks = []
                    offset = 0
                    block_num = 0
                    file_size = src_stat.st_size

                    while offset < file_size:
                        current_block_size = min(block_size, file_size - offset)
                        blocks.append((offset, current_block_size, block_num))
                        offset += current_block_size
                        block_num += 1

                    # Copy blocks in parallel (without progress tracking)
                    write_lock = threading.Lock()
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        futures = []
                        for offset, size, _ in blocks:
                            future = executor.submit(
                                _benchmark_copy_block,
                                str(test_file), str(dest_file), offset, size, write_lock
                            )
                            futures.append(future)

                        for future in as_completed(futures):
                            future.result()

                    shutil.copystat(test_file, dest_file)

                elapsed = time.time() - start
                times.append(elapsed)

            avg_time = sum(times) / len(times)
            results[workers] = avg_time

            if not quiet:
                speed_mbps = (test_size / (1024 * 1024)) / avg_time
                print(f"  {workers:2d} workers: {avg_time:.3f}s  ({speed_mbps:.1f} MB/s)")

        # Find optimal worker count (worker count with minimum time)
        optimal_workers = min(results.keys(), key=lambda k: results[k])

        # Save to config
        config = load_config()
        config['optimal_parallel_workers'] = optimal_workers
        config['benchmark_date'] = time.strftime('%Y-%m-%d %H:%M:%S')
        config['benchmark_results'] = {str(k): f"{v:.3f}s" for k, v in results.items()}
        save_config(config)

        if not quiet:
            print(f"\n{Colors.GREEN}✓ Optimal configuration: {optimal_workers} workers{Colors.RESET}")
            print(f"{Colors.DIM}Configuration saved to: {CONFIG_FILE}{Colors.RESET}\n")
        else:
            print(f"{Colors.GREEN}✓ Optimal: {optimal_workers} workers (saved to config){Colors.RESET}")

    return optimal_workers


def _benchmark_copy_block(src: str, dst: str, offset: int, size: int, lock: threading.Lock):
    """Copy a block for benchmarking (without progress tracking)."""
    with open(src, 'rb') as fsrc:
        fsrc.seek(offset)
        data = fsrc.read(size)

        with lock:
            with open(dst, 'r+b') as fdst:
                fdst.seek(offset)
                fdst.write(data)


def main():
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