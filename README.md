# cpbar (cprm)

**cpbar** (installed as `cprm`) is a lightweight wrapper for `cp` and `rm` commands that adds a unified, beautiful progress bar to your terminal file operations. It is written in Python and designed to be a drop-in replacement for standard file management commands.

## Features

- **Unified Progress Bar**: Tracks total progress across all files and directories.
- **Visual Feedback**: Shows operation type (📋/🗑️), percentage, progress bar, item count, total size, elapsed time, and current filename.
- **Time Tracking**: Real-time elapsed time display during operations.
- **Dry-Run Mode**: Preview what will be copied or deleted with time estimates before executing.
- **Recursive Support**: Fully supports recursive copy (`cp -r`) and remove (`rm -r`).
- **Dry-Run Mode** (`-n` / `--dry-run`):
  - Preview exactly what will happen before executing
  - Shows: file count, total size, estimated time, and first 10 files to be processed
  - Perfect for verifying complex operations before committing
- **Smart Overwrite Handling**:
  - Prompts when destination files exist with options: yes (y), no (n), all (a), quit (q).
  - All prompts appear in the same line for a clean interface.
- **Safety First**:
  - `rm` asks for confirmation by default with a 3-second safety countdown.
  - `rm -f` skips confirmation (like standard `rm`).
- **Drop-in Replacement**: Installs aliases so you can keep using `cp` and `rm` as usual.
- **Original Commands**: Provides `cpo` and `rmo` aliases if you need the original system commands.

## Installation

To install `cpbar`, simply run the installation script:

```bash
./install.sh
```

The script will:
1. Install `cprm` to `~/.local/bin/` (automatically overwrites any existing version).
2. Add `~/.local/bin` to your `PATH` if needed.
3. Configure aliases in your `.zshrc` or `.bashrc`.

After installation, reload your shell configuration:

```bash
source ~/.zshrc  # or source ~/.bashrc
```

To update to a newer version, just run `./install.sh` again.

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

When copying files that already exist at the destination, `cprm` will prompt you for each file:

```
Overwrite '/path/to/file.txt'? [y/n/a/q]:
```

Options:
- **y** (yes) - Overwrite this file
- **n** (no) - Skip this file
- **a** (all) - Overwrite all remaining files without asking
- **q** (quit) - Cancel the entire operation

All prompts appear on the same line for a clean, organized interface.

### Dry-Run Mode

Preview operations before executing them with the `-n` or `--dry-run` flag:

```bash
# See what would be copied without actually copying
cp -n file.txt /destination/
cp -n -r large_folder/ /backup/

# See what would be deleted without actually deleting
rm -n file.txt
rm -n -r temp_files/
```

The dry-run mode shows:
- Number of files that would be affected
- Total size of the operation
- Estimated time to complete
- Preview of files (first 10)

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

`cprm` calculates the total size of all source files before starting the operation to provide an accurate progress bar. It handles both file-to-file and directory-to-directory operations, preserving metadata where possible.

In dry-run mode, it scans all files without performing any operations, providing a detailed preview including estimated time based on typical disk speeds (80 MB/s for copy, 200 MB/s for delete).
