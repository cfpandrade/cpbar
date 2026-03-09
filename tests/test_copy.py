"""
Tests for copy operations in cpbar.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import os
import tempfile
import shutil
from pathlib import Path
import pytest

from cpbar.operations import get_all_files, copy_file_with_progress
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
