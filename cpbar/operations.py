"""
File operations for cpbar.
Handles copy and remove operations with progress tracking.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import os
import sys
import shutil
import time
import threading
import subprocess
import termios
import tty
from pathlib import Path
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from .ui import ProgressBar, Colors, getch
from .utils import (
    format_size, estimate_operation_time, is_system_directory,
    compute_checksum, BUFFER_SIZE, BLOCK_SIZE, PARALLEL_THRESHOLD
)


def get_all_files(paths: List[str], recursive: bool, force: bool = False) -> List[Tuple[str, int]]:
    """
    Get all files from given paths with their sizes.
    Returns list of tuples (filepath, size).
    Symlinks are returned as entries themselves (never followed), like rm does.
    With force, missing paths are ignored silently, like rm -f.
    """
    files = []

    for path in paths:
        p = Path(path)
        if p.is_symlink():
            files.append((str(p), 0))
            continue
        if not p.exists():
            if not force:
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


def verify_copy(src: str, dst: str, progress: ProgressBar = None) -> bool:
    """Verify that dst is a byte-identical copy of src using SHA256 checksums.
    Returns True if checksums match, False otherwise.
    Prints a failure message to stderr on mismatch.
    """
    src_hash = compute_checksum(src)
    dst_hash = compute_checksum(dst)
    if src_hash != dst_hash:
        message = (
            f"{Colors.RED}Verification FAILED: '{src}' → '{dst}' "
            f"(src={src_hash[:8]}… dst={dst_hash[:8]}…){Colors.RESET}"
        )
        if progress is not None:
            progress.log(message, file=sys.stderr)
        else:
            print(message, file=sys.stderr)
        return False
    return True


def copy_file_with_progress(src: str, dst: str, progress: ProgressBar, buffer_size: int = BUFFER_SIZE, verify: bool = False, preserve_symlinks: bool = False, confirmed: bool = False):
    """Copy a single file with progress updates. Default buffer: 16MB for optimal performance.
    With confirmed, an existing destination is overwritten without asking (the caller already did).
    """
    src_path = Path(src)
    dst_path = Path(dst)

    # Handle destination being a directory
    if dst_path.is_dir():
        dst_path = dst_path / src_path.name

    # Preserve symlinks as symlinks instead of dereferencing
    if src_path.is_symlink() and preserve_symlinks:
        link_target = os.readlink(src)
        if dst_path.exists() or dst_path.is_symlink():
            if not confirmed and not progress.ask_overwrite(str(dst_path)):
                return False
            dst_path.unlink()
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(link_target, dst_path)
        progress.update(src_path.name, 0)
        return True

    # Check if destination file already exists
    if dst_path.exists() and not confirmed:
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

    if verify and not verify_copy(src, str(dst_path), progress):
        return False

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
            # Update progress inside lock to avoid race conditions
            progress.update(os.path.basename(src), len(data))

    return block_num


def copy_file_parallel(src: str, dst: str, progress: ProgressBar, num_workers: int = 4, block_size: int = BLOCK_SIZE, verify: bool = False, confirmed: bool = False):
    """Copy a large file using parallel block copying.

    Args:
        src: Source file path
        dst: Destination file path
        progress: ProgressBar instance for tracking
        num_workers: Number of parallel workers (default: 4)
        block_size: Size of each block in bytes (default: 32MB)
        verify: Verify copy with SHA256 checksum after transfer
        confirmed: Overwrite an existing destination without asking
    """
    src_path = Path(src)
    dst_path = Path(dst)

    # Handle destination being a directory
    if dst_path.is_dir():
        dst_path = dst_path / src_path.name

    # Check if destination file already exists
    if dst_path.exists() and not confirmed:
        if not progress.ask_overwrite(str(dst_path)):
            return False
    confirmed = True

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
        return copy_file_with_progress(src, str(dst_path), progress, verify=verify, confirmed=confirmed)

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
    block_size_str = format_size(block_size)
    progress.log(f"{Colors.CYAN}⚡ Parallel mode: {num_workers} workers, {len(blocks)} blocks of {block_size_str}{Colors.RESET}")

    # Copy blocks in parallel
    write_lock = threading.Lock()
    try:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = []
            for offset, size, num in blocks:
                future = executor.submit(copy_block, src, str(dst_path), offset, size, num, progress, write_lock)
                futures.append(future)

            # Wait for all blocks to complete
            for future in as_completed(futures):
                future.result()  # This will raise any exceptions that occurred
    except Exception as e:
        # Cleanup: remove partially written destination file
        try:
            if dst_path.exists():
                dst_path.unlink()
        except OSError:
            pass  # Best effort cleanup
        raise  # Re-raise the original exception

    # Preserve metadata
    shutil.copystat(src, dst_path)

    if verify and not verify_copy(src, str(dst_path), progress):
        return False

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
                progress.log(f"{Colors.YELLOW}Warning: Could not copy '{src_file}': {e}{Colors.RESET}", file=sys.stderr)


def make_directory_tree(src_dir: Path, dst_dir: Path, follow_symlinks: bool = True):
    """Recreate the directory structure of src_dir under dst_dir, including empty directories.
    Without follow_symlinks, symlinked subdirectories are left for the caller to copy as links.
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    for root, dirs, _ in os.walk(str(src_dir), followlinks=follow_symlinks):
        rel_root = os.path.relpath(root, src_dir)
        for d in dirs:
            if not follow_symlinks and os.path.islink(os.path.join(root, d)):
                continue
            (dst_dir / rel_root / d).mkdir(parents=True, exist_ok=True)


