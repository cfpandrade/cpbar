"""
Tests for copy operations in cpbar.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import io
import os
import sys
import tempfile
import shutil
from pathlib import Path
import pytest

from cpbar.operations import get_all_files, copy_file_with_progress, copy_file_parallel, do_copy
from cpbar.ui import ProgressBar


class TestCopyOperations:
    """Test suite for copy operations."""

    def setup_method(self):
        """Setup test fixtures before each test."""
        self.test_dir = tempfile.mkdtemp()
        self.src_dir = Path(self.test_dir) / "src"
        self.dst_dir = Path(self.test_dir) / "dst"
        self.src_dir.mkdir()
        self.dst_dir.mkdir()

    def teardown_method(self):
        """Cleanup after each test."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_copy_single_file(self):
        """Test copying a single file."""
        # Create a test file
        test_file = self.src_dir / "test.txt"
        test_content = "Hello, cpbar!"
        test_file.write_text(test_content)

        # Copy it
        dst_file = self.dst_dir / "test.txt"
        progress = ProgressBar(total_items=1, total_bytes=len(test_content), operation="cp")
        
        result = copy_file_with_progress(str(test_file), str(dst_file), progress)
        
        assert result is True
        assert dst_file.exists()
        assert dst_file.read_text() == test_content
        progress.finish()

    def test_copy_empty_file(self):
        """Test copying an empty file."""
        test_file = self.src_dir / "empty.txt"
        test_file.touch()

        dst_file = self.dst_dir / "empty.txt"
        progress = ProgressBar(total_items=1, total_bytes=0, operation="cp")
        
        result = copy_file_with_progress(str(test_file), str(dst_file), progress)
        
        assert result is True
        assert dst_file.exists()
        assert dst_file.stat().st_size == 0
        progress.finish()

    def test_copy_large_file(self):
        """Test copying a larger file (1MB)."""
        test_file = self.src_dir / "large.bin"
        size = 1024 * 1024  # 1MB
        test_file.write_bytes(b'x' * size)

        dst_file = self.dst_dir / "large.bin"
        progress = ProgressBar(total_items=1, total_bytes=size, operation="cp")
        
        result = copy_file_with_progress(str(test_file), str(dst_file), progress)
        
        assert result is True
        assert dst_file.exists()
        assert dst_file.stat().st_size == size
        progress.finish()

    def test_copy_to_directory(self):
        """Test copying a file to a directory (destination is dir)."""
        test_file = self.src_dir / "test.txt"
        test_file.write_text("content")

        progress = ProgressBar(total_items=1, total_bytes=7, operation="cp")
        result = copy_file_with_progress(str(test_file), str(self.dst_dir), progress)
        
        dst_file = self.dst_dir / "test.txt"
        assert result is True
        assert dst_file.exists()
        assert dst_file.read_text() == "content"
        progress.finish()

    def test_copy_preserves_permissions(self):
        """Test that file permissions are preserved."""
        test_file = self.src_dir / "executable.sh"
        test_file.write_text("#!/bin/bash\necho test")
        test_file.chmod(0o755)

        dst_file = self.dst_dir / "executable.sh"
        progress = ProgressBar(total_items=1, total_bytes=test_file.stat().st_size, operation="cp")
        
        copy_file_with_progress(str(test_file), str(dst_file), progress)
        
        # Check permissions are preserved (using stat.S_IMODE to mask out type bits)
        import stat
        src_mode = stat.S_IMODE(test_file.stat().st_mode)
        dst_mode = stat.S_IMODE(dst_file.stat().st_mode)
        assert src_mode == dst_mode
        progress.finish()

    def test_get_all_files_single(self):
        """Test getting files from a single file path."""
        test_file = self.src_dir / "file.txt"
        test_file.write_text("content")

        files = get_all_files([str(test_file)], recursive=False)
        
        assert len(files) == 1
        assert files[0][0] == str(test_file)
        assert files[0][1] == 7  # "content" size

    def test_get_all_files_directory_non_recursive(self):
        """Test getting files from directory without recursion should fail."""
        import sys
        from io import StringIO
        
        # Capture stderr
        old_stderr = sys.stderr
        sys.stderr = StringIO()
        
        files = get_all_files([str(self.src_dir)], recursive=False)
        
        error_output = sys.stderr.getvalue()
        sys.stderr = old_stderr
        
        assert len(files) == 0
        assert "is a directory" in error_output

    def test_get_all_files_directory_recursive(self):
        """Test getting files from directory with recursion."""
        # Create test structure
        (self.src_dir / "file1.txt").write_text("a")
        (self.src_dir / "file2.txt").write_text("bb")
        subdir = self.src_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("ccc")

        files = get_all_files([str(self.src_dir)], recursive=True)
        
        assert len(files) == 3
        # Check total size
        total_size = sum(f[1] for f in files)
        assert total_size == 6  # 1 + 2 + 3

    def test_get_all_files_multiple_paths(self):
        """Test getting files from multiple paths."""
        file1 = self.src_dir / "file1.txt"
        file2 = self.src_dir / "file2.txt"
        file1.write_text("a")
        file2.write_text("bb")

        files = get_all_files([str(file1), str(file2)], recursive=False)
        
        assert len(files) == 2

    def test_get_all_files_nonexistent(self):
        """Test handling of non-existent files."""
        import sys
        from io import StringIO

        old_stderr = sys.stderr
        sys.stderr = StringIO()

        files = get_all_files(["/nonexistent/file.txt"], recursive=False)

        error_output = sys.stderr.getvalue()
        sys.stderr = old_stderr

        assert len(files) == 0
        assert "does not exist" in error_output

    # --- Dry-run tests ---

    def test_copy_dry_run_no_files_created(self):
        """Test that dry-run mode does not create any files."""
        src_file = self.src_dir / "file.txt"
        src_file.write_text("content")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            do_copy([str(src_file)], str(self.dst_dir), recursive=False, dry_run=True)
        finally:
            sys.stdout = old_stdout

        assert not (self.dst_dir / "file.txt").exists()

    def test_copy_dry_run_shows_summary(self):
        """Test that dry-run output includes file count and summary."""
        for i in range(3):
            (self.src_dir / f"file{i}.txt").write_text("x")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            do_copy([str(self.src_dir)], str(self.dst_dir), recursive=True, dry_run=True)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert "Dry-run" in output
        assert "3" in output  # file count

    # --- Overwrite prompt tests ---

    def test_copy_overwrite_yes(self, monkeypatch):
        """Test that overwrite prompt with 'y' overwrites the destination."""
        src_file = self.src_dir / "file.txt"
        src_file.write_text("new content")
        dst_file = self.dst_dir / "file.txt"
        dst_file.write_text("old content")

        monkeypatch.setattr("cpbar.ui.getch", lambda valid_keys: "y")

        progress = ProgressBar(total_items=1, total_bytes=len("new content"), operation="cp")
        result = copy_file_with_progress(str(src_file), str(dst_file), progress)
        progress.finish()

        assert result is True
        assert dst_file.read_text() == "new content"

    def test_copy_overwrite_no(self, monkeypatch):
        """Test that overwrite prompt with 'n' skips the file."""
        src_file = self.src_dir / "file.txt"
        src_file.write_text("new content")
        dst_file = self.dst_dir / "file.txt"
        dst_file.write_text("old content")

        monkeypatch.setattr("cpbar.ui.getch", lambda valid_keys: "n")

        progress = ProgressBar(total_items=1, total_bytes=len("new content"), operation="cp")
        result = copy_file_with_progress(str(src_file), str(dst_file), progress)
        progress.finish()

        assert result is False
        assert dst_file.read_text() == "old content"

    def test_copy_overwrite_all(self, monkeypatch):
        """Test that 'a' sets overwrite_all so subsequent files skip the prompt."""
        getch_call_count = [0]

        def counting_getch(valid_keys):
            getch_call_count[0] += 1
            return "a"

        monkeypatch.setattr("cpbar.ui.getch", counting_getch)

        # Create two matching src/dst files
        for name in ["f1.txt", "f2.txt"]:
            (self.src_dir / name).write_text("new")
            (self.dst_dir / name).write_text("old")

        progress = ProgressBar(total_items=2, total_bytes=6, operation="cp")
        copy_file_with_progress(str(self.src_dir / "f1.txt"), str(self.dst_dir / "f1.txt"), progress)
        copy_file_with_progress(str(self.src_dir / "f2.txt"), str(self.dst_dir / "f2.txt"), progress)
        progress.finish()

        assert getch_call_count[0] == 1, "getch should only be called once when 'a' is chosen"
        assert (self.dst_dir / "f1.txt").read_text() == "new"
        assert (self.dst_dir / "f2.txt").read_text() == "new"

    def test_copy_overwrite_quit(self, monkeypatch):
        """Test that 'q' causes sys.exit."""
        src_file = self.src_dir / "file.txt"
        src_file.write_text("new content")
        dst_file = self.dst_dir / "file.txt"
        dst_file.write_text("old content")

        monkeypatch.setattr("cpbar.ui.getch", lambda valid_keys: "q")

        progress = ProgressBar(total_items=1, total_bytes=len("new content"), operation="cp")
        with pytest.raises(SystemExit):
            copy_file_with_progress(str(src_file), str(dst_file), progress)

    # --- Parallel copy tests ---

    def test_parallel_copy_small_file_falls_back(self):
        """Test that copy_file_parallel falls back to sequential for small files."""
        src_file = self.src_dir / "small.bin"
        size = 1024  # 1KB — well below block_size * 2 threshold
        src_file.write_bytes(b'z' * size)
        dst_file = self.dst_dir / "small.bin"

        progress = ProgressBar(total_items=1, total_bytes=size, operation="cp")
        # block_size=2048: file_size (1024) < block_size * 2 (4096) → sequential fallback
        result = copy_file_parallel(str(src_file), str(dst_file), progress, num_workers=2, block_size=2048)
        progress.finish()

        assert result is True
        assert dst_file.read_bytes() == b'z' * size

    def test_parallel_copy_produces_identical_content(self):
        """Test that parallel copy produces byte-identical output."""
        src_file = self.src_dir / "data.bin"
        content = bytes(range(256)) * 16  # 4KB with varied pattern
        src_file.write_bytes(content)
        dst_file = self.dst_dir / "data.bin"

        progress = ProgressBar(total_items=1, total_bytes=len(content), operation="cp")
        # block_size=1024: 4KB file → 4 blocks → actual parallel path
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            result = copy_file_parallel(str(src_file), str(dst_file), progress, num_workers=2, block_size=1024)
        finally:
            sys.stdout = old_stdout
        progress.finish()

        assert result is True
        assert dst_file.read_bytes() == content

    def test_do_copy_parallel_flag(self, monkeypatch):
        """Test do_copy with parallel flag copies files correctly."""
        src_file = self.src_dir / "file.bin"
        content = b'p' * 2048
        src_file.write_bytes(content)

        # Lower threshold so small file triggers parallel path
        monkeypatch.setattr("cpbar.operations.PARALLEL_THRESHOLD", 0)

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            do_copy([str(src_file)], str(self.dst_dir), recursive=False, parallel=2)
        finally:
            sys.stdout = old_stdout

        assert (self.dst_dir / "file.bin").read_bytes() == content

    # --- Symlink tests ---

    def test_copy_symlink_dereferenced_by_default(self):
        """Test that copying a symlink copies the target's content (default behavior)."""
        target = self.src_dir / "target.txt"
        target.write_text("target content")
        link = self.src_dir / "link.txt"
        link.symlink_to(target)

        dst_file = self.dst_dir / "link.txt"
        progress = ProgressBar(total_items=1, total_bytes=target.stat().st_size, operation="cp")
        result = copy_file_with_progress(str(link), str(dst_file), progress)
        progress.finish()

        assert result is True
        assert dst_file.exists()
        assert not dst_file.is_symlink(), "Default should dereference: dst must be a regular file"
        assert dst_file.read_text() == "target content"

    def test_copy_symlink_preserved_with_flag(self):
        """Test that --preserve-symlinks copies symlinks as symlinks."""
        target = self.src_dir / "target.txt"
        target.write_text("target content")
        link = self.src_dir / "link.txt"
        link.symlink_to(target)

        dst_file = self.dst_dir / "link.txt"
        progress = ProgressBar(total_items=1, total_bytes=0, operation="cp")
        result = copy_file_with_progress(str(link), str(dst_file), progress, preserve_symlinks=True)
        progress.finish()

        assert result is True
        assert dst_file.is_symlink(), "With --preserve-symlinks, dst must be a symlink"
        assert os.readlink(str(dst_file)) == os.readlink(str(link))

    def test_do_copy_preserve_symlinks(self):
        """Test do_copy with --preserve-symlinks flag."""
        target = self.src_dir / "target.txt"
        target.write_text("data")
        link = self.src_dir / "link.txt"
        link.symlink_to(target)

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            do_copy([str(link)], str(self.dst_dir), recursive=False, preserve_symlinks=True)
        finally:
            sys.stdout = old_stdout

        dst_link = self.dst_dir / "link.txt"
        assert dst_link.is_symlink()

    # --- cp -r destination semantics ---

    def test_copy_dir_to_new_path_creates_copy(self):
        """Test that cp -r src new copies the contents into 'new', like cp does."""
        (self.src_dir / "sub").mkdir()
        (self.src_dir / "sub" / "file.txt").write_text("content")
        new = Path(self.test_dir) / "new"

        self._run_quiet(do_copy, [str(self.src_dir)], str(new), recursive=True)

        assert (new / "sub" / "file.txt").read_text() == "content"
        assert not (new / "src").exists()

    def test_copy_dir_into_existing_dir(self):
        """Test that cp -r src existing/ copies into existing/src."""
        (self.src_dir / "file.txt").write_text("content")

        self._run_quiet(do_copy, [str(self.src_dir)], str(self.dst_dir), recursive=True)

        assert (self.dst_dir / "src" / "file.txt").read_text() == "content"

    def test_copy_dir_keeps_empty_directories(self):
        """Test that empty subdirectories are copied too."""
        (self.src_dir / "empty").mkdir()

        self._run_quiet(do_copy, [str(self.src_dir)], str(self.dst_dir), recursive=True)

        assert (self.dst_dir / "src" / "empty").is_dir()

    def _run_quiet(self, func, *args, **kwargs):
        """Run func suppressing stdout (progress bar output)."""
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            return func(*args, **kwargs)
        finally:
            sys.stdout = old_stdout
