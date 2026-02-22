"""
UI components for cpbar.
Handles progress bar, colors, and cursor control.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import sys
import shutil
import signal
import time
import threading
from typing import Tuple

from .utils import (
    format_size, format_time, format_speed,
    load_config, save_config,
    SPEED_UPDATE_INTERVAL, SPEED_SMOOTHING_FACTOR
)


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

        # Speed tracking
        self.last_bytes = 0
        self.current_speed = 0.0  # bytes per second

        # Thread safety lock for concurrent updates
        self._lock = threading.Lock()

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

    def _get_elapsed_time(self) -> str:
        """Get elapsed time since operation started."""
        elapsed = time.time() - self.start_time
        return format_time(elapsed)

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
        """Update progress bar with current state (thread-safe)."""
        self._setup()

        with self._lock:
            self.current_file = current_file
            self.completed_bytes += bytes_delta

            # Calculate speed (with smoothing)
            current_time = time.time()
            time_delta = current_time - self.last_update_time

            # Reset speed if there was a long pause (e.g., waiting for user input)
            if time_delta > 2.0:
                self.current_speed = 0.0
                self.last_bytes = self.completed_bytes
                self.last_update_time = current_time
            elif time_delta > SPEED_UPDATE_INTERVAL:  # Update speed every 100ms
                bytes_since_last = self.completed_bytes - self.last_bytes
                instant_speed = bytes_since_last / time_delta
                # Smooth the speed using exponential moving average
                self.current_speed = SPEED_SMOOTHING_FACTOR * self.current_speed + (1 - SPEED_SMOOTHING_FACTOR) * instant_speed
                self.last_bytes = self.completed_bytes
                self.last_update_time = current_time
            else:
                self.last_update_time = current_time

            # Capture values for rendering outside lock
            progress_data = {
                'completed_bytes': self.completed_bytes,
                'completed_items': self.completed_items,
                'total_bytes': self.total_bytes,
                'total_items': self.total_items,
                'current_speed': self.current_speed,
                'current_file': self.current_file,
            }

        cols, rows = self._get_terminal_size()

        # Calculate progress using captured data
        completed_bytes = progress_data['completed_bytes']
        completed_items = progress_data['completed_items']
        total_bytes = progress_data['total_bytes']
        total_items = progress_data['total_items']
        current_speed = progress_data['current_speed']
        display_file = progress_data['current_file']

        if total_bytes > 0:
            progress = min(completed_bytes / total_bytes, 1.0)
        else:
            progress = completed_items / total_items if total_items > 0 else 1.0

        # Build components
        op_icon = "📋" if self.operation == "cp" else "🗑️ "
        pct = f"{progress * 100:5.1f}%"
        items_str = f"{completed_items}/{total_items}"
        size_str = f"{format_size(completed_bytes)}/{format_size(total_bytes)}"

        # Show elapsed time and speed
        elapsed_str = self._get_elapsed_time()
        speed_str = format_speed(current_speed) if current_speed > 0 else "---"
        time_display = f"{elapsed_str} @ {speed_str}"

        # Truncate filename to reasonable length and pad to fixed width
        max_filename_len = 20  # Reduced to make room for time and speed
        display_name = display_file
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
        """Mark one item as complete (thread-safe)."""
        with self._lock:
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
        summary = f"{icon} {Colors.GREEN}{op_name}: {self.completed_items} files ({format_size(self.completed_bytes)}){Colors.RESET}"

        if self.skipped_items > 0:
            summary += f" {Colors.YELLOW}(Skipped: {self.skipped_items}){Colors.RESET}"

        sys.stdout.write(summary)
        # Don't add extra newline - the shell prompt will handle spacing

        self._cleanup()
