"""
Tests for remove (rm) operations in cpbar.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import os
import tempfile
import shutil
from pathlib import Path
import pytest

from cpbar.operations import get_all_files


class TestRemoveOperations:
    """Test suite for remove operations."""

    def setup_method(self):
        """Setup test fixtures before each test."""
        self.test_dir = tempfile.mkdtemp()
        self.work_dir = Path(self.test_dir)

    def teardown_method(self):
        """Cleanup after each test."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_files_for_removal_single(self):
        """Test getting a single file for removal."""
        test_file = self.work_dir / "file.txt"
        test_file.write_text("content")

        files = get_all_files([str(test_file)], recursive=False)
        
        assert len(files) == 1
        assert files[0][0] == str(test_file)

    def test_get_files_for_removal_directory_recursive(self):
        """Test getting files from a directory recursively for removal."""
        # Create test structure
        (self.work_dir / "file1.txt").write_text("a")
        (self.work_dir / "file2.txt").write_text("bb")
        subdir = self.work_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("ccc")

        files = get_all_files([str(self.work_dir)], recursive=True)
        
        assert len(files) == 3

    def test_remove_empty_directory_requires_recursive(self):
        """Test that removing a directory without -r flag should fail."""
        import sys
        from io import StringIO
        
        test_dir = self.work_dir / "emptydir"
        test_dir.mkdir()
        
        old_stderr = sys.stderr
        sys.stderr = StringIO()
        
        files = get_all_files([str(test_dir)], recursive=False)
        
        error_output = sys.stderr.getvalue()
        sys.stderr = old_stderr
        
        assert len(files) == 0
        assert "is a directory" in error_output
