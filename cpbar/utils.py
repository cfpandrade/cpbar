"""
Utility functions for cpbar.
Handles configuration management and formatting functions.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import json
from pathlib import Path
from typing import Tuple

# Configuration file management
CONFIG_FILE = Path.home() / ".config" / "cpbar" / "config.json"

# Constants
BUFFER_SIZE = 16 * 1024 * 1024  # 16MB
BLOCK_SIZE = 32 * 1024 * 1024   # 32MB
PARALLEL_THRESHOLD = 64 * 1024 * 1024  # 64MB
SPEED_UPDATE_INTERVAL = 0.1  # seconds
SPEED_SMOOTHING_FACTOR = 0.7


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


def format_size(size: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


def format_time(seconds: float) -> str:
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


def format_speed(bytes_per_second: float) -> str:
    """Format speed to human-readable format."""
    if bytes_per_second < 1024:
        return f"{bytes_per_second:.0f}B/s"
    elif bytes_per_second < 1024 * 1024:
        return f"{bytes_per_second / 1024:.1f}KB/s"
    elif bytes_per_second < 1024 * 1024 * 1024:
        return f"{bytes_per_second / (1024 * 1024):.1f}MB/s"
    elif bytes_per_second < 1024 * 1024 * 1024 * 1024:
        return f"{bytes_per_second / (1024 * 1024 * 1024):.1f}GB/s"
    else:
        return f"{bytes_per_second / (1024 * 1024 * 1024 * 1024):.1f}TB/s"


def estimate_operation_time(total_bytes: int, operation: str = 'cp') -> str:
    """Estimate time based on learned speeds from past operations.
    Falls back to conservative defaults if no history exists.

    Args:
        total_bytes: Total bytes to process
        operation: 'cp' for copy or 'rm' for remove

    Returns:
        Formatted time string
    """
    if total_bytes == 0:
        return "< 1s"

    config = load_config()
    key = 'copy_speeds_mbps' if operation == 'cp' else 'delete_speeds_mbps'
    default_speed = 100 if operation == 'cp' else 200

    learned_speeds = config.get(key, [])
    avg_speed_mbps = sum(learned_speeds) / len(learned_speeds) if learned_speeds else default_speed

    bytes_per_second = avg_speed_mbps * 1024 * 1024
    estimated_seconds = total_bytes / bytes_per_second

    return format_time(estimated_seconds)


def validate_destination(path: Path) -> None:
    """Validate destination is not a critical system directory.

    Args:
        path: Destination path to validate

    Raises:
        ValueError: If path is a critical system directory
    """
    critical_paths = ['/bin', '/boot', '/etc', '/lib', '/lib64', '/sbin', '/sys', '/usr', '/proc', '/dev']

    try:
        resolved = path.resolve()
        for critical in critical_paths:
            critical_path = Path(critical)
            if not critical_path.exists():
                continue
            critical_resolved = critical_path.resolve()

            # Check if destination is exactly a critical path or inside one
            if resolved == critical_resolved:
                raise ValueError(f"Cannot write to system directory: {path}")

            # Use is_relative_to if available (Python 3.9+), otherwise use try/except
            if hasattr(resolved, 'is_relative_to'):
                if resolved.is_relative_to(critical_resolved):
                    raise ValueError(f"Cannot write to system directory: {path}")
            else:
                try:
                    resolved.relative_to(critical_resolved)
                    raise ValueError(f"Cannot write to system directory: {path}")
                except ValueError:
                    pass  # Not relative, this is fine
    except (OSError, RuntimeError) as e:
        # If we can't resolve the path due to permissions, warn but allow
        # The operation will fail later with a more specific error
        import sys
        print(f"Warning: Could not validate destination path: {e}", file=sys.stderr)
