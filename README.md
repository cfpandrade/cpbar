# cpbar

[![CI](https://github.com/cfpandrade/cpbar/actions/workflows/ci.yml/badge.svg)](https://github.com/cfpandrade/cpbar/actions/workflows/ci.yml)

**cpbar** is a lightweight wrapper for `cp` and `rm` commands that adds a unified, beautiful progress bar to your terminal file operations. It is written in Python and designed to be a drop-in replacement for standard file management commands.

## Features

- **Unified Progress Bar**: Tracks total progress across all files and directories.
- **Real-Time Speed Display**: Shows current transfer speed (MB/s or GB/s) with smoothing for accurate readings.
- **Visual Feedback**: Shows operation type (📋/🗑️), percentage, progress bar, item count, total size, elapsed time, speed, and current filename.
- **Optimized Performance**:
  - 16MB buffer size for efficient file operations
  - Parallel copy mode for large files (> 64MB) using multi-threading
  - Can achieve 2-4x faster speeds on SSDs with parallel mode
- **Dry-Run Mode** (`-n` / `--dry-run`):
  - Preview exactly what will happen before executing
  - Shows: file count, total size, estimated time, and first 10 files to be processed
  - Perfect for verifying complex operations before committing
- **Parallel Copy Mode** (`--parallel=N`):
  - Multi-threaded copying for large files using block-based parallel I/O
  - Automatically activates for files > 64MB when enabled
  - Configurable worker count (optimal: 4-8 for SSDs)
  - Auto-benchmark to detect optimal settings for your system
- **Recursive Support**: Fully supports recursive copy (`cp -r`) and remove (`rm -r`).
- **Smart Overwrite Handling**:
  - Prompts when destination files exist with options: yes (y), no (n), all (a), quit (q).
  - All prompts appear in the same line for a clean interface.
- **Safety First**:
  - `rm` asks for confirmation by default with a 3-second safety countdown.
  - `rm -f` skips confirmation (like standard `rm`).
- **Drop-in Replacement**: Installs aliases so you can keep using `cp` and `rm` as usual.
- **Original Commands**: Provides `cpo` and `rmo` aliases if you need the original system commands.
- **Non-TTY/Script Compatibility**:
  - Automatically detects if running in a TTY (interactive terminal)
  - Falls back to simple line-based output when used in pipes, scripts, or cronjobs
  - No ANSI escape codes are printed in non-interactive mode
  - Works seamlessly in automation contexts

## Installation

### Option 1: Debian / Ubuntu (.deb) — recommended

Download the latest `.deb` from [Releases](../../releases/latest) and install:

```bash
wget https://github.com/cfpandrade/cpbar/releases/latest/download/cpbar_<version>_all.deb
sudo dpkg -i cpbar_<version>_all.deb
```

Bash users get aliases automatically via `/etc/profile.d/cpbar.sh` (takes effect on next login or `source /etc/profile.d/cpbar.sh`).

Zsh users: add these lines to `~/.zshrc` and reload:

```bash
alias cpo='/bin/cp'
alias rmo='/bin/rm'
alias cp='cpbar cp'
alias rm='cpbar rm'
```

To upgrade, just install the new `.deb` over the old one with `sudo dpkg -i`.

### Option 2: Script install (any distro)

```bash
./install.sh
```

The script will:
1. Install the `cpbar` package to `~/.local/lib/cpbar/` (library files).
2. Create an executable wrapper in `~/.local/bin/cpbar` (entry point).
3. Add `~/.local/bin` to your `PATH` if needed.
4. Configure aliases in your `.zshrc` or `.bashrc`.
5. Optionally run a benchmark to detect optimal parallel settings for your system (~30 seconds).

After installation, reload your shell configuration:

```bash
source ~/.zshrc  # or source ~/.bashrc
```

**Note:** The installer will ask if you want to run a benchmark to optimize performance. This is recommended but optional—you can run `cpbar benchmark` later if you skip it.

## Usage

Once installed, you can use `cp` and `rm` normally, and they will now show progress bars!

### Copying Files

```bash
# Copy a single file
cp big_file.iso /mnt/backup/

# Copy a directory recursively
cp -r Photos/ /mnt/backup/Photos/

# Copy multiple files
cp *.jpg /mnt/backup/images/

# Dry-run: preview what would be copied
cp -n -r Photos/ /mnt/backup/

# Parallel copy for large files (2-4x faster on SSDs)
cp -P large_file.iso /backup/                # Use auto-detected optimal workers
cp --parallel=4 large_file.iso /backup/      # Or specify workers manually
cp --parallel=8 huge_database.sql /backup/   # More workers for very large files
```

### Removing Files

```bash
# Remove a file (asks for confirmation)
rm old_file.txt

# Remove a directory recursively
rm -r old_folder/

# Force remove (no confirmation)
rm -rf temp_folder/

# Dry-run: preview what would be deleted
rm -n -r old_folder/
```

### Dry-Run Mode: Preview Before Executing

Before performing potentially risky operations, use the dry-run flag to see exactly what will happen:

```bash
# Preview what will be copied
cp -n large_folder/ /backup/

# Preview what will be deleted
rm -n --dry-run old_folder/
```

**Dry-run output includes:**
- Total number of files to process
- Total size that will be affected
- Estimated time for the operation (80 MB/s for copy, 200 MB/s for delete)
- Preview of the first 10 files

Example output:
```
🔍 Dry-run mode - No files will be copied

Summary:
  Files to copy: 42
  Total size: 2.5GB
  Estimated time: ~31s
  Destination: /backup/

Files (showing first 10):
  → photos/vacation_2024/IMG_001.jpg (4.2MB)
  → photos/vacation_2024/IMG_002.jpg (3.8MB)
  → documents/report.pdf (1.2MB)
  ... and 39 more files
```

### Handling File Overwrites

When copying files that already exist at the destination, `cpbar` will prompt you for each file:

```
Overwrite '/path/to/file.txt'? [y/n/a/q]:
```

Options:
- **y** (yes) - Overwrite this file
- **n** (no) - Skip this file
- **a** (all) - Overwrite all remaining files without asking
- **q** (quit) - Cancel the entire operation

All prompts appear on the same line for a clean, organized interface.

### Parallel Copy Mode: Speed Up Large File Transfers

For copying large files (> 64MB), use parallel mode to significantly speed up transfers on modern SSDs:

```bash
# Use parallel mode with auto-detected optimal workers
cp -P large_video.mp4 /backup/

# Or specify a custom number of workers
cp --parallel=4 database_dump.sql /backup/

# Works great with multiple large files
cp -P *.iso /backup/
```

**When to use parallel mode:**
- ✅ **Large files** (> 64MB): Significant speed improvements
- ✅ **SSD to SSD**: 2-4x faster transfer speeds
- ✅ **NVMe drives**: Best performance with 4-8 workers
- ❌ **Small files** (< 64MB): Automatically uses normal mode
- ❌ **HDD to HDD**: May not improve or could be slower

**Performance tips:**
- Run `cpbar benchmark` to auto-detect the optimal settings for your system
- Use `-P` flag to use the benchmarked optimal value
- Files > 1GB see the most benefit
- Real-time speed shown in progress bar (watch for MB/s or GB/s)

### Benchmark: Optimize for Your System

`cpbar` can automatically detect the optimal parallel worker count for your specific hardware:

```bash
# Run benchmark to detect optimal settings
cpbar benchmark

# The optimal value is saved and becomes the default when using -P
cp -P large_file.iso /backup/
```

**What the benchmark does:**
- Creates a temporary 100MB test file
- Tests with 1, 2, 4, 6, and 8 workers
- Runs 3 trials for each configuration
- Determines the fastest configuration
- Saves the result to `~/.config/cpbar/config.json`

**Note:** The installer optionally runs the benchmark automatically during installation. You can re-run it anytime if you upgrade your hardware or move to a different system.

### Using in Scripts, Pipes, and Cronjobs

`cpbar` automatically detects when it's not running in an interactive terminal (e.g., in pipes, scripts, or cronjobs) and switches to a simplified output mode:

**Interactive mode (TTY):**
```bash
# Beautiful progress bar with colors and animations
$ cpbar cp large_file.iso /backup/
📋  45.2% [████████████░░░░░░░░░░░░░] 1/1 | 2.1GB/4.6GB | 3m 15s @ 11.2MB/s | large_file.iso
```

**Non-interactive mode (no TTY):**
```bash
# Simple line-based output, no ANSI codes
$ cpbar cp file.txt /backup/ | tee log.txt
Copying 1 files (13.0B)...
Copied [1/1] (100.0%) file.txt
✅ Copied: 1 files (13.0B)

# In a script
#!/bin/bash
cpbar cp data.tar.gz /backup/  # Works seamlessly

# In a cronjob
0 2 * * * cpbar rm -rf /tmp/old_backups  # Clean output for logs

# Piped with other commands
find . -name '*.log' | xargs cpbar rm
```

**What changes in non-TTY mode:**
- No ANSI escape codes or cursor control
- Simple line-based progress updates instead of animated progress bar
- One line per completed file instead of continuously updating display
- All functionality works identically (dry-run, parallel, confirmation prompts, etc.)

This makes `cpbar` perfect for automation while still providing progress tracking in logs!

### Using Original Commands

If you need to use the standard system commands without the progress bar wrapper (e.g., for scripts or piping), use the `o` suffix:

```bash
cpo file.txt dest/
rmo file.txt
```

## Requirements

- Python 3
- Linux/macOS (Bash or Zsh)

## How it Works

`cpbar` calculates the total size of all source files before starting the operation to provide an accurate progress bar. It handles both file-to-file and directory-to-directory operations, preserving metadata where possible.

### Performance Optimizations

- **Large Buffer**: Uses a 16MB buffer (vs standard 1MB) to reduce system calls and improve throughput
- **Parallel I/O**: When `--parallel` is enabled, divides large files into 32MB blocks and copies them simultaneously using multiple threads
- **Speed Tracking**: Monitors transfer speed in real-time with exponential smoothing for stable readings
- **Smart Mode Selection**: Automatically uses regular copy for files < 64MB even when parallel mode is enabled

In dry-run mode, it scans all files without performing any operations, providing a detailed preview including estimated time based on modern SSD speeds (500 MB/s for copy, 1000 MB/s for delete).

## Project Structure

The project is organized as a modular Python package:

```
cpbar/
├── cpbar.py             # Main entry point
├── install.sh           # Installation script
└── cpbar/               # Python package
    ├── __init__.py      # Package initialization
    ├── __main__.py      # Module entry point
    ├── core.py          # CLI argument parsing
    ├── operations.py    # File copy/remove operations
    ├── ui.py            # Progress bar and UI components
    ├── utils.py         # Utility functions and config
    └── benchmark.py     # Performance benchmarking
```

## Troubleshooting

### Progress bar shows garbled characters

**Cause:** Your terminal doesn't support ANSI escape codes, or you're using an old terminal emulator.

**Solution:**
- Use a modern terminal (iTerm2, Terminal.app, GNOME Terminal, etc.)
- Update your terminal emulator
- The tool automatically detects TTY and falls back to simple output in non-interactive mode

### "Permission denied" errors

**Cause:** Insufficient permissions to read source or write to destination.

**Solution:**
```bash
# Check file permissions
ls -la source_file

# Check destination directory permissions
ls -la /destination/

# Use sudo if necessary (be careful!)
sudo cpbar cp protected_file.txt /system/location/
```

### Parallel mode slower than normal mode

**Cause:** Not all systems benefit from parallel I/O. HDDs and network drives may perform worse.

**Solution:**
```bash
# Run benchmark to find optimal settings for your system
cpbar benchmark

# For HDDs, use normal mode (don't use -P)
cpbar cp large_file.iso /backup/

# Parallel mode is best for: SSD to SSD, NVMe, and files > 1GB
```

### "File already exists" but no overwrite prompt

**Cause:** Might be running in non-interactive mode (pipe, script, cron) where prompts aren't possible.

**Solution:**
- Run the command directly in a terminal for interactive prompts
- Or accept that existing files will be overwritten in batch operations

### Slow performance compared to standard cp

**Cause:** Progress tracking adds minimal overhead, but could be Python startup time for very small files.

**Solution:**
```bash
# For single small files, use original cp
cpo tiny_file.txt dest/

# cpbar shines with large files and directories
cpbar cp -r huge_folder/ /backup/
cpbar cp -P multi_gigabyte_file.iso /backup/  # 2-4x faster than cp!
```

### CI/Tests failing locally

**Cause:** Virtual environment or dependencies issue.

**Solution:**
```bash
# Clean setup
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

### Can't install due to "externally-managed-environment"

**Cause:** Modern Python prevents system-wide pip installs to protect the OS.

**Solution:**
```bash
# Use the install script (recommended)
./install.sh

# Or use a virtual environment
python3 -m venv ~/.cpbar-env
source ~/.cpbar-env/bin/activate
pip install cpbar
```

### Progress bar doesn't show speed/time

**Cause:** Very fast operations (< 100ms) don't have enough data to calculate meaningful speed.

**Solution:** This is normal for small files. Speed tracking works best for operations > 1 second.

### Aliases not working after installation

**Cause:** Shell hasn't reloaded configuration.

**Solution:**
```bash
# Reload shell config
source ~/.bashrc  # or ~/.zshrc

# Or restart your terminal

# Verify aliases
alias | grep cpbar
```

### "Module not found" error when running cpbar

**Cause:** Python can't find the cpbar package.

**Solution:**
```bash
# Check installation
which cpbar
python3 -m cpbar --version

# Reinstall if needed
./install.sh

# Or verify PATH includes ~/.local/bin
echo $PATH | grep .local/bin
```

## Performance Tips

### For Maximum Speed

1. **Use parallel mode for large files (> 1GB):**
   ```bash
   cpbar cp -P huge_database.sql /backup/
   ```

2. **Run benchmark to optimize for your hardware:**
   ```bash
   cpbar benchmark
   # Then use -P for optimal workers
   ```

3. **SSD to SSD transfers benefit most:**
   - HDD to HDD: Stick with normal mode
   - SSD to SSD: Use `-P` or `--parallel=4`
   - NVMe: Can go up to `--parallel=8`

4. **For many small files, normal mode is best:**
   - Parallel overhead > benefit for files < 64MB

## Author

**Carlos Andrade**
- Email: carlos@perezandrade.com
- GitHub: [@cfpandrade](https://github.com/cfpandrade)
- Repository: [github.com/cfpandrade/cpbar](https://github.com/cfpandrade/cpbar)

## License

This project is open source and available under the MIT License.

## Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/cfpandrade/cpbar/issues).


Author: Carlos Andrade <carlos@perezandrade.com>