def directory_destination(src_dir: Path, dst_path: Path, copy_into: bool) -> Path:
    """Where a source directory lands: inside dst_path if it was an existing directory
    (or there are several sources), otherwise dst_path becomes the copy, like cp -r and mv.
    """
    return dst_path / src_dir.name if copy_into else dst_path


def do_copy(sources: List[str], destination: str, recursive: bool, dry_run: bool = False, parallel: int = 0, verify: bool = False, preserve_symlinks: bool = False):
    """Execute copy operation with progress bar.

    Args:
        sources: List of source file/directory paths
        destination: Destination path
        recursive: Whether to copy directories recursively
        dry_run: Preview mode without copying
        parallel: Number of parallel workers for large files (0 = disabled)
        verify: Verify each file with SHA256 checksum after copying
        preserve_symlinks: Preserve symlinks as symlinks instead of copying target contents
    """
    # Validate inputs
    if not sources:
        print(f"{Colors.RED}Error: No source files specified{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    dst_path = Path(destination)

    # Fall back to native /bin/cp for system directories
    if is_system_directory(dst_path):
        print(f"{Colors.DIM}System directory detected, using /bin/cp...{Colors.RESET}")
        cmd = ['/bin/cp']
        if recursive:
            cmd.append('-r')
        cmd.extend(sources)
        cmd.append(destination)
        result = subprocess.run(cmd)
        sys.exit(result.returncode)

    # Source directories go inside the destination only if it already is a directory
    copy_into = dst_path.is_dir() or len(sources) > 1

    # If multiple sources, destination must be a directory
    if len(sources) > 1 and not dst_path.is_dir():
        if not dst_path.exists():
            if not dry_run:
                dst_path.mkdir(parents=True)
        else:
            print(f"{Colors.RED}Error: Destination must be a directory for multiple sources{Colors.RESET}", file=sys.stderr)
            sys.exit(1)

    # BUG FIX #2: Single pass through files - collect all files efficiently
    all_files = []

    for src in sources:
        src_path = Path(src)
        if not src_path.exists():
            print(f"{Colors.RED}Error: '{src}' does not exist{Colors.RESET}", file=sys.stderr)
            continue

        if src_path.is_symlink() and preserve_symlinks:
            # Treat the symlink itself as an entry (size 0 — we copy the link, not the content)
            all_files.append((str(src_path), 0))
        elif src_path.is_file():
            all_files.append((str(src_path), src_path.stat().st_size))
        elif src_path.is_dir():
            if recursive:
                # Walk directory and collect files in one pass
                follow = not preserve_symlinks
                for root, dirs, files in os.walk(str(src_path), followlinks=follow):
                    for filename in files:
                        filepath = os.path.join(root, filename)
                        fp = Path(filepath)
                        if fp.is_symlink() and preserve_symlinks:
                            all_files.append((filepath, 0))
                        else:
                            try:
                                all_files.append((filepath, os.path.getsize(filepath)))
                            except (PermissionError, OSError) as e:
                                print(f"{Colors.YELLOW}Warning: Cannot access '{filepath}': {e}{Colors.RESET}", file=sys.stderr)
                                all_files.append((filepath, 0))
                    if preserve_symlinks:
                        # Symlinked subdirs won't be descended into; add them as entries
                        for d in dirs:
                            dir_path_str = os.path.join(root, d)
                            if Path(dir_path_str).is_symlink():
                                all_files.append((dir_path_str, 0))
            else:
                print(f"{Colors.RED}Error: '{src}' is a directory. Use -r to copy recursively{Colors.RESET}", file=sys.stderr)

    # An empty source directory is still something to copy
    if not all_files and not any(recursive and Path(src).is_dir() for src in sources):
        print(f"{Colors.RED}Error: No files to copy{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    total_bytes = sum(size for _, size in all_files)
    total_items = len(all_files)

    # Dry-run mode: just show what would be copied
    if dry_run:
        size_str = format_size(total_bytes)
        estimated_time = estimate_operation_time(total_bytes, 'cp')

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
            print(f"  {Colors.DIM}→{Colors.RESET} {rel_path} {Colors.DIM}({format_size(size)}){Colors.RESET}")

        if len(all_files) > 10:
            print(f"  {Colors.DIM}... and {len(all_files) - 10} more files{Colors.RESET}")

        return

    print(f"{Colors.BLUE}Copying {total_items} files ({format_size(total_bytes)})...{Colors.RESET}")

    progress = ProgressBar(total_items, total_bytes, "cp")

    # Group files by their source directory for efficient copying
    # BUG FIX #1: Use is_relative_to instead of startswith to avoid false positives
    dir_sources = [Path(src) for src in sources if Path(src).is_dir() and recursive]

    for dir_path in dir_sources:
        try:
            make_directory_tree(dir_path, directory_destination(dir_path, dst_path, copy_into),
                                follow_symlinks=not preserve_symlinks)
        except (PermissionError, OSError) as e:
            progress.log(f"{Colors.RED}Error: Cannot create '{destination}': {e}{Colors.RESET}", file=sys.stderr)
            sys.exit(1)

    verify_failures = 0

    # Copy all files
    for src_file, file_size in all_files:
        src_file_path = Path(src_file)

        # Check if file is part of a directory being copied recursively
        # BUG FIX #1: Use proper path relationship checking
        is_in_dir = False
        parent_dir = None
        for dir_path in dir_sources:
            try:
                # Use is_relative_to if available (Python 3.9+)
                if hasattr(src_file_path, 'is_relative_to'):
                    if src_file_path.is_relative_to(dir_path):
                        is_in_dir = True
                        parent_dir = dir_path
                        break
                else:
                    # Fallback for older Python versions
                    try:
                        src_file_path.relative_to(dir_path)
                        is_in_dir = True
                        parent_dir = dir_path
                        break
                    except ValueError:
                        pass
            except (ValueError, TypeError):
                pass

        if is_in_dir and parent_dir:
            # File is part of a directory - copy with directory structure
            try:
                rel_path = src_file_path.relative_to(parent_dir)
                dst_file = directory_destination(parent_dir, dst_path, copy_into) / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)

                # Use parallel mode for large files (> 64MB) if enabled
                # (a file skipped at the overwrite prompt is not a verification failure)
                skipped_before = progress.skipped_items
                if parallel > 0 and file_size > PARALLEL_THRESHOLD:
                    ok = copy_file_parallel(src_file, str(dst_file), progress, num_workers=parallel, verify=verify)
                else:
                    ok = copy_file_with_progress(src_file, str(dst_file), progress, verify=verify, preserve_symlinks=preserve_symlinks)
                if ok:
                    progress.complete_item()
                elif verify and progress.skipped_items == skipped_before:
                    verify_failures += 1
            except (PermissionError, OSError) as e:
                progress.log(f"{Colors.YELLOW}Warning: Could not copy '{src_file}': {e}{Colors.RESET}", file=sys.stderr)
        else:
            # Individual file - copy directly
            try:
                # Use parallel mode for large files (> 64MB) if enabled
                # (a file skipped at the overwrite prompt is not a verification failure)
                skipped_before = progress.skipped_items
                if parallel > 0 and file_size > PARALLEL_THRESHOLD:
                    ok = copy_file_parallel(src_file, destination, progress, num_workers=parallel, verify=verify)
                else:
                    ok = copy_file_with_progress(src_file, destination, progress, verify=verify, preserve_symlinks=preserve_symlinks)
                if ok:
                    progress.complete_item()
                elif verify and progress.skipped_items == skipped_before:
                    verify_failures += 1
            except (PermissionError, OSError) as e:
                progress.log(f"{Colors.YELLOW}Warning: Could not copy '{src_file}': {e}{Colors.RESET}", file=sys.stderr)

    if verify:
        if verify_failures > 0:
            progress.log(f"{Colors.RED}Verification: {verify_failures} file(s) failed{Colors.RESET}", file=sys.stderr)
            progress.finish()
            sys.exit(1)
        else:
            progress.log(f"{Colors.GREEN}Verification: all files OK{Colors.RESET}")

    progress.finish()


def do_move(sources: List[str], destination: str, recursive: bool, dry_run: bool = False, parallel: int = 0):
    """Execute move operation with progress bar.

    Args:
        sources: List of source file/directory paths
        destination: Destination path
        recursive: Whether to move directories recursively (implied for directories)
        dry_run: Preview mode without moving
        parallel: Number of parallel workers for large files (0 = disabled)
    """
    # Validate inputs
    if not sources:
        print(f"{Colors.RED}Error: No source files specified{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    dst_path = Path(destination)

    # Fall back to native /bin/mv for system directories
    if is_system_directory(dst_path):
        print(f"{Colors.DIM}System directory detected, using /bin/mv...{Colors.RESET}")
        cmd = ['/bin/mv']
        cmd.extend(sources)
        cmd.append(destination)
        result = subprocess.run(cmd)
        sys.exit(result.returncode)

    # Source directories go inside the destination only if it already is a directory
    copy_into = dst_path.is_dir() or len(sources) > 1

    # If multiple sources, destination must be a directory
    if len(sources) > 1 and not dst_path.is_dir():
        if not dst_path.exists():
            if not dry_run:
                dst_path.mkdir(parents=True)
        else:
            print(f"{Colors.RED}Error: Destination must be a directory for multiple sources{Colors.RESET}", file=sys.stderr)
            sys.exit(1)

    # Collect all files to move
    all_files = []
    dirs_to_process = []

    for src in sources:
        src_path = Path(src)
        if not src_path.exists():
            print(f"{Colors.RED}Error: '{src}' does not exist{Colors.RESET}", file=sys.stderr)
            continue

        if src_path.is_file():
            all_files.append((str(src_path), src_path.stat().st_size))
        elif src_path.is_dir():
            # For directories, collect all files recursively
            dirs_to_process.append(src_path)
            for root, _, files in os.walk(str(src_path)):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    try:
                        all_files.append((filepath, os.path.getsize(filepath)))
                    except (PermissionError, OSError) as e:
                        print(f"{Colors.YELLOW}Warning: Cannot access '{filepath}': {e}{Colors.RESET}", file=sys.stderr)
                        all_files.append((filepath, 0))

    # An empty source directory is still something to move
    if not all_files and not dirs_to_process:
        print(f"{Colors.RED}Error: No files to move{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    total_bytes = sum(size for _, size in all_files)
    total_items = len(all_files)

    # Dry-run mode: just show what would be moved
    if dry_run:
        size_str = format_size(total_bytes)
        estimated_time = estimate_operation_time(total_bytes, 'mv')

        print(f"{Colors.CYAN}🔍 Dry-run mode - No files will be moved{Colors.RESET}\n")
        print(f"{Colors.BOLD}Summary:{Colors.RESET}")
        print(f"  Files to move: {Colors.GREEN}{total_items}{Colors.RESET}")
        print(f"  Total size: {Colors.GREEN}{size_str}{Colors.RESET}")
        print(f"  Estimated time: {Colors.YELLOW}~{estimated_time}{Colors.RESET}")
        print(f"  Destination: {Colors.BLUE}{destination}{Colors.RESET}\n")

        # Show first 10 files as preview
        print(f"{Colors.BOLD}Files (showing first 10):{Colors.RESET}")
        for filepath, size in all_files[:10]:
            rel_path = os.path.relpath(filepath)
            print(f"  {Colors.DIM}→{Colors.RESET} {rel_path} {Colors.DIM}({format_size(size)}){Colors.RESET}")

        if len(all_files) > 10:
            print(f"  {Colors.DIM}... and {len(all_files) - 10} more files{Colors.RESET}")

        return

    print(f"{Colors.BLUE}Moving {total_items} files ({format_size(total_bytes)})...{Colors.RESET}")

    progress = ProgressBar(total_items, total_bytes, "mv")

    # Recreate the directory structure first so empty directories are moved too
    for dir_path in dirs_to_process:
        try:
            make_directory_tree(dir_path, directory_destination(dir_path, dst_path, copy_into),
                                follow_symlinks=False)
        except (PermissionError, OSError) as e:
            progress.log(f"{Colors.RED}Error: Cannot create '{destination}': {e}{Colors.RESET}", file=sys.stderr)
            sys.exit(1)

    # Check if source and destination are on the same filesystem
    # If so, we can use rename for instant moves
    same_fs = {}
    for src in sources:
        src_path = Path(src)
        if src_path.exists():
            try:
                src_stat = src_path.stat()
                dst_stat = dst_path.stat() if dst_path.exists() else dst_path.parent.stat()
                same_fs[str(src_path)] = (src_stat.st_dev == dst_stat.st_dev)
            except (PermissionError, OSError):
                same_fs[str(src_path)] = False

    # Move files
    for src_file, file_size in all_files:
        src_file_path = Path(src_file)

        # Determine if this file is part of a directory being moved
        is_in_dir = False
        parent_dir = None
        for dir_path in dirs_to_process:
            try:
                if hasattr(src_file_path, 'is_relative_to'):
                    if src_file_path.is_relative_to(dir_path):
                        is_in_dir = True
                        parent_dir = dir_path
                        break
                else:
                    try:
                        src_file_path.relative_to(dir_path)
                        is_in_dir = True
                        parent_dir = dir_path
                        break
                    except ValueError:
                        pass
            except (ValueError, TypeError):
                pass

        if is_in_dir and parent_dir:
            # File is part of a directory - move with directory structure
            try:
                rel_path = src_file_path.relative_to(parent_dir)
                dst_file = directory_destination(parent_dir, dst_path, copy_into) / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)

                # Check if destination file already exists
                if dst_file.exists():
                    if not progress.ask_overwrite(str(dst_file)):
                        continue

                # Try rename first (instant if same filesystem)
                parent_key = str(parent_dir)
                if parent_key in same_fs and same_fs[parent_key]:
                    try:
                        src_file_path.rename(dst_file)
                        progress.update(src_file_path.name, file_size)
                        progress.complete_item()
                        continue
                    except OSError:
                        # Rename failed, fall back to copy+delete
                        pass

                # Fall back to copy + delete
                if parallel > 0 and file_size > PARALLEL_THRESHOLD:
                    if copy_file_parallel(src_file, str(dst_file), progress, num_workers=parallel, confirmed=True):
                        os.remove(src_file)
                        progress.complete_item()
                else:
                    if copy_file_with_progress(src_file, str(dst_file), progress, confirmed=True):
                        os.remove(src_file)
                        progress.complete_item()
            except (PermissionError, OSError) as e:
                progress.log(f"{Colors.YELLOW}Warning: Could not move '{src_file}': {e}{Colors.RESET}", file=sys.stderr)
        else:
            # Individual file - move directly
            try:
                # Handle destination being a directory
                if dst_path.is_dir():
                    dst_file = dst_path / src_file_path.name
                else:
                    dst_file = dst_path

                # Check if destination file already exists
                if dst_file.exists():
                    if not progress.ask_overwrite(str(dst_file)):
                        continue

                # Try rename first (instant if same filesystem)
                src_key = str(src_file_path)
                if src_key in same_fs and same_fs[src_key]:
                    try:
                        src_file_path.rename(dst_file)
                        progress.update(src_file_path.name, file_size)
                        progress.complete_item()
                        continue
                    except OSError:
                        # Rename failed, fall back to copy+delete
                        pass

                # Fall back to copy + delete
                if parallel > 0 and file_size > PARALLEL_THRESHOLD:
                    if copy_file_parallel(src_file, str(dst_file), progress, num_workers=parallel, confirmed=True):
                        os.remove(src_file)
                        progress.complete_item()
                else:
                    if copy_file_with_progress(src_file, str(dst_file), progress, confirmed=True):
                        os.remove(src_file)
                        progress.complete_item()
            except (PermissionError, OSError) as e:
                progress.log(f"{Colors.YELLOW}Warning: Could not move '{src_file}': {e}{Colors.RESET}", file=sys.stderr)

    # Remove the now empty source directories, deepest first
    for dir_path in reversed(dirs_to_process):
        for root, _, _ in os.walk(str(dir_path), topdown=False):
            try:
                # Only remove if empty
                if not any(os.scandir(root)):
                    os.rmdir(root)
            except (PermissionError, OSError):
                pass  # Directory not empty or can't remove, that's OK

    progress.finish()


def do_remove(targets: List[str], recursive: bool, force: bool, dry_run: bool = False):
    """Execute remove operation with progress bar."""
    if not targets:
        print(f"{Colors.RED}Error: No files specified for deletion{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    # Collect all files to remove
    all_files = get_all_files(targets, recursive, force)
    dirs_to_remove = []

    # Also collect directories if recursive (a symlink to a directory is just a file here)
    if recursive:
        for target in targets:
            p = Path(target)
            if p.is_dir() and not p.is_symlink():
                dirs_to_remove.append(str(p))

    if not all_files and not dirs_to_remove:
        if force:
            # rm -f exits successfully when there is nothing to delete
            return
        print(f"{Colors.RED}Error: No files to delete{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    total_bytes = sum(size for _, size in all_files)
    total_items = len(all_files)

    # Dry-run mode: just show what would be deleted
    if dry_run:
        size_str = format_size(total_bytes)
        estimated_time = estimate_operation_time(total_bytes, 'rm')

        print(f"{Colors.CYAN}🔍 Dry-run mode - No files will be deleted{Colors.RESET}\n")
        print(f"{Colors.BOLD}Summary:{Colors.RESET}")
        print(f"  Files to delete: {Colors.RED}{total_items}{Colors.RESET}")
        print(f"  Total size: {Colors.RED}{size_str}{Colors.RESET}")
        print(f"  Estimated time: {Colors.YELLOW}~{estimated_time}{Colors.RESET}\n")

        # Show first 10 files as preview
        print(f"{Colors.BOLD}Files (showing first 10):{Colors.RESET}")
        for filepath, size in all_files[:10]:
            rel_path = os.path.relpath(filepath)
            print(f"  {Colors.DIM}→{Colors.RESET} {rel_path} {Colors.DIM}({format_size(size)}){Colors.RESET}")

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
        print(f"{Colors.YELLOW}Will delete {total_items} files ({format_size(total_bytes)}){Colors.RESET}")

        # 3-second countdown before allowing confirmation
        # Disable terminal echo during countdown to suppress visual noise
        fd = None
        old_settings = None
        try:
            fd = sys.stdin.fileno()
            # Save current terminal settings
            old_settings = termios.tcgetattr(fd)
            # Disable echo
            new_settings = termios.tcgetattr(fd)
            new_settings[3] = new_settings[3] & ~termios.ECHO  # lflags
            termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)
        except (termios.error, AttributeError, OSError):
            # Not a TTY or termios not available, continue without echo suppression
            pass

        try:
            for i in range(3, 0, -1):
                sys.stdout.write(f"\r{Colors.DIM}Wait {i}s before confirming...{Colors.RESET}  ")
                sys.stdout.flush()
                time.sleep(1)
        finally:
            # Restore terminal settings
            if old_settings is not None:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except (termios.error, OSError):
                    pass

        sys.stdout.write("\r" + " " * 40 + "\r")  # Clear countdown line
        sys.stdout.flush()

        # Prompt for confirmation - only accepts y or n (Enter defaults to n)
        sys.stdout.write(f"{Colors.BOLD}Continue? [y/N]: {Colors.RESET}")
        sys.stdout.flush()
        
        confirm = getch("yn\r\n")  # Accept y, n, or Enter
        
        if confirm == 'y':
            print()  # Newline after single char input
        elif confirm in ['n', '\r', '\n']:
            print()  # Newline
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
            progress.log(f"{Colors.YELLOW}Warning: Could not delete '{filepath}': {e}{Colors.RESET}", file=sys.stderr)

    # Remove directories (in reverse order to handle nested dirs)
    if recursive:
        for target in dirs_to_remove:
            p = Path(target)
            if p.is_dir():
                try:
                    shutil.rmtree(target)
                except (PermissionError, OSError) as e:
                    progress.log(f"{Colors.YELLOW}Warning: Could not delete directory '{target}': {e}{Colors.RESET}", file=sys.stderr)

    progress.finish()
