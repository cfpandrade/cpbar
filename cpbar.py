#!/usr/bin/env python3
"""
cpbar - Enhanced cp/rm with unified progress bar

Usage:
    cpbar cp <source>... <destination>
    cpbar rm <files>...
    cpbar cp -r <source>... <destination>
    cpbar rm -r <directories>...

This is the main entry point that delegates to the cpbar package.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

from cpbar.core import main

if __name__ == '__main__':
    main()
