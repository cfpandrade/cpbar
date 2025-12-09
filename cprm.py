#!/usr/bin/env python3
"""
cprm - Enhanced cp/rm with unified progress bar

Usage:
    cprm cp <source>... <destination>
    cprm rm <files>...
    cprm cp -r <source>... <destination>
    cprm rm -r <directories>...

This is the main entry point that delegates to the cprm package.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

from cprm.core import main

if __name__ == '__main__':
    main()
