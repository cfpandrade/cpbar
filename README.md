# cpbar (cprm)

**cpbar** (installed as `cprm`) is a lightweight wrapper for `cp` and `rm` commands that adds a unified, beautiful progress bar to your terminal file operations. It is written in Python and designed to be a drop-in replacement for standard file management commands.

## Features

- **Unified Progress Bar**: Tracks total progress across all files and directories.
- **Visual Feedback**: Shows operation type (📋/🗑️), percentage, progress bar, item count, total size, and current filename.
- **Recursive Support**: Fully supports recursive copy (`cp -r`) and remove (`rm -r`).
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
1. Install `cprm` to `~/.local/bin/`.
2. Add `~/.local/bin` to your `PATH` if needed.
3. Configure aliases in your `.zshrc` or `.bashrc`.

After installation, reload your shell configuration:

```bash
source ~/.zshrc  # or source ~/.bashrc
```

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
```

### Removing Files

```bash
# Remove a file (asks for confirmation)
rm old_file.txt

# Remove a directory recursively
rm -r old_folder/

# Force remove (no confirmation)
rm -rf temp_folder/
```

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
