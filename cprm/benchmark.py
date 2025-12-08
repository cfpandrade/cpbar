"""
Benchmark functionality for cprm.
Tests different worker counts to determine optimal configuration.

Author: Carlos Andrade <cfpandrade@gmail.com>
"""

import os
import shutil
import time
import threading
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from .ui import Colors
from .utils import load_config, save_config, CONFIG_FILE, BLOCK_SIZE


def _benchmark_copy_block(src: str, dst: str, offset: int, size: int, lock: threading.Lock):
    """Copy a block for benchmarking (without progress tracking)."""
    with open(src, 'rb') as fsrc:
        fsrc.seek(offset)
        data = fsrc.read(size)

        with lock:
            with open(dst, 'r+b') as fdst:
                fdst.seek(offset)
                fdst.write(data)


def run_benchmark(quiet: bool = False):
    """Run benchmark to determine optimal number of parallel workers.

    Args:
        quiet: If True, minimal output. If False, detailed output.

    Returns:
        Optimal number of workers
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

                    block_size = BLOCK_SIZE  # 32MB blocks
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
