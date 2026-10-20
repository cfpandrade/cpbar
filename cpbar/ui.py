"""
UI components for cpbar.
Handles progress bar, colors, and cursor control.

TTY Detection:
- Automatically detects if running in an interactive terminal (TTY)
- In TTY mode: Shows interactive progress bar with ANSI colors and cursor control
- In non-TTY mode: Falls back to simple line-based output (e.g., in pipes, cronjobs, scripts)
- No ANSI escape codes are printed when not in a TTY

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import sys
import shutil
import signal
import time
import threading
import termios
import tty
from typing import Tuple

from .utils import (
    format_size, format_time, format_speed,
    load_config, save_config,
    SPEED_UPDATE_INTERVAL, SPEED_SMOOTHING_FACTOR
)


# Detect if we're running in a TTY
IS_TTY = sys.stdout.isatty()


# ANSI escape codes for styling (empty if not TTY)
class Colors:
    RESET = "\033[0m" if IS_TTY else ""
    BOLD = "\033[1m" if IS_TTY else ""
    GREEN = "\033[32m" if IS_TTY else ""
    BLUE = "\033[34m" if IS_TTY else ""
    CYAN = "\033[36m" if IS_TTY else ""
    YELLOW = "\033[33m" if IS_TTY else ""
    RED = "\033[31m" if IS_TTY else ""
    DIM = "\033[2m" if IS_TTY else ""


# ANSI escape codes for cursor/screen control (empty if not TTY)
class Cursor:
    HIDE = "\033[?25l" if IS_TTY else ""
    SHOW = "\033[?25h" if IS_TTY else ""
    # Return to column 1 and erase the current line
    CLEAR_LINE = "\r\033[2K" if IS_TTY else ""


def getch(valid_keys: str) -> str:
    """Read a single character from stdin, blocking until a valid key is pressed.
    Only accepts characters in valid_keys (case-insensitive).
    Returns the lowercase character.
    
    Args:
        valid_keys: String of valid characters (e.g., "ynaq")
    
    Returns:
        Single lowercase character from valid_keys. If stdin runs out
        (e.g. </dev/null or a script) the safe answer 'n' is returned.
    """
    if not sys.stdin.isatty():
        # Fallback to line-based input when stdin is not a terminal
        while True:
            try:
                response = input().strip().lower()
            except EOFError:
                if 'n' in valid_keys.lower():
                    return 'n'
                raise KeyboardInterrupt
            if response and response[0] in valid_keys.lower():
                return response[0]

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            char = sys.stdin.read(1).lower()
            # Handle Ctrl+C
            if char == '\x03':
                raise KeyboardInterrupt
            # Only accept valid keys
            if char in valid_keys.lower():
                # Echo the character
                sys.stdout.write(char)
                sys.stdout.flush()
                return char
            # Ignore invalid keys silently
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


class ProgressBar:
    """A single progress bar that tracks total progress across all files.
    Drawn inline on the line where the operation started (the terminal is never
    scrolled to the bottom) and adapts to terminal width.
    In non-TTY mode, falls back to simple line-based progress updates.
    """

    # Minimum seconds between redraws, so thousands of tiny files don't flood the terminal
    RENDER_INTERVAL = 0.05

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
        self.is_tty = IS_TTY

        # Time estimation
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_render_time = 0.0

        # Speed tracking
        self.last_bytes = 0
        self.current_speed = 0.0  # bytes per second

        # Thread safety lock for concurrent updates. Reentrant so the SIGWINCH
        # handler can redraw even if it interrupts the main thread mid-render.
        self._lock = threading.RLock()

        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self._signal_handler)
        if self.is_tty:
            signal.signal(signal.SIGWINCH, self._resize_handler)

    def _signal_handler(self, signum, frame):
        self.interrupted = True
        self._cleanup()
        print(f"{Cursor.CLEAR_LINE}{Colors.YELLOW}⚠ Operation cancelled by user{Colors.RESET}")
        sys.exit(130)

    def _resize_handler(self, signum, frame):
        """Handle terminal resize."""
        if self.started:
            self._update_tty_display(force=True)

    def _get_terminal_size(self) -> Tuple[int, int]:
        """Get terminal dimensions (columns, lines)."""
        size = shutil.get_terminal_size()
        return size.columns, size.lines

    def _setup(self):
        """Setup the progress bar display area."""
        if self.started:
            return
        self.started = True
        sys.stdout.write(Cursor.HIDE)
        sys.stdout.flush()

    def _cleanup(self):
        """Restore terminal state."""
        # Show cursor
        sys.stdout.write(Cursor.SHOW)
        sys.stdout.flush()

    def log(self, message: str, file=None):
        """Print a message above the progress bar without corrupting it."""
        file = file or sys.stdout
        with self._lock:
            if self.is_tty and self.started:
                sys.stdout.write(Cursor.CLEAR_LINE)
                sys.stdout.flush()
            print(message, file=file)
            file.flush()
            if self.is_tty and self.started:
                self._update_tty_display(force=True)

    def _reset_speed_baseline(self):
        """Restart speed measurement, e.g. after waiting for user input."""
        with self._lock:
            self.current_speed = 0.0
            self.last_bytes = self.completed_bytes
            self.last_update_time = time.time()

    def ask_overwrite(self, filepath: str) -> bool:
        """Ask user if they want to overwrite a file.
        Returns True if file should be overwritten, False to skip.
        Can also set self.overwrite_all if user chooses 'all'.
        """
        if self.overwrite_all:
            return True

        # Replace the progress bar line with the prompt
        sys.stdout.write(Cursor.CLEAR_LINE)
        sys.stdout.write(Cursor.SHOW)
        sys.stdout.write(f"{Colors.YELLOW}Overwrite '{filepath}'? [y/n/a/q]: {Colors.RESET}")
        sys.stdout.flush()

        # Read single character, only accepting valid keys
        response = getch("ynaq")

        if response == 'q':
            self._cleanup()
            print(f"\n{Colors.YELLOW}⚠ Operation cancelled by user{Colors.RESET}")
            sys.exit(0)

        if response == 'n':
            self.skipped_items += 1
        elif response == 'a':
            self.overwrite_all = True

        # Clear the prompt and put the progress bar back in its place
        # (outside a TTY the prompt can't be erased, so just end its line)
        sys.stdout.write(Cursor.CLEAR_LINE if self.is_tty else "\n")
        sys.stdout.write(Cursor.HIDE)
        sys.stdout.flush()
        self._reset_speed_baseline()
        if self.started:
            self._update_tty_display(force=True)
        return response in ('y', 'a')

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
        with self._lock:
            self.current_file = current_file
            self.completed_bytes += bytes_delta

        if self.is_tty:
            self._update_tty_display()
        # Non-TTY mode: updates happen in complete_item()

    def _update_tty_display(self, force: bool = False):
        """Update progress bar display in TTY mode (interactive terminal)."""
        with self._lock:
            current_time = time.time()
            if not force and current_time - self.last_render_time < self.RENDER_INTERVAL:
                return
            self.last_render_time = current_time

            self._setup()

            # Calculate speed (with smoothing)
            time_delta = current_time - self.last_update_time
            if time_delta > SPEED_UPDATE_INTERVAL:  # Update speed every 100ms
                bytes_since_last = self.completed_bytes - self.last_bytes
                instant_speed = bytes_since_last / time_delta
                # Smooth the speed using exponential moving average
                self.current_speed = SPEED_SMOOTHING_FACTOR * self.current_speed + (1 - SPEED_SMOOTHING_FACTOR) * instant_speed
                self.last_bytes = self.completed_bytes
                self.last_update_time = current_time

            # Capture values for rendering
            completed_bytes = self.completed_bytes
            completed_items = self.completed_items
            total_bytes = self.total_bytes
            total_items = self.total_items
            current_speed = self.current_speed
            display_file = self.current_file

            cols, _ = self._get_terminal_size()

            if total_bytes > 0:
                progress = min(completed_bytes / total_bytes, 1.0)
            else:
                progress = completed_items / total_items if total_items > 0 else 1.0

            # Build components
            if self.operation == "cp":
                op_icon = "📋"
            elif self.operation == "mv":
                op_icon = "🚚"
            else:
                op_icon = "🗑️ "
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

            # The line must never wrap, or the carriage return would only redraw its
            # last row. On narrow terminals drop the filename, then the time.
            if fixed_len + 15 > cols:
                fixed_len -= 3 + max_filename_len
                display_name = None
            if fixed_len + 15 > cols:
                fixed_len -= 3 + len(time_display)
                time_display = None

            # Calculate bar width to fill remaining space
            bar_width = self._calculate_bar_width(fixed_len)

            filled = int(bar_width * progress)
            empty = bar_width - filled
            bar = f"{Colors.GREEN}{'█' * filled}{Colors.DIM}{'░' * empty}{Colors.RESET}"

            # Build the line
            line = f"{op_icon} {Colors.BOLD}{pct}{Colors.RESET} [{bar}] {items_str} | {size_str}"
            if time_display is not None:
                line += f" | {Colors.DIM}{time_display}{Colors.RESET}"
            if display_name is not None:
                line += f" | {Colors.CYAN}{display_name}{Colors.RESET}"

            # Redraw in place on the current line
            sys.stdout.write(Cursor.CLEAR_LINE)
            sys.stdout.write(line)
            sys.stdout.flush()

    def complete_item(self):
        """Mark one item as complete (thread-safe)."""
        with self._lock:
            self.completed_items += 1
            
            # In non-TTY mode, print simple progress updates
            if not self.is_tty:
                if self.operation == "cp":
                    op_name = "Copied"
                elif self.operation == "mv":
                    op_name = "Moved"
                else:
                    op_name = "Deleted"
                progress_pct = (self.completed_items / self.total_items * 100) if self.total_items > 0 else 100
                print(f"{op_name} [{self.completed_items}/{self.total_items}] ({progress_pct:.1f}%) {self.current_file}")
                sys.stdout.flush()

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
                if self.operation == 'cp':
                    key = 'copy_speeds_mbps'
                elif self.operation == 'mv':
                    key = 'move_speeds_mbps'
                else:
                    key = 'delete_speeds_mbps'
                speeds = config.get(key, [])
                speeds.append(speed_mbps)
                # Keep only last 10 observations to prevent unbounded growth
                speeds = speeds[-10:]
                config[key] = speeds
                save_config(config)

        # Print summary
        if self.operation == "cp":
            op_name = "Copied"
            icon = "✅"
        elif self.operation == "mv":
            op_name = "Moved"
            icon = "✅"
        else:
            op_name = "Deleted"
            icon = "🗑️ "
        summary = f"{icon} {op_name}: {self.completed_items} files ({format_size(self.completed_bytes)}) in {self._get_elapsed_time()}"

        if self.skipped_items > 0:
            summary += f" (Skipped: {self.skipped_items})"

        # Replace the progress bar line with the summary (no-op prefix outside a TTY)
        print(f"{Cursor.CLEAR_LINE}{summary}")

        self._cleanup()
