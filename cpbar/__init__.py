"""
cpbar - Enhanced cp/rm with unified progress bar

A lightweight wrapper for cp and rm commands that adds a unified,
beautiful progress bar to terminal file operations.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

__version__ = "1.5.0"
__author__ = "Carlos Andrade"
__email__ = "carlos@perezandrade.com"

from .core import main
from .operations import do_copy, do_remove
from .benchmark import run_benchmark
from .ui import ProgressBar, Colors, Cursor
from .utils import (
    format_size,
    format_time,
    format_speed,
    load_config,
    save_config,
    get_optimal_workers,
)

__all__ = [
    'main',
    'do_copy',
    'do_remove',
    'run_benchmark',
    'ProgressBar',
    'Colors',
    'Cursor',
    'format_size',
    'format_time',
    'format_speed',
    'load_config',
    'save_config',
    'get_optimal_workers',
]